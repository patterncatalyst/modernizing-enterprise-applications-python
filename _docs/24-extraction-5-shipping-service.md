---
title: "Orchestrated Sagas & Extraction 5 — Shipping (FastAPI Saga Coordinator)"
order: 24
part: "Coordinating Across Services"
description: "Shipping becomes a bounded, orchestrated saga: a single FastAPI saga coordinator sequences dispatch and owns the compensation decision, in contrast to Chapter 23's choreography; the cross-context undo is delegated to the order context that owns the data it must reverse, and the equivalence suite is extended to prove it net-zero across an even longer chain."
duration: 40 minutes
---

ch.23 built a saga with no coordinator at all — three services, each
reacting only to an event it already subscribed to, the sequence emerging
rather than being directed. This chapter builds the opposite shape for the
fifth extraction: `examples/06-shipping-service` reacts to the same
`payment.captured` event payment-service already produces, but instead of
reacting once and handing off, it runs a four-step **orchestrated saga** —
`enrich → dispatch → book_carrier → emit` — with one coordinator that
decides what happens next after every step, including whether to undo what
already happened. This is this book's orchestrated contrast, promised back
in ch.23, and it closes a real gap that chapter left open: a payment
captured and then stranded by a shipping failure.

The code is in `examples/06-shipping-service/`. The run script there builds
the service's own `shipping` schema, starts its consumer and outbox relay,
and runs the saga end to end; its `README.md` and `AGENTS.md` cover the
commands and the module layout. `MIGRATION.md`, `EVENTS.md`, and
`CUTOVER.md` in that same directory are the measured record this chapter
cites throughout.

## Orchestration, concretely: one coordinator, one decision point

ch.23 already named the conceptual distinction — in choreography, the
sequence emerges from independent reactions; in orchestration, a central
coordinator calls each participant in turn and decides the next step based
on the result. This chapter is where that distinction stops being a
definition and becomes code you can point at. `app/orchestrator.py` is the
coordinator, and it is worth being precise about what "coordinator" buys you
here that three independent consumers could not.

```python
# app/orchestrator.py -- the forward steps, each naming its one inverse
STEPS: list[dict[str, str | None]] = [
    {"name": "enrich", "compensate": None},
    {"name": "dispatch", "compensate": "cancel_shipment"},
    {"name": "book_carrier", "compensate": None},
    {"name": "emit", "compensate": None},
]
```

That table is the entire saga's shape, declared in one place, in one
process. Compare this to ch.23's choreography, where the shape of the saga —
order.placed leads to payment-service's reaction leads to the monolith's
reaction — exists nowhere as a single artifact; it has to be reconstructed by
reading three services' code and noticing which topics they share. Here,
`STEPS` *is* the saga. A reader who wants to know what shipping does, in
what order, and what each step undoes, reads one list.

The coordinator's other job — deciding whether to keep going or unwind — is
equally centralized. `advance()` drives a saga forward one step at a time and
inspects the result of each step to decide what happens next:

```python
# app/orchestrator.py -- advance(), the coordinator's top-level loop
async def advance(session_factory, settings, saga_id):
    status = await _advance_one_step(session_factory, settings, saga_id)
    if status == SAGA_RUNNING:
        await advance(session_factory, settings, saga_id)
    elif status == SAGA_COMPENSATING:
        await compensate(session_factory, settings, saga_id)
```

No step function calls another step function. No step function decides
whether to compensate. `enrich` does not know `dispatch` exists; `dispatch`
does not know whether it will be undone. All of that knowledge — the
sequence, and the decision to abort it — lives in exactly one place, which is
the structural fact that makes this orchestration rather than choreography
with extra steps. Figure 24.2 puts ch.23's payment saga and this chapter's
shipping saga side by side so the contrast reads as a picture, not just a
paragraph: the left panel has no box that knows the whole sequence; the right
panel has exactly one.

