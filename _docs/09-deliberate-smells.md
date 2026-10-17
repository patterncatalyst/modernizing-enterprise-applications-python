---
title: "The Deliberate Smells"
order: 9
part: "The Reference Monolith"
description: "The coupling, god-service, shared-table, and transaction-scope smells planted in the reference monolith, each tagged to the pattern that will later cure it."
duration: 30 minutes
---

Ch.8 built the monolith as a defensible "before." This chapter reads the
same codebase a second time, this time hunting: seven smells, planted by
design, each one tagged in-code with a comment of the exact shape
`# SMELL[ch.NN]: ...`, naming the chapter — later in this book — that cures
it. None of them are bugs. Every one of them is the ordinary, idiomatic way
to write this code *inside one process with one shared database* — which is
exactly why they're worth naming now, before Part 5 starts cutting seams.

Find every one of them yourself:

```sh
grep -rn 'SMELL\[ch\.' examples/00-monolith
```

{% include excalidraw.html file="smell-map" alt="Map of the monolith's seven deliberate smells, each pointing from its planted location to the chapter that cures it" caption="Figure 9.1 — Seven smells, seven curing chapters" %}

## A seam is a line the system already wants to be cut along

Martin Fowler's definition of a seam — a place where behavior can change
without editing the code at that spot — is the quiet idea underneath this
whole chapter. Every smell below sits exactly on one of this monolith's
seams: the place where a bounded context's own logic butts up against
another context's, or against infrastructure it doesn't actually own. A
seam doesn't announce itself as a seam while the system is young and small.
It looks like the normal, unremarkable way anyone would write this code.
Naming it is what turns "normal code" into "a smell with an address" — a
location `grep` can find, mapped to the exact chapter that resolves it.

## Smell 1 — the god checkout service

**Where:** `order/services.py::place_order()`
**Cured in:** ch.26 (order extraction) — the last and hardest, by design

`place_order()` is the single orchestration point for checkout. It reaches
directly into inventory's, payment's, shipping's, and notification's
services and models, instead of treating those contexts as independently
deployable collaborators reached over a stable contract:

```python
# SMELL[ch.26]: reaching directly into inventory's services/model
# layer from the order context, with no anti-corruption layer at the
# seam -- the Python equivalent of the Java monolith's `OrderService`
# calling straight into `InventoryService`.
for line in items:
    inventory_item = inventory_services.get_by_sku(line["sku"])
    inventory_services.reserve(line["sku"], line["quantity"])
    ...
```

Order is the *last* context this book extracts, by design, not the first,
because every other context's extraction removes one of this function's
direct dependencies before order's own turn comes. By the time ch.26 gets
to it, inventory, payment, shipping, and notification are already gone —
order is the only thing left reaching into empty air.

Notice what the fix can't be, too. It isn't "write cleaner code inside
`place_order()`" — the function is already short, already readable, already
doing exactly what it says. The smell isn't in the code's style; it's in
how this one function's correctness depends on four other contexts'
internals being reachable in the same call stack. A code review of
`place_order()` in isolation, with no knowledge of the other five contexts,
would find nothing wrong with it at all — which is exactly why this kind of
coupling survives so many code reviews in real systems.

## Smell 2 — one ACID transaction spanning six contexts

**Where:** `order/services.py::place_order` (the `transaction.atomic()` block)
**Cured in:** ch.22 (ACID → ACD), ch.23/24 (choreographed/orchestrated sagas)

The entire checkout body — order persistence, inventory reservation,
payment capture, shipment dispatch, and the outbox write — runs inside one
`transaction.atomic()` block. A failure anywhere unwinds everything written
so far, in every context, automatically:

```python
with transaction.atomic():
    order = Order.objects.create(...)
    inventory_services.reserve(...)
    payment_services.charge(...)
    shipping_services.dispatch(...)
    _write_order_placed_outbox_event(...)
```

