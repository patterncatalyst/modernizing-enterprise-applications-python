# AGENTS.md -- 04-inventory-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r04 extraction of the `inventory` bounded context off `../00-monolith`
onto a standalone FastAPI service, `:8084` (ch.19, DRQ-039/DRQ-041/DRQ-042/
DRQ-044). Two surfaces:

- `GET /api/inventory` / `GET /api/inventory/{sku}` -- the lifted read
  surface, matching the monolith's `inventory/views.py` contract
  byte-for-byte.
- A **net-new gRPC server** on `:9004` (`CheckStock`/`Reserve`/`Release`/
  `GetStock`) -- the synchronous order<->inventory anti-corruption-layer
  contract. There is no Django original to lift here: the monolith's
  `reserve` concern lived in-process against a pessimistic-lock derived
  query, a fundamentally different mechanism from a server-side atomic
  conditional `UPDATE` exposed over gRPC.

This is the Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/04-inventory-service`
(Java/Quarkus) -- same role in the book, same chapter -- but it is its own
independent implementation (grpc.aio instead of Quarkus/Mutiny gRPC, aiokafka
instead of SmallRye Reactive Messaging for the transition-only CDC consumer).

The `.proto` contract (`proto/dev/patterncatalyst/inventory/v1/inventory.proto`)
and its generated stubs (`app/grpc_gen/`) were authored and committed by a
separate PROTO lane -- **this lane only imports them**
(`from app.grpc_gen import inventory_pb2, inventory_pb2_grpc`); never edit
`proto/` or `app/grpc_gen/` from here.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **Alembic 1.20.0**,
  **grpcio 1.84.0**, **protobuf 7.36.2**, **aiokafka 0.14.0** (transition-only
  CDC consumer). Dev-only: **pytest 9.1.1** + **pytest-asyncio 1.4.0** +
  **httpx 0.28.1**, **ruff 0.17.1**, **testcontainers 4.15.0**,
  **grpcio-tools 1.84.0**.

## Commands

```sh
uv sync --group dev

# One-time: creates the `inventory` schema + table + unique index on sku,
# then seeds the 3 demo skus:
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8084
uv run ruff check .
uv run pytest
```

`DATABASE_URL` (same convention as every other service in this project,
default `postgresql://monolith:monolith@localhost:5432/monolith`) is
normalized onto the asyncpg driver scheme by `app/db.py::resolve_database_url`.
`HTTP_PORT` (8084) and `GRPC_PORT` (9004) are independently overridable.
`INVENTORY_CDC_ENABLED` (default `false`), `KAFKA_BOOTSTRAP_SERVERS`,
`INVENTORY_CDC_TOPIC`, `INVENTORY_CDC_GROUP` configure the transition-only CDC
consumer (`app/cdc_consumer.py`) -- see `../CUTOVER.md`. All read via
`app/config.py::Settings.from_env()`.

## Structure

- `app/main.py` -- FastAPI app factory + lifespan. Builds the async engine/
  session factory, starts a `grpc.aio.server()` on `GRPC_PORT` sharing the
  SAME session factory as an asyncio task on the same event loop, and
  (only if `INVENTORY_CDC_ENABLED`) starts the CDC consumer -- all stopped
  cleanly on shutdown. `/health` reports `grpcServerListening` once the gRPC
  server has bound its port (a CI readiness signal).
- `app/routes.py` -- the two `/api/inventory*` HTTP endpoints.
- `app/service.py` -- read-path business logic (`list_all`/`get_by_sku`,
  raising `ResourceNotFound` for an unknown sku). The mutating
  `reserve`/`release` concern deliberately is NOT here -- it stays
  server-side on the gRPC path.
- `app/grpc_server.py` -- `InventoryGrpcServiceServicer`, implementing the
  generated `inventory_pb2_grpc.InventoryGrpcServiceServicer` interface.
  Each RPC opens its OWN async session (no FastAPI request scope to hook
  into for a gRPC call).
- `app/repository.py` -- async SQLAlchemy queries against the owned schema,
  including `reserve`/`release`'s single conditional/unconditional `UPDATE`
  statements (the concurrency-safety mechanism -- see its docstring).
- `app/schemas.py` -- Pydantic v2 `StockOut` (camelCase via `Field(alias=...)`).
- `app/models.py` -- SQLAlchemy declarative mapping for
  `inventory.inventory_items`.
- `app/db.py` -- async engine/session factory; sets
  `search_path=inventory,public` on every connection.
- `app/config.py` -- `Settings.from_env()`, read at call time.
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  ported from `02-review-service`/`03-notification-service`'s `app/errors.py`.
- `app/cdc_consumer.py` -- TRANSITION-ONLY, flag-gated OFF by default. See
  its module docstring and `../CUTOVER.md`.
- `app/grpc_gen/`, `proto/` -- generated gRPC stubs + the `.proto` contract.
  **Owned by the PROTO lane, not this one** -- import only, never edit.
- `migrations/` -- Alembic, async (`Connection.run_sync`),
  `version_table_schema="inventory"`. `versions/0001_...py` creates the
  schema + table + unique index on sku; `versions/0002_...py` seeds the 3
  demo skus (idempotent `ON CONFLICT (sku) DO NOTHING`).
- `tests/` -- REST contract tests (`test_inventory_rest.py`), gRPC servicer
  tests incl. the concurrency race proof (`test_inventory_grpc.py`), against
  a real, already-migrated-and-seeded Postgres. An autouse fixture
  (`conftest.py::reset_inventory_quantities`) restores the seed baseline
  after every test so order never matters.

## Contract notes (don't "fix" these -- they match the monolith/proto on purpose)

- REST JSON is **camelCase**, no trailing slash, same uniform error body as
  `00-monolith`'s `common/exceptions.py` -- see `README.md`'s endpoint table.
- The gRPC wire vocabulary (`stock_keeping_unit`/`display_name`/
  `unit_price_cents`/`on_hand_qty`) is DELIBERATELY DISTINCT from the REST/
  internal vocabulary (`sku`/`name`/`priceCents`/`quantityOnHand`) -- this IS
  the anti-corruption layer, not an inconsistency to reconcile.
- `Reserve`/`Release` are single atomic SQL statements, NOT
  read-then-write -- see `app/repository.py`'s docstrings for why that
  matters under concurrency. Don't "simplify" them into a `SELECT` followed
  by an `UPDATE`; that reintroduces the race the current design prevents.
- `Release` is intentionally unconditional and non-idempotent (an honest,
  documented limitation, not a bug) -- see `app/grpc_server.py`'s `Release`
  docstring and `../CUTOVER.md`.
- `app/cdc_consumer.py` is NOT used by CI and NOT part of this service's
  end-state -- don't wire it into the default test/dev path.

## Testing

Needs a reachable Postgres with this service's OWN `inventory` schema
already migrated and seeded:

```sh
docker run -d --name mea-inventory-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
uv run alembic upgrade head
uv run pytest
```

No Kafka broker is required for any test in this suite -- the CDC consumer
is flag-gated off, and the gRPC tests call `InventoryGrpcServiceServicer`'s
coroutine methods directly rather than through a live network listener.
