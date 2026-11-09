---
title: "Orchestrated Sagas & Extraction 5: Shipping (FastAPI Saga Coordinator)"
order: 24
part: "Coordinating Across Services"
description: "Shipping becomes a bounded, orchestrated saga: one FastAPI coordinator sequences dispatch and owns the compensation decision, the cross-context undo is delegated to the order context that owns the data, and a refund hop closes the stranded-payment gap."
duration: 40 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain how shipping's extraction removes dispatch from any checkout or payment `transaction.atomic()` block.
- Contrast orchestration, a DB-backed `app/orchestrator.py` that sequences steps and owns compensation, with choreography, and say why the `STEPS` table is the whole saga's shape.
- Apply the four disciplines a DB-backed orchestrator needs: a row lock per step (`FOR UPDATE`), an idempotent status guard, one transaction per step, and reassigning a JSONB `context` column so SQLAlchemy sees the update.
- Explain why cross-context compensation is delegated: shipping emits `shipment.failed`, and `order_saga_listener`, which owns the reserved-line snapshot, issues the gRPC `Release`.
- Trace the order states `AWAITING_SHIPMENT` and `SHIPPING_FAILED` and how `SHIPPING_MODE` makes a hidden window observable without changing the `202` contract.
- Explain how persisting `status`, `step_index` and `context` as a row makes a mid-saga crash resumable.
- Explain how `shipment.failed` lets payment-service's refund hop close the stranded-payment gap.

## Why this matters

The choreographed payment saga has no coordinator: each service reacts to events it subscribes to and the sequence emerges. Shipping takes the opposite shape. `examples/06-shipping-service` reacts to the `payment.captured` event payment-service already produces, then runs a four-step **orchestrated saga**, `enrich`, `dispatch`, `book_carrier`, `emit`, with one coordinator that decides what happens after every step, including whether to undo what already happened. It also closes a gap the payment saga left open: a payment captured and then stranded by a shipping failure.

The code is in `examples/06-shipping-service/`. Its run script builds the `shipping` schema, starts the consumer and outbox relay and runs the saga end to end; `README.md` and `AGENTS.md` cover commands and layout. `MIGRATION.md`, `EVENTS.md` and `CUTOVER.md` in that directory are the measured record cited below.

## Pattern: Saga, orchestrated

In choreography the shape of the saga exists nowhere as one artifact; you rebuild it by reading three services and noticing shared topics. In orchestration it is one list:

```python
# app/orchestrator.py -- the forward steps, each naming its one inverse
STEPS: list[dict[str, str | None]] = [
    {"name": "enrich", "compensate": None},
    {"name": "dispatch", "compensate": "cancel_shipment"},
    {"name": "book_carrier", "compensate": None},
    {"name": "emit", "compensate": None},
]
```

`STEPS` is the saga. `advance()` drives it one step at a time and inspects each result to decide what comes next:

```python
# app/orchestrator.py -- advance(), the coordinator's top-level loop
async def advance(session_factory, settings, saga_id):
    status = await _advance_one_step(session_factory, settings, saga_id)
    if status == SAGA_RUNNING:
        await advance(session_factory, settings, saga_id)
    elif status == SAGA_COMPENSATING:
        await compensate(session_factory, settings, saga_id)
```

No step calls another step and none decides whether to compensate. `enrich` does not know `dispatch` exists, and `dispatch` does not know whether it will be undone. The sequence and the decision to abort live in one place.

{% include excalidraw.html file="choreography-vs-orchestration-contrast" alt="The choreographed payment saga and the orchestrated shipping saga side by side, the left panel has no box that knows the whole sequence, the right panel has exactly one" caption="Figure 24.1: Choreography has no coordinator and orchestration has exactly one" %}

| | Choreography | Orchestration |
|---|---|---|
| Shape of the saga | Reconstructed from several services | One file, auditable |
| Failure domain | No single box can crash the saga | The coordinator is a dependency every step runs through |
| Fits when | Each side already knows its reaction (payment) | The sequence is worth making explicit and has a real undo path (shipping) |

## A DB-backed orchestrator on SQLAlchemy

`app/orchestrator.py` is adapted from the Python orchestrator in `cloud-native-design-patterns` (`17-sagas`) and its saga design doc, re-homed onto async SQLAlchemy. The original drives raw `asyncpg` with hand-encoded JSON text columns and a manual `FOR UPDATE` query string; this service has ORM models and `select(Saga).with_for_update()`. The engine's shape, one step per transaction, a persisted `step_index` and reverse-order compensation over only the steps that ran, is the same. Only the row-locking syntax and ORM wiring are stack-specific.

Every call to `_advance_one_step` executes exactly one step in its own transaction:

```python
# app/orchestrator.py -- _advance_one_step, one step per transaction
async with session_factory() as session, session.begin():
    saga = await repository.get_saga_for_update(session, saga_id)
    if saga is None:
        return None
    if saga.status != SAGA_RUNNING:
        return saga.status          # idempotent guard: already resolved
    step = STEPS[saga.step_index]
    func = _STEP_FUNCS[step["name"]]
    result = await func(session, settings=settings, order_id=saga.order_id,
                         context=saga.context)
    saga.context = {**saga.context, step["name"]: result}
    saga.step_index += 1
    await repository.add_saga_log(session, saga_id=saga.id, step=step["name"],
                                   status="EXECUTED", detail=result, now=now)
    if saga.step_index >= len(STEPS):
        saga.status = SAGA_COMPLETED
    return saga.status
```

Four decisions in that function each answer a question you will hit building your own:

- **Why `SELECT ... FOR UPDATE`?** A saga row can be driven by more than one caller, for example a redelivered `payment.captured` racing the startup crash-resume scan. Without the lock, two callers could both read `step_index=1`, both run step 2 and both append a log row. With it, the second caller reads the advanced state and continues from there.
- **Why check `saga.status != SAGA_RUNNING` first?** This idempotent-advance guard makes `advance()` safe to call repeatedly, which happens because `payment.captured` is delivered at least once. A saga already `COMPLETED`, `COMPENSATED` or flipped to `COMPENSATING` is a no-op, not an error. Without it, a redelivered trigger would re-execute a step, corrupting `context` or double-persisting a shipment.
- **Why reassign `saga.context`?** SQLAlchemy does not notice an in-place `dict.update()` on a mutable JSON value; it flushes a column only when the object's identity changes. `saga.context = {**saga.context, step_name: result}` creates a new dict. It also threads output between steps: `dispatch` writes `shipment_id` and `address` to `context["dispatch"]`, and `book_carrier` reads them two steps later without another round trip.
- **Why does `advance()` recurse instead of looping?** Each call opens a new transaction. Looping in one transaction would roll back steps one and two when step three fails, the all-or-nothing atomicity the saga exists to avoid. One transaction per step leaves a crash between any two steps in a well-defined, committed state.

{% include excalidraw.html file="orchestrated-shipping-saga-sequence" alt="The four-step orchestrated saga top to bottom, with one coordinator sequencing enrich, dispatch, book_carrier, and emit, and the reverse-order compensation path on a book_carrier failure" caption="Figure 24.2: The orchestrated saga, with one coordinator, four steps and one compensation decision" %}

## Crash-resume

A coordinator that tracks progress in memory has no resume path: a pod restart between `dispatch` and `book_carrier` loses the saga, and nothing on restart knows a shipment was in flight. This service persists `status`, `step_index` and `context` as a row in `shipping.sagas`, and `resume_running_sagas()` uses it:

```python
# app/orchestrator.py -- resume_running_sagas(), the startup crash-resume scan
async def resume_running_sagas(session_factory, settings) -> int:
    async with session_factory() as session:
        resumable = await repository.list_resumable_saga_ids(session)
    for saga_id, status in resumable:
        if status == SAGA_RUNNING:
            await advance(session_factory, settings, saga_id)
        else:
            await compensate(session_factory, settings, saga_id)
    return len(resumable)
```

`app/main.py`'s lifespan calls this before the service reports ready. It finds every saga still `RUNNING` or `COMPENSATING` from whatever process last touched it, whether a crash, a redeploy or `kill -9`. Resuming is not a special path. Because `advance()` and `compensate()` are idempotent and the row is locked per step, it is the same `advance()` call a fresh trigger makes, aimed at a saga that already has a `step_index` and `context`.

{% include excalidraw.html file="saga-state-machine-crash-resume" alt="The saga's status state machine, the saga_log row each step appends, and the crash-resume path that is this service's durability upgrade over an in-memory saga coordinator" caption="Figure 24.3: Resumable by construction, since the row remembers what the process forgot" %}

The live cutover reproduced the failure against a running container. A `RUNNING` saga row was inserted into the container's Postgres with `step_index=1`, simulating a death right after `enrich` committed, and the container was `docker restart`ed. The startup log showed `resuming saga <id> (status=RUNNING)` followed by `dispatch` and `emit`. No new `GET /api/orders/{id}` request was logged for that order, so `enrich` did not re-run, and `/health` reported `resumedSagaCount: 1`.

## Enrich: reading across the seam

The first step cannot answer from its own data where an order ships. `payment.captured` correctly carries no address, and the event contract should not grow a field one consumer needs. `enrich` reads across the boundary:

```python
# app/steps.py -- enrich, saga step 1
async def enrich(session, *, settings, order_id, context):
    address = await enrich_client.fetch_shipping_address(
        base_url=settings.monolith_base_url, order_id=order_id,
        timeout_s=settings.enrich_timeout_s,
    )
    return {"address": address}
```

