---
title: "Event Sourcing & CQRS"
order: 21
part: "Data Across the Seam"
description: "CQRS read/write split, central to the gateway read side; event sourcing covered but kept light and optional; the trade-offs of each, proven against the real order_view same-transaction projection."
duration: 40 minutes
---

ch.20 generalized the outbox past Notification's single case and answered
the question "how do I get a fact out of one service and onto a log
reliably." This chapter asks the question on the other side of that log:
once a fact is published, reliably, what do you *do* with it on the
consuming side — and when does building a second model around "react to
facts" pays for itself rather than adding cost for no reason? That is the
question CQRS and event sourcing both answer, in two related but distinct
ways, and this chapter was held back, by design, to answer it
against the one artifact in this book built to make the answer concrete:
`examples/07-order-service`'s `order_view`, a read model projected inside
the **same transaction** as every write to the order it describes. ch.17's
`examples/03-notification-service` already qualified as a CQRS read model
two parts ago, without either chapter using the term — this chapter names
what that service already was, then builds the harder version: a read
model owned by the same service as its write model, kept current by
construction rather than by a separate consumer reacting to a topic.

The code is in `examples/07-order-service/app/repository.py` (the write
functions that do the projecting) and `app/models.py` (`OrderView`'s own
docstring states the contract this chapter explains). There is no new run
script for this chapter — `07-order-service`'s existing run path already
exercises every mechanism described below, and its `README.md` covers how
to drive it.

## CQRS: one model for writing, maybe several for reading

Command Query Responsibility Segregation says something smaller than its
name suggests: stop assuming the model you use to *change* data and the
model you use to *read* data have to be the same shape, stored the same
way, or kept consistent on the same schedule. A conventional service
collapses both responsibilities into one table, one entity, one query path
serving both an `INSERT` that enforces an invariant and a `SELECT` that
renders a screen — which is free, and correct, exactly when the two
responsibilities want the same shape. That is why `review-service`
(ch.15) and `inventory-service`'s stock table (ch.19) are plain CRUD and
are right to be plain CRUD: nothing about their read shape differs from
their write shape enough to justify a second model. CQRS pays for its
own cost precisely where that assumption breaks — where the write side
needs to enforce an invariant across a small, normalized cluster of fields
(can this customer place this order, is there enough stock to reserve)
while the read side needs to answer a differently-shaped question, at a
different scale (show me this order's current status, its line items, and
its total, denormalized into one response, served to however many clients
are polling it). Force both needs through one model and the result is
either a write table polluted with read-shaped denormalization it doesn't
need, or a read path paying for joins the write side was never designed to
make cheap. CQRS's actual mechanism for avoiding both outcomes is
unglamorous: keep the write model exactly as normalized as it should
already be, and build a separate, purpose-shaped read model next to it.

## `order_view`: the read model this book builds CQRS to demonstrate

`07-order-service/app/models.py` ships two distinct table families in one
`order_svc` schema, and the module's own docstring names the split
directly: a **command side** — `customers`, `orders`, `order_items`,
`outbox` — and a **read side** — `order_view`, the one table
`app/routes.py`'s `GET` handlers ever query. `OrderView` is a denormalized
projection: one row per order, `items` stored as a JSON array rather than
a joined child table, because the read side's only query shape is "the
whole order, exactly as the wire contract renders it" — there is no
normalized-query benefit to a child table here, only an extra join on
every read that nothing in this service ever needs. This is CQRS in its
smallest, plainest form: not a second datastore, not a second team of
infrastructure to operate, just two tables in one schema, each shaped for
the job it does.

What makes `order_view` the concrete example this chapter was held back to
teach against is not the table's shape — it's *when* it gets written.
Every write path in this service upserts `order_view` inside the exact
same local transaction as the aggregate mutation that produced it, not in
a follow-up step, not from a separate consumer reacting to the service's
own event:

{% include codetabs.html langs="create_order_with_outbox_and_view — the checkout write|transition_order_status_with_view — a saga reaction's write" %}

