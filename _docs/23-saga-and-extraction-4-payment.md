---
title: "Distributed Transactions, the Saga & Extraction 4: Payment (choreographed)"
order: 23
part: "Coordinating Across Services"
description: "Checkout's synchronous 201 or 402 becomes an asynchronous 202 with a PENDING order, a choreographed saga captures payment and confirms or compensates, and the equivalence suite learns to verify an outcome it cannot observe on the same request."
duration: 45 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why `_place_order_choreographed` never calls payment-service, so no `except` block is left to compensate from.
- Distinguish choreography from orchestration as saga control styles, and say why payment is choreographed.
- Explain why checkout changes from `201 Created` with a terminal status to `202 Accepted` with a pollable resource.
- Trace the two-outbox topology (`order.placed` to `payment.captured` or `payment.declined`) and identify `order_saga_listener` as the monolith's first saga consumer.
- Explain how compensation moves from an inline `except` to `handle_payment_declined`.
- Apply two-layer idempotency, a status-transition guard plus a database `ON CONFLICT DO NOTHING` ledger, so a compensating release fires at most once per order.
- Use a negative check, killing payment-service, to show a bounded-wait assertion tests the real pipeline.

## Why this matters

Once payment moves to a service that reacts to an event instead of answering a call, checkout's single transaction can no longer span the business operation, and isolation is the guarantee that does not survive. What replaces it is a **choreographed saga**, the fourth extraction and the first where no single request resolves an order. `examples/05-payment-service` reacts to `order.placed`. The monolith's `order_saga_listener` reacts to what payment-service publishes back. `POST /api/orders` answers `202 Accepted` rather than a terminal `201`, because the accurate answer to "did this order succeed" is "not yet."

The code is in `examples/05-payment-service/` (the FastAPI participant) and `examples/00-monolith/order/` (the choreographed checkout path and its listener). `CUTOVER.md` in the service directory and the cutover section of `tooling/newman/GOLDEN-BASELINE.md` record the measured numbers below.

## Dispatch: PAYMENT_MODE

`settings.PAYMENT_MODE` is the dispatch point:

```python
# order/services.py -- place_order, the three-way dispatch
def place_order(customer_id, items, payment_method, shipping_address):
    customer = _get_customer(customer_id)
    if settings.PAYMENT_MODE == "choreographed":
        return _place_order_choreographed(customer, items, payment_method, shipping_address)
    if settings.INVENTORY_MODE == "grpc":
        return _place_order_remote(customer, items, payment_method, shipping_address)
    return _place_order_local(customer, items, payment_method, shipping_address)
```

`PAYMENT_MODE` is orthogonal to `INVENTORY_MODE`. Both payment modes reserve inventory through the same `_reserve_lines_remote` and `_release_reserved` helpers, so flipping payment never changes how stock is reserved, only what happens to the rest of checkout once the reservation succeeds.

## Pattern: Saga, choreographed

In an **orchestrated** saga a central coordinator calls each participant and decides the next step. In a **choreographed** saga there is no coordinator: each participant reacts to events it subscribes to, and the sequence emerges from those reactions. The absence is structural here. payment-service has no knowledge that `order_saga_listener` exists, and the listener never calls payment-service; it only subscribes to topics payment-service publishes. Either side can be redeployed or replaced without the other changing a line, because the only contract is the shape of two Kafka topics.

Choreography fits payment because nothing about capturing a payment needs a coordinator: the monolith already knows what to do with a captured payment (confirm and ship) or a declined one (release and decline). Orchestration is not inferior; shipping uses it, for a sequence that is itself worth making explicit.

## The checkout contract: 202, not 201 with PENDING

The decision lives in `order/views.py`:

```python
# order/views.py -- OrderListCreateView.post
response_status = (
    status.HTTP_202_ACCEPTED
    if order.status == Order.Status.PENDING
    else status.HTTP_201_CREATED
)
return Response(body, status=response_status, headers={"Location": f"/api/orders/{order.id}"})
```