{% include excalidraw.html file="choreography-vs-orchestration-contrast" alt="The choreographed payment saga and the orchestrated shipping saga side by side -- the left panel has no box that knows the whole sequence, the right panel has exactly one" caption="Figure 24.1 — Choreography has no coordinator; orchestration has exactly one" %}

This is a trade, not a strict improvement. Choreography scales its failure
domain naturally — no single box can crash the whole saga — but makes the
*shape* of the saga something you reconstruct by reading several services at
once. Orchestration makes the shape explicit and auditable in one file, at
the cost of that one file becoming a real dependency every step runs
through. Payment chose choreography in ch.23 because nothing about capturing
a payment needed a coordinator to decide what happens next — the reacting
side already knew. Shipping chooses orchestration here because the sequence
*itself* — enrich, then dispatch, then book the carrier, then emit, undo in
reverse on failure — is the thing worth making explicit, and because a
four-step sequence with a real compensation path is exactly the shape an
orchestrator is built for.

## Adapting a DB-backed orchestrator onto SQLAlchemy

`app/orchestrator.py`'s own module docstring names its source directly: it is
adapted from `cloud-native-design-patterns`'s `17-sagas` Python
orchestrator and that project's own saga design doc
(`_docs/17-appendix-d-sagas.md`), re-homed onto this project's async
SQLAlchemy stack rather than lifted verbatim. The CNDP original drives raw
`asyncpg` with hand-encoded JSON text columns and a manual `FOR UPDATE`
query string; this service has real ORM models and
`select(Saga).with_for_update()`. The engine's *shape* — one step per
transaction, a persisted `step_index`, reverse-order compensation over only
the steps that actually ran — is identical. What changed is the driver
underneath it, which matters for a reader deciding how much of this pattern
transfers to their own stack: the saga-engine *idea* is stack-independent;
only the row-locking syntax and the ORM wiring are SQLAlchemy-specific.

`_advance_one_step` is where that adaptation shows up concretely. Every call
executes **exactly one** step, inside its own transaction:

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

Four decisions in that function are worth naming individually, because each
one answers a question a reader building their own orchestrator will hit.

**Why `SELECT ... FOR UPDATE`?** Because the saga's row can be driven from
more than one caller at once — a redelivered `payment.captured` event
racing the startup crash-resume scan this chapter covers below, for
instance — and without a row lock, two concurrent callers could both read
`step_index=1`, both execute step 2, and both append a log row for it. The
lock serializes callers at the row level: whichever transaction commits
first advances `step_index`; the second one, reading the row fresh after the
first commits, sees the already-advanced state and proceeds correctly from
there instead of duplicating work.

**Why check `saga.status != SAGA_RUNNING` before doing anything?** This is
the idempotent-advance guard, and it is what makes `advance()` safe to call
more than once for the same saga — which happens routinely, since
`payment.captured` is delivered at-least-once. A saga already `COMPLETED`,
already `COMPENSATED`, or already flipped to `COMPENSATING` by a concurrent
caller is a no-op here, not an error. Omit this check and a redelivered
trigger event would try to re-execute a step that already ran, corrupting
`context` or double-persisting a shipment.

**Why reassign `saga.context` instead of mutating it in place?** `context`
is a JSONB column, and SQLAlchemy's change-tracking on a mutable JSON value
does not notice an in-place `dict.update()` — it only flushes a column whose
*object identity* changed. `saga.context = {**saga.context, step_name:
result}` creates a new dict, which SQLAlchemy sees as a new value to write.
This is also the mechanism that threads one step's output to the next
without a second round trip: `dispatch`'s returned `shipment_id`/`address`
land in `context["dispatch"]`, and `book_carrier` reads them straight back
out of the same persisted structure two steps later.

**Why does `advance()` recurse instead of looping?** Each recursive call to
`advance()` triggers a fresh call to `_advance_one_step()`, which opens a
*new* transaction. Looping inside one transaction would mean a failure three
steps in rolls back steps one and two as well — exactly the ACID-style
atomicity this book has spent several chapters moving away from in service
of resumability. One transaction per step is what makes a crash between any
two steps leave the saga in a well-defined, already-committed state instead
of an all-or-nothing block that a crash could leave half-applied with no
record of how far it got.

