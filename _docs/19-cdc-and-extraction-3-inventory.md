---
title: "CDC, Transaction Log Tailing & Extraction 3 — Inventory"
order: 19
part: "Data Across the Seam"
description: "Debezium-style transaction-log tailing bridges the monolith's still-live table during the cutover window; a gRPC proto-as-ACL seam, an atomic conditional-UPDATE reserve, and an explicit compensating release replace the free rollback a shared transaction used to give away."
duration: 60 minutes
---

ch.18 named the plan: give Inventory its own schema, move `reserve`/
`release` across a real network boundary, bridge the transition without
losing a reservation, and cut `OrderItem`'s foreign key loose. This chapter
builds all four, against the real, already-extracted
`examples/04-inventory-service` and the real cutover inside
`examples/00-monolith/order/services.py`. It is also where this book's
free lunch runs out for the first time on the *write* side: ch.15's Review
extraction moved a read; ch.17's Notification extraction moved a one-way
event; this chapter moves a synchronous decrement that checkout cannot
proceed without an answer to, and once that decrement commits in a
different process's database, there is no longer a shared write-ahead log for Postgres to undo it with.

The code is in `examples/04-inventory-service/` (the new FastAPI + gRPC
service) and `examples/00-monolith/order/` (the client-side ACL and the
`grpc`-mode checkout path). `MIGRATION.md` and `CUTOVER.md` in the service
directory record what it does, how it cuts over, and the measured numbers
cited below; `tooling/newman/GOLDEN-BASELINE.md`'s r04 NEWMAN-GRPC lane is
this chapter's end-to-end proof.

## Why Inventory leaves third, and why it's the hardest cut yet

Extraction order in this book has never been arbitrary. Review (ch.15) went
first because it has no synchronous collaborator — the mechanism could be
proven in isolation. Notification (ch.17) went second because, although it
introduced a real distributed-systems problem (the dual-write hazard), that
problem was solvable entirely on the *producer* side, with delivery
semantics (at-least-once) that an idempotent consumer can absorb without the
monolith ever needing a synchronous answer back. Inventory is the first
extraction where the monolith needs to know, **before it can confirm an
order**, whether a remote call succeeded — `place_order()` cannot return
`201 CONFIRMED` until it knows stock was actually secured, and it cannot
treat "the inventory service didn't answer" the same as "there wasn't
enough stock." That requirement is what makes this extraction structurally
different from the two before it, along three axes at once:

1. **The seam is synchronous**, not fire-and-forget. A gRPC call, not a
   Kafka topic, carries `Reserve`/`Release`/`CheckStock`/`GetStock` — this
   book's first synchronous *mutation* across a service boundary (Review's
   synchronous calls were read-only).
2. **The data has to move out from under a live writer.** Review's and
   Notification's data postures (ch.18) were each a clean case — shared by
   design, or owned from a blank slate. Inventory's `inventory_items` table
   has real rows the monolith has been writing to since r01, and a one-time
   transaction-log backfill has to bridge the gap during cutover without
   losing a reservation.
3. **The free rollback disappears.** `examples/00-monolith/SMELLS.md`'s
   smell #2 — one `transaction.atomic()` spanning all five contexts checkout
   touches — has been "free" since r01 because Postgres can unwind five
   tables' writes with one `ROLLBACK`. The moment `Reserve` commits in
   Inventory's own database, that single write-ahead log no longer spans
   both writes, and the rollback this book has been getting for nothing has
   to be rebuilt by hand.

## The gRPC seam and the proto as a typed anti-corruption layer

`examples/04-inventory-service/app/grpc_server.py` exposes four RPCs —
`CheckStock`, `Reserve`, `Release`, `GetStock` — defined in
`proto/dev/patterncatalyst/inventory/v1/inventory.proto` and compiled into
both the service's own `app/grpc_gen/` and the monolith's `order/grpc_gen/`
from the same `.proto` source. The proto's own header comment states its
job directly:

```proto
// r04/ch.19 -- the gRPC contract IS the anti-corruption layer for the
// synchronous order<->inventory seam: a strongly-typed, versioned wire
// vocabulary (stock_keeping_unit/display_name/unit_price_cents/
// on_hand_qty) deliberately DISTINCT from the monolith's domain
// vocabulary (sku/name/priceCents/quantityOnHand) so the ACL earns its
// keep translating between the two, rather than the two shapes
// happening to already agree.
```

{% include excalidraw.html file="inventory-grpc-proto-acl" alt="The monolith's domain vocab, inventory.proto's distinct wire vocab, and inventory-service's own domain vocab, each translated by a client-side and server-side ACL" caption="Figure 19.1 — The proto IS the ACL: two separate vocabularies meet only at the wire" %}

This is ch.16's ACL argument carried one step further. Notification's ACL
(`OrderPlacedEvent`) was a Pydantic model this service's own code owned,
translating a Kafka JSON payload into a locally-owned shape; there was
nothing enforcing that translation except the consumer's own code. A proto
contract enforces more at the type-system level: `inventory.proto`'s field
names and numbers are frozen and versioned, generated into strongly-typed
stub code on *both* sides, so a field rename on either side is a compile-
time (code-generation-time) break, not a runtime surprise discovered by a
malformed payload. Each side still owns its own translation, though — the
proto itself does not collapse the two vocabularies into one shared shape,
and that's deliberate. On the client side, `order/inventory_client.py::
RemoteInventoryClient` is the only place in the monolith that imports the
generated `inventory_pb2` types at all:

```python
# order/inventory_client.py -- client-side ACL translator
@dataclass(frozen=True)
class StockSnapshot:
    """Clean translation of StockReply -- the raw proto type never leaks
    past this client."""
    sku: str
    name: str
    unit_price_cents: int
    on_hand_qty: int
    available: bool


class RemoteInventoryClient:
    def reserve(self, sku: str, quantity: int) -> ReserveResult:
        request = inventory_pb2.ReserveRequest(stock_keeping_unit=sku, requested_qty=quantity)
        reply = self._unary(self._stub.Reserve, request)
        if not reply.reservation_ok:
            raise InsufficientStock(
                f"Requested {quantity} of {sku} but only {reply.on_hand_qty} on hand"
            )
        return ReserveResult(sku=reply.stock_keeping_unit,
                              reservation_ok=reply.reservation_ok,
                              on_hand_qty=reply.on_hand_qty)