The status code derives from the order's persisted status, not from a parallel `PAYMENT_MODE` branch that could drift from what the order is. Returning `201 Created` for a `PENDING` order would be cheaper and dishonest: `201` says the resource exists in its final form, and a `PENDING` order does not. `202 Accepted` means accepted for processing, not yet complete.

{% include excalidraw.html file="checkout-sync-to-async-contract" alt="Before/after panels: PAYMENT_MODE=synchronous's one round trip ending in a terminal 201/402/422/409, versus choreographed's same round trip ending in a 202 PENDING promise the caller must poll to resolve" caption="Figure 23.1: The contract change. 202 is a promise, not a faster 201" %}

This is the first deliberate change to a previously stable wire contract. Every earlier extraction added a field, a header or an endpoint and never changed what an existing response code meant, so it needed an explicit decision at the planning gate.

## The event topology: two outboxes, no coordinator

{% include excalidraw.html file="choreographed-payment-saga-sequence" alt="The full choreographed saga top to bottom, branching into its three terminal outcomes, every arrow is an event one side reacted to, no orchestrator box anywhere" caption="Figure 23.2: The choreographed saga, where every arrow is a reaction and none is a call" %}

One checkout takes this path:

1. `_place_order_choreographed` persists the `PENDING` order and its `order.placed` outbox row in one local transaction and returns `202`. The row carries an optional, additive `paymentMethod` field that consumers ignoring unknown fields are unaffected by.
2. The monolith's `outbox_relay` publishes the row to Kafka.
3. payment-service's `OrderPlacedConsumer` calls `process_order_placed`, which charges deterministically (`DECLINE_SENTINEL = "DECLINE"`, lifted from the monolith's original rule) and writes a `Payment` row plus its own outbox event atomically in the `payment` schema.
4. payment-service's `OutboxRelay` publishes `payment.captured` or `payment.declined`.
5. `order_saga_listener`, a Django management command shaped like `outbox_relay` and `order_placed_consumer` but subscribed to two topics on one consumer group, calls `handle_payment_captured` or `handle_payment_declined`.

No participant knows the chain beyond the topic it touches. The two halves of the monolith communicate only through Kafka and payment-service's decision, with no shared in-process state, which is what makes this a saga and not an indirect function call.

## The saga listener

The reaction logic lives in `order.services.handle_payment_captured` and `handle_payment_declined`, where it can be unit tested by calling a function with a dict. The command is only the aiokafka wiring:

```python
# order/management/commands/order_saga_listener.py
consumer = AIOKafkaConsumer(
    captured_topic, declined_topic,
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    group_id=group_id,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
)
...
batches = await consumer.getmany(timeout_ms=1000)
for topic_partition, records in batches.items():
    for record in records:
        event = json.loads(record.value.decode("utf-8"))
        if topic_partition.topic == captured_topic:
            order = await _handle_payment_captured_async(event)
        else:
            order = await _handle_payment_declined_async(event)
```

One `AIOKafkaConsumer` accepts a list of topics, so a single consumer group reacts to both outcomes. `getmany(timeout_ms=1000)` replaces `async for record in consumer` so the `stop_event` is checked every second on an idle topic and `SIGINT` or `SIGTERM` can end the loop. `enable_auto_commit=True` is safe because a crash after processing redelivers the message and the handlers are idempotent.

## Compensation without a catch block

`_place_order_remote` compensates with `try`/`except` in one call stack, a few milliseconds after the reservation. Here the decision to compensate arrives on a different stack, in a different process, seconds later.

```python
# order/services.py -- handle_payment_declined
def handle_payment_declined(event: dict) -> Order | None:
    order = _get_order_for_saga_event(event, event_type="payment.declined")
    if order is None or not _is_pending(order, event_type="payment.declined"):
        return order

    _release_order_lines(order)
    order.decline_payment()
    order.save(update_fields=["status"])
    return order
```

`_release_order_lines` recovers what to release from the persisted `OrderItem` snapshot rows (`sku`, `quantity`), because no in-memory `reserved` list survives to this stack. The shipping-failure branch of `handle_payment_captured` compensates the same way, triggered by a different event:

```python
# order/services.py -- handle_payment_captured, the shipping-fail branch
try:
    shipping_services.dispatch(order, order.shipping_address)
except ShippingFailed:
    _release_order_lines(order)
    order.ship_fail()
    order.save(update_fields=["status"])
    return order

order.confirm()
order.save(update_fields=["status"])
return order
```

Shipping dispatch moved into the `payment.captured` reaction, so shipping now happens after payment captures. A shipping failure releases inventory but leaves the captured payment unrefunded, a documented gap that an orchestrated saga closes.

## Idempotency: at-least-once delivery, exactly-once effect

Two layers are needed, because a client-side check cannot see a crash window on the server it calls.

**Layer 1, the status-transition guard**, on the listener side:

```python
# order/services.py -- _is_pending
def _is_pending(order: Order, event_type: str) -> bool:
    if order.status != Order.Status.PENDING:
        logger.info("%s redelivered for order_id=%s status=%s -- no-op (status guard)",
                    event_type, order.id, order.status)
        return False
    return True
```

An order that already left `PENDING`, through an earlier delivery of this event or of the other outcome, makes every later call a no-op before it reaches `_release_order_lines` or a second `confirm()`. This handles the common case: Kafka redelivering after a rebalance.

**Layer 2, the `idempotency_key` ledger**, on inventory-service's side. The caller derives a stable key once and sends it on every retry of the same logical release:

```python
# order/services.py -- _release_order_lines
for item in order.items.all():
    idempotency_key = f"{order.id}:{item.sku}:release"
    client.release(item.sku, item.quantity, idempotency_key=idempotency_key)
```

```python
# examples/04-inventory-service/app/repository.py -- release
stmt = pg_insert(Compensation).values(idempotency_key=idempotency_key, ...)
stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
result = await session.execute(stmt.returning(Compensation.id))
if result.first() is not None:
    await session.execute(
        update(InventoryItem).where(InventoryItem.sku == sku)
        .values(quantity_on_hand=InventoryItem.quantity_on_hand + qty)
    )
await session.commit()
```

This is one `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id`, not a `SELECT` followed by a conditional `INSERT`. Postgres's unique index serializes concurrent inserts on one key, so of two racing identical calls exactly one gets a row back and proceeds to the `UPDATE`. Both statements commit in one transaction, so a crash between ledger insert and stock update cannot leave one without the other.

Layer 1's blind spot is the crash window. The gRPC `Release` succeeds and increments stock, then the listener crashes before committing the order's new status. Kafka redelivers `payment.declined`, the order is still `PENDING`, and the guard lets a second `Release` through. The ledger stops it, because it checks the RPC's own key, not the caller's belief about what it already did.

{% include excalidraw.html file="idempotent-compensation-two-layers" alt="A compensating Release survives redelivery at both the Kafka-event layer (the saga's status-transition guard) and the RPC layer (inventory-service's compensations ledger, INSERT ... ON CONFLICT DO NOTHING)" caption="Figure 23.3: Idempotent compensation at the event layer and at the RPC layer, independently" %}

The cutover lane in `tooling/newman/GOLDEN-BASELINE.md` exercised both layers against the same resolved order:

- Re-publishing the `payment.declined` event by hand made `order_saga_listener.log` record `payment.declined redelivered for order_id=12 status=PAYMENT_DECLINED -- no-op (status guard)`, and stock held at 94.
- Calling `Release` directly over gRPC twice with the key the listener derives (`"12:SKU-WIDGET-001:release"`) answered `reservation_ok=true` both times, because a duplicate is not an error, and `on_hand_qty` stayed at 94.

## Verifying a contract you cannot observe synchronously

Every earlier cutover could be verified by the same Newman collection because checkout kept a terminal synchronous contract. This one does not, and a suite that can pass vacuously tests nothing.