{% include excalidraw.html file="orchestrated-shipping-saga-sequence" alt="The four-step orchestrated saga top to bottom, with one coordinator sequencing enrich, dispatch, book_carrier, and emit, and the reverse-order compensation path on a book_carrier failure" caption="Figure 24.2 — The orchestrated saga: one coordinator, four steps, one compensation decision" %}

## Crash-resume: the durability upgrade over the Java sibling

The Java sibling (`modernizing-enterprise-applications/examples/06-shipping-service`)
implements the identical four-step saga as a Camel Saga EIP route. Camel's
`CamelSagaService` coordinator tracks which saga is in which step **in
memory** — correct while the process is alive, with no documented resume
path if a pod restarts mid-saga. That is not a minor footnote; it means a
crash between `dispatch` and `book_carrier` in the Java implementation loses
the saga's progress entirely, and nothing on restart knows there was ever a
shipment in flight for that order.

This service's orchestrator persists the identical state — `status`,
`step_index`, `context` — as a row in `shipping.sagas`, and
`resume_running_sagas()` is the mechanism that makes that persistence pay
off:

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

`app/main.py`'s lifespan calls this **before** the service reports itself
ready to serve traffic, and it queries for every saga still `RUNNING` or
`COMPENSATING` from whatever process last touched it — a crash, a redeploy,
a `kill -9` mid-step. Because `advance()`/`compensate()` are already
idempotent and the row is locked per step, resuming a saga is not a special
code path; it is the exact same `advance()` call any fresh trigger would
make, just aimed at a saga that already has a `step_index` and `context` to
pick up from instead of starting at zero.

{% include excalidraw.html file="saga-state-machine-crash-resume" alt="The saga's status state machine, the saga_log row each step appends, and the crash-resume path that is this service's durability upgrade over the Java sibling's in-memory saga coordinator" caption="Figure 24.3 — Resumable by construction: the row remembers what the process forgot" %}

This claim is not asserted from authoring alone — it is tested, and then
re-proven live. `tests/integration/test_crash_resume.py` seeds a `RUNNING`
saga row directly with `step_index=1` (simulating a process that died right
after `enrich` committed but before `dispatch` ran), calls
`resume_running_sagas()` directly, and asserts two things: `enrich` is
**never re-invoked** — proving the persisted `step_index`/`context` were
actually honored rather than the saga starting over from scratch — and the
saga still reaches `COMPLETED` with a `DISPATCHED` shipment and exactly one
`shipment.dispatched` outbox row. The live cutover reproduced the identical
scenario against a running container: a `RUNNING` saga row was inserted
directly into the container's Postgres with `step_index=1`, the container
was `docker restart`ed, and the startup log showed `resuming saga <id>
(status=RUNNING)` followed immediately by `dispatch`/`emit` — with **no**
new `GET /api/orders/{id}` HTTP request logged for that order, confirming
`enrich` was not re-run — and `/health` reported `resumedSagaCount: 1` after
restart. The Java sibling has no equivalent test, because its coordinator
has no equivalent recovery path to test against.

## Enrich: reading across the seam, and the ACL boundary

The saga's first step has to answer a question it cannot answer from its own
data: where is this order shipping to? `shipping.sagas` has no shipping
address of its own — the saga is triggered by `payment.captured`, a payload
that (correctly) carries nothing about addresses, because payment and
shipping are different concerns and the event contract should not grow a
field one consumer needs just because that consumer happens to exist.
`enrich` closes that gap with a read across the service boundary:

```python
# app/steps.py -- enrich, saga step 1
async def enrich(session, *, settings, order_id, context):
    address = await enrich_client.fetch_shipping_address(
        base_url=settings.monolith_base_url, order_id=order_id,
        timeout_s=settings.enrich_timeout_s,
    )
    return {"address": address}
```