```

On the server side, `app/grpc_server.py::InventoryGrpcServiceServicer`
translates in the opposite direction, and its own module docstring names
the same deliberate mismatch from the other end — `stock_keeping_unit`/
`on_hand_qty`/`unit_price_cents` on the wire, `sku`/`quantity_on_hand`/
`price_cents` internally, "so the order-side ACL's message translator earns
its keep converting between the two, instead of the two shapes happening to
already agree." A `grpc.RpcError` on any call — a timeout, `UNAVAILABLE`, a
dead connection — is translated by `_unary()` into this project's own
`InventoryServiceUnavailable`, a separate exception from
`InsufficientStock`: a service that can't be reached and a sku that's
actually out of stock are different failure modes with different HTTP
status codes (503 versus 409), and `common/exceptions.py`'s docstring is
explicit that confusing the two would be a correctness bug, not a cosmetic
one.

## Transaction-log tailing: Debezium reads the write-ahead log

The gRPC seam alone doesn't solve the problem ch.18 raised: `inventory_items`
is a real table with real rows the monolith has been writing to since r01,
and Inventory's own schema starts out empty. If cutover meant flipping
straight from "monolith owns the table" to "Inventory owns an empty table,"
every row already in stock would vanish from Inventory's point of view on
day one. `examples/04-inventory-service/app/cdc_consumer.py` exists to
bridge exactly that gap, and its docstring states directly what it is and
isn't: "Role: backfill + sync during the cutover window, retired after it."

The mechanism is **transaction-log tailing**, not application-level
polling. `infra/debezium/inventory-connector.json` configures a Debezium
Postgres connector against `public.inventory_items` using Postgres's
*logical replication* machinery — the same write-ahead log (WAL) Postgres
already maintains for crash recovery and streaming replication, repurposed
as a change-event source:

```json
{
  "name": "meap-inventory-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "table.include.list": "public.inventory_items",
    "plugin.name": "pgoutput",
    "slot.name": "meap_inventory_slot",
    "publication.name": "meap_inventory_publication",
    "publication.autocreate.mode": "filtered",
    "snapshot.mode": "initial"
  }
}
```

`snapshot.mode=initial` is what makes this a **backfill**, not just an
ongoing sync: on first start, the connector emits one `op=r` ("read") event
per row already in `public.inventory_items` — the one-time copy that
populates Inventory's otherwise-empty schema — before switching to
streaming `op=c`/`u`/`d` events for every subsequent insert, update, and
delete. `scripts/register-debezium.sh` runs one extra step before
registering the connector, `ALTER TABLE public.inventory_items REPLICA
IDENTITY FULL`, which is what makes Postgres include a *complete*
before-image on `UPDATE`/`DELETE` events rather than just the primary key —
without it, a deleted row's change event would carry only an id, not the
full row Inventory's consumer needs to apply the delete correctly.

`app/cdc_consumer.py::InventoryCdcConsumer` is the subscriber on the other
end — an `aiokafka` consumer, same library this project already uses for
Notification's event pipeline, applying every event through a single
idempotent upsert:

```python
async def _upsert(session: AsyncSession, after: dict) -> None:
    stmt = pg_insert(InventoryItem).values(
        id=after["id"], sku=after["sku"], name=after["name"],
        price_cents=after["price_cents"],
        quantity_on_hand=after["quantity_on_hand"],
        updated_at=_parse_debezium_timestamp(after.get("updated_at")),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[InventoryItem.id],
        set_={"sku": stmt.excluded.sku, "name": stmt.excluded.name,
              "price_cents": stmt.excluded.price_cents,
              "quantity_on_hand": stmt.excluded.quantity_on_hand,
              "updated_at": stmt.excluded.updated_at},
    )
    await session.execute(stmt)
    await session.commit()
