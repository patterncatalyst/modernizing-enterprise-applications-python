---
title: "Distributed Transactions, the Saga & Extraction 4 — Payment (choreographed)"
order: 23
part: "Coordinating Across Services"
description: "ACID gives way to ACD; checkout's synchronous 201/402 contract becomes an asynchronous 202/PENDING handoff; a choreographed saga captures payment, confirms or compensates, and the equivalence suite is taught to verify an outcome it can no longer observe on the same request."
duration: 45 minutes
---

ch.22 named the cost: once payment moves to a service that reacts to an
event instead of answering a call, checkout's single transaction can no
longer span the whole business operation, and Isolation is the guarantee
that doesn't survive the cut. This chapter builds what replaces it — a
**choreographed saga**, the fourth extraction in this book and the first one
where no single request, synchronous or otherwise, resolves an order by
itself. `examples/05-payment-service` reacts to `order.placed`;
the monolith's own `order_saga_listener` reacts to what payment-service
publishes back; and checkout's `POST /api/orders` answers `202 Accepted`
instead of a terminal `201`, because for the first time in this book, the
accurate answer to "did this order succeed" is "not yet."

The code is in `examples/05-payment-service/` (the new FastAPI choreography
participant) and `examples/00-monolith/order/` (the choreographed checkout
path and its saga listener). `CUTOVER.md` in the service directory and
`tooling/newman/GOLDEN-BASELINE.md`'s cutover section record the measured
numbers cited throughout this chapter.

## ACID gives way to ACD: SMELL #3 paid off, for payment

ch.22 built the vocabulary; this chapter is where it becomes concrete for a
specific seam. `settings.PAYMENT_MODE` is the dispatch point, and
`order.services.place_order()`'s own docstring states the choice directly:

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

`PAYMENT_MODE` is an orthogonal axis on top of `INVENTORY_MODE` — both
choreographed and synchronous payment reserve inventory the same way
(`_place_order_choreographed` reuses the exact same `_reserve_lines_remote`/
`_release_reserved` helpers `_place_order_remote` established in ch.19), so
flipping payment's mode never changes how inventory is reserved, only what
happens to the rest of checkout once the reservation succeeds.

## Choreography, not orchestration — and the contrast with Chapter 24

This book's stack-substitution mapping named the distinction between
choreography and orchestration as a planning decision before any payment
code existed, and it is worth being precise about what each word means,
because the difference is not "more services" versus "fewer services" — it
is about where the decision logic for "what happens next" lives. In an
**orchestrated** saga, a central coordinator calls each participant in turn
and decides the next step based on the result — the coordinator knows the
whole sequence. In a **choreographed** saga, there is no coordinator at
all: every participant reacts only to events it already subscribes to, and
the sequence emerges from those reactions rather than being directed by any
one of them. Trace the actual code in this extraction and that absence is
structural, not just a design label: `examples/05-payment-service` has no
knowledge that an order_saga_listener exists downstream of it, nothing in
payment-service's code names the monolith, and nothing in the monolith's
`order_saga_listener` calls payment-service directly — it only ever
subscribes to Kafka topics payment-service happens to publish to. Each side
can be redeployed, restarted, or replaced without the other changing a
single line, because the only contract between them is the shape of two
Kafka topics.

This is a design choice, and a temporary one for
this *specific* seam, not a verdict on orchestration as inferior. Chapter 24's
shipping extraction is positioned as this book's orchestrated contrast — a
central coordinator calling shipping synchronously and deciding the next
step based on its answer — precisely so a reader sees both shapes solve
related problems with opposite control-flow topologies, and can judge for
themselves which one a given seam calls for. Payment chose choreography here
because nothing about capturing a payment needs a coordinator to decide what
happens next; the monolith already knows what it wants to do with a captured
or declined payment (confirm-and-ship, or release-and-decline), so there is
no decision left for an external coordinator to make that the reacting side
doesn't already know how to make itself.

## The sync→async checkout contract: why `202`, not `201`-with-`PENDING`