That automatic rollback is a gift of sharing one Postgres instance across
six contexts. The moment any one of them gets its own database, the
rollback stops happening on its own — it has to be rebuilt by hand as a
saga, with explicit
compensating actions for everything that already committed. `tests/
test_checkout.py` proves this rollback is real, not theoretical, with two
deterministic failure sentinels:

- A `paymentMethod` of `CARD-DECLINE` → `402 PAYMENT_DECLINED`, and the
  inventory reservation taken earlier in the same request is rolled back
  (net-zero stock).
- A `shippingAddress` containing `SHIP-FAIL` → `422 SHIPPING_FAILED`, and
  the *entire* checkout unwinds — inventory reservation, order row, and
  payment capture, all of it.

## Smell 3 — a shared single schema for all six apps

**Where:** `config/settings.py` (`INSTALLED_APPS`/`DATABASES`), every
model's `db_table`
**Cured in:** ch.18 (shared data → owned data)

One Postgres schema, one Django migration history, all six bounded
contexts migrating and deploying together. A schema change to `inventory`
and a schema change to `payment` land in the same `manage.py migrate` run
whether or not the two contexts intended to ship at the same time —
`config/settings.py` says so directly, right above `INSTALLED_APPS`:
"all six bounded contexts ... are Django apps in ONE project, sharing ONE
Postgres schema ... and migrating together."

The cost of this smell is easy to underrate because nothing about it looks
expensive on any single day. Adding a column to `reviews` is a one-line
migration, same as it would be in six separate schemas. The expense shows
up later, as a *rate limit* on how independently any one context can
change: every migration against this one database is a migration every
other context's deploy has to tolerate, whether or not that context's code
changed at all. Ch.18 names the destination this smell is cured into —
each context owning its own schema outright — and spends real time on why
"owned" doesn't have to mean "a separate physical database" on day one of
that cure.

## Smell 4 — cross-context foreign keys