`enrich_client.fetch_shipping_address` calls `GET {MONOLITH_BASE_URL}/api/orders/{orderId}` and reads `shippingAddress`, an additive field on the monolith's `OrderSerializer` added so the saga can enrich itself without touching the monolith's database. That is the anti-corruption layer: a contract, not a shared table. shipping-service never imports a monolith model or opens a connection to its schema, and knows only the shape of one HTTP response. If addresses later move to their own service, this one `GET` is all that changes. A `tenacity` retry with a timeout wraps the call, the one resilience mechanism added for the failure-modes work.

`enrich` has no compensation in `STEPS`, and that is structural: it persists nothing. If it fails (monolith unreachable, retries exhausted, response missing `shippingAddress`), the exception goes to the orchestrator like any step failure and routes the saga to `COMPENSATING`, but `dispatch` has not run, so `compensate()` finds no `Shipment` to undo.

## The SHIP-FAIL compensation

`book_carrier`, step 3, hosts the deterministic failure injection, lifted from the monolith's `SHIP_FAIL_SENTINEL` rule in `shipping.services.dispatch`, now moot there once `SHIPPING_MODE=orchestrated` routes shipping through the saga:

```python
# app/steps.py -- book_carrier, saga step 3
async def book_carrier(session, *, settings, order_id, context):
    address = context["dispatch"]["address"]
    if SHIP_FAIL_SENTINEL in address.upper():
        raise BookCarrierFailed(f"carrier booking failed for order {order_id}: ...")
    return {"booked": True}
```

The ordering matters. `book_carrier` runs after `dispatch` has committed a `Shipment` row as `DISPATCHED` in its own closed transaction, so when it fails there is always a durable row to act on. Checking the carrier before persisting anything would need no compensation and teach the wrong lesson: most real saga failures happen after an earlier step has left a durable mark.

`compensate()` is the coordinator's second job:

```python
# app/orchestrator.py -- compensate(), reverse-order over only-completed steps
completed_steps = STEPS[: saga.step_index]
for step in reversed(completed_steps):
    compensation_name = step["compensate"]
    if compensation_name is None:
        continue
    func = _COMPENSATION_FUNCS[compensation_name]
    result = await func(session, settings=settings, order_id=saga.order_id,
                         context=saga.context)
    await repository.add_saga_log(session, saga_id=saga.id, step=compensation_name,
                                   status="COMPENSATED", detail=result, now=now)
await _emit_shipment_failed(session, saga_id=saga.id, order_id=saga.order_id,
                             context=saga.context, now=now)
saga.status = SAGA_COMPENSATED
```

`STEPS[: saga.step_index]`, only the steps that completed, reversed, is the whole algorithm. Here that is exactly one undo, `cancel_shipment`, since `enrich` and `book_carrier` have nothing to reverse. It flips the `Shipment` to `CANCELLED` rather than deleting it, so an auditable record of the aborted attempt survives. The terminal `shipment.failed` outbox write and the flip to `COMPENSATED` share one transaction, as `emit` and `COMPLETED` do on the happy path, so a saga is never marked done in either direction without a queued outcome event.

## AWAITING_SHIPMENT and two cutover dimensions

The monolith sees the saga only as two outcome events on topics it can subscribe to. Its side of the cutover adds a third settings axis beside `INVENTORY_MODE` and `PAYMENT_MODE`: `settings.SHIPPING_MODE`, read only inside `handle_payment_captured`.

```python
# examples/00-monolith/order/services.py -- handle_payment_captured, the orchestrated branch
if settings.SHIPPING_MODE == "orchestrated":
    order.await_shipment()
    order.save(update_fields=["status"])
    return order
```

With `SHIPPING_MODE=orchestrated` the monolith neither dispatches nor confirms. It moves the order to `AWAITING_SHIPMENT` and returns. `order_saga_listener` now consumes four topics and resolves the hand-off:

```python
# order/management/commands/order_saga_listener.py -- four topics, one consumer group
consumer = AIOKafkaConsumer(
    captured_topic, declined_topic, dispatched_topic, failed_topic,
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    group_id=group_id, auto_offset_reset="earliest", enable_auto_commit=True,
)
```

`handle_shipment_dispatched` moves `AWAITING_SHIPMENT` to `CONFIRMED`. `handle_shipment_failed` moves it to `SHIPPING_FAILED` through the same compensating `Release` by stable key used for a payment decline. Both are guarded by `_is_awaiting_shipment`, the same shape as `_is_pending`, so redelivery can never double-confirm or double-release.

{% include excalidraw.html file="order-lifecycle-awaiting-shipment-refund" alt="The full order lifecycle once SHIPPING_MODE=orchestrated: PENDING to AWAITING_SHIPMENT to CONFIRMED or SHIPPING_FAILED, plus the refund hop that closes the stranded-payment gap" caption="Figure 24.4: AWAITING_SHIPMENT is a real intermediate status, not an implementation detail" %}

