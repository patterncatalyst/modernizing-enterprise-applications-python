---
title: "The Deliberate Smells"
order: 9
part: "The Reference Monolith"
description: "The coupling, god-service, shared-schema and transaction-scope smells planted in the reference monolith, each tagged in code to the extraction that cures it."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- Find every `SMELL` tag in the monolith with one `grep` and map each of the seven smells to its cure.
- Explain a seam as a boundary the implementation currently welds shut, not an arbitrary place to split code.
- Diagnose the shared-schema smell and say why cross-context foreign keys stay invisible until a migration in one app breaks a query in another.
- Diagnose the god `place_order()` function with the "describe it in one sentence without 'and'" test, and say why only removing other contexts' direct calls cures it.
- Explain why one `transaction.atomic()` across five contexts is correct only while they share a Postgres instance, and name what replaces it (sagas) once they don't.
- Name the pattern that cures the synchronous-notification and dual-write smells: a transactional outbox plus an idempotent consumer.

## Why this matters

The monolith is a defensible "before." Read a second time, it has seven smells planted by design, each tagged in code with a comment of the form `# SMELL[ch.NN]: ...` that names the cure. None is a bug. Each is the ordinary way to write the code inside one process with one shared database, and naming them now gives every later extraction a target.

```sh
grep -rn 'SMELL\[ch\.' examples/00-monolith
```

{% include excalidraw.html file="smell-map" alt="Map of the monolith's seven deliberate smells, each pointing from its planted location to the extraction that cures it" caption="Figure 9.1: Seven smells, each mapped to its cure" %}

## Pattern: Seam

Martin Fowler defines a seam as a place where behavior can change without editing the code at that spot. Every smell below sits on one: where a context's logic butts against another context's, or against infrastructure it doesn't own. A seam doesn't announce itself while the system is small. It looks like the normal way to write the code. Tagging it turns it into a smell with an address that `grep` can find and a named cure.

## Smell 1: the god checkout service

**Where:** `order/services.py::place_order()`
**Cure:** the order extraction, last and hardest by design

`place_order()` is the single orchestration point for checkout. It reaches directly into the services and models of inventory, payment, shipping and notification instead of calling independently deployable collaborators over a stable contract:

```python
# SMELL[ch.26]: reaching directly into inventory's services/model
# layer from the order context, with no anti-corruption layer at the
# seam -- the same shape as a monolith's `OrderService`
# calling straight into `InventoryService`.
for line in items:
    inventory_item = inventory_services.get_by_sku(line["sku"])
    inventory_services.reserve(line["sku"], line["quantity"])
    ...
```

Order goes last because each earlier extraction removes one of this function's direct dependencies. When order's turn comes, inventory, payment, shipping and notification are gone and it is the only thing left reaching into empty air.

The cure isn't cleaner code inside `place_order()`. The function is short, readable and does what it says. The smell is that its correctness depends on four other contexts' internals being reachable in the same call stack. A review of the function in isolation finds nothing wrong, which is why this coupling survives so many reviews.

## Smell 2: one ACID transaction across six contexts

**Where:** the `transaction.atomic()` block in `order/services.py::place_order`
**Cure:** moving from ACID to ACD, then choreographed and orchestrated sagas

The whole checkout body runs inside one block, and a failure anywhere unwinds every write in every context:

```python
with transaction.atomic():
    order = Order.objects.create(...)
    inventory_services.reserve(...)
    payment_services.charge(...)
    shipping_services.dispatch(...)
    _write_order_placed_outbox_event(...)
```

That rollback is a gift of one shared Postgres instance. When any context gets its own database, it stops happening, and has to be rebuilt as a saga with compensating actions for everything already committed. Two deterministic sentinels show the rollback is real:

- A `paymentMethod` of `CARD-DECLINE` returns `402 PAYMENT_DECLINED`, and the reservation made earlier in the request is rolled back, leaving stock net-zero.
- A `shippingAddress` containing `SHIP-FAIL` returns `422 SHIPPING_FAILED`, and the whole checkout unwinds: reservation, order row and payment capture.

## Smell 3: one shared schema for all six apps

**Where:** `config/settings.py` (`INSTALLED_APPS`, `DATABASES`) and every model's `db_table`
**Cure:** shared data to owned data