The actual decision point lives in `order/views.py`, and it is worth reading
exactly what it does, because a subtly dishonest version of this cutover was
rejected at the planning gate for a specific reason:

```python
# order/views.py -- OrderListCreateView.post
response_status = (
    status.HTTP_202_ACCEPTED
    if order.status == Order.Status.PENDING
    else status.HTTP_201_CREATED
)
return Response(body, status=response_status, headers={"Location": f"/api/orders/{order.id}"})
```

This derives the status code purely from the order's own persisted status —
not from a parallel `if PAYMENT_MODE == "choreographed"` branch that could
drift out of sync with what the order actually is. A rejected alternative
would have kept returning `201 Created` for a `PENDING` order and let the
client discover later that "created" didn't mean "confirmed" — cheaper to
implement, and dishonest in exactly the way this book's conventions forbid:
`201` is HTTP's own vocabulary for "the resource now exists in its final
form," and a PENDING order is not in its final form. `202 Accepted` is the
correct status for exactly this situation — "the request was accepted for
processing, but the processing has not completed" — and using it here is
not a stylistic nicety, it's the HTTP spec applying the same accurate-status-code
discipline this book's own conventions already apply everywhere
else.

{% include excalidraw.html file="checkout-sync-to-async-contract" alt="Before/after panels: PAYMENT_MODE=synchronous's one round trip ending in a terminal 201/402/422/409, versus choreographed's same round trip ending in a 202 PENDING promise the caller must poll to resolve" caption="Figure 23.1 — The contract change: 202 is a promise, not a faster 201" %}

This is also, by this project's own ledger, the first deliberate change to a
previously-stable wire contract rather than an additive extension — every
earlier extraction added a field, a header, a new endpoint, never *changed*
what an existing response code meant for an existing endpoint. That is a
meaningfully different kind of risk, which is exactly why it required an
explicit, named, non-silent decision at the planning gate rather than being
treated as an implementation detail discovered mid-build.

## The event topology: two outboxes, no coordinator

ch.20 already walked payment-service's half of the outbox mechanism in
detail; this section is about the *shape* the two outboxes make together,
end to end, which is the concrete realization of choreography this chapter
is about.

{% include excalidraw.html file="choreographed-payment-saga-sequence" alt="The full choreographed saga top to bottom, branching into its three terminal outcomes -- every arrow is an event one side reacted to, no orchestrator box anywhere" caption="Figure 23.2 — The choreographed saga: every arrow is a reaction, not a call" %}