```

`r`, `c`, and `u` events all funnel through this one `INSERT ... ON CONFLICT
DO UPDATE` — a database-native upsert, not a check-then-insert pattern like
Notification's idempotency layer (ch.17), because there's no natural
"already applied" marker for a row *update* the way there is for a
notification keyed on `order_id`. `d` events funnel through a keyed
`DELETE`. Both are safe under Kafka's at-least-once redelivery for the same
reason ch.17's dedupe is: applying the same upsert or the same delete twice
produces the same end state as applying it once.

{% include excalidraw.html file="cdc-backfill-then-retire" alt="Transaction-log tailing end to end: Postgres WAL, replication slot, Debezium Postgres connector, Kafka topic, and InventoryCdcConsumer's upsert into the owned schema, with the retire runbook ghosted as the step that follows cutover" caption="Figure 19.2 — CDC tails the WAL for a one-time backfill plus transition sync, then is retired" %}

## Owned data, then own seed: why you retire the tailed log

The CDC consumer is flag-gated (`INVENTORY_CDC_ENABLED`, default `false`)
for a specific reason: it is **not** this project's CI
posture, and it is **not** Inventory's end state. `uv run pytest` never sets
the flag; the test suite and this book's default dev/CI posture seed
Inventory's schema directly, via `migrations/versions/0002_seed_inventory.py`,
with the same three demo skus the monolith seeds (`SKU-WIDGET-001`/100,
`SKU-GADGET-002`/50, `SKU-GIZMO-003`/5). CDC is a real operational concern
for a *staged production rollout* where the monolith and Inventory run
side by side for some period — not a testing concern — which is exactly why
it ships disabled by default rather than on.

`CUTOVER.md`'s retire runbook is explicit about the condition that makes the
tailed log safe to tear down, and it's a conjunction, not either half alone:

1. The monolith's checkout code calls Inventory's gRPC `Reserve`/`Release`
   **exclusively** — Inventory's own table is now the only place stock
   mutations land, so there is nothing left on the monolith's side to
   stream from.
2. The monolith's `public.inventory_items` table (and the Django
   `inventory` app around it) is decommissioned, matching this project's
   strangler end-state posture for every other extracted context.

Once both hold, `scripts/retire-debezium.sh` deletes the connector and
drops both the replication slot and the publication — not just the
connector, because an un-drained replication slot retains WAL on the
source Postgres indefinitely, a disk-fill risk with no further benefit once
nothing is reading from it. The script is written defensively: deleting an
already-gone connector returns `404`, treated as already-retired rather
than a failure; dropping the slot retries briefly if Postgres still reports
it active (Kafka Connect's replication connection takes a moment to close
after the connector is deleted), rather than racing a `pg_drop_
replication_slot` call that would otherwise fail loudly. This is the same
discipline ch.17's outbox relay docstring stated about itself when it called
out that CDC was a deferred alternative to its own polling
loop — "CDC becomes worth its complexity once polling latency or database
load from polling itself becomes the bottleneck." Here, that complexity is
finally worth paying, but only for the duration of a cutover window, and
the runbook that retires it is as much a deliverable as the connector
config that registers it.

## Two phases, and a gRPC server with no Django original to lift

Following the same two-phase discipline ch.15 established, `MIGRATION.md`
measures what a Django-ORM-lifted Phase A would have cost — but this
extraction is a hybrid of Review's and Notification's stories, not a clean
match for either. The **REST read surface** (`GET /api/inventory`) does have
a monolith original to lift, so it gets the same Phase A/B treatment Review's
own `MIGRATION.md` used. The **gRPC mutating surface** has no monolith
original at all, and the reason is structural, not incidental: the
monolith's `reserve` concern lived against a pessimistic-lock derived query,
running inside the same Django transaction as the rest of checkout. A
faithful Phase A `Reserve` would have to call into that in-process mechanism
from a separate FastAPI process over a network call — which is incoherent,
because the monolith's mechanism is specifically "stay in one transaction,"
and a gRPC call from a different process cannot join it. There is no
smaller, less-idiomatic version of "atomic check-and-decrement exposed over
gRPC" to lift; the mutating surface is Phase-B-idiomatic by construction,
the same conclusion Notification's `MIGRATION.md` reached for its consumer.

| Metric | Phase A (proxy: `django.setup()` + `import fastapi, uvicorn`) | Phase B (shipped, includes `grpc` + `aiokafka`) |
|---|---|---|
| Cold interpreter floor | 0.01 s | 0.01 s |
| Import/startup time (3-run avg) | 0.264 s | 0.312 s |
| Import-only RSS | ~74.3 MB | ~90.3 MB |
| Running server RSS (after 20 requests, gRPC server also bound) | not measured (no server built) | ~105.8 MB |

Taken at face value, this extraction lands closer to Notification's
reading than Review's near-wash: Phase B costs noticeably more at both the
import stage (`grpc`'s own C-extension, `aiokafka`'s import graph) and the
running-server stage. That gap is not a regression to chase down — Phase A's
proxy measures a read-only surface with no gRPC capability at all, while
Phase B's running number reflects a *second, live network server* actually
bound and accepting connections on `:9004` alongside the HTTP surface on
`:8084`, real capability Phase A structurally could never have measured.

## The consistency crux: where the free rollback went

Everything above explains how Inventory gets its own, correctly-backfilled
copy of the data. It says nothing yet about the harder problem ch.19 opened
with: once `Reserve` is a network call into a different process's database,
what happens to the free rollback smell #2 has been describing since r01?

`order/services.py::place_order()` now dispatches on `settings.INVENTORY_MODE`
between two checkout strategies, and reading them side by side is the
clearest way to see exactly what changed:

{% include codetabs.html langs="local mode (r01-r03, UNCHANGED) — free rollback|grpc mode (r04/ch.19) — explicit compensation" %}

```python
# order/services.py -- _place_order_local, UNCHANGED since r01
def _place_order_local(customer, items, payment_method, shipping_address):
    with transaction.atomic():
        order = Order.objects.create(customer=customer, ...)
        for line in items:
            inventory_item = inventory_services.get_by_sku(line["sku"])
            inventory_services.reserve(line["sku"], line["quantity"])  # same tx
            OrderItem.objects.create(order=order, sku=inventory_item.sku, ...)
        payment_services.charge(order, order.total_cents, payment_method)  # a
        order.confirm()                                                    # decline
        shipping_services.dispatch(order, order.shipping_address)          # here
        _write_order_placed_outbox_event(customer, order)                  # rolls
    return order                                                           # back
                                                                             # everything