`enrich_client.fetch_shipping_address` calls `GET
{MONOLITH_BASE_URL}/api/orders/{orderId}` and reads back `shippingAddress` —
an additive field a sibling lane added to the monolith's own
`order/serializers.py::OrderSerializer` specifically so this saga could
enrich itself without reaching into the monolith's database directly. That
"without reaching into the database directly" clause is the anti-corruption
layer this chapter relies on without building new machinery for it: ch.16
established the ACL as a contract rather than a shared table, and this step
honors the same discipline — shipping-service never imports a monolith model,
never opens a second connection to the monolith's schema, and never assumes
anything about how `shippingAddress` is stored on the other side. It only
knows the shape of one HTTP response. If the monolith ever moves addresses
into a separate microservice of their own, this one `GET` call is the only
thing that needs to change.

`enrich` has no entry in `STEPS`' compensation column, and the reason is
structural rather than an oversight: this step persists nothing of its own.
If `enrich` fails — the monolith unreachable, retries exhausted, a response
missing `shippingAddress` — the exception propagates straight out, the
orchestrator catches it exactly like any other step failure, and routes the
saga to `COMPENSATING`. But since `dispatch` has not run yet in that case,
`compensate()` finds no `Shipment` row to undo; there is nothing *to*
compensate, because nothing durable happened. ch.25 covers what makes this
particular HTTP call resilient in its own right — the `tenacity` retry
wrapping it is this chapter's forward reference to that chapter's anchor
mechanism.

## The SHIP-FAIL compensation: why the failure point comes after persistence

`book_carrier`, step 3, is where this saga's deterministic failure injection
lives — lifted byte-for-byte from the monolith's original
`shipping.services.dispatch`'s `SHIP_FAIL_SENTINEL` rule, now moot in the
monolith once `SHIPPING_MODE=orchestrated` routes shipping through this
saga instead:

```python
# app/steps.py -- book_carrier, saga step 3
async def book_carrier(session, *, settings, order_id, context):
    address = context["dispatch"]["address"]
    if SHIP_FAIL_SENTINEL in address.upper():
        raise BookCarrierFailed(f"carrier booking failed for order {order_id}: ...")
    return {"booked": True}
```

The ordering here is required, and it is the kind of detail a reader
retyping this code could easily get backwards without understanding why it
matters: `book_carrier` runs *after* `dispatch` (step 2) has already
committed a `Shipment` row as `DISPATCHED`, in its own already-closed
transaction. That means by the time `book_carrier` can possibly fail, there
is always a real, durable row for `compensate()` to act on. Had the ordering
been reversed — check the carrier before persisting anything — a failure
would need no compensation at all, which sounds simpler but would teach the
wrong lesson: most real saga failures happen *after* some earlier step has
already left a durable mark, which is exactly the case this chapter needs to
demonstrate a real undo, not a no-op.

`compensate()` is where the coordinator's second responsibility lives — not
just sequencing forward, but deciding how to unwind:

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

