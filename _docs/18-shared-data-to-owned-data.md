---
title: "From Shared Data to Owned Data"
order: 18
part: "Data Across the Seam"
description: "Shared-database coupling is the hardest coupling to break. Database-per-service trades referential integrity for independence, and the OrderItem foreign key becoming a snapshot is the concrete move that makes inventory extractable."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why a shared database is harder to break than any code-level smell: a foreign key is a dependency Postgres enforces, not one application code declares.
- Weigh what database-per-service buys (independent migrations, independent scaling, an uncontested row lock) against what it costs (referential integrity becomes a contract kept by agreement).
- Replace a cross-context foreign key with a snapshot using an add, backfill, drop migration that never loses data.
- Treat duplicated data across a service boundary as a deliberate choice, and name its cost.
- Choose between shared tables, an owned schema from day one, and an owned schema fed by a one-time backfill, using the two-writer argument.

## Why this matters

The extractions so far deferred the same question. `examples/02-review-service` reads and writes the monolith's own Postgres tables, database-per-service with no database-per-service yet. `examples/03-notification-service` was new enough to never share anything: its schema was owned and migrated from its first commit. Neither had to take a table away from a context that was still using it.

The inventory extraction does. The reasoning has to land first: why a shared schema is the hardest coupling, what owning data buys, and the mechanical move, `order.OrderItem`'s foreign key becoming a snapshot, that the codebase had to make.

## Why a shared database is the hardest coupling to break

`examples/00-monolith/SMELLS.md` planted the smell and has carried it open:

> **#3: Shared single schema/DB for all six apps**: one Postgres schema, one set of Django migrations, all six bounded contexts migrate and deploy together.

> **#4: Cross-context foreign keys**: `order.Order.customer`, `order.OrderItem.inventory_item`, `payment.Payment.order`, `shipping.Shipment.order`, `notification.Notification.customer`/`.order`, `review.Review.customer`/`.inventory_item` are all direct FKs crossing bounded-context boundaries in the one shared schema.

