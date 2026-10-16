# AGENTS.md -- 07-order-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r07 **CQRS** extraction of the `order` bounded context -- the LAST
extraction in this series -- off `../00-monolith` onto a standalone
**FastAPI** service, `:8088`. See `README.md` for the full picture;
`MIGRATION.md` for the lift-and-reshape write-up (including why this lane
skips Phase A outright); `EVENTS.md` for the event contracts; `CUTOVER.md`
for why this lane has no reversible flag of its own.

This service has no monolith original for its read model
(`order_view`, net-new) and no monolith original for its checkout write path
(always gRPC-reserve, always choreographed+orchestrated) -- only the GET
contract's field list, the reserve/release gRPC vocabulary, the saga
status-transition guards' INTENT, and the stable Release idempotency key are
lifted. Don't go looking for a byte-for-byte Django original beyond those.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **Alembic 1.20.0**,
  **aiokafka 0.14.0**, **grpcio 1.84.0** + **protobuf 7.36.2**. Dev:
  **pytest 9.1.1** + **pytest-asyncio 1.4.0**, **httpx 0.28.1**, **ruff
  0.17.1**, **testcontainers 4.15.0**, **grpcio-tools 1.84.0** (only used to
  regenerate `app/grpc_gen/` -- see "Regenerating the gRPC stubs" below).

## Commands

```sh
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8088
uv run ruff check .
uv run pytest -m "not integration"   # needs a reachable, migrated Postgres only
uv run pytest -m integration         # Testcontainers Kafka+Postgres + an in-process fake gRPC inventory server
```

See `README.md`'s "Commands" section for env var defaults.

## Structure

- `app/main.py` -- app factory + lifespan (engine/session factory, starts
  `OrderSagaConsumer` + `OutboxRelay`), `/health`.
- `app/routes.py` -- `POST /api/orders`, `GET /api/orders[/{id}]`. Reads call
  `app/repository.py`'s `order_view`-only functions EXCLUSIVELY -- never
  import `Order`/`OrderItem` here.
- `app/service.py` -- `place_order` (the command) + `handle_payment_captured`/
  `handle_payment_declined`/`handle_shipment_dispatched`/
  `handle_shipment_failed` (the four reactions) + `rebuild_order_view`. This
  is the ONE module that decides transaction boundaries at the call-site
  level (gRPC calls always happen in their own `async with
  AsyncInventoryClient(...)` block, OUTSIDE any `session_factory()` block).
- `app/repository.py` -- the ONLY module that touches `app/models.py`'s
  ORM classes directly. Every write function owns its own commit/rollback.
  `create_order_with_outbox_and_view` and `transition_order_status_with_view`
  are the two functions implementing the "aggregate + order_view + (outbox)
  in one transaction" guarantee -- if you add a new write path, it MUST go
  through one of these two shapes (or a new function following the same
  discipline), never a bare `session.add(Order(...))` from `app/service.py`.
- `app/inventory_client.py` -- `AsyncInventoryClient`, `grpc.aio`-based.
  Translates `app/grpc_gen/`'s raw proto types into `StockSnapshot`/
  `ReserveResult` dataclasses; never let a raw proto message escape this
  module.
- `app/consumer.py` -- `OrderSagaConsumer`, one `aiokafka` consumer group,
  four topics, a `_dispatch` method keyed by topic name.
- `app/relay.py` -- `OutboxRelay`, polls `order_svc.outbox`, publishes
  `order.placed`.
- `app/models.py` -- the 5-table CQRS schema. `SCHEMA = "order_svc"` is
  exported and reused by `migrations/env.py`/`migrations/versions/
  0001_create_order_schema.py` -- don't hard-code the literal string
  `"order_svc"` a second time anywhere; import `SCHEMA`.
- `app/schemas.py` -- Pydantic v2. `order_view_to_out` is the ONE function
  that bridges `OrderView`'s column names (`order_id`) onto `OrderOut`'s
  wire field names (`id`) -- route handlers call this, never construct
  `OrderOut` by hand.
- `app/grpc_gen/`, `proto/` -- vendored gRPC stubs + the `.proto` contract,
  generated from `04-inventory-service/proto/.../inventory.proto` (see
  "Regenerating the gRPC stubs" below). Byte-identical to the canonical copy
  -- don't hand-edit the `.proto` here; if the contract changes, copy the
  canonical file over this one and regenerate.
- `tests/unit/fakes.py` -- `FakeInventoryClient`, a Kafka-free, gRPC-free
  test double. `install_fake_inventory_client(monkeypatch, fake)` patches
  `app.service.AsyncInventoryClient` -- the ONLY place `app/service.py`
  constructs the real client, so this one patch covers `place_order` and
  both compensating reactions.
- `tests/integration/conftest.py` -- `_FakeInventoryServicer`, a REAL
  `grpc.aio.server()` bound to an ephemeral localhost port, implementing the
  SAME servicer interface `04-inventory-service/app/grpc_server.py` does.
  Integration tests exercise the real `AsyncInventoryClient` against this
  real (if minimal) network listener -- not mocked away like the unit-test
  double.

## Regenerating the gRPC stubs

```sh
cd examples/07-order-service
uv run python -m grpc_tools.protoc \
  -I proto/dev/patterncatalyst/inventory/v1 \
  --python_out=app/grpc_gen --grpc_python_out=app/grpc_gen \
  proto/dev/patterncatalyst/inventory/v1/inventory.proto
# then re-apply the import-path fixup scripts/gen-proto.sh documents:
sed -i \
  -e 's/^import inventory_pb2 as inventory__pb2$/from . import inventory_pb2 as inventory__pb2/' \
  app/grpc_gen/inventory_pb2_grpc.py
```

`../../scripts/gen-proto.sh` regenerates this service's stubs too (it covers
the canonical `04-inventory-service` proto plus the three vendored copies in
`00-monolith`, `07-order-service`, and `08-graphql-gateway`), following its
`-I`/import-fixup conventions. `proto/dev/patterncatalyst/inventory/v1/
inventory.proto` is byte-identical to `04-inventory-service/proto/.../
inventory.proto`, and `scripts/check-proto-drift.sh` fails if any of the four
copies diverge. Run `scripts/gen-proto.sh` after any change to the canonical
proto, then confirm `scripts/check-proto-drift.sh` exits 0.

## Contract notes (don't "fix" these -- they match the design intent on purpose)

- `POST /api/orders` returns **`202`**, never `201` -- see `README.md`.
- Reads are `order_view`-only -- see `app/repository.py`'s module docstring.
- The schema is `order_svc`, not `order` -- see `app/db.py`'s docstring.
- `app/service.py`'s four `handle_*` reactions each open a sub-transaction
  for the read-before-release guard, release over gRPC OUTSIDE that
  transaction, then open a SECOND sub-transaction for the atomic
  conditional-UPDATE + `order_view` upsert. Don't try to collapse this into
  one transaction spanning the gRPC call -- a network call inside an open
  DB transaction holding a row lock is exactly the anti-pattern
  `00-monolith/order/services.py`'s own module docstring (the
  `_place_order_remote`/`_place_order_choreographed` comparison) warns
  against for `place_order` itself.

## Testing

```sh
docker run -d --name mea-order-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
uv run alembic upgrade head
uv run pytest -m "not integration"   # 24 tests, no Kafka, no gRPC server needed

uv run pytest -m integration         # 3 tests, Testcontainers-managed Kafka + Postgres,
                                      # plus an in-process fake gRPC inventory server
```