`STEPS[: saga.step_index]` — only the steps that actually completed —
reversed, is the whole compensation algorithm. In this saga's case that
reverses to exactly one undo (`cancel_shipment`, `dispatch`'s inverse),
because `enrich` and `book_carrier` have nothing of their own to reverse.
`cancel_shipment` flips the `Shipment` row to `CANCELLED` rather than
deleting it — an auditable record of the aborted attempt survives, matching
the posture every other compensating action in this book has taken since
ch.19's `Release`. The terminal `shipment.failed` outbox write and the
saga's own flip to `COMPENSATED` happen in that same transaction, which is
the same atomicity discipline `_advance_one_step` already applies to the
happy path's `emit`/`COMPLETED` pair: a saga is never left marked done, in
either direction, with no outcome event queued to match.

## The AWAITING_SHIPMENT lifecycle and the two cutover dimensions

None of this saga is visible to the monolith as anything other than two
possible outcomes on a topic it already knows how to subscribe to. The
monolith's side of this cutover — built in a sibling lane, not by this
chapter, but required by everything above — is a third, orthogonal
settings axis alongside `INVENTORY_MODE` (ch.19) and `PAYMENT_MODE` (ch.23):
`settings.SHIPPING_MODE`, read only inside `handle_payment_captured`.

```python
# examples/00-monolith/order/services.py -- handle_payment_captured, the orchestrated branch
if settings.SHIPPING_MODE == "orchestrated":
    order.await_shipment()
    order.save(update_fields=["status"])
    return order
```

When `SHIPPING_MODE=orchestrated`, the monolith does not dispatch shipping
and does not confirm the order here at all — it transitions to a new
`AWAITING_SHIPMENT` status and returns, leaving the rest of the decision
entirely to this chapter's saga. `order_saga_listener` — already extended
from ch.23's two-topic consumer to four — picks up the saga's own outcome
events and resolves the hand-off:

```python
# order/management/commands/order_saga_listener.py -- four topics, one consumer group
consumer = AIOKafkaConsumer(
    captured_topic, declined_topic, dispatched_topic, failed_topic,
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    group_id=group_id, auto_offset_reset="earliest", enable_auto_commit=True,
)
```

`handle_shipment_dispatched` resolves `AWAITING_SHIPMENT → CONFIRMED`;
`handle_shipment_failed` resolves `AWAITING_SHIPMENT → SHIPPING_FAILED`, via
the identical compensating-`Release`-by-stable-key mechanism ch.23 already
built for a payment decline. Both are guarded by `_is_awaiting_shipment`, the
same status-transition idempotency shape as ch.23's `_is_pending` — an order
that already left `AWAITING_SHIPMENT` on an earlier delivery of either event
is a no-op, so Kafka's at-least-once redelivery can never double-confirm or
double-release.

{% include excalidraw.html file="order-lifecycle-awaiting-shipment-refund" alt="The full order lifecycle once SHIPPING_MODE=orchestrated: PENDING to AWAITING_SHIPMENT to CONFIRMED or SHIPPING_FAILED, plus the refund hop that closes the stranded-payment gap" caption="Figure 24.4 — AWAITING_SHIPMENT is a real intermediate status, not an implementation detail" %}

This extraction, like ch.19's and ch.23's, has **two independent cutover
dimensions**, and conflating them is the mistake this book has repeatedly
warned against. Dimension 1 is the read surface: the strangler proxy's
`STRANGLER_SHIPPING_ENABLED` flag routes `GET /api/shipments*` to this
service instead of the monolith's Django view — pure read traffic, reversible
instantly. Dimension 2 is `SHIPPING_MODE` itself, the monolith-side
environment variable that decides who *dispatches* shipping at all. Flipping
`SHIPPING_MODE` back to `inprocess` is fully reversible with no data
migration — restart the monolith with the other value — and it is orthogonal
to `PAYMENT_MODE`: both values of `SHIPPING_MODE` react to the same
`payment.captured` event regardless of whether payment itself was charged
synchronously or choreographed.

## The refund hop: closing the stranded-payment gap

ch.22 and ch.23 both named the same gap and left it open as a documented deferral: a
payment captured, then stranded, when shipping fails afterward — the
monolith releases inventory but never refunds the customer, because
payment-service exposed no refund mechanism at all. This chapter's
orchestrator is what finally makes closing that gap possible, because for
the first time, shipping's failure outcome is a **named event on a topic**
(`shipment.failed`) rather than an exception inside the monolith's own
in-process call stack. payment-service can simply subscribe to it.

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

`ShipmentFailedConsumer` subscribes to this service's own `shipment.failed`
topic — the identical event the monolith's `order_saga_listener` also
consumes to resolve `AWAITING_SHIPMENT → SHIPPING_FAILED` — and
`process_shipment_failed` refunds a `CAPTURED` payment the instant the
saga compensates. The guard is a conditional status transition, not a
blind write: `transition_payment_status_with_outbox_event` only moves a
payment from `CAPTURED` to `REFUNDED`, which makes the function idempotent
by construction and also safe against the cases where there is
nothing to refund — a payment already `REFUNDED` by an earlier delivery of
this same event, a payment that was `DECLINED` and never captured in the
first place, or an order with no payment recorded at all. None of those
cases emits a second `payment.refunded` event or moves money twice, because
the only path to `REFUNDED` requires finding a row that is currently
`CAPTURED`.

The live cutover proved this chain end to end, not just at the unit level: a
`SHIP-FAIL` checkout resolved to `SHIPPING_FAILED`, with the same captured
payment reaching `REFUNDED` — the win `tooling/newman/GOLDEN-BASELINE.md`
records against the fully-orchestrated topology — and a redelivered
`shipment.failed` against an already-`REFUNDED` payment was confirmed as a
safe no-op, no double refund, no second `payment.refunded` event. Earlier
drafts of this service's own `CUTOVER.md` carried the earlier documented gap
forward verbatim; it has since been rewritten to record the gap as **closed**,
with the proof attached, rather than left as an open deferral one more
iteration.

> **ADLC in Action** — The refund hop was not an improvisation discovered
> mid-build; closing the stranded-payment gap was named as an explicit
> acceptance criterion before `ShipmentFailedConsumer` was written, specifically
> *because* an orchestrated saga gives shipping's failure outcome a durable,
> subscribable event that a choreographed in-process exception never had.
> The planning record also considered and rejected refunding synchronously
> inside the monolith's own `handle_shipment_failed` — rejected because it
> would require the monolith to know about payment-service's internal
> status model directly, reintroducing exactly the coupling the extraction
> is meant to remove, instead of payment-service owning its own refund
> decision off a wire event it already has every right to see.

## What you learned

- Orchestration and choreography solve the same class of problem —
  multi-step work with compensation — with opposite control-flow shapes;
  this chapter's `STEPS` table is a single artifact that *is* the saga's
  shape, where ch.23's choreographed saga has no equivalent single artifact
  at all.
- A DB-backed orchestrator needs exactly four disciplines to be safe under
  concurrency and crashes: a row lock per step (`FOR UPDATE`), an idempotent
  status guard before executing anything, one transaction per step (not one
  transaction for the whole saga), and reassigning (not mutating) a JSONB
  context column so the ORM's change-tracking actually sees the update.
- Persisting `status`/`step_index`/`context` as a row — instead of tracking
  saga progress in memory the way the Java sibling's Camel coordinator does
  — turns a crash mid-saga into a resumable condition instead of a lost one;
  `resumedSagaCount: 1` and a `enrich` step that was never re-invoked are the
  live proof, not just a unit test's assertion.
- `book_carrier`'s failure point runs *after* `dispatch` has
  already persisted a `Shipment` row, which is what gives `cancel_shipment`
  something real to undo — most real saga failures happen after an earlier
  step already left a durable mark, and a saga design should be tested
  against that case, not just the trivial first-step failure.
- Giving a saga's failure outcome a durable, subscribable event
  (`shipment.failed`) instead of an in-process exception is what let
  payment-service close the stranded-payment gap ch.22 and ch.23 both
  named and left open — the refund hop was possible *because* this
  extraction is orchestrated, not despite it.

This closes Extraction 5. The next chapter stays with this same service as
its anchor example, but turns to a different question: now that a saga can
crash and resume, what else can fail, and what is this book's system already
doing — and not yet doing, by design — about it? ch.25 covers failure
modes and the resilience chassis.

---

*Verification status: <span class="status status--verified">verified</span>. The full topology — monolith, inventory/payment/shipping services, the strangler proxy, and a real Kafka broker — was brought up live for the cutover run in `tooling/newman/`: the happy and ship-fail paths resolve correctly, reversibility and crash-resume are reproduced against a live restarted container, and the negative check fails as required. 6 consecutive stable runs followed the poll-script fix ch.25 covers; no application-code bug surfaced, only a test-harness one.*