The other smells (the god checkout service, the one ACID transaction spanning six contexts, review's tangled auth) are cured by moving code: a new process, a new endpoint, a flag that decides who answers. Smells #3 and #4 differ in kind. The database itself enforces a foreign key. While `order_items.inventory_item_id` exists, Postgres rejects deleting an `inventory_items` row that order lines still reference, and every query that needs a line's current name or price joins across what would be two services' schemas.

Review worked because it never had to answer this: its `app/models.py` maps onto the monolith's tables. That deferral was documented, and it comes due for the context that has to give up a table it still has writers for.

{% include excalidraw.html file="shared-data-vs-owned-data" alt="Three stacked panels: Review stays on the monolith's shared schema (a named deferral), Notification owns its schema from day one (async seam), and Inventory owns its schema too but needs a one-time transaction-log backfill from the still-live monolith table during the cutover window" caption="Figure 18.1: The three data-ownership postures, in the order they were built" %}

A strangler proxy can intercept an HTTP path because requests are what it sits between. Nothing sits between two services and a table. Either exactly one process owns the writes to `inventory_items`, or two processes race on the same rows with no shared transaction to arbitrate. That isn't a degraded database-per-service. It is the shared-database anti-pattern with extra steps.

## Pattern: Database per Service

Database-per-service has a cost the project has already paid. notification-service's `app/models.py` keeps `customer_id` and `order_id` as plain `BIGINT` columns, not foreign keys, because "this service's schema must not reach across into tables it does not own." `examples/04-inventory-service` does the same for `inventory_items`. Giving up the foreign key gives up the database's referential-integrity guarantee at that boundary. Nothing in Postgres stops a customer id from being deleted on one side while the other still references it. The sides agree on that invariant by contract, such as a frozen event shape or a versioned proto.

| Axis | Shared schema | Owned schema |
| --- | --- | --- |
| Migrations | One Django migration history, deployed together | Inventory's Alembic migrations run without coordinating an order release |
| Storage | One Postgres schema | Re-index, re-shard or move to another instance without anyone outside noticing |
| Row lock | A lock in one context says nothing about another context's query on the same row | `Reserve` and `Release` take a row-level write lock for one `UPDATE` with no second writer |
| Integrity | Enforced by foreign keys | Kept by a contract both sides honor |

The trade is the move from an implicit contract (whatever shape the shared schema has today) to an explicit one (a proto, an event, a REST response shape). Every ACL is the cost of that explicitness, paid once per seam, in exchange for never needing a cross-schema join again.

### The shortcut: a read replica

A team under deadline reaches first for a read replica of the monolith's `public.inventory_items`. It works for the read surface: `GET /api/inventory` and `GET /api/inventory/{sku}` need only an eventually consistent copy, and logical replication provides one. It does nothing for the write surface. `Reserve` is a single atomic, concurrency-safe conditional `UPDATE` against a row one service alone writes, and a replica is read-only. Writing through to the monolith's primary from a second service is the two-writers split-brain, moved one layer down.

A replica answers a question inventory wasn't asking and leaves the real one, who owns the write, open. The transition mechanism is a change-data-capture backfill that looks like a replica but is scoped as transition-only. Once inventory's own schema is the write path, the replicated copy is retired instead of kept as a permanent read path nobody owns.

## From foreign key to snapshot

The clearest instance in this codebase is `order.OrderItem.inventory_item`, smell #4's own example. Before the inventory extraction, `order/models.py::OrderItem` held a live foreign key into `inventory.InventoryItem`:

{% include codetabs.html langs="Before: live FK (SMELL[ch.18])|After: denormalized snapshot" %}

```python
# order/models.py -- BEFORE (the cross-context FK this project planted
# deliberately, SMELL #4)
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    inventory_item = models.ForeignKey("inventory.InventoryItem", on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()
```

```python
# order/models.py -- AFTER (the shipped code)
class OrderItem(models.Model):
    """SMELL[ch.18] CURED here -- sku/item_name are now a denormalized
    SNAPSHOT captured once at checkout time, a plain soft string reference
    with no database FK and no cross-app join. Because the price is
    captured at order time, a later price change in inventory never
    retroactively rewrites a historical order line -- the correct
    semantics for a read model regardless of which mode wrote it."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", db_column="order_id"
    )
    sku = models.CharField(max_length=64)
    item_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()
```

Two string columns replace one foreign key. With the FK, "what did this line cost" means joining into `inventory_items` and reading its current `price_cents`. That is wrong the moment the price changes after the order shipped, and impossible once `inventory_items` lives in another service's database. With the snapshot, `unit_price_cents` is the price when the line was reserved, captured once. The process can always answer locally, whichever mode (`local` or `grpc`) wrote the row.

`order/migrations/0002_orderitem_sku_snapshot.py` cuts the key in the only order that can't lose data:

```python
# order/migrations/0002_orderitem_sku_snapshot.py
def backfill_sku_and_item_name(apps, schema_editor):
    OrderItem = apps.get_model("order", "OrderItem")
    for item in OrderItem.objects.select_related("inventory_item").all():
        item.sku = item.inventory_item.sku
        item.item_name = item.inventory_item.name
        item.save(update_fields=["sku", "item_name"])


class Migration(migrations.Migration):
    operations = [
        migrations.AddField(model_name="orderitem", name="sku", ...),
        migrations.AddField(model_name="orderitem", name="item_name", ...),
        migrations.RunPython(backfill_sku_and_item_name, migrations.RunPython.noop),
        migrations.RemoveField(model_name="orderitem", name="inventory_item"),
    ]
```

**Add, then backfill, then drop.** Adding the columns first with a safe default makes every existing row valid at once. Backfilling while the FK is live lets `select_related("inventory_item")` still do the join, which is the migration's only chance to read `inventory_item.sku` and `.name`. Dropping the key last means nothing ever sees a row whose snapshot columns exist but are unpopulated. Drop first and the backfill has nothing left to read. The same shape appears in the CDC path (`scripts/register-debezium.sh`): copy one fact out of the field a boundary is about to put away.

{% include excalidraw.html file="orderitem-fk-to-snapshot" alt="Before and after OrderItem's relationship to InventoryItem: a live FK requiring a join versus a denormalized sku/item_name/unit_price_cents snapshot with no FK, plus the three-step add-backfill-drop migration sequence" caption="Figure 18.2: From foreign key to snapshot, the denormalization move" %}

## Duplication as a considered choice

`OrderItem.sku` and `.item_name` now duplicate `inventory.InventoryItem.sku` and `.name`. In one shared database that is a normalization bug. Across a service boundary it is correct, and the difference is precise. The FK version had one fact with one home, read through a join. The snapshot version has two facts that start out equal: inventory's current name and price, and the order's name and price at the moment of purchase. They are allowed, even expected, to diverge. Renaming an item in the catalog must not rewrite last month's invoices.

Notification's plain `BIGINT` columns follow the same reasoning: when two contexts meet over a stable contract instead of a shared table, each side's copy of a fact is scoped to what that side needs it for. Querying inventory live for every historical order line would couple order's read path to inventory's availability for data that never changes after the order is placed.

The cost is real. Two copies of "what did this sku cost" are two places a schema change must land. If `InventoryItem.price_cents` gains a currency field, `OrderItem.unit_price_cents` doesn't inherit the decision, and nobody is forced to notice until a report sums amounts across both tables. The FK made that inconsistency impossible by construction. The snapshot makes it possible and relies on each side's contracts and tests to keep the shapes aligned. That is the price of independence, and it is still right here, because the alternative is a live join across a boundary that is about to become a network call.

## Read models fed by events

The snapshot is the first example of a read model populated by something other than a live query against the system of record. `OrderItem`'s snapshot is filled once, synchronously, at the write that creates it. The same shape works asynchronously. notification-service's `Notification` rows are built entirely from the `order.placed` payload, consumed once and queried locally afterward. The inventory service's transition-only CDC consumer is the same again, with Debezium's change stream standing in for a domain event.

The idea is to own your data and keep it current by consuming a fact someone else already decided was true, instead of reaching into their database to ask. The general case, where a read model is rebuilt from an append-only event log, is event sourcing and CQRS.

## Three postures

Each extraction took a different position on data ownership, for reasons specific to its seam:

| Extraction | Data posture | Why |
|---|---|---|
| Review | **Shared**: reads and writes the monolith's tables directly, no ACL at this seam | A named deferral: proving the extraction mechanism came first |
| Notification | **Owned from day one**: its own Alembic-migrated `notification` schema, no monolith import | The seam is asynchronous; a second uncoordinated writer to a shared table is a split-brain |
| Inventory | **Owned, reached via a one-time transaction-log backfill** | A synchronous seam (checkout needs stock availability right now) on top of data the monolith was still writing |

Review's deferral stays a named open item in `examples/02-review-service/MIGRATION.md`. Notification could start clean because nothing pre-existed to migrate. Inventory is neither: `inventory_items` has real rows, real foreign keys pointing at it, and a checkout path that needs a correct stock answer on every order. The extraction has to own the data without losing a committed reservation during the transition.

## Planning the split

Four problems have to be solved together for the inventory extraction to be correct and reversible:

1. **Give inventory its own schema and seed.** The notification posture: an Alembic-migrated `inventory` schema, independently seeded, with no foreign key back into the monolith's tables.
2. **Move `reserve` and `release` across a network boundary.** Reviews and notifications moved one direction of traffic (reads, or a one-way event). `Reserve` is a synchronous, stock-affecting write that checkout can't proceed without, and `Release` is the explicit compensating action for a write that a local transaction can no longer roll back automatically.
3. **Bridge "the monolith owns `inventory_items`" and "inventory owns its copy"** without losing or duplicating a reservation. A one-time, then-retired transaction-log backfill does this, using Debezium to tail Postgres's write-ahead log.
4. **Cut `OrderItem.inventory_item`'s foreign key**, as in the migration above, so `order`'s schema stops depending on a table that is about to leave its database.

> **Decision**
>
> Replace a cross-context foreign key with a snapshot when the referenced table is leaving your database and the copied fact is historical. Give the service that writes a table sole ownership of it; use a transition-only backfill, not a permanent replica, while writers move.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith`, list every remaining cross-context foreign key from SMELLS.md #4 (`payment.Payment.order`, `shipping.Shipment.order`, `notification.Notification.customer`) and draft an add, backfill, drop migration for `shipping.Shipment.order` that snapshots the order id and customer email, without running it."
>
> Check: read the proposed migration and confirm `RunPython` comes after the `AddField` operations and before `RemoveField`.

## Build, run, observe

Nothing new runs here; the code is the migration and models already in `examples/00-monolith`.

```bash
cd examples/00-monolith
uv run python manage.py migrate order
uv run python manage.py sqlmigrate order 0002
```

`migrate order` applies the add, backfill, drop sequence. `sqlmigrate` prints it in that order: two `ADD COLUMN` statements, a "Raw Python operation" placeholder for the backfill, then `DROP COLUMN "inventory_item_id"`. After it, `order_items` has `sku` and `item_name` columns and no `inventory_item_id`.

- Reorder `0002_orderitem_sku_snapshot.py` so `RemoveField` runs before `RunPython`: the backfill has no `inventory_item` left to read from.
