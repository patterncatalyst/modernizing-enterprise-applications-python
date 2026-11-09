---
title: "CDC, Transaction Log Tailing & Extraction 3: Inventory"
order: 19
part: "Data Across the Seam"
description: "Log tailing bridges the monolith's live inventory table during cutover, a gRPC contract acts as the anti-corruption layer, an atomic conditional UPDATE reserves stock, and an explicit Release replaces the rollback a shared transaction provided."
duration: 60 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why a synchronous, mutating collaborator (Inventory's `Reserve` and `Release`) is harder to extract than a read-only leaf or an asynchronous consumer.
- Keep a gRPC wire vocabulary (`stock_keeping_unit`, `on_hand_qty`) distinct from the monolith's (`sku`, `quantity_on_hand`) and put the translation in `RemoteInventoryClient` and `InventoryGrpcServiceServicer`.
- Configure a Debezium Postgres connector (`pgoutput`, `snapshot.mode: initial`, `REPLICA IDENTITY FULL`) for a one-time backfill, and retire it afterward.
- Apply Debezium's read, create, update and delete events through one idempotent `INSERT ... ON CONFLICT DO UPDATE`.
- Reserve stock with a single conditional `UPDATE` so Postgres's row lock serializes concurrent callers.
- Replace the free rollback of a shared transaction with an explicit compensating `Release`, and verify it by querying stock before and after a failed checkout.
- Read a dead inventory service as a 502 on proxied reads and a 503 `INVENTORY_UNAVAILABLE` on checkout.

## Why this matters

Giving Inventory its own schema, moving `reserve` and `release` across a network boundary, bridging the transition without losing a reservation and cutting `OrderItem`'s foreign key loose are one extraction. It is the first one that moves a synchronous write. The Review extraction moved a read, and the Notification extraction moved a one-way event. Checkout cannot proceed without an answer to the stock decrement, and once that decrement commits in another process's database, no shared write-ahead log exists for Postgres to undo it with.

The code is in `examples/04-inventory-service/` (FastAPI plus gRPC) and `examples/00-monolith/order/` (the client-side ACL and the `grpc`-mode checkout). `MIGRATION.md` and `CUTOVER.md` in the service directory record the measured numbers cited below.

## Why Inventory is the hardest cut so far

`place_order()` cannot return `201 CONFIRMED` until stock is secured, and it cannot treat "the inventory service didn't answer" the same as "there wasn't enough stock." Three things differ from the earlier extractions:

1. **The seam is synchronous.** A gRPC call carries `Reserve`, `Release`, `CheckStock` and `GetStock`. Review's synchronous calls were read-only.
2. **The data has to move out from under a live writer.** `inventory_items` has real rows the monolith has been writing since the start, and a one-time backfill has to bridge the gap during cutover.
3. **The free rollback disappears.** One `transaction.atomic()` spans all five contexts checkout touches (the transaction smell in `examples/00-monolith/SMELLS.md`), so one `ROLLBACK` unwinds everything. After `Reserve` commits in Inventory's database, that log no longer spans both writes, and the rollback has to be rebuilt by hand.

## Pattern: Anti-Corruption Layer (the proto as the seam)

`CheckStock`, `Reserve`, `Release` and `GetStock` are defined in `proto/dev/patterncatalyst/inventory/v1/inventory.proto` and compiled into both the service's `app/grpc_gen/` and the monolith's `order/grpc_gen/` from the same source. The proto's header comment states its job:

```proto
// The gRPC contract IS the anti-corruption layer for the
// synchronous order<->inventory seam: a strongly-typed, versioned wire
// vocabulary (stock_keeping_unit/display_name/unit_price_cents/
// on_hand_qty) deliberately DISTINCT from the monolith's domain
// vocabulary (sku/name/priceCents/quantityOnHand) so the ACL earns its
// keep translating between the two, rather than the two shapes
// happening to already agree.
```

{% include excalidraw.html file="inventory-grpc-proto-acl" alt="The monolith's domain vocabulary, the distinct wire vocabulary in inventory.proto, and inventory-service's own domain vocabulary, each translated by a client-side and a server-side ACL" caption="Figure 19.1: Two separate vocabularies meet only at the wire, and the proto is the anti-corruption layer between them." %}

A proto enforces more than a Pydantic model the consumer owns. Field names and numbers are frozen and versioned and generated into typed stubs on both sides, so a rename breaks at code-generation time, not on a malformed payload. Each side still translates for itself. `order/inventory_client.py::RemoteInventoryClient` is the only place in the monolith that imports `inventory_pb2`:

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

`app/grpc_server.py::InventoryGrpcServiceServicer` translates the other way. A `grpc.RpcError` on any call (timeout, `UNAVAILABLE`, dead connection) becomes `InventoryServiceUnavailable`, which is separate from `InsufficientStock`. An unreachable service and an out-of-stock sku are different failures with different statuses (503 and 409), and confusing them is a correctness bug.

## Pattern: Change Data Capture

The gRPC seam doesn't move the rows already in `inventory_items`, and Inventory's schema starts empty. Flipping straight from "the monolith owns the table" to "Inventory owns an empty table" would make every row in stock vanish on day one. `app/cdc_consumer.py` bridges that gap and is retired after cutover.

The mechanism is transaction-log tailing, not polling. `infra/debezium/inventory-connector.json` configures a Debezium Postgres connector against `public.inventory_items` using logical replication, which repurposes the write-ahead log (WAL) Postgres already keeps for crash recovery as a change-event source:

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

`snapshot.mode=initial` makes it a backfill: on first start the connector emits one `op=r` event per existing row, then streams `op=c`, `u` and `d` events for every later insert, update and delete. `scripts/register-debezium.sh` first runs `ALTER TABLE public.inventory_items REPLICA IDENTITY FULL`, so update and delete events carry a complete before-image and not just the primary key. Without it a delete event carries only an id, not the row the consumer needs to apply it.

`InventoryCdcConsumer` is an `aiokafka` consumer that applies every event through one idempotent upsert:

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

Read, create and update events all go through this `INSERT ... ON CONFLICT DO UPDATE`, and deletes through a keyed `DELETE`. An upsert fits here because a row update has no natural "already applied" marker the way a notification keyed on `order_id` does. Both operations converge to the same end state when Kafka redelivers an event.

{% include excalidraw.html file="cdc-backfill-then-retire" alt="Transaction-log tailing end to end: Postgres WAL, replication slot, Debezium Postgres connector, Kafka topic, and InventoryCdcConsumer's upsert into the owned schema, with the retire runbook shown as the step that follows cutover" caption="Figure 19.2: CDC tails the WAL for a one-time backfill and transition sync, then is retired." %}

### Retire the tailed log

The consumer is gated by `INVENTORY_CDC_ENABLED`, default `false`. It is a staged-rollout concern, not Inventory's end state: the default dev and CI posture seeds Inventory directly with `migrations/versions/0002_seed_inventory.py` (`SKU-WIDGET-001` at 100, `SKU-GADGET-002` at 50, `SKU-GIZMO-003` at 5).

The retire runbook in `CUTOVER.md` requires both of these:

1. The monolith's checkout calls Inventory's gRPC `Reserve` and `Release` exclusively, so nothing on the monolith side is left to stream from.
2. The monolith's `public.inventory_items` table and the Django `inventory` app are decommissioned.

`scripts/retire-debezium.sh` then deletes the connector and drops both the replication slot and the publication, because an undrained slot retains WAL on the source Postgres indefinitely and fills the disk. A 404 on an already-deleted connector counts as retired. Dropping the slot retries briefly while Postgres still reports it active, since Kafka Connect's replication connection takes a moment to close. Log-based CDC costs a slot, a connector and a Connect runtime, so it is worth paying for the length of a cutover window, and the runbook that retires it is a deliverable like the connector config.

## Two phases, and a gRPC server with no Django original

`MIGRATION.md` measures what a Django-ORM-lifted Phase A would have cost. This extraction is a hybrid. The REST read surface (`GET /api/inventory`) has a monolith original to lift, so it gets the Phase A and Phase B treatment. The gRPC mutating surface has no original: the monolith's `reserve` ran against a pessimistic-lock query inside the same Django transaction as the rest of checkout, and a gRPC call from another process cannot join that transaction. No smaller Phase A of an atomic check-and-decrement over gRPC exists to lift, so the mutating surface is Phase B by construction.

| Metric | Phase A (proxy: `django.setup()` + `import fastapi, uvicorn`) | Phase B (shipped, includes `grpc` + `aiokafka`) |
|---|---|---|
| Cold interpreter floor | 0.01 s | 0.01 s |
| Import/startup time (3-run avg) | 0.264 s | 0.312 s |
| Import-only RSS | ~74.3 MB | ~90.3 MB |
| Running server RSS (after 20 requests, gRPC server also bound) | not measured (no server built) | ~105.8 MB |

Phase B costs more at import (the `grpc` C extension and `aiokafka`'s import graph) and at runtime. Phase A measures a read-only surface with no gRPC at all, while Phase B's running number includes a second live server on `:9004` beside HTTP on `:8084`.

## Where the free rollback went

`order/services.py::place_order()` dispatches on `settings.INVENTORY_MODE` between two checkout strategies:

{% include codetabs.html langs="local mode: free rollback|grpc mode: explicit compensation" %}

```python
# order/services.py -- _place_order_local, UNCHANGED from the monolith
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
# order/services.py -- _place_order_remote
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

`_place_order_remote`'s docstring states the crux: a remote `Reserve` is not part of this process's Postgres transaction and cannot be rolled back by it. In `local` mode `reserve()` sits inside the same `transaction.atomic()` as the order row, the charge and the dispatch, so a `PaymentDeclined` unwinds the reservation with everything else. In `grpc` mode `client.reserve()` runs before the `atomic()` block opens, against another process's Postgres. By the time a decline happens, the remote `UPDATE` has committed on Inventory's own WAL.

{% include excalidraw.html file="reserve-release-saga-lite" alt="Before and after panels: a single local transaction.atomic() gives a free rollback across reserve, order, payment and shipping, while the gRPC Reserve commits outside any local transaction and an explicit compensating Release is wired to PaymentDeclined and ShippingFailed" caption="Figure 19.3: Reserve and Release across the boundary, and where the free rollback went." %}

So `except Exception: _release_reserved(client, reserved); raise` is the mechanism that keeps checkout behavior identical across the two modes. `_reserve_lines_remote` tracks every `(sku, quantity)` it has reserved. When anything fails, whether a later line's `InsufficientStock`, an `InventoryServiceUnavailable`, or a `PaymentDeclined` or `ShippingFailed` raised from the local block, every reserved sku gets a `Release` before the exception propagates. This is a choreographed saga in its smallest form: no coordinator, only the caller that knows what it reserved undoing it.

## Reserve's atomic conditional decrement, and Release its mirror

The compensation only works because `Reserve` is correct under concurrency. `app/repository.py::reserve` earns that with one SQL statement:

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

A `SELECT` followed by an `UPDATE` leaves a window in which a second caller reads the same starting quantity, which is the lost-update race and oversells stock. A single conditional `UPDATE` has no window, because Postgres holds a row-level write lock for the statement. Two concurrent `Reserve(sku, 1)` calls against one remaining unit serialize on that lock. The first commit leaves `quantity_on_hand` below the second's `>= qty` predicate, so exactly one `UPDATE` affects a row (`reservation_ok=true`) and the other affects none (`reservation_ok=false`, no decrement). No application lock, no `SELECT ... FOR UPDATE` and no version column are needed.

`Release` is the mirror statement (`quantity_on_hand = quantity_on_hand + :qty`), but unconditional and with no upper bound. It carries no idempotency key, so a retried `Release` whose first attempt already landed over-restores stock. The docstrings in `app/repository.py::release` and the servicer name this as a limitation. The fix is an idempotency key per reservation or a ledger of reserve and release pairs, which belongs with a full saga treatment.

## `OrderItem`'s foreign key, cut

`_reserve_lines_remote` fills `OrderItem`'s denormalized fields from the `GetStock` reply, not from a local join:

```python
stock = client.get_stock(sku)
line_snapshots.append({
    "sku": stock.sku,
    "item_name": stock.name,
    "unit_price_cents": stock.unit_price_cents,
    "quantity": quantity,
})
```

`OrderItem.inventory_item` no longer exists in either mode. `local` mode reads the row `inventory_services.reserve()` returns in process, and `grpc` mode reads the same facts off the reply. Both write the identical `OrderItem` shape, so nothing downstream can tell which mode wrote it.

## Cutover: two independent dimensions

| Dimension | Flag | Lives in | Controls |
|---|---|---|---|
| Checkout-time reserve/release | `INVENTORY_MODE` (`local`\|`grpc`) | the monolith, `config/settings.py` | who answers the synchronous write path inside `place_order()` |
| `GET /api/inventory*` reads | `STRANGLER_INVENTORY_ENABLED` | the strangler proxy, `examples/01-strangler-proxy/app/config.py` | who answers the read path |

{% include excalidraw.html file="two-cutover-dimensions" alt="The two independent cutover flags as a 2x2 grid, marking the two locked-together corners that are exercised against the two split corners that are sound only during the CDC-backfilled transition window" caption="Figure 19.4: Two independent cutover dimensions, locked together in the exercised runs." %}

The flags can move separately. A split combination (`grpc` reserve with monolith-served reads, or the reverse) is sound during the CDC-backfilled window, when both copies are kept consistent. As a steady state, only the two locked-together corners are exercised. The gRPC lane in `tooling/newman/GOLDEN-BASELINE.md` runs the unedited `mea.postman_collection.json` against both:

| Run | `INVENTORY_MODE` | `STRANGLER_INVENTORY_ENABLED` | Result |
|---|---|---|---|
| A: fully gRPC | `grpc` | `true` | 71/71 assertions green, 0 failed |
| B: fully local (reversibility) | `local` | unset | 71/71 assertions green, 0 failed, byte-identical shape to A |

Querying `GET /api/inventory/SKU-WIDGET-001` directly around the payment-declined and shipping-failed scenarios in run A shows `quantityOnHand` held at 96:

```
Before:           {"quantityOnHand": 96}
After decline:     {"quantityOnHand": 96}   (PAYMENT_DECLINED, 402)
After ship-fail:   {"quantityOnHand": 96}   (SHIPPING_FAILED, 422)
```

In `grpc` mode that net-zero is `_release_reserved` firing a `Release` RPC, not Postgres's rollback. Run B's byte-identical result confirms the flip is reversible.

## The negative check: both surfaces fail loudly

With both flags on, killing `examples/04-inventory-service` must break each surface in its own way. Proxied reads return `502 Bad Gateway`, the documented fail-safe for a dead upstream (4/4 assertions failed, newman exit 1):

```
01. AssertionError  Inventory list returns 200
                    expected response to have status code 200 but got 502
```

`POST /api/orders` returns `503`, not a hang and not a silently confirmed order (9/10 assertions failed, newman exit 1):

```json
{"error":"INVENTORY_UNAVAILABLE","message":"Inventory service unavailable: StatusCode.UNAVAILABLE failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:9004: Failed to connect to remote host: Connection refused","timestamp":"2026-10-16T14:08:22.850691+00:00"}
```

This is `RemoteInventoryClient._unary()` mapping `grpc.RpcError` to `InventoryServiceUnavailable`. An operator deciding whether to page someone needs the difference between "we're sold out" (409 `OUT_OF_STOCK`) and "a dependency is down" (503). Restarting the service returns both folders to green: the Inventory contract folder at 11/11 and the happy-path scenario at 14/14. A control run with no flags leaves the existing callers untouched; the Notification folder still halts where it always has, at the baseline's 60/60.

No Kafka broker ran for the gRPC lane. Inventory's end state never depends on the CDC consumer, so the gRPC server and the REST surface are backed entirely by its own seeded schema. A production rollout runs the real backfill during its transition window, and the run proves the steady state that window leads to.

> **Decision**
>
> Extract a synchronous write only once the monolith has an explicit compensation for every step that can fail after the remote commit. Use log-based CDC for a one-time backfill during the cutover window, and retire the connector, slot and publication when the monolith stops writing the table.

> **🤖 Explore with your agent**
>
> "In examples/00-monolith/order/services.py, `_place_order_remote` reserves stock over gRPC before the local `transaction.atomic()` block. Add a third failure point after the order is saved, then show that `_release_reserved` restores `quantityOnHand` for `SKU-WIDGET-001` in examples/04-inventory-service, using the rule that every failure after a remote commit needs an explicit compensating call."
>
> Check: `GET http://localhost:8084/api/inventory/SKU-WIDGET-001` returns the same `quantityOnHand` before and after the failed checkout.

## Build, run, observe

Start the full topology, with inventory in `grpc` mode and every proxy flag on, and run the unedited collection through the proxy. The demo was built for the payment cutover and includes the inventory seam:

```bash
bash demos/demo-payment-cutover.sh
```

That script brings up Postgres, Kafka, inventory-service (HTTP `:8084`, gRPC `:9004`), the other services, the monolith and the strangler proxy (`:8888`), and tears everything down on exit. To run the service alone:

```bash
cd examples/04-inventory-service
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8084
uv run pytest
```

Reserve over gRPC with `grpcurl`, passing the `.proto` because reflection is off:

```bash
grpcurl -plaintext -import-path proto -proto dev/patterncatalyst/inventory/v1/inventory.proto \
  -d '{"stock_keeping_unit":"SKU-WIDGET-001","requested_qty":5}' \
  localhost:9004 dev.patterncatalyst.inventory.v1.InventoryGrpcService/Reserve
```

Experiments:

- Stop inventory-service with both flags on. Proxied reads return 502 and `POST /api/orders` returns 503 `INVENTORY_UNAVAILABLE`, never 409.
- Set `INVENTORY_MODE=local` and unset `STRANGLER_INVENTORY_ENABLED`. The collection still passes 71/71.
- Place an order with a declined payment and query `GET /api/inventory/SKU-WIDGET-001` before and after. `quantityOnHand` is unchanged.

## For deeper coverage

- `examples/04-inventory-service/CUTOVER.md`: both cutover dimensions and the CDC retire runbook.
- `examples/04-inventory-service/MIGRATION.md`: the Phase A and Phase B measurements.
- `tooling/newman/GOLDEN-BASELINE.md`: the gRPC lane and negative checks.
- Debezium documentation, PostgreSQL connector: logical decoding, `pgoutput` and snapshot modes.
