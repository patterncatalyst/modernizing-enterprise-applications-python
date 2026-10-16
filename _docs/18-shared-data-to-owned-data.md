---
title: "From Shared Data to Owned Data"
order: 18
part: "Data Across the Seam"
description: "Shared-database coupling as the hardest coupling to break; the database-per-service tradeoff; the FK-to-snapshot move on order_items; data duplication as a deliberate choice; planning the split ch.19 executes."
duration: 30 minutes
---

Every extraction this book has built so far has quietly deferred the same
question. `examples/02-review-service` (ch.15) reads and writes the
monolith's own shared Postgres tables directly — a database-per-service
pattern with no database-per-service yet. `examples/03-notification-service`
(ch.17) sidesteps the question by being new enough to never have shared
anything: its schema was created, owned, and migrated from its very first
commit. Neither extraction had to *take* a table away from a context that
was still using it. ch.19's Inventory extraction does, and this chapter is
the reasoning that has to land before that cut makes sense: why a shared
schema is coupling of the hardest kind, what a service actually buys by
owning its data outright, and the specific, mechanical move —
`order.OrderItem`'s foreign key becoming a snapshot — that this book's own
codebase had to make to get there.

## Why shared-database coupling is the hardest coupling to break

`examples/00-monolith/SMELLS.md` planted this smell in r01 and has carried it
open ever since:

> **#3 — Shared single schema/DB for all six apps** — one Postgres schema,
> one set of Django migrations, all six bounded contexts migrate and deploy
> together.

> **#4 — Cross-context foreign keys** — `order.Order.customer`,
> `order.OrderItem.inventory_item`, `payment.Payment.order`,
> `shipping.Shipment.order`, `notification.Notification.customer`/`.order`,
> `review.Review.customer`/`.inventory_item` are all direct FKs crossing
> bounded-context boundaries in the one shared schema.