```

```python
# order/services.py -- _place_order_remote, r04/ch.19
def _place_order_remote(customer, items, payment_method, shipping_address):
    client = inventory_client.RemoteInventoryClient()
    try:
        line_snapshots, reserved = _reserve_lines_remote(client, items)  # OUTSIDE
        try:                                                              # any local
            with transaction.atomic():                                    # atomic()
                order = Order.objects.create(customer=customer, ...)
                for snapshot in line_snapshots:
                    OrderItem.objects.create(order=order, sku=snapshot["sku"], ...)
                payment_services.charge(order, order.total_cents, payment_method)
                order.confirm()
                shipping_services.dispatch(order, order.shipping_address)
                _write_order_placed_outbox_event(customer, order)
        except Exception:
            _release_reserved(client, reserved)   # explicit compensation
            raise
        return order
    finally:
        client.close()
```

`_place_order_remote`'s own docstring states the crux directly: "a remote
Reserve is not part of this process's Postgres transaction and cannot be
rolled back by it." `local` mode's `reserve()` call sits *inside* the same
`transaction.atomic()` as the order row, the payment charge, and the
shipping dispatch — a `PaymentDeclined` three lines later unwinds the
reservation along with everything else automatically, because all of it shares one
write-ahead log. `grpc` mode's `client.reserve(sku, quantity)` call happens
**before** that `transaction.atomic()` even opens, against a *different*
process's Postgres instance — by the time a decline happens inside the
local block, the remote `UPDATE` has already committed in Inventory's own
database, on Inventory's own WAL, which this process has no way to touch.

{% include excalidraw.html file="reserve-release-saga-lite" alt="Before and after panels: the single local transaction.atomic() giving a free rollback across reserve, order, payment, and shipping, versus the gRPC Reserve committing outside any local transaction with an explicit compensating Release wired to PaymentDeclined and ShippingFailed" caption="Figure 19.3 — Reserve/release across the boundary: where the free rollback went" %}

This is why `Release` exists at all, and why `_place_order_remote`'s
`except Exception: _release_reserved(client, reserved); raise` is not
defensive boilerplate — it is the entire mechanism that keeps checkout's
observable behavior identical between the two modes. `_reserve_lines_remote`
tracks every `(sku, quantity)` pair this checkout has successfully reserved
so far; the moment anything fails — a later line's `InsufficientStock`, a
dead inventory service raising `InventoryServiceUnavailable`, or (caught by
the outer `try`) a `PaymentDeclined`/`ShippingFailed` raised from inside the
still-local atomic block — every sku reserved this checkout gets an explicit
compensating `Release` call before the exception propagates to the caller.
This is this book's first deliberate taste of a **choreographed saga**
(forward-referenced to ch.23's full treatment): no central coordinator, no
saga framework, just the one caller that knows what it reserved taking
responsibility for undoing it when a later step fails.

## Reserve's atomic conditional decrement, and Release its mirror

The compensating `Release` only works because `Reserve` itself is correct
under concurrency in the first place — a guarantee `app/repository.py::reserve`
earns with a single SQL statement, not a read-then-write:

```python
async def reserve(session: AsyncSession, sku: str, qty: int) -> int:
    stmt = (
        update(InventoryItem)
        .where(InventoryItem.sku == sku, InventoryItem.quantity_on_hand >= qty)
        .values(quantity_on_hand=InventoryItem.quantity_on_hand - qty)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
```

One conditional `UPDATE`, not a `SELECT` to check stock followed by a
separate `UPDATE` to decrement it. That distinction is the entire
concurrency-safety argument: a read-then-write has a window between the two
statements where a second caller's own read-then-write can interleave,
and both can believe they're decrementing from the same starting quantity —
the classic lost-update race, oversold stock. A single conditional `UPDATE`
has no such window, because Postgres takes a row-level write lock for the
*duration of the statement itself*; two concurrent `Reserve(sku, 1)` calls
against a sku with exactly one unit left serialize on that lock, and
whichever commits first leaves `quantity_on_hand` below the other's
`>= qty` predicate — so exactly one `UPDATE` affects a row (`rowcount == 1`,
`reservation_ok=true`) and the other affects none (`rowcount == 0`,
`reservation_ok=false`, no partial or duplicate decrement). No application-
level lock, no `SELECT ... FOR UPDATE`, no optimistic-locking version
column — the database's own write-lock semantics are the entire mechanism.

`tests/test_inventory_grpc.py::test_reserve_concurrent_requests_for_last_unit_exactly_one_succeeds`
proves exactly this, against the real `InventoryGrpcServiceServicer` coroutine
methods and `asyncio.gather`, with no stand-in collaborator:

```python
reply_a, reply_b = await asyncio.gather(
    servicer.Reserve(request_a, None),
    servicer.Reserve(request_b, None),
)
outcomes = [reply_a.reservation_ok, reply_b.reservation_ok]
assert outcomes.count(True) == 1   # never both oversold
assert outcomes.count(False) == 1  # never both stuck/under-sold
```

`Release` is the mirror statement — `UPDATE ... SET quantity_on_hand =
quantity_on_hand + :qty WHERE sku = :sku` — but **unconditional**,
with no upper-bound check. The docstring in both `app/repository.py::release`
and `app/grpc_server.py::InventoryGrpcServiceServicer.Release` names a
documented limitation rather than quietly building around it: unlike `Reserve`'s
conditional `UPDATE`, this increment carries no dedupe or idempotency key, so
a *retried* `Release` call whose effect already landed server-side would
over-restore stock. A full fix — an idempotency key per reservation,
or a saga ledger recording reserve/release pairs — is deferred
to a later choreographed-saga chapter. This is this project's scope
discipline doing its job: building that machinery now, for a flag this
book's own exercised paths never need to retry against, would be
speculative infrastructure ahead of the chapter that actually earns it.

## `OrderItem`'s foreign key, finally cut

ch.18 built the FK-to-snapshot change as a standalone lesson; this chapter is
where it stops being a lesson and becomes the thing that makes `grpc` mode
possible at all. `_reserve_lines_remote` populates `OrderItem`'s denormalized
fields from the gRPC reply itself, not from a local join:

```python
stock = client.get_stock(sku)
line_snapshots.append({
    "sku": stock.sku,
    "item_name": stock.name,
    "unit_price_cents": stock.unit_price_cents,
    "quantity": quantity,
})
```

There is no `inventory_item` FK left to populate even if this code wanted
one — `OrderItem.inventory_item` doesn't exist anymore, in either mode.
`local` mode still reads the row returned by `inventory_services.reserve()`
in-process; `grpc` mode reads the same facts off `GetStock`'s reply, carried
across the network instead of across a join. Both modes write the identical
`OrderItem` shape, which is exactly why the two modes are observably
indistinguishable to anything downstream — the snapshot ch.18 introduced is
what makes `OrderItem` agnostic to which mode wrote it.

## Cutover: two independent dimensions, not one

`CUTOVER.md` is explicit that this extraction has **two independent cutover
dimensions**, and conflating them is the single easiest mistake to make
reasoning about this chapter:

| Dimension | Flag | Lives in | Controls |
|---|---|---|---|
| Checkout-time reserve/release | `INVENTORY_MODE` (`local`\|`grpc`) | the monolith, `config/settings.py` | who answers the synchronous write path inside `place_order()` |
| `GET /api/inventory*` reads | `STRANGLER_INVENTORY_ENABLED` | the strangler proxy, `examples/01-strangler-proxy/app/config.py` | who answers the read path |

{% include excalidraw.html file="two-cutover-dimensions" alt="The two independent cutover flags as a 2x2 grid, marking the two exercised locked-together corners against the two split corners sound only during the CDC-backfilled transition window" caption="Figure 19.4 — Two independent cutover dimensions, locked together in this book's exercised runs" %}

They don't have to move together — a split combination (`grpc` reserve with
monolith-served reads, or the reverse) is sound precisely during the
CDC-backfilled transition window this chapter just built, when both copies
of the data are being kept consistent by design. As a *steady-state*
configuration, though, this book only exercises the two corners where both
dimensions point the same direction, because that's the pair the CI gate
below actually proves end to end.

`tooling/newman/GOLDEN-BASELINE.md`'s r04 NEWMAN-GRPC lane runs the unedited
`mea.postman_collection.json` against both locked-together configurations:

| Run | `INVENTORY_MODE` | `STRANGLER_INVENTORY_ENABLED` | Result |
|---|---|---|---|
| A — fully gRPC | `grpc` | `true` | **71/71 assertions green**, 0 failed |
| B — fully local (reversibility) | `local` | unset | **71/71 assertions green**, 0 failed, byte-identical shape to A |

Run A's result is the proof this chapter's compensation logic actually
fires, not just that the suite's own before/after assertions matched:
querying `GET /api/inventory/SKU-WIDGET-001` **directly**, outside the
suite's own assertions, around Scenario 3 (payment-declined) and Scenario 4
(shipping-failed) confirms `quantityOnHand` held at the same value, 96,
across both:

```
Before:           {"quantityOnHand": 96}
After decline:     {"quantityOnHand": 96}   (PAYMENT_DECLINED, 402)
After ship-fail:   {"quantityOnHand": 96}   (SHIPPING_FAILED, 422)
```

Net-zero stock here is not Postgres's free rollback doing the work, the way
it was in `local` mode — it's `_place_order_remote`'s `except Exception:
_release_reserved(...)` firing a genuine `Release` RPC, proven by direct
query rather than inferred from the suite's own internal bookkeeping. Run
B's byte-identical 71/71 confirms the flip is still fully reversible: the
monolith's own in-process path (`SMELL[ch.22]`'s free rollback, intact)
produces the same external contract as the cross-network path, which is the
whole point of routing both through the identical, unedited collection.

## The hard negative check: both surfaces must fail loudly

With `INVENTORY_MODE=grpc` and `STRANGLER_INVENTORY_ENABLED=true` still
active, killing `examples/04-inventory-service` outright has to break
**both** surfaces this cutover touches, each in its own correct way — a
single negative check covering only one of them would leave the other
unproven.

**Reads**, through the strangler proxy: every request gets a real `502 Bad
Gateway`, the same documented fail-safe ch.14 established for a dead
upstream —

```
01. AssertionError  Inventory list returns 200
                    expected response to have status code 200 but got 502
```

**4/4 assertions failed, newman exit code 1.** **Checkout**, through the
monolith's `grpc`-mode reserve: `POST /api/orders` gets a real `503 Service
Unavailable`, not a hang and not a silently-confirmed order —

```json
{"error":"INVENTORY_UNAVAILABLE","message":"Inventory service unavailable: StatusCode.UNAVAILABLE failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:9004: Failed to connect to remote host: Connection refused","timestamp":"2026-10-16T14:08:22.850691+00:00"}
```

**9/10 assertions failed, newman exit code 1.** This is
`RemoteInventoryClient._unary()`'s `grpc.RpcError` → `InventoryServiceUnavailable`
mapping working exactly as designed: a dead inventory service fails checkout
cleanly with a 503, and that 503 is never confused with a logical 409
`OUT_OF_STOCK` — a materially different failure mode `common/exceptions.py`'s
docstring calls out explicitly, because an operator deciding whether to page
someone needs to know the difference between "we're sold out" and "a
dependency is down." Restarting the service returns both folders to fully
green (`Inventory Context Contract: 3 requests, 11/11 assertions, 0 failed`;
`Scenario 1 — Happy-Path: 4 requests, 14/14 assertions, 0 failed`) —
recovery proven, not assumed.

A no-flags control run (the plain default invocation, no `--env-var` at all)
confirms the new Inventory folder is a true no-op for every pre-existing
caller: all three Inventory requests fire as harmless, idempotent reads and
assert nothing with their guard off, and critically the Notification folder
is **not stranded** — it still fires and halts exactly where it always has,
at the identical 60/60 assertions the r03 lane's own baseline established.
A new folder that could strand an existing one would be a regression no
amount of new coverage should be allowed to hide behind.

## A green gRPC gate, no Debezium required

One detail in the numbers above is easy to miss: **no Kafka broker was
started for the NEWMAN-GRPC lane at all.** Both Run A
and Run B exercise the full checkout and read surfaces — including the
compensating `Release` path — without the CDC consumer running, because by
design, Inventory's end state never depends on it. The gRPC server and the
REST read surface are backed entirely by Inventory's own, independently
seeded `inventory` schema; Debezium's only job was bridging a transition
window this CI posture doesn't need to simulate. A production rollout would
run the real backfill during its own transition; this project's gate proves
the steady state that transition leads to, which is the state this book's
tests actually need to be fast and deterministic in CI.

## What you learned

- Inventory is the hardest extraction in this book so far because it
  combines all three axes the earlier two never had at once: a synchronous
  write the caller can't proceed without an answer to, data that has to
  move out from under a live writer, and the loss of a free, in-process
  rollback the moment that write crosses a process boundary.
- A proto contract is a stronger-typed version of ch.16's ACL argument: the
  wire vocabulary (`stock_keeping_unit`/`on_hand_qty`/...) is held
  distinct from each side's own domain vocabulary, so a client-side and a
  server-side translator each earn their keep rather than relying on the
  two shapes happening to agree.
- Transaction-log tailing (Debezium reading Postgres's WAL via a logical
  replication slot) is the correct tool for a one-time backfill plus
  transition sync — and the correct discipline is retiring it, with an
  explicit runbook, the moment the condition that justified it (both
  dimensions of cutover complete) is met, not leaving it running as
  permanent infrastructure nobody owns.
- Once `Reserve` commits in a different process's database, the free
  rollback a shared transaction used to provide is gone for good; a
  caller-tracked, explicitly-invoked compensating `Release` is what rebuilds
  it — proven not by inference but by directly querying stock before and
  after a declined/failed checkout and finding it unchanged.
- `Reserve`'s single conditional `UPDATE` is concurrency-safe without any
  application-level lock because Postgres's own row-level write lock
  serializes concurrent callers for the statement's duration — proven
  against two real concurrent RPC calls racing the last unit of stock, not
  asserted in prose.
- Inventory's cutover has two independent dimensions (checkout-time
  reserve/release, and `GET /api/inventory*` reads) that can move
  separately during a transition but are only exercised, end to end, as two
  locked-together configurations in this project's CI gate — and a dead
  downstream has to fail loudly on *both* surfaces it touches, each with
  its own correct status code, for the gate to mean anything.

Next: ch.20 turns from "how one more context left the monolith" back to the
outbox pattern itself, generalizing beyond Notification's single `order.placed`
event to the shape every future extraction in this book reuses.

---

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes 16/16 in `examples/04-inventory-service` (REST and
gRPC, including a concurrency race test stable across 5 repeated runs),
`ruff check` is clean, and `alembic upgrade head` seeds correctly. The full
cutover is verified live in `tooling/newman/GOLDEN-BASELINE.md`'s
NEWMAN-GRPC lane: 71/71 assertions green across both configurations,
net-zero stock confirmed by direct query, and a negative check that fails
strictly then recovers on restart. The Debezium CDC path is transition-only
infrastructure, exercised manually against the compose stack rather than by
the pytest/Newman CI gates.*