Two independent cutover dimensions are in play:

| Dimension | Control | Effect | Reverse |
|---|---|---|---|
| Read surface | `STRANGLER_SHIPPING_ENABLED` on the strangler proxy | Routes `GET /api/shipments*` to this service instead of the Django view | Instant |
| Dispatch ownership | `SHIPPING_MODE` on the monolith | Decides who dispatches shipping at all | Restart the monolith with `inprocess`; no data migration |

`SHIPPING_MODE` is orthogonal to `PAYMENT_MODE`: both values react to the same `payment.captured` event whether payment was charged synchronously or choreographed.

## Pattern: Compensating transaction, the refund hop

The monolith releases inventory when shipping fails but never refunded the customer, because payment-service had no refund mechanism. With an orchestrator, shipping's failure is a **named event on a topic** (`shipment.failed`) rather than an exception inside the monolith's call stack, so payment-service can subscribe to it.

```python
# examples/05-payment-service/app/service.py -- process_shipment_failed
payment = await repository.transition_payment_status_with_outbox_event(
    session, order_id=event.order_id,
    expected_status=STATUS_CAPTURED, new_status=STATUS_REFUNDED,
    created_at=now, event_type=PAYMENT_REFUNDED_EVENT_TYPE,
    build_payload=lambda p: _build_refund_event_payload(p, occurred_at=now),
)
if payment is None:
    return  # already REFUNDED, DECLINED, or never existed -- safe no-op
```

`ShipmentFailedConsumer` subscribes to `shipment.failed`, the same event `order_saga_listener` uses to resolve `AWAITING_SHIPMENT` to `SHIPPING_FAILED`. `process_shipment_failed` refunds a `CAPTURED` payment through a conditional status transition, not a blind write: `transition_payment_status_with_outbox_event` only moves `CAPTURED` to `REFUNDED`. A payment already `REFUNDED`, one that was `DECLINED` and never captured, and an order with no payment all fall through as no-ops, with no second `payment.refunded` event and no money moved twice.

The live cutover proved the chain end to end. A `SHIP-FAIL` checkout resolved to `SHIPPING_FAILED` with the captured payment reaching `REFUNDED`, recorded in `tooling/newman/GOLDEN-BASELINE.md` against the fully orchestrated topology. A redelivered `shipment.failed` against an already `REFUNDED` payment was a no-op. `CUTOVER.md` now records the gap as closed, with that proof.

> **ADLC in Action.** The refund hop was an acceptance criterion set before `ShipmentFailedConsumer` was written, because an orchestrated saga gives shipping's failure a durable, subscribable event. The plan also rejected refunding synchronously inside the monolith's `handle_shipment_failed`: that would make the monolith know payment-service's internal status model and reintroduce the coupling the extraction removes. payment-service owns its refund decision off a wire event it has every right to see.

> **Decision**
>
> Orchestrate when the sequence is worth declaring in one place and has a real undo path. Persist saga state as a row, lock it per step, guard on status, commit one step per transaction, and publish failure as an event so the context that owns the data does its own compensation.

> **🤖 Explore with your agent**
>
> "In `examples/06-shipping-service/app/orchestrator.py`, add a fifth step `notify_customer` to `STEPS` with no compensation, wire a stub function into `_STEP_FUNCS`, and show that `compensate()` still reverses only `dispatch` when `book_carrier` fails on a `SHIP-FAIL` address."
>
> Check: run the service's tests, then `demos/demo-shipping-cutover.sh`; the `SHIP-FAIL` order ends `SHIPPING_FAILED` and the payment ends `REFUNDED`.

## Build, run, observe

Run `demos/demo-shipping-cutover.sh`. It brings up Postgres, Kafka, inventory, payment and shipping services, the monolith with `SHIPPING_MODE=orchestrated` and `PAYMENT_MODE=choreographed`, and the strangler proxy with the inventory, payment and shipping flags on, runs the Newman suite through the proxy and tears everything down. The crash-resume and stuck-`AWAITING_SHIPMENT` negative proofs need manual process kills and are not part of the scripted pass.

- Check out with a `SHIP-FAIL` address: the order ends `SHIPPING_FAILED`, stock is released and the payment ends `REFUNDED`.
- Insert a `RUNNING` row into `shipping.sagas` with `step_index=1` and restart the container: the log shows `resuming saga`, `enrich` does not re-run and `/health` reports `resumedSagaCount: 1`.
- Redeliver `shipment.failed` for a `REFUNDED` payment: no second `payment.refunded` event.
- Set `SHIPPING_MODE=inprocess` and restart the monolith: dispatch returns to the monolith with no data migration.
