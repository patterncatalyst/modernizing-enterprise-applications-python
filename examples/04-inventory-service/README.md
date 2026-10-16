# 04-inventory-service

**ch.19, DRQ-039/DRQ-041/DRQ-042/DRQ-044 -- r04.** The monolith's
(`../00-monolith`) `inventory` bounded context, extracted onto a standalone
**FastAPI** service with TWO protocol surfaces:

- `GET /api/inventory` / `GET /api/inventory/{sku}` on **`:8084`** -- the
  lifted read surface, matching the monolith's `inventory/views.py` contract
  byte-for-byte.
- A **net-new gRPC server** on **`:9004`** (`CheckStock`/`Reserve`/`Release`/
  `GetStock`) -- the synchronous order<->inventory anti-corruption-layer
  contract. There is no Django original for this surface: the monolith's
  `reserve` concern lived in-process against a pessimistic-lock derived
  query, a fundamentally different mechanism from a server-side atomic
  conditional `UPDATE` exposed over the network.

See `MIGRATION.md` for the full two-phase write-up, `CUTOVER.md` for the two
cutover dimensions (REST read-path strangling + the CDC consumer's retire
runbook), and `AGENTS.md` for agent-facing structure notes.

## Why own schema, not shared

Same rationale as `03-notification-service`'s DRQ-035 (contrast with
`02-review-service`'s shared-schema DRQ-028 posture): the gRPC `Reserve`/
`Release` mutating hot path needs this service's own atomic, concurrency-safe
`UPDATE` statements against rows it alone owns. Sharing the monolith's table
would mean two writers -- the monolith's own checkout path and this
service's gRPC server -- racing on the same rows with no way to reconcile
them. This service's `inventory` Postgres schema is created, seeded, and
migrated entirely by its own Alembic chain from day one.

## The gRPC contract IS the anti-corruption layer

The wire vocabulary (`stock_keeping_unit`/`display_name`/`unit_price_cents`/
`on_hand_qty`, see `proto/dev/patterncatalyst/inventory/v1/inventory.proto`)
is deliberately DISTINCT from the internal/REST vocabulary (`sku`/`name`/
`priceCents`/`quantityOnHand`) so the order-side ACL's message translator
earns its keep converting between the two, instead of the two shapes
happening to already agree.

| RPC | Mutates state? | Semantics |
|---|---|---|
| `CheckStock(sku, requestedQty)` | No | `available` = can `requestedQty` be satisfied right now |
| `Reserve(sku, requestedQty)` | Yes | Atomic check-and-decrement. `reservationOk=false` + unchanged `onHandQty` means insufficient stock -- no decrement happened |
| `Release(sku, requestedQty)` | Yes | Compensating re-increment -- the monolith calls this when a later checkout step (e.g. payment) fails after a successful `Reserve` |
| `GetStock(sku)` | No | Full read of one sku's current stock record -- the content-enricher fetch target for the order-side ACL |

### Reserve: atomic, concurrency-safe, no application lock

`app/repository.py::reserve` issues a SINGLE conditional statement:

```sql
UPDATE inventory.inventory_items
   SET quantity_on_hand = quantity_on_hand - :qty
 WHERE sku = :sku AND quantity_on_hand >= :qty
```

and reports the rows-affected count. Exactly 1 means the reservation
succeeded atomically; 0 means insufficient stock (or an unknown sku) and NO
decrement happened. This is **concurrency-safe without an explicit
application-level lock** -- no `SELECT ... FOR UPDATE`, no optimistic-locking
version column -- because Postgres takes a row-level write lock for the
duration of the `UPDATE` statement itself: two concurrent `Reserve` calls
racing the same row serialize on that lock, and whichever commits first
leaves `quantity_on_hand` below the other's `>= :qty` predicate. Proven by
`tests/test_inventory_grpc.py::test_reserve_concurrent_requests_for_last_unit_exactly_one_succeeds`.

### Release: an honest, documented limitation

`app/repository.py::release` issues the inverse, UNCONDITIONAL statement
(`... SET quantity_on_hand = quantity_on_hand + :qty WHERE sku = :sku`) and
carries no dedupe/idempotency key. A retried `Release` call whose effect
already landed server-side would over-restore stock. This is deliberately
NOT solved here -- a full fix (an idempotency key per reservation/
compensation, or a saga ledger) is out of scope for this chapter's scope
discipline; see `app/grpc_server.py::InventoryGrpcServiceServicer.Release`'s
docstring and `CUTOVER.md` for the deferral's record.