```python
# app/repository.py -- three writes, one transaction
async def create_order_with_outbox_and_view(session, *, customer, items,
                                             shipping_address, payment_method,
                                             created_at):
    order = Order(customer_id=customer.id, customer_email=customer.email,
                   status="PENDING", total_cents=total_cents, ...)
    session.add(order)
    await session.flush()                      # populates order.id

    order_items = [OrderItem(order_id=order.id, **snapshot) for snapshot in items]
    session.add_all(order_items)
    await session.flush()

    view = OrderView(order_id=order.id, customer_id=order.customer_id,
                      status=order.status, total_cents=order.total_cents,
                      shipping_address=order.shipping_address,
                      created_at=order.created_at,
                      items=_item_view_payload(order_items))
    session.add(view)

    outbox_event = OutboxEvent(aggregate_type="order", aggregate_id=str(order.id),
                                event_type="order.placed", payload=payload, ...)
    session.add(outbox_event)

    await session.flush()
    await session.commit()                      # all three rows together, or none
    return order
```

```python
# app/repository.py -- a saga reaction, the same discipline
async def transition_order_status_with_view(session, *, order_id,
                                             expected_status, new_status):
    stmt = (
        update(Order)
        .where(Order.id == order_id, Order.status == expected_status)
        .values(status=new_status)
        .returning(Order)
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        await session.rollback()
        return None                              # idempotent no-op, redelivery

    items = await list_order_items(session, order_id)
    await _upsert_order_view(session, order, items)  # SAME transaction

    await session.flush()
    await session.commit()
    return order
```

Both functions commit the aggregate change and the `order_view` upsert
together, inside the one transaction Postgres's own write-ahead log
already spans — the same mechanism ch.20 built the outbox pattern around,
reused here for a projection instead of an event row. `create_order_with_
outbox_and_view` is this service's three-way atomicity guarantee: the
`orders`/`order_items` write, the `order_view` PENDING row, and the
`order.placed` outbox row all land together, or none of them do, which
means a reader can never observe the aggregate without a matching view row
and the outbox relay can never publish an event for an order that didn't
actually persist. `transition_order_status_with_view` carries the same
discipline into every one of the four saga reactions (`handle_
payment_captured`/`handle_payment_declined`/`handle_shipment_dispatched`/
`handle_shipment_failed`, built in full in ch.26): the conditional `UPDATE`
is the idempotency backstop against a redelivered event racing a second
delivery — a `WHERE status = expected_status` clause that only one of two
concurrent deliveries can satisfy — and the `order_view` upsert that
follows it, inside the same transaction, is what keeps the read model from
ever lagging behind a transition that already committed.

{% include excalidraw.html file="order-cqrs-write-read-split" alt="The CQRS command/query split inside order-service: the command path reserves over gRPC outside any local transaction, then persists the write aggregate, the order_view projection, and the order.placed outbox row in one transaction; the query path reads order_view exclusively, never the write tables" caption="Figure 21.1 — CQRS, concretely: one write aggregate, one projection, upserted in the same transaction as every mutation" %}

## Read-your-writes within a service, not across a saga

What this buys is precise, and the precise version matters more than
a generous one. Because the `order_view` upsert commits in the same
transaction as the write it reflects, a `GET /api/orders/{id}` issued the
instant after `POST /api/orders` returns its `202` sees the new `PENDING`
row immediately — no polling, no delay, no window where the aggregate
exists but the read model hasn't caught up yet. That is **read-your-writes
consistency**, and it is a real, structural guarantee this service's own
`app/routes.py` depends on: `get_order_view_by_id`/`list_order_views` are
the *only* two query functions `app/routes.py`'s `GET` handlers call —
`Order`/`OrderItem`, the write-model classes, are never imported there at
all. What this guarantee does **not** buy is consistency across the saga
that eventually resolves the order. A client polling `GET /api/orders/{id}`
moments after checkout can and will observe `PENDING`, then
`AWAITING_SHIPMENT`, then `CONFIRMED`, each a real, committed intermediate
state — the `CONFIRMED` transition is only as fresh as the Kafka event
(`shipment.dispatched`) that eventually drives `handle_shipment_dispatched`
to write it. ch.22 names that gap by its proper terms (PACELC, isolation
traded for latency); this chapter's narrower claim is that the gap starts
exactly at the service boundary, not one line earlier — `order_view` closes
the distance between a write and its own service's read to zero, and
closes nothing else.

## Proving it: the projection-disabled negative

A read path that could silently fall back to querying `orders`/
`order_items` directly whenever the projection lagged would hide a broken
projection completely, and a chapter that only asserted "reads come from
`order_view`" in prose would be making exactly the kind of claim this
book's own verification discipline refuses to let stand unproven.
`tooling/newman/`'s order-service contract run closes that gap with a
real intervention, not a thought experiment: the `await
_upsert_order_view(session, order, items)` call inside `transition_order_
status_with_view` was temporarily commented out — the aggregate still
transitions correctly, only the CQRS read-side projection stops being kept
in sync — the service restarted, and Scenario 1 (a plain happy-path
checkout) run alone:

```
1. AssertionError  Order reaches terminal status CONFIRMED within the bounded-wait budget (40 x 750ms, attempt 40/40)
                   expected 'PENDING' to deeply equal 'CONFIRMED'
```

`GET /api/orders/{id}` — which reads `order_view` exclusively, per this
service's own contract — never observed the real, successful transition
happening on the write side. The bounded-wait poll exhausted its full
40-attempt budget and failed loudly: **1/53 assertions failed, newman exit
code 1.** Restoring the one commented-out line and re-running Scenario 1
produced a clean pass: **0 failed, exit 0.** That is the proof this
chapter's central claim needed and the kind every CQRS read model in this
book should be held to: not "the projection code exists," but "removing
the projection call breaks exactly the read path it was supposed to keep
current, and restoring it fixes exactly that." A projection that can't be
proven this way, by breaking it to see what actually fails, is a
projection nobody has confirmed does anything at all.

{% include excalidraw.html file="order-view-rebuildable-projection" alt="Aggregate feeds a projection feeds the view under normal operation; rebuild_order_view recomputes the view from the current aggregate at any time; the projection-disabled negative test proves the read path never silently falls back to the aggregate by showing it go stale instead" caption="Figure 21.2 — A rebuildable read model: the projection-disabled negative is the proof the read path never falls back to the aggregate" %}

## Rebuildable, not a second source of truth

The property that keeps `order_view` from quietly becoming a second,
competing source of truth is that it is always recomputable from the
aggregate it describes. `app/repository.py::rebuild_order_view` does
exactly this — reads the current `Order`/`OrderItem` rows and calls the
same `_upsert_order_view` helper every write path already calls, producing
an identical result whether it runs as a side effect of a checkout or as a
standalone repair. `app/service.py::rebuild_order_view` wraps it as an
operational entry point, and the test suite's own projection-disabled
negative reuses it directly to restore `order_view` to a known-correct
state after breaking it by hand. `OrderView`'s own docstring states
the property without hedging: this table is "a cache of the aggregate's
shape for reads, never a second source of truth." That property is what
makes a read model's own storage *disposable* rather than precious — a
corrupted or lost `order_view` is an operational inconvenience fixed by
one function call, never a data-loss incident, because the aggregate
tables remain the only place a fact about an order is ever decided.

## `notification-service` was already a CQRS read model

ch.17 built `examples/03-notification-service` without this chapter's
vocabulary, and it is worth going back to name precisely why it qualifies.
The monolith's checkout — the write side — decides whether an order is
valid and commits that decision as ordinary relational rows. Notification
is a second, independently stored, independently scaled model: its own
`notification` schema, its own `Notification` table, built for exactly one
query shape — "what has this customer been told, and when." It consumes
`order.placed` off the same outbox-fed topic every other consumer in this
book reads, applies a check-then-insert idempotency guard backstopped by a
database unique index, and produces one row representing a fact the write
side already decided. It does not enforce the order's invariants and
cannot reject a checkout; it is, in Kleppmann's term, a **materialized
view** — a derived answer kept current by folding new facts into it,
rebuildable from the source topic if it were ever lost, never itself a
source of truth. That makes it a CQRS read model by every test that
matters, and the contrast with `order_view` is instructive precisely
because the two differ on the one axis CQRS leaves open: Notification's
projection is fed by an asynchronous consumer reacting to a topic, owned by
a *different* service than the one that wrote the fact; `order_view`'s
projection is a direct method call inside the *same* transaction as the
write, owned by the same service. Both are CQRS. Only one of them buys
read-your-writes consistency, and the difference between them is exactly
the difference between "eventually consistent, rebuildable from a topic's
retention window" and "immediately consistent within one transaction,
rebuildable on demand from the aggregate itself" — two legitimate points on
the same spectrum, chosen for different reasons by different services in
this same book.

## Why this book builds CQRS, not event sourcing — stated as a decision