Every other smell this project named — the god checkout service (#1), the
one ACID transaction spanning six contexts (#2), review's tangled shared
auth (#7) — can be cured by moving *code*: stand up a new process, give it
its own endpoint, flip a flag that decides who answers a request. Smells #3
and #4 are different in kind, not degree. A foreign key is not a coupling
you can route around; it is a coupling the *database itself enforces*. As
long as `order_items.inventory_item_id` exists, Postgres will reject any
attempt to delete an `inventory_items` row that order lines still reference,
and every `SELECT` that needs a line's current name or price has to join
across what would otherwise be two services' schemas. Review's extraction
(ch.15) worked precisely because it never had to answer this question —
`examples/02-review-service`'s own `app/models.py` maps onto the monolith's
tables because ch.15's whole point was proving the extraction *mechanism*
(capture the contract, stand up the service, flip the flag) without also
solving a distributed-data problem in the same chapter. That deferral was
documented at the time it was made, and this chapter is where it comes due
for the context that needs to actually give up a table it still has writers
for.

{% include excalidraw.html file="shared-data-vs-owned-data" alt="Three stacked panels: Review stays on the monolith's shared schema (a named deferral), Notification owns its schema from day one (async seam), and Inventory owns its schema too but needs a one-time transaction-log backfill from the still-live monolith table during the cutover window" caption="Figure 18.1 — The three data-ownership postures this book builds, in the order they were built" %}

The reason shared-database coupling resists the same strangler-fig treatment
every other seam in this book has used is structural: a strangler proxy can
intercept an HTTP path and decide who answers it because HTTP requests are
the thing the proxy sits between. There is no equivalent place to sit between
two services and a *table*. Either exactly one process owns the writes to
`inventory_items`, or two processes race on the same rows with no shared
transaction to arbitrate between them — the same split-brain risk ch.17
named for Notification's async seam, except now the two writers are not
"the monolith's consumer and this service's consumer reading the same
topic," they would be two independent processes issuing `UPDATE` statements
against the identical row with no coordination at all. That is not a
degraded version of database-per-service; it is the shared-database anti-
pattern with extra steps.

## The database-per-service tradeoff: what you buy, what you give up

Database-per-service is not free, and this book has already paid some of
its cost without naming it as such. `examples/03-notification-service`'s
`app/models.py` docstring states the policy directly: `customer_id`/
`order_id` are plain `BIGINT` columns, **not** foreign keys into the
monolith's `customers`/`orders` tables, because "this service's schema must
not reach across into tables it does not own." `examples/04-inventory-
service`'s `app/models.py` says the identical thing about `inventory_items`
having no FK back into the monolith. Giving up the foreign key means giving
up the database's own referential-integrity guarantee at that boundary —
nothing in Postgres stops a customer id from being deleted on one side while
still referenced on the other; the two sides now have to *agree* on that
invariant by contract (a frozen event shape, a versioned proto) rather than
have the database enforce it for them.

What that buys back is independence along every axis a shared schema
forecloses: Inventory's Alembic migrations can run without coordinating a
release with order's Django migrations; Inventory's table can be re-indexed,
re-sharded, or moved to a different Postgres instance entirely without
anyone outside that service noticing; and — the specific property ch.19
needs — Inventory's `Reserve`/`Release` RPCs can take a Postgres row-level
write lock for the duration of a single `UPDATE` statement and know that
lock is uncontested by any writer this service doesn't control, because
there is no second writer. A shared schema can't make that last guarantee
at all: a pessimistic lock taken by one context's query says nothing about
whether a different context's query, against the same row, is waiting
behind it or working around it.

The tradeoff has a name in the literature this book has already cited
(ch.13's Khononov reference): this is the move from an *implicit* contract
(whatever shape the shared schema happens to have today) to an *explicit*
one (a proto, an event, a REST response shape) that both sides have to keep
honoring by agreement, not by database constraint. Every ACL this book has built — ch.16's `OrderPlacedEvent`
translator, ch.19's proto wire vocabulary — is the cost of that explicitness,
paid once per seam, in exchange for never again needing a cross-schema join
to answer a question.

## The tempting shortcut: a read replica instead of an owned schema

Before accepting that Inventory needs its own schema, it's worth naming the
alternative a team under deadline pressure reaches for first: point a
read-replica connection at the monolith's `public.inventory_items` table and
call the data problem solved, without migrating anything at all. It's worth
naming specifically because it solves exactly one of Inventory's two
problems and makes the other one worse.

A read replica would, in fact, work for the **read** surface —
`GET /api/inventory`/`GET /api/inventory/{sku}` need nothing but an
eventually-consistent copy to answer correctly, and a logical-replication
subscriber is a perfectly serviceable way to get one. It does nothing at all
for the **write** surface. `Reserve`'s whole value is a single, atomic,
concurrency-safe conditional `UPDATE` against a row this service alone
writes; a read replica is, definitionally, read-only — there is no write
path through it for `Reserve` to use. A team that stopped at "replicate the
table" would still have to solve reservation some other way, and the
obvious other way (writing straight through to the monolith's primary from
a second service) is the two-writers-one-table split-brain this chapter
already ruled out, just relocated one layer down. A read replica isn't a
cheaper version of database-per-service; it's a correct answer to a
question Inventory wasn't actually asking, bought at the cost of leaving the
harder question — who owns the write — completely unaddressed. That's why
ch.19's transition mechanism (the CDC backfill) looks superficially like a
read replica but is explicitly scoped as transition-only, not an end state:
once Inventory's own schema is the write path for `Reserve`/`Release`, the
replicated copy has no further job and is retired, rather than being kept
around indefinitely as a permanent, parallel read path nobody owns.

## From foreign key to snapshot: the `OrderItem` change, concretely

The clearest instance of this tradeoff in this project's own codebase is
`order.OrderItem.inventory_item` — smell #4's own example — and ch.19's
Inventory extraction is exactly what forces it to move. Before this
project's r04 build, `order/models.py::OrderItem` carried a live foreign
key into `inventory.InventoryItem`:

{% include codetabs.html langs="Before — live FK (SMELL[ch.18])|After — denormalized snapshot" %}

```python
# order/models.py -- BEFORE (the cross-context FK this project planted
# deliberately in r01, SMELL #4)
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    inventory_item = models.ForeignKey("inventory.InventoryItem", on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()
```

```python
# order/models.py -- AFTER (r04/ch.19, this project's shipped code)
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

Reading these two side by side, the change looks small: two string columns
replace one foreign key. What that small change buys is everything ch.19
needs. With the FK, "what did this order line cost" means joining into
`inventory_items` and reading its *current* `price_cents` — which is wrong
the moment inventory's price changes after the order shipped, and which is
structurally impossible once `inventory_items` lives in a different
service's database that this process can no longer join against at the SQL
level at all. With the snapshot, `OrderItem.unit_price_cents` is the price
*at the moment this line was reserved*, captured once and never revisited —
correct history, and a query this process can always answer locally, no
matter which mode (`local` or `grpc`) wrote the row.

Cutting the FK safely is itself a small lesson in migration discipline.
`order/migrations/0002_orderitem_sku_snapshot.py` does it in the only order
that cannot lose data:

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

**Add, then backfill, then drop — never any other order.** Adding the new
columns first, with a safe default, means every existing row is valid the
instant the migration's first step completes. Backfilling *while the FK is
still live* means `select_related("inventory_item")` can still do the join
that is about to become impossible — this is the migration's only chance to
read `inventory_item.sku`/`.name` at all, because the next step removes the
column that makes that join possible. Dropping the FK last means nothing
ever observes a row where the snapshot columns exist but haven't been
populated yet. Running these steps in any other order — drop first, backfill
second — would mean the backfill has nothing left to read from: this is
precisely why `scripts/register-debezium.sh`'s CDC path and this migration's
own `RunPython` step share a shape, "copy one fact out of the field a
boundary is about to put away."

{% include excalidraw.html file="orderitem-fk-to-snapshot" alt="Before and after OrderItem's relationship to InventoryItem: a live FK requiring a join versus a denormalized sku/item_name/unit_price_cents snapshot with no FK, plus the three-step add-backfill-drop migration sequence" caption="Figure 18.2 — From foreign key to snapshot: the denormalization move, concretely" %}

## Duplication as a deliberate choice, not a lapse

`OrderItem.sku`/`.item_name` now duplicate data that also lives in
`inventory.InventoryItem.sku`/`.name` — the same fact, stored twice, in two
services with two independent schemas. In a single shared database that
would be a normalization bug a code reviewer should flag. Across a service
boundary it is the *correct* design, and the distinction is worth being
precise about: this isn't the same kind of duplication. The FK version had
one fact (`inventory_items.name`) with one home, read through a join
whenever a second context needed it. The snapshot version has two facts
that happen to start out equal — Inventory's *current* name/price, and
Order's *historical* name/price at the moment of purchase — and they are
allowed, even expected, to diverge over time. A rename in Inventory's
catalog should not rewrite last month's invoices; a denormalized snapshot
is what keeps it from doing so.

This is the same reasoning ch.17 already applied to Notification's owned
`customer_id`/`order_id` columns (plain `BIGINT`s, not FKs) and ch.16's ACL
discussion named directly: once two contexts are reached over a stable
contract instead of a shared table, each side's copy of a fact is scoped to
what *that side* needs it for, not a globally normalized source of truth
every reader has to reach into. The alternative — querying Inventory live
for every historical order's line-item details — would couple Order's read
path to Inventory's availability for data that, by definition, never
changes once the order is placed. Duplication here isn't a shortcut around
solving the coupling problem; it *is* the solution, applied at the one place
a snapshot is semantically correct rather than merely convenient.

Duplication of this kind has a real cost, and it's worth naming what that
cost is rather than presenting it as a pure win. Two copies of "what did
this sku cost" means two places a future schema change has to be considered
against: if Inventory's `InventoryItem.price_cents` ever needs a currency
field, `OrderItem.unit_price_cents` doesn't automatically inherit that
decision, and nobody is forced to notice the gap until a report tries to sum
amounts across both tables. The FK version made that inconsistency
*impossible* by construction — one column, one home, one truth. The snapshot
version makes it *possible* and relies on each side's own tests and
contracts to keep the shapes consistent independently. That's the real price of
the independence this chapter has been arguing for: fewer guarantees the
database enforces for you, more that the team has to enforce by discipline
and contract instead. Paying it is still the right call here, because the
alternative — a live join across a boundary that is about to become a
network call — is strictly worse, not because duplication is free.

## Read models fed by events: the shape ch.21 completes

The snapshot captured at checkout time is this book's first example of a
pattern it has not yet named directly: a **read model populated by
something other than a live query against the system of record**.
`OrderItem`'s sku/name/price snapshot is populated once, synchronously, at
the moment of the write that creates it — but the same shape generalizes to
read models populated *asynchronously*, from events, well after the write
that caused them. ch.17's `notification-service` already builds exactly
this: its `Notification` rows are not read through a live join against
`order`'s tables; they are built entirely from the `order.placed` event's
payload, consumed once, stored locally, and queried locally forever after.
Inventory's transition-only CDC consumer (ch.19) is the same shape again,
with Debezium's change stream standing in for a domain event: a local copy,
kept current by consuming something published elsewhere, queried without
ever reaching back across the seam.

Naming this pattern precisely — and building the general case, where a
read model's entire storage IS a rebuild from an append-only event log, rather than
backed by its own mutable table at all — is ch.21's job (event sourcing and
CQRS), not this chapter's. What matters here is recognizing that this
chapter's humble FK-to-snapshot move and ch.17's Kafka-fed `Notification`
table are the same idea at two different distances: own your data, and keep
it current by consuming a fact someone else already decided was true,
rather than reaching into their database to ask.

## The lived contrast: one schema, one deferral, one clean start

Three extractions now exist in this project, and each took a different
position on data ownership, for reasons specific to what each extraction
actually needed:

| Extraction | Data posture | Why |
|---|---|---|
| Review (ch.15) | **Shared** — reads/writes the monolith's own tables directly, no ACL at this seam | A deliberate, named deferral: ch.15's job was proving the extraction mechanism, not solving data ownership in the same chapter |
| Notification (ch.17) | **Owned from day one** — its own Alembic-migrated `notification` schema, zero monolith import | The seam is asynchronous; a second, uncoordinated writer to a shared table *is* a split-brain, not a simplification |
| Inventory (ch.19, next) | **Owned, reached via a one-time transaction-log backfill** — the hybrid this book hasn't built yet | The hardest case: a *synchronous* seam (checkout needs to know *right now* whether stock is available) layered on top of data that still has to move out of a table the monolith was still writing |

Review's deferral was correct for what ch.15 needed to prove and remains a
named, open item — `examples/02-review-service`'s own `MIGRATION.md` says
so. Notification's clean start was correct because nothing pre-existed to
migrate: `OrderPlacedConsumer` had no monolith original to lift, so there
was no live data to move, only a new schema to create. Inventory is neither
of those: `inventory_items` is a table the monolith has been writing to
since r01, with real rows, real foreign keys pointing at it, and a checkout
path that needs a correct answer to "is this in stock" on every single
order. ch.19 is the chapter that has to reconcile "own the data" with "don't
lose a single committed reservation during the transition."

## Planning the split: what ch.19 actually has to do

Four separate problems have to be solved together for Inventory's extraction
to be both correct and safely reversible, and naming them now is this
chapter's last job before ch.19 builds the answer to each:

1. **Give Inventory its own schema and its own seed.** Same posture
   Notification already established (DRQ-035/DRQ-044 in this project's
   build plan) — an Alembic-migrated `inventory` schema, created and
   independently seeded, with no foreign key reaching back into the
   monolith's tables.
2. **Move the checkout-time `reserve`/`release` concern across a real
   network boundary**, not just move a read. Review's and Notification's
   extractions each moved one direction of traffic (reads, or a one-way
   event); Inventory's `Reserve` is a synchronous, stock-affecting write
   that checkout cannot proceed without an answer to, and `Release` is a
   new concept this book hasn't needed yet: an explicit compensating action
   for a write that a local transaction can no longer roll back automatically.
3. **Bridge the gap between "the monolith still owns `inventory_items`"
   and "Inventory owns its own copy"** without losing or duplicating a
   reservation during the transition — the job a one-time, then-retired
   transaction-log backfill does, which is new infrastructure this book
   hasn't introduced yet (Debezium, tailing Postgres's write-ahead log).
4. **Cut `OrderItem.inventory_item`'s foreign key** — this chapter's own
   concrete example above — so `order`'s schema no longer has a live
   dependency on a table that's about to leave its database entirely.

ch.19 builds all four, in that order, against the real, already-extracted
`examples/04-inventory-service` and the real `order.services.place_order()`
cutover path this project ships.

## What you learned

- Shared-database coupling (SMELL #3/#4) is harder to break than the
  coupling every prior extraction in this book cured, because the database
  itself — not just the code — enforces the dependency: a foreign key
  cannot be routed around by a proxy the way an HTTP path can.
- Database-per-service trades the database's own referential-integrity
  guarantee for independent deployability, independent schema evolution,
  and (the property ch.19's `Reserve` needs specifically) an uncontested
  row-level lock with exactly one writer.
- `OrderItem.inventory_item`'s foreign key becoming `sku`/`item_name`/
  `unit_price_cents` snapshot columns is this project's concrete instance
  of that trade: add the columns, backfill them *while the FK is still
  live* (the only moment the join that populates them is still possible),
  then drop the FK — never any other order.
- Duplication across a service boundary is a deliberate design choice when
  the two copies are allowed to diverge by design — a checkout-time price
  snapshot and inventory's live catalog price are two different facts that
  happen to start out equal, not one fact stored twice by mistake.
- This project's three extractions took three different, individually
  correct positions on data ownership (Review shared/deferred, Notification
  owned-from-day-one, Inventory owned-via-backfill) because each extraction
  needed a different thing from its seam — there is no single universally
  "right" answer, only the answer that fits what the seam actually has to
  do.

Next: ch.19 builds the extraction this chapter planned — Inventory's own
schema, the gRPC seam and its proto-as-ACL, the transaction-log backfill
that bridges the transition, and the compensating `Release` that rebuilds
the free rollback a shared transaction used to give away for nothing.

---

*Verification status: <span class="status status--verified">verified</span>.
This chapter is a planning and analysis chapter — it introduces no new code
of its own — and every artifact it cites is real, already-built r04 code:
`order/models.py::OrderItem` and `order/migrations/0002_orderitem_sku_snapshot.py`
(confirmed via `python manage.py migrate` and `python manage.py sqlmigrate
order 0002`, which shows the `ADD COLUMN` / backfill / `DROP COLUMN`
sequence in that exact order), `examples/00-monolith/SMELLS.md`'s smells #3
and #4, and `examples/02-review-service`/`examples/03-notification-service`'s
own `MIGRATION.md`/model docstrings for the shared-vs-owned contrast. The
extraction this chapter plans is verified built and cut over in ch.19's own
verification record.*