One Postgres schema and one Django migration history mean all six contexts migrate and deploy together. A change to `inventory` and a change to `payment` land in the same `manage.py migrate` whether or not the two meant to ship together. `config/settings.py` says so above `INSTALLED_APPS`: "all six bounded contexts ... are Django apps in ONE project, sharing ONE Postgres schema ... and migrating together."

The cost is easy to underrate because no single day looks expensive. Adding a column to `reviews` is a one-line migration, same as in a separate schema. The expense is a rate limit on how independently any context can change: every migration against this database is one every other context's deploy has to tolerate, whether or not its code changed. The destination is each context owning its own schema outright, and "owned" doesn't have to mean a separate physical database on day one.

## Smell 4: cross-context foreign keys

**Where:** every cross-app `ForeignKey` (see each app's `models.py`)
**Cure:** shared data to owned data, then a change-data-capture backfill and decommission

`order.Order.customer`, `order.OrderItem.inventory_item` (in its original shape), `payment.Payment.order`, `shipping.Shipment.order`, `notification.Notification.customer` and `.order`, and `review.Review.customer` and `.inventory_item` all cross context boundaries inside the shared schema. Each is an idiomatic Django relation and a decision in waiting: an owned copy, a field replicated through change data capture, or a soft reference carried in an event.

`OrderItem` shows the cure once. It originally held a live `ForeignKey` onto `inventory.InventoryItem`, so reading an order's lines joined into inventory's table on every request. The inventory extraction replaced the join with a denormalized snapshot (`sku`, `item_name`, `unit_price_cents`) captured at checkout. A later price change in inventory can no longer rewrite a historical order line; the repo's regression test changes an item's price after an order exists and asserts the existing line is untouched. The other five keys are still live joins at the state described here.

## Smell 5: synchronous notification inside the checkout transaction (cured)

**Where:** `order/services.py::place_order`, which now writes an `OutboxEvent`
**Cure:** the notification extraction, with a transactional outbox and an async consumer

The original `place_order()` called `notification/services.py::send_order_confirmation()` inside the same `transaction.atomic()` as the rest of checkout. Checkout latency was coupled to however long "sending" took, and a failure there rolled back the order. That call is gone. `place_order()` writes an `order.placed` row in the same transaction and returns:

```python
OutboxEvent.objects.create(
    aggregate_type="order",
    aggregate_id=str(order.id),
    event_type="order.placed",
    payload=payload,
)
```

## Smell 6: the dual-write hazard (cured)

**Where:** `notification/services.py::record_order_placed`, replacing `send_order_confirmation` and `_dispatch_via_external_provider`
**Cure:** the transactional outbox

The old `send_order_confirmation()` made two writes to two systems with no shared transaction: a `Notification` row, atomic with checkout, and a call to a stand-in external provider. A crash between them loses the notification silently, and a naive retry can duplicate it. The cure makes the outbox write the only thing inside the local transaction. A separate process, `common.management.commands.outbox_relay`, reads the outbox and publishes to Kafka at least once, stamping `published_at` after a successful send. `notification.management.commands.order_placed_consumer` consumes that topic and calls `record_order_placed()`, which is idempotent: a check-then-create backed by a partial unique constraint on `order`, so a redelivered event creates one `Notification`, never two.

Because the outbox write is inside the same transaction, it rides along with the free rollback. The happy path leaves one `order.placed` row, and a `DECLINE` or `SHIP-FAIL` checkout leaves none.

## Smell 7: review tangled into shared security

**Where:** `review/views.py::ReviewListCreateView`
**Cure:** the review extraction, the first context pulled out

`review/models.py` states that review has no runtime dependency on order, inventory, payment, shipping or notification. Yet `POST /api/reviews` is gated by Basic auth against the monolith's own `django.contrib.auth` `auth_user` table, the shared-security surface any other context would reach for:

```python
# SMELL[ch.15]: POST is gated by HTTP Basic auth against THIS module's
# shared `django.contrib.auth` `auth_user` table ... the same shared-
# security surface every other context in this monolith would reach for
# if it needed auth.
authentication_classes = [BasicAuthentication]
```

`GET /api/reviews` and `GET /api/reviews/{id}` stay open, and only the write is gated, per view. The contract is `401` unauthenticated and `201` authenticated. After extraction, review has its own auth configuration and no longer touches this table.

This is the existence proof that "tag it, name the cure, extract it" survives a real codebase. Review is cheap to cure because it was always the least-coupled context: no synchronous collaborator to disentangle, no saga to build, only an auth gate to re-home onto a service with its own user store. The extracted service's `uv run pytest` passes 11/11 against a throwaway Postgres container, and the same unedited Newman collection stays green re-pointed at the new service's address.

## The smell table

| # | Smell | Cure | Status |
|---|---|---|---|
| 1 | God checkout service | Order extraction | open |
| 2 | One ACID transaction across six contexts | ACID to ACD, sagas | open |
| 3 | Shared single schema | Shared data to owned data | open |
| 4 | Cross-context foreign keys | Owned data, CDC backfill | open |
| 5 | Synchronous notification in checkout | Outbox, notification extraction | **cured** |
| 6 | Dual-write hazard | Transactional outbox | **cured** |
| 7 | Review and shared-auth coupling | Review extraction | open |

"Open" means not yet cured, not undiscovered: every smell is named, tagged and pointed at its cure. Smells 5 and 6 were cured inside the still-whole monolith, by building the outbox and an idempotent consumer before notification became a service. Curing a smell and extracting a context are different moves, and the first can happen before the second.

## Why "deliberate" matters

None of this is bad code. `place_order()` calling four contexts directly is the most natural checkout in one process: no network separates `order` from `inventory`, so nobody writes a contract. One `transaction.atomic()` over five contexts is the natural way to get correctness, because Postgres gives it away. A shared schema is the natural way to model a domain with this many cross-references, because the ORM makes each join a one-line `ForeignKey`. The smells need no careless engineer, only one condition: everything in one process, talking to one database. Each extraction removes that condition for one context and forces exactly one smell into the open.

> **Decision**
>
> Tag a smell when the code is correct only because everything shares one process and one database. Cure it by changing the condition (extract the context, give it its own data), never by cleaning up the code at the tag.

> **🤖 Explore with your agent**
>
> "Run `grep -rn 'SMELL\[ch\.' examples/00-monolith` and group the hits by smell number. For smell 4, list every cross-app `ForeignKey` in `examples/00-monolith/*/models.py` and propose, for each one, whether it should become an owned copy, a CDC-replicated field or an event-carried reference, with a one-line reason."
>
> Check: the reply lists seven cross-context keys, the `SMELLS.md` smell 4 list minus `OrderItem.inventory_item`, and names `OrderItem` as the one already cured with a snapshot.

## Build, run, observe

Find the tags, then run the checkout behaviors:

```sh
grep -rn 'SMELL\[ch\.' examples/00-monolith
cd examples/00-monolith && uv run pytest
```

Four checkout behaviors, triggered by sentinels in the request body, make smells 1 and 2 observable. The same four are exercised from outside the process by the Scenario 1 to 4 folders of `tooling/newman/mea.postman_collection.json`.

| Request | Response | Side effects |
|---|---|---|
| Happy path | `201 Created`, `Location: /api/orders/{id}`, `status: CONFIRMED` | one `order.placed` outbox row |
| Line exceeds `quantityOnHand` | `409 Conflict`, `OUT_OF_STOCK` | raised before any write |
| `paymentMethod` containing `DECLINE` (case-insensitive) | `402 Payment Required`, `PAYMENT_DECLINED` | reservation rolled back, stock net-zero, no outbox row |
| `shippingAddress` containing `SHIP-FAIL` (case-insensitive) | `422 Unprocessable Entity`, `SHIPPING_FAILED` | reservation, order row and payment all rolled back, no outbox row |

The rollback in the last two rows is free today and is what gets expensive once a context has its own database. Experiments:

- Send an over-ordered line: no order row and no outbox row exist afterward.
- Send a `DECLINE` checkout and query stock for the SKU: it matches its value before the request.

## For deeper coverage

`examples/00-monolith/SMELLS.md` has the full table with each smell's recorded status, and `tooling/newman/GOLDEN-BASELINE.md` has the baseline runs that later extractions were held to.
