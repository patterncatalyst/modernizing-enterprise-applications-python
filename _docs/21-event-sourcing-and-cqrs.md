---
title: "Event Sourcing & CQRS"
order: 21
part: "Data Across the Seam"
description: "CQRS splits the write model from the read model, shown with order_view, a projection committed in the same transaction as its aggregate. Event sourcing is covered as the heavier, optional pattern and declined."
duration: 40 minutes
---

## Learning objectives

By the end of this chapter you can:

- Define CQRS and say when a separate read model pays off.
- Recognize `examples/03-notification-service` as a CQRS read model: its own schema, no foreign key into the monolith, populated by idempotently folding `order.placed` events.
- Build `order_view` as a read model owned by the same service as its write model and projected in the same transaction as every write.
- Distinguish a CQRS read model (a materialized view) from event sourcing, where the event log is the system of record and state is computed by replay.
- Name the costs of event sourcing (event schema evolution and upcasting, snapshots to bound replay, tooling and team familiarity) and the reason to decline them.
- Prove a read model is current with a bounded-wait poll, and prove a read path never falls back to the aggregate with a projection-disabled negative check.
- Tell apart two forms of rebuildability: replay bounded by a topic's retention, and on-demand recompute from the current aggregate.

## Why this matters

Once a fact is published reliably, the consumer has to do something with it, and a second model built around "react to facts" has to pay for itself. CQRS and event sourcing answer that in two related ways. `examples/07-order-service`'s `order_view` makes the first concrete: a read model owned by the same service as its write model and kept current by construction, not by a consumer reacting to a topic. `examples/03-notification-service` was already a CQRS read model without the name.

The code is in `examples/07-order-service/app/repository.py` (the write functions that project) and `app/models.py`. Its `README.md` covers how to run it.

## Pattern: CQRS

Command Query Responsibility Segregation says the model that changes data and the model that reads it needn't share a shape, storage or consistency schedule. A conventional service uses one table and one query path for both an `INSERT` that enforces an invariant and a `SELECT` that renders a screen. That is correct when both want the same shape, which is why `review-service` and `inventory-service`'s stock table are plain CRUD.

CQRS pays where the assumption breaks. The write side enforces an invariant across a small normalized cluster of fields (can this customer place this order, is there enough stock). The read side answers a differently shaped question at a different scale: this order's status, line items and total, denormalized into one response for however many clients poll it. One model for both leaves either a write table polluted with read-shaped denormalization or a read path paying for joins the write side never made cheap. CQRS keeps the write model as normalized as it should be and builds a purpose-shaped read model beside it.

### `order_view`

`07-order-service/app/models.py` holds two table families in one `order_svc` schema: a command side (`customers`, `orders`, `order_items`, `outbox`) and a read side (`order_view`), the only table the `GET` handlers in `app/routes.py` query. `OrderView` is one row per order with `items` stored as a JSON array, because the only read shape is the whole order as the wire contract renders it, and a child table would add a join on every read. This is CQRS in its plainest form: two tables in one schema, each shaped for its job, with no second datastore.

What makes it the strongest example is when it's written. Every write path upserts `order_view` in the same local transaction as the aggregate change, not in a follow-up step and not from a consumer of the service's own event:

{% include codetabs.html langs="create_order_with_outbox_and_view: the checkout write|transition_order_status_with_view: a saga reaction's write" %}

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

Both functions commit the aggregate change and the `order_view` upsert in the one transaction Postgres's WAL already spans, the mechanism the outbox uses, reused for a projection. `create_order_with_outbox_and_view` makes three writes atomic: the `orders` and `order_items` rows, the `PENDING` view row and the `order.placed` outbox row. A reader never sees the aggregate without its view row, and the relay never publishes an event for an order that didn't persist.

`transition_order_status_with_view` applies the same rule to all four saga reactions (`handle_payment_captured`, `handle_payment_declined`, `handle_shipment_dispatched`, `handle_shipment_failed`). Its conditional `UPDATE ... WHERE status = expected_status` is the idempotency backstop: only one of two concurrent deliveries can satisfy it. The `order_view` upsert after it, in the same transaction, keeps the read model from lagging a transition that already committed.

{% include excalidraw.html file="order-cqrs-write-read-split" alt="The CQRS command and query split inside order-service: the command path reserves over gRPC outside any local transaction, then persists the write aggregate, the order_view projection and the order.placed outbox row in one transaction; the query path reads order_view exclusively and never the write tables" caption="Figure 21.1: One write aggregate and one projection, upserted in the same transaction as every mutation." %}

### Read-your-writes within a service, not across a saga

Because the upsert commits with the write, a `GET /api/orders/{id}` issued right after `POST /api/orders` returns `202` sees the new `PENDING` row with no polling and no lag. That is read-your-writes consistency. `get_order_view_by_id` and `list_order_views` are the only query functions the `GET` handlers call, and the write-model classes `Order` and `OrderItem` are never imported in `app/routes.py`.

It doesn't extend across the saga that resolves the order. A client polling after checkout observes `PENDING`, then `AWAITING_SHIPMENT`, then `CONFIRMED`, each a committed intermediate state, and `CONFIRMED` is only as fresh as the `shipment.dispatched` event that drives `handle_shipment_dispatched`. `order_view` closes the distance between a write and its own service's read to zero and closes nothing else.

### Prove the projection: the disabled negative

A read path that fell back to `orders` and `order_items` whenever the projection lagged would hide a broken projection completely. The order-service contract run in `tooling/newman/` disables the projection: the `await _upsert_order_view(session, order, items)` call inside `transition_order_status_with_view` was commented out, so the aggregate still transitions and only the projection stops. After a restart, the happy-path scenario ran alone:

```
1. AssertionError  Order reaches terminal status CONFIRMED within the bounded-wait budget (40 x 750ms, attempt 40/40)
                   expected 'PENDING' to deeply equal 'CONFIRMED'
```

`GET /api/orders/{id}` never saw the transition that succeeded on the write side. The poll exhausted its 40-attempt budget and failed: 1 of 53 assertions failed, newman exit 1. Restoring the line produced 0 failed, exit 0. A projection that can't be shown to break the read path when removed hasn't been shown to do anything.

{% include excalidraw.html file="order-view-rebuildable-projection" alt="Aggregate feeds a projection which feeds the view in normal operation; rebuild_order_view recomputes the view from the current aggregate at any time; the projection-disabled negative shows the read path going stale instead of falling back to the aggregate" caption="Figure 21.2: A rebuildable read model, and the projection-disabled negative that proves the read path never falls back." %}

### Rebuildable, not a second source of truth

`order_view` is always recomputable from the aggregate. `app/repository.py::rebuild_order_view` reads the current `Order` and `OrderItem` rows and calls the same `_upsert_order_view` helper every write path calls. `app/service.py::rebuild_order_view` wraps it as an operational entry point, and the projection-disabled check reuses it to restore the view afterward. The `OrderView` docstring puts it this way: the table is "a cache of the aggregate's shape for reads, never a second source of truth." A corrupted or lost `order_view` is fixed by one function call, never a data-loss incident, because the aggregate tables are the only place a fact about an order is decided.

### Notification was already a read model

The monolith's checkout, the write side, decides whether an order is valid and commits ordinary relational rows. Notification is a second, independently stored model with its own `notification` schema and `Notification` table, built for one query: "what has this customer been told, and when." It consumes `order.placed` from the outbox-fed topic, applies a check-then-insert guard backed by a unique index, and writes one row recording a fact the write side already decided. It can't reject a checkout. It is what Kleppmann calls a materialized view: a derived answer kept current by folding in new facts, rebuildable from the source topic, never a source of truth.

The two differ on the axis CQRS leaves open:

| | `notification` | `order_view` |
|---|---|---|
| Fed by | An asynchronous consumer of a topic | A method call in the write transaction |
| Owned by | A different service than the writer | The same service as the writer |
| Consistency | Eventual | Read-your-writes |
| Rebuilt from | The topic, within its retention window | The aggregate, on demand |

Both are CQRS, and each service chose the point on the spectrum that fits.

## Pattern: Event Sourcing (declined)

CQRS separates the model you write from the model you read. Event sourcing is stronger and concerns the write side: don't store current state as mutable rows. Store the append-only sequence of events that produced it as the only system of record, and compute current state by replay.

This system doesn't do that. `Order` in `07-order-service/app/models.py` is a mutable row with a `status` column changed by an ordinary `UPDATE`. There is no event store and no code that rebuilds an order by folding past events. What it has is CQRS with an outbox event log: the outbox and `order_view` let other things react to what the write side already decided, without redefining the write side as a log.

Event sourcing commits a team to costs a mutable-row system doesn't have:

| Cost | What it means |
|---|---|
| Schema evolution | Every event type is versioned forever, and a consumer written years from now must still read `order.placed` v1 |
| Snapshots | A strategy to bound replay cost as history grows |
| Tooling and familiarity | Event stores, replay and upcasting that most teams don't have on day one |

Every read model here needs "current state, derived from recent facts," not "replay this aggregate's history to reconstruct an arbitrary past point," which is the question event sourcing answers well. The event payloads (`order.placed`, `payment.captured` and the rest) stay JSON on the wire, versioned by convention. A schema registry with compatibility enforcement (Avro, Apicurio) addresses a different problem: keeping independently deployed consumers safe when a producer's event shape changes.

> **ADLC in Action**
>
> The plan held this material back until the right artifact existed. Teaching CQRS against Notification's topic-fed read model would have shown half the pattern. The stronger example is a projection written in the same transaction as its aggregate, with a negative check that the read path never falls back to the write tables, and that didn't exist until `07-order-service` did. The projection-disabled run above is that artifact, exercised against live code in the order-service contract run.

> **Decision**
>
> Add a read model when reads and writes need different shapes or scale, and project it in the write transaction when the owning service needs read-your-writes. Choose event sourcing only when the question is "what was the state at time T," because the schema evolution, snapshot and tooling costs never go away.

> **🤖 Explore with your agent**
>
> "In examples/07-order-service/app/repository.py, add a new status transition for a cancelled order using `transition_order_status_with_view` so the `order_view` row is upserted in the same transaction as the `orders` update, with the conditional `WHERE status = expected_status` guard. Then show `GET /api/orders/{id}` returns the new status right after the write."
>
> Check: `uv run pytest -m "not integration"` in examples/07-order-service passes, and removing the `_upsert_order_view` call from your new function makes the read return the old status.

## Build, run, observe

`07-order-service` needs a migrated Postgres. From its directory:

```bash
cd examples/07-order-service
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8088
uv run pytest -m "not integration"
uv run pytest -m integration
```

The integration marker uses Testcontainers for Kafka and Postgres plus an in-process fake gRPC inventory server. `bash demos/demo-final-topology.sh` runs the whole topology.

Experiments:

- Comment out the `_upsert_order_view` call in `transition_order_status_with_view`, restart, and run the happy-path scenario. The order stays `PENDING` and the bounded-wait poll fails after 40 attempts.
- Call `rebuild_order_view` for an order. The view row is recomputed from the aggregate and matches what the write path produced.

## For deeper coverage

- Martin Fowler, "CQRS" and "Event Sourcing" on martinfowler.com.
- Martin Kleppmann, *Designing Data-Intensive Applications*: derived data, materialized views and event sourcing.
- Chris Richardson, *Microservices Patterns*: CQRS and Event Sourcing.