Trace the full path a single checkout takes. `_place_order_choreographed`
persists the `PENDING` order and its `order.placed` outbox row — now
carrying an optional `paymentMethod` field, additive and backward-compatible
with every consumer that already ignores unknown fields — in one local
transaction, then returns `202`. The monolith's own `outbox_relay` (ch.20)
publishes that row to Kafka. `examples/05-payment-service`'s
`OrderPlacedConsumer` picks it up and calls `process_order_placed`, which
charges deterministically (`DECLINE_SENTINEL = "DECLINE"`, lifted
byte-for-byte from the monolith's original synchronous rule) and writes a
`Payment` row plus its own outbox event, atomically, in payment-service's
own `payment` schema. Payment-service's own `OutboxRelay` publishes
`payment.captured` or `payment.declined`. The monolith's
`order_saga_listener` — a new Django management command, structurally
identical to `outbox_relay`/`order_placed_consumer`, just subscribed to two
topics on one consumer group instead of one — consumes whichever event
arrived and calls `handle_payment_captured` or `handle_payment_declined`.

Nowhere in that chain does any participant know the chain exists beyond the
one topic it personally touches. The monolith that started the chain is
also the process that finishes it, but the two halves of that same process
(`_place_order_choreographed` and `order_saga_listener`) communicate with
each other exclusively through Kafka and through payment-service's own
decision — not through any shared in-process state, which is precisely what
makes this a saga rather than just an unusually indirect function call.

## The monolith's first saga consumer

`order_saga_listener.py`'s own docstring is explicit about where the actual
decision logic lives and why: "All the actual reaction logic... lives in
`order.services.handle_payment_captured`/`handle_payment_declined`, where
it's unit-testable without Kafka; this command is just the aiokafka
wiring." That separation matters for the same reason it has mattered in
every consumer this book has built since ch.17 — a status-transition
decision should be testable by calling a function with a dict, not by
standing up a broker:

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

One `AIOKafkaConsumer` subscribed to *two* topic names at once — aiokafka
accepts a list — is what lets a single consumer group react to both outcome
events without two separate processes. `getmany(timeout_ms=1000)` rather
than `async for record in consumer` is the same idiom `order_placed_consumer`
already established: an unbounded `async for` blocks indefinitely on an idle
topic, which would never give the `stop_event` a chance to end the loop on
`SIGINT`/`SIGTERM`; polling with a timeout checks the stop condition every
second even when nothing has arrived. `enable_auto_commit=True` is the same
simplest-correct-starting-point choice every consumer in this book makes,
and it's safe here for the identical reason it's safe everywhere else in
this project: a crash after processing but before the next auto-commit
redelivers the message, and redelivery is safe *only* because the handler
functions underneath are idempotent — which is the next section's subject.

## Compensation via choreography: the catch block retires for this path

ch.19's `_place_order_remote` compensates with a plain Python `try`/`except`
wrapped around a single request's call stack — the compensation and the
thing it's compensating for live in the same function, the same stack
frame, the same few milliseconds. That shape is structurally impossible for
this chapter's saga: the decision to compensate arrives on a *different*
call stack, in a *different* process, seconds or longer after the original
reservation. `handle_payment_declined` is what compensation looks like when
there is no catch block to attach it to:

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

`_release_order_lines` recovers *what* to release from the persisted
`OrderItem` snapshot rows — `sku`, `quantity` — rather than from an
in-memory list, because the saga listener runs on a completely different
call stack than the checkout request that did the original `Reserve`;
there is no `reserved` list left over to reuse the way `_place_order_remote`
had one sitting on its own stack. `handle_payment_captured`'s branch for a
shipping failure does the identical compensation, triggered by a different
event:

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

This is Option A from the planning gate: shipping dispatch moves
*into* the `payment.captured` reaction, meaning shipping now happens after
payment captures rather than before, and a shipping failure here
compensates inventory but — as ch.22 already named — leaves the captured
payment unrefunded, a documented deferral to Chapter 24's orchestrated saga
rather than a silent gap.

## Idempotency: at-least-once delivery, exactly-once effect

Closing the gap ch.19 explicitly deferred — "idempotency of
`Release` and over-restore protection... to the saga chapters" — required
two layers, not one, and the reason for two is itself instructive: a
client-side check can never see a crash window on the server it's calling.

**Layer 1, the status-transition guard**, lives entirely on the saga
listener's side:

```python
# order/services.py -- _is_pending
def _is_pending(order: Order, event_type: str) -> bool:
    if order.status != Order.Status.PENDING:
        logger.info("%s redelivered for order_id=%s status=%s -- no-op (status guard)",
                    event_type, order.id, order.status)
        return False
    return True
```

An order that has already left `PENDING` — because an earlier delivery of
*this* event, or of the *other* outcome event for the same order, already
resolved it — makes every subsequent call a no-op before it ever reaches
`_release_order_lines` or a second `confirm()`. This is cheap, fast, and
correct for the common case: Kafka redelivering the same message to the
same consumer after a rebalance.

**Layer 2, the `idempotency_key` ledger**, lives on inventory-service's
side, and it exists because Layer 1 alone has a blind spot the function's
own compensation helper names directly — a stable, deterministic key is
derived once and sent on every retry of the same logical release:

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

One `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id`, not
a `SELECT` followed by a conditional `INSERT` — the same concurrency
argument ch.19's conditional `Reserve` already made for the decrement side
applies here to the increment side: Postgres's unique index serializes
concurrent inserts targeting the same key, so of two racing identical-key
calls, exactly one gets a row back and proceeds to the `UPDATE`; the other
sees no row and short-circuits as a no-op. Both statements commit together
in one transaction, so a crash between the ledger insert and the stock
update can never leave one without the other.

The blind spot Layer 1 can't see is precisely the crash window this two-layer
design closes: the gRPC `Release` call succeeds and increments stock, but the
saga listener crashes *before* it commits the order's new status — on
restart, Kafka redelivers the same `payment.declined` event, the order is
still `PENDING` (the status write never landed), and Layer 1's guard would
let a second `Release` call straight through. Layer 2's ledger is what
stops *that* second call from over-restoring stock, because it checks the
RPC's own idempotency key, not the caller's belief about what it already
did.

{% include excalidraw.html file="idempotent-compensation-two-layers" alt="A compensating Release survives redelivery at both the Kafka-event layer (the saga's status-transition guard) and the RPC layer (inventory-service's compensations ledger, INSERT ... ON CONFLICT DO NOTHING)" caption="Figure 23.3 — The deferred idempotency gap closed: idempotent at the event layer, idempotent at the RPC layer, independently" %}

`tooling/newman/GOLDEN-BASELINE.md`'s cutover lane proved both layers
live, independently, against the same already-resolved order. The exact
`payment.declined` event payment-service had published was re-published to
Kafka by hand; `order_saga_listener.log` recorded `payment.declined
redelivered for order_id=12 status=PAYMENT_DECLINED -- no-op (status
guard)`, and stock held at 94 before and after. Separately, bypassing the
saga guard entirely, the monolith's compensating `Release` RPC was called
directly over gRPC *twice*, using the identical stable key the saga listener
itself derives (`"12:SKU-WIDGET-001:release"`): both calls answered
`reservation_ok=true` — a duplicate is not treated as an error — but
`on_hand_qty` never moved past its pre-redelivery value of 94 across either
call. Stock was never over-restored at either layer, proven by direct query,
not inferred from the suite's own bookkeeping.

## Keeping the equivalence suite sound across a contract it can no longer observe synchronously

Every extraction before this one could be verified by the same Newman
collection, unchanged in shape, because every prior cutover preserved
checkout's synchronous terminal contract. This chapter's cutover breaks
that assumption by design, and the equivalence suite had to be taught a new
verification shape without losing the property that made it trustworthy in
the first place: a suite that can pass vacuously isn't actually testing
anything.

The fix reuses an idiom this book already built rather than inventing a new
one. Every checkout-scenario `POST` became tolerant of `201|402|202` — the
request assertion no longer insists on a single status code, because both
modes are legitimate depending on which flag is active. The assertion that
actually proves something moved to a **bounded-wait poll** of `GET /api/orders/{id}`,
reusing the exact `setNextRequest` retry idiom ch.17's notification folder
already established for its own Kafka-backed eventual consistency, extended
to a strict terminal-status assertion rather than a soft "it eventually
changed" check:

```
1c. Bounded-wait poll: order reaches terminal status -> strictly CONFIRMED
    (20 x 750ms budget)
```

That strictness is the entire point of the assertion. A version of this check
that accepted *any* non-`PENDING` status, or that treated a timeout as a
pass, would also pass against a stuck order silently masquerading as
resolved — exactly the failure mode this chapter's negative check exists to
catch. Before trusting this new shape against the choreographed topology,
it had to baseline green against the **unmodified synchronous monolith**:
every poll resolving on attempt 1/20, zero added latency, confirming the
bounded-wait mechanism isn't a no-op that happens to always pass.

Against the real choreographed topology, `tooling/newman/GOLDEN-BASELINE.md`
recorded the suite doing real work: **95 assertions, 0 failed**, with
Scenario 1's poll resolving `CONFIRMED` on **attempt 2/20** — a real round
trip through Kafka and back, not an artifact of a fast loop — and Scenario
3/4 resolving `PAYMENT_DECLINED`/`SHIPPING_FAILED` the same way, each
followed by an *unconditional* stock poll (not gated on the status
assertion passing) confirming the compensating `Release` actually ran:
stock held at 94 both times. Reversing both cutover dimensions —
`PAYMENT_MODE=synchronous`, `STRANGLER_PAYMENT_ENABLED` unset — the suite
stayed green at **89 assertions, 0 failed**, Scenario 1 back to `201`
resolving on attempt 1/20, zero async latency, proving the flip reverses
cleanly with no data migration.

The proof that this matters is the negative check. With payment-service killed
outright (both its consumer and its relay), a checkout still returned `202`
and persisted `PENDING` — the write side of this chapter's saga doesn't need
payment-service alive at all — but the bounded-wait poll exhausted its full
`20 x 750ms` budget, a real `15.1s` run duration, and **Newman exited 1**:

```
1) AssertionError  Order reaches terminal status CONFIRMED within the
   bounded-wait budget (20 x 750ms, attempt 20/20)
   expected 'PENDING' to deeply equal 'CONFIRMED'
```

A dead payment-service is RED, not a false green — the exact property a
bounded-wait suite has to have to be trusted at all. Restarting
payment-service drained every order stuck during the outage to `CONFIRMED`
within seconds, with zero manual intervention, confirming the self-healing
property of an at-least-once pipeline with an idempotent consumer on both
ends.

> **ADLC in Action** — Converting the equivalence suite's shape was planned,
> not improvised: the iteration's build plan named the bounded-wait
> conversion and its required non-vacuity baseline (green against
> the unmodified synchronous monolith, before trusting it against the new
> topology) as an explicit acceptance criterion before the saga listener
> was written. Two rejected alternatives — a forked async-only collection,
> and an "accept any 2xx" relaxation — are recorded in the ledger alongside
> *why* each was rejected (a forked suite diverges from this project's
> one-suite-per-seam precedent; "any 2xx" would also pass a silently stuck
> order), so the choice a reader sees in this chapter's code is traceable
> back to a planning-phase decision with its alternatives still visible.

## What you learned

- Choreography and orchestration are distinguished by where the "what
  happens next" decision lives, not by topology or service count — this
  extraction's payment-service has zero knowledge that a saga listener
  exists downstream of it, which is what makes it an actual choreography
  rather than an orchestration with extra hops.
- `202 Accepted`, derived purely from the order's own persisted status, is
  the accurate HTTP vocabulary for "accepted for processing, not yet
  resolved" — a rejected alternative that kept returning `201` for a
  PENDING order would have been a misleading contract, not a simpler one.
- Compensation via choreography has no catch block to attach to, because
  the decision to compensate arrives on a different call stack than the
  original reservation; `_release_order_lines` recovers what to release
  from persisted snapshot rows, not from in-memory state that no longer
  exists by the time the reaction runs.
- Closing a compensation idempotency gap took two independent
  layers, not one: a cheap client-side status-transition guard for the
  common redelivery case, and a server-side ledger
  (`INSERT ... ON CONFLICT DO NOTHING`) for the crash window the client-side
  guard structurally cannot see — proven live at both layers, stock held at
  94 across both.
- An equivalence suite that changes shape across a contract-breaking cutover
  has to prove it isn't vacuous before it can be trusted: baseline green
  against the unchanged synchronous system first, then require a real
  negative (a dead payment-service failing the bounded-wait budget, exit 1,
  15.1s) before the new green result means anything.

This closes Extraction 4. Part 7 continues with ch.24, where shipping leaves
the monolith under the opposite control-flow shape — an orchestrated saga,
with a coordinator that can finally close the refund gap ch.22 and this
chapter both named and left open.

---

*Verification status: <span class="status status--verified">verified</span>. The full choreographed topology — monolith, payment/inventory/review/notification services, the strangler proxy, and a real Kafka broker — was brought up live for the cutover run in `tooling/newman/`: 95/95 and 89/89 assertions green across the forward and reversed runs, the negative check fails strictly then self-heals on restart, and double-delivery idempotency is proven independently at both the saga and inventory layers. No integration bug surfaced; the known stranded-payment-on-ship-fail gap (ch.22) remains open by design, deferred to the next extraction (ch.24).*