It is worth being precise about which pattern this chapter is and is not
teaching, because the two are easy to conflate and the conflation causes
real design mistakes. CQRS says: separate the model you write from the
model you read. Event sourcing says something stronger, and specifically
about the *write* side: don't store current state as mutable rows at all —
store the append-only sequence of events that produced that state, and
treat that sequence as the only system of record, with current state
computed by replaying it. This book's write side never does that. `Order`
in `07-order-service/app/models.py` is a conventional, mutable row with a
`status` column updated in place by an ordinary `UPDATE` statement; there
is no event store anywhere in this project, and no code that reconstructs
an order's state by folding a stream of past events. What this book builds
instead is **CQRS with an outbox event log, not event sourcing** — the
outbox (ch.17, ch.20) and `order_view`'s projection (this chapter) are both
ways of letting other things react to what the write side already decided,
without the write side itself being redefined as a log. That is a
deliberate scoping decision, not an unfinished one: event sourcing commits
a team to schema evolution of every event type forever (a consumer written
years from now still has to deserialize and correctly interpret `order.
placed` v1), to a snapshot strategy that bounds replay cost as history
grows, and to tooling and team familiarity most shops don't have on day
one — real, ongoing costs with no equivalent in a mutable-row system, where
a migration simply retires the old shape. Nothing in this project's own
needs justifies paying them: every read model this book builds —
Notification's "has this customer been told," `order_view`'s "what does
this order currently look like" — needs "the current state, derived from
recent facts," never "replay this aggregate's entire history to reconstruct
an arbitrary past point in time," which is the specific question event
sourcing exists to answer well. Building the heavier pattern to answer a
question this migration never asks would be exactly the kind of
unjustified complexity this book's scope discipline argues against
everywhere else, dressed up as thoroughness here. The event payloads this
project does publish — `order.placed`, `payment.captured`, and the rest —
stay JSON on the wire, versioned only by convention; a schema registry with
real compatibility enforcement (Avro, Apicurio) is a different, later
concern this book picks up in ch.28, once the question shifts from "should
events be the system of record" (no) to "how do independently-deployed
consumers stay safe when a producer's event shape changes" (yes, and that
needs tooling CQRS alone doesn't provide).

> **ADLC in Action** — Deferring this chapter was
> a planning-phase decision, not a scheduling accident: the build plan
> judged that teaching CQRS against a read model fed by an asynchronous
> consumer (Notification, already shipped) would only demonstrate half the
> pattern, and that the stronger teaching example — a projection written
> inside the same transaction as its aggregate, with a negative test proving
> the read path never falls back to the write tables — did not exist until
> `07-order-service` did. Rather than writing a weaker version of this
> chapter early and revising it later, the decision was to hold the whole
> chapter until the artifact that earns it was real, verified code. The
> projection-disabled evidence cited above is exactly that artifact,
> exercised in `tooling/newman/`'s order-service contract run, not a
> claim asserted from reading `repository.py` alone.

## What you learned

- **CQRS separates the model that accepts writes from the model that serves
  reads** because the two often want different shapes, different scales, and
  different consistency guarantees — not because splitting a model is
  inherently better than keeping one.
- **`order_view` is this book's strongest CQRS example because the
  projection commits inside the same transaction as the write it reflects**
  (`create_order_with_outbox_and_view`, `transition_order_status_with_view`)
  — a stronger guarantee than Notification's asynchronous, topic-fed
  projection, and a deliberate choice available only because both the
  aggregate and the read model are owned by the same service.
- **Read-your-writes is a within-service promise, not a whole-saga one**: a
  `GET` right after a `POST` sees the new row immediately, but a status that
  depends on a later Kafka event is only as fresh as that event — the gap
  starts at the service boundary, nowhere earlier.
- **A read path that could silently fall back to the aggregate would hide a
  broken projection completely** — the only real proof a CQRS read model
  does anything at all is a negative check that disables the projection and
  watches the read go stale while the write moves on, exactly what
  that contract run did against live code.
- **A CQRS read model should be rebuildable, not precious** —
  `rebuild_order_view` recomputes `order_view` from the current aggregate at
  any time, which is what keeps it a cache rather than a second source of
  truth.
- **This book builds CQRS with an outbox event log, not event sourcing** —
  the write side stays conventional, mutable rows throughout; the heavier
  pattern (the log as the only system of record, state computed by replay)
  is a cost this migration's own needs never justify paying, and real
  schema-evolution tooling for the events this project does publish is a
  separate concern ch.28 picks up.

Next: ch.22's ACID → ACD argument already named what a saga costs once no
single transaction spans a whole business operation; read it alongside this
chapter's narrower claim — a same-transaction projection closes the
consistency gap at exactly one service boundary, and nowhere past it.