## REST endpoints

CamelCase JSON, **no trailing slash** (`redirect_slashes=False`, same
contract posture as every other service in this project).

| Method | Path | Notes |
|---|---|---|
| GET | `/api/inventory` | all stock items |
| GET | `/api/inventory/{sku}` | `404 NOT_FOUND` (uniform body) for an unknown sku |
| GET | `/health` | reports `grpcServerListening` (CI readiness signal) |

Response body: `{sku, name, priceCents, quantityOnHand}` -- matches
`inventory.serializers.InventoryItemSerializer`'s field list exactly. Error
body (every non-2xx response): `{"error": "<CODE>", "message": ...,
"timestamp": ...}`.

## Persistence: owned schema, Alembic-migrated and seeded

`app/db.py` sets `search_path=inventory,public` on every connection AND
`app/models.py::InventoryItem` declares `schema="inventory"` explicitly --
the search path is a convenience, the explicit schema is the correctness
guarantee. `migrations/versions/0001_create_inventory_schema.py` creates the
schema, table, and a unique index on `sku`;
`migrations/versions/0002_seed_inventory.py` idempotently seeds the three
demo skus with the SAME names/prices/quantities as the monolith's own seed
(`../00-monolith/common/management/commands/seed.py`):

| sku | name | priceCents | quantityOnHand |
|---|---|---|---|
| `SKU-WIDGET-001` | Standard Widget | 1999 | 100 |
| `SKU-GADGET-002` | Deluxe Gadget | 4999 | 50 |
| `SKU-GIZMO-003` | Pocket Gizmo | 999 | 5 (deliberately low, exercises the insufficient-stock path) |

## Transition-only CDC consumer

`app/cdc_consumer.py` is a flag-gated (`INVENTORY_CDC_ENABLED`, default
`false`) `aiokafka` consumer of a Debezium change stream off the monolith's
`public.inventory_items` table, for the cutover window ONLY -- see
`CUTOVER.md`. It is not used by CI and not part of this service's end-state
story; the Alembic seed migration above is this service's own, independent
system of record once cutover completes.

## Quickstart

```sh
uv sync --group dev

# One-time: create + seed this service's own `inventory` schema.
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8084
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`
(the INFRA lane's compose stack). A quick standalone Postgres for local use:

```sh
docker run -d --name mea-inventory-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

### Try it

```sh
curl "http://localhost:8084/api/inventory"
curl -i "http://localhost:8084/api/inventory/NOPE"   # 404, uniform body
curl "http://localhost:8084/health"                   # {"status":"ok","grpcServerListening":true}
```

gRPC, via `grpcurl` (reflection is not enabled, so pass the `.proto` file):

```sh
grpcurl -plaintext -import-path proto -proto dev/patterncatalyst/inventory/v1/inventory.proto \
  -d '{"stock_keeping_unit":"SKU-WIDGET-001","requested_qty":5}' \
  localhost:9004 dev.patterncatalyst.inventory.v1.InventoryGrpcService/Reserve
```

## Cutover

See `CUTOVER.md` for both cutover dimensions: (1) the strangler proxy
(`../01-strangler-proxy`) flipping `STRANGLER_INVENTORY_ENABLED=true` so
`/api/inventory*` and the order<->inventory gRPC calls route here instead of
the monolith, and (2) retiring the transition-only CDC consumer once this
service's own schema is the system of record.

## Testing

```sh
uv run pytest
uv run ruff check .
```

See `AGENTS.md` for the exact setup commands.

## Container

```sh
docker build -f Containerfile -t mea-inventory-service:r04 .
docker run --rm -p 8084:8084 -p 9004:9004 \
  -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith \
  mea-inventory-service:r04
```

UBI 10 (`ubi10/python-314-minimal`, the same verified tag every other service
in this project uses), multi-stage `uv sync`, non-root (UID 1001, GID 0). The
container's `CMD` runs `alembic upgrade head` before starting uvicorn.

## Structured logging

Rotating file logs land in `logs/inventory-service.log` alongside console
output (see `app/main.py::_configure_logging`), same convention as the other
services.