**Where:** every cross-app `ForeignKey` field (see each app's `models.py`)
**Cured in:** ch.18 (shared data → owned data), ch.19 (CDC backfill + decommission)

`order.Order.customer`, `order.OrderItem.inventory_item` (its original
shape, before ch.19's snapshot cure), `payment.Payment.order`,
`shipping.Shipment.order`, `notification.Notification.customer`/`.order`,
and `review.Review.customer`/`.inventory_item` are all direct foreign keys
crossing bounded-context boundaries inside the one shared schema. Each one
is an ordinary, idiomatic Django relation — and each one is also a decision
in waiting: an owned copy, a replicated field via CDC, or a soft reference
carried in an event, once the tables on either end of that join no longer
live in the same database.

`order.models.OrderItem` is the clearest worked example of what "in
waiting" means, because this project has already cured it once. Its
original shape held a live `ForeignKey` onto `inventory.InventoryItem`, so
reading an order's line items meant joining into inventory's own table on
every request. Ch.19's cure replaces that live join with a denormalized
snapshot — `sku`, `item_name`, `unit_price_cents` captured once, at checkout
time, onto `OrderItem` itself — so a later price change in inventory can
never retroactively rewrite a historical order line. `tests/
test_order_snapshot.py` is the regression test that proves this: it changes
an `InventoryItem`'s price after an order already exists and asserts the
existing order's line item is untouched. The other five foreign keys in
this smell are still live joins at the state this chapter describes; ch.18
and ch.19 walk the same snapshot-or-replicate decision for each of them in
turn.

## Smell 5 — synchronous notification inside the checkout transaction *(cured)*

**Where:** `order/services.py::place_order` (now writes an `OutboxEvent` instead)
**Cured in:** ch.17 (notification extraction: transactional outbox + async consumer)
**Status:** cured

This smell's original shape called `notification/services.py::
send_order_confirmation()` synchronously, from inside the same
`transaction.atomic()` as the rest of checkout — checkout latency coupled
to however long "sending" a notification took, and a failure there would
have rolled back the whole order. That call is gone. `place_order()` now
writes an `order.placed` `OutboxEvent` row in the same transaction and
returns; nothing notification-shaped runs synchronously in the checkout
path anymore:

```python
OutboxEvent.objects.create(
    aggregate_type="order",
    aggregate_id=str(order.id),
    event_type="order.placed",
    payload=payload,
)
```

## Smell 6 — the dual-write hazard *(cured)*

**Where:** `notification/services.py::record_order_placed` (replaces the old
`send_order_confirmation`/`_dispatch_via_external_provider`)
**Cured in:** ch.17 (the transactional outbox)
**Status:** cured

The old `send_order_confirmation()` made two independent writes to two
independent systems with no shared transaction: a `Notification` row
(atomic with checkout) and a call to a stand-in external provider. A crash
between the two would have lost the notification silently; a naive retry
could have duplicated it — the textbook dual-write problem. The cure makes
the outbox write the *only* thing inside the local transaction. A separate
process, `common.management.commands.outbox_relay`, is the only thing that
reads the outbox and publishes to Kafka at-least-once, stamping
`published_at` after a successful send. `notification.management.commands.
order_placed_consumer` consumes that topic and calls
`notification.services.record_order_placed()`, which is idempotent — a
check-then-create backstopped by a partial unique constraint on `order` —
so a redelivered event creates exactly one `Notification`, never two.

## Smell 7 — review tangled into shared security despite being independent

**Where:** `review/views.py::ReviewListCreateView`
**Cured in:** ch.15 (review extraction — the first context pulled out)

`review/models.py` says outright that review has no runtime dependency on
order, inventory, payment, shipping, or notification — it's REST-only, with
no synchronous collaborator. And yet `POST /api/reviews` is gated by Basic
auth against this monolith's own shared `django.contrib.auth` table, the
same shared-security surface every other context would reach for if it
needed auth:

```python
# SMELL[ch.15]: POST is gated by HTTP Basic auth against THIS module's
# shared `django.contrib.auth` `auth_user` table ... the same shared-
# security surface every other context in this monolith would reach for
# if it needed auth.
authentication_classes = [BasicAuthentication]
```

`GET /api/reviews` and `GET /api/reviews/{id}` stay open — only the write
is gated, per-view. That contract (401 unauthenticated, 201 authenticated)
is exactly what `tests/test_review_auth.py` asserts. Review gets its own,
independent auth configuration once it's extracted in ch.15 — no longer
borrowing this module's `auth_user` table at all.

## Deterministic failure injection: proving smells 1 and 2 are real

A smell that only exists in prose is easy to dismiss as theoretical. This
one doesn't stay in prose. Four checkout behaviors, triggered by
deterministic sentinels in the request body, prove smells 1 and 2 are real
mechanisms with observable consequences, not just an architectural
observation:

- The happy path → `201 Created`, `Location: /api/orders/{id}`,
  `status: CONFIRMED`.
- A checkout line that exceeds `quantityOnHand` → `409 Conflict`,
  `error: OUT_OF_STOCK`, raised *before* any writes happen at all.
- A `paymentMethod` containing `DECLINE` (case-insensitive) → `402 Payment
  Required`, `error: PAYMENT_DECLINED`, and the inventory reservation made
  earlier in the same transaction is rolled back — net-zero stock.
- A `shippingAddress` containing `SHIP-FAIL` (case-insensitive) → `422
  Unprocessable Entity`, `error: SHIPPING_FAILED`, and the entire checkout
  rolls back — inventory reservation, order row, and payment capture, all
  of it, also net-zero stock. This is smell 2's whole point, made
  concrete: today, this rollback is free.

Since smells 5 and 6 were cured, the `OutboxEvent` write rides along with
that same free rollback: the happy path leaves exactly one `order.placed`
row behind; a `DECLINE` or `SHIP-FAIL` checkout leaves zero. `tests/
test_checkout.py` and `tests/test_outbox.py` assert every one of these
outcomes directly, and the same four scenarios are what `tooling/newman/
mea.postman_collection.json`'s Scenario 1–4 folders assert from outside the
process (ch.10 covers that collection in full). Neither suite is testing
"the smell." Both are testing the ordinary checkout contract — the smell
is just the reason that contract is so cheap to get right today, and
exactly what gets expensive to keep once any one of these contexts gets
its own database.

## The proof this method works: review, already cured

Naming a smell and tagging it to a curing chapter is only useful if the
cure actually lands. By the time this book reaches Part 5, it does: ch.15
pulls review out of this monolith first — precisely *because* `review/
models.py` already says, in its own docstring, that review has no runtime
dependency on any other context. That's not a coincidence this chapter is
pointing out after the fact; it's the same reasoning in reverse. Smell 7 is
cheap to cure exactly because review was always the least-coupled context
in the schema — no synchronous collaborator to disentangle, no saga to
build, just an auth gate to re-home onto a service that owns its own user
store. Ch.15 records the result: `uv run pytest` passing 11/11 against a
real, throwaway Postgres container for the extracted service, and the same
unedited Newman collection this chapter described staying green re-pointed
at the new service's own address. Smell 7, planted here, cured there — with
nothing in between but the chapters that build the extraction mechanism
itself (ch.14's strangler proxy, which every extraction after review reuses
too).

## The smell table

| # | Smell | Curing chapter | Status |
|---|---|---|---|
| 1 | God checkout service | ch.26 | open |
| 2 | One ACID transaction across six contexts | ch.22, ch.23/24 | open |
| 3 | Shared single schema | ch.18 | open |
| 4 | Cross-context foreign keys | ch.18, ch.19 | open |
| 5 | Synchronous notification in checkout | ch.17 | **cured** |
| 6 | Dual-write hazard | ch.17 | **cured** |
| 7 | Review/shared-auth coupling | ch.15 | open |

Five of the seven are still open at the state this chapter describes —
"open" here means *not yet cured*, not *undiscovered*; every one of them is
already named, tagged, and pointed at its curing chapter. Two are already
cured, and their cure is already live in this same codebase: smells 5 and 6
prove the method works before Part 5 even starts, because the fix for both
of them — a transactional outbox plus an idempotent consumer — was built
directly into this still-whole monolith, without extracting notification
into its own service first. That is the chapter-9 argument in miniature:
curing a smell and extracting a context are two different moves, and
sometimes the first one can happen before the second one does.

## Why "deliberate" matters

Nothing above is bad code. `place_order()` reaching into four other
contexts' services directly is the single most natural way to write a
checkout function inside one process — there is no network between
`order` and `inventory` to make a contract feel necessary, so nobody writes
one. A single `transaction.atomic()` spanning five contexts is the single
most natural way to get correctness without writing any of it by hand,
because Postgres already gives it away. A shared schema is the single most
natural way to model a domain with this many cross-references, because the
ORM makes every one of those joins a one-line `ForeignKey`. None of these
smells required a careless engineer. They required exactly one condition:
everything living in the same process, talking to the same database. Part 5
removes that condition, context by context, and every removal forces
exactly one of these smells into the open and cures it, by design.

Next: ch.10 looks at how this same monolith is tested — and why the test
suite built for it today is the thing that will later prove every
extraction behaves identically to what it replaced.

---

*Verification status: <span class="status status--verified">verified</span>.
All seven smells are grep-locatable in `examples/00-monolith` via
`grep -rn 'SMELL\[ch\.' .`; the two deterministic failure injections
(`CARD-DECLINE` → 402, `SHIP-FAIL` → 422) are exercised live by `tests/
test_checkout.py`, and the outbox cure is exercised by `tests/
test_outbox.py`. The monolith is frozen/break-glass only; this chapter
describes the pre-extraction "before" preserved on `reference/
monolith-before` and tag `v0-monolith`.*