Every checkout `POST` now accepts `201`, `402` or `202`, since both modes are legitimate. The assertion that proves something is a **bounded-wait poll** of `GET /api/orders/{id}`, using the same `setNextRequest` retry idiom the notification folder uses for its Kafka-backed eventual consistency, with a strict terminal-status check:

```
1c. Bounded-wait poll: order reaches terminal status -> strictly CONFIRMED
    (20 x 750ms budget)
```

Strictness is the point. A check that accepted any non-`PENDING` status, or treated a timeout as a pass, would also pass a stuck order. Before use against the choreographed topology it had to baseline green against the unmodified synchronous monolith, every poll resolving on attempt 1/20.

Against the choreographed topology, `tooling/newman/GOLDEN-BASELINE.md` recorded:

| Run | Assertions failed | Scenario 1 |
|---|---|---|
| Choreographed, `PAYMENT_MODE=choreographed` | 0 of 95 | `CONFIRMED` on attempt 2/20 |
| Reversed, `PAYMENT_MODE=synchronous`, `STRANGLER_PAYMENT_ENABLED` unset | 0 of 89 | `201`, attempt 1/20, no async latency |

Scenarios 3 and 4 resolve to `PAYMENT_DECLINED` and `SHIPPING_FAILED` the same way, each followed by an unconditional stock poll, not gated on the status assertion, confirming the compensating `Release` ran: stock held at 94 both times. The reversed run shows the flip undoes cleanly with no data migration.

The negative check shows the check is not vacuous. With payment-service killed (consumer and relay), a checkout still returned `202` and persisted `PENDING`, since the write side does not need payment-service alive. The poll exhausted its `20 x 750ms` budget in a `15.1s` run and **Newman exited 1**:

```
1) AssertionError  Order reaches terminal status CONFIRMED within the
   bounded-wait budget (20 x 750ms, attempt 20/20)
   expected 'PENDING' to deeply equal 'CONFIRMED'
```

A dead payment-service is red, not a false green. Restarting it drained every stuck order to `CONFIRMED` within seconds with no manual step: the self-healing property of an at-least-once pipeline with an idempotent consumer at both ends.

> **ADLC in Action.** The bounded-wait conversion and its non-vacuity baseline, green against the unmodified synchronous monolith first, were acceptance criteria set before the saga listener was written. Two alternatives were rejected in the ledger: a forked async-only collection, which diverges from the one-suite-per-seam precedent, and an "accept any 2xx" relaxation, which would also pass a silently stuck order.

> **Decision**
>
> Choreograph when each participant already knows its own reaction and no one needs to see the whole sequence. Return `202` for any decision not known at response time, make every handler idempotent at the event layer and at the RPC layer, and prove the pipeline with a bounded-wait assertion that fails when a participant is dead.

> **🤖 Explore with your agent**
>
> "Read `order_saga_listener` and `order.services.handle_payment_declined` in `examples/00-monolith`. Re-publish a `payment.declined` event for an already-declined order and show that stock in inventory-service for `SKU-WIDGET-001` does not change, then say which of the two idempotency layers stopped it."
>
> Check: `order_saga_listener.log` shows `redelivered ... no-op (status guard)` and `GET /api/inventory/SKU-WIDGET-001` returns the same `quantityOnHand` before and after.

## Build, run, observe

Run `demos/demo-payment-cutover.sh`. It starts Postgres, Kafka, inventory, payment, review and notification services, the monolith with `PAYMENT_MODE=choreographed` and the strangler proxy with every flag on, runs the full Newman suite through the proxy and tears everything down on exit.

- Expect Newman green with Scenario 1's order reaching `CONFIRMED` on poll attempt 2 of 20.
- Kill payment-service and run Newman again: checkout returns `202`, the order stays `PENDING`, the bounded-wait poll fails after 20 x 750ms and Newman exits 1.
- Set `PAYMENT_MODE=synchronous` and unset `STRANGLER_PAYMENT_ENABLED`: Newman stays green and checkout returns `201`.
- Re-publish a `payment.declined` event for a resolved order: the listener logs a no-op and stock does not move.
