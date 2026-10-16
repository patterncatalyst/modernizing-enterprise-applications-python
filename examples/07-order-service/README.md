# 07-order-service

**r07 -- the FINALE.** The monolith's (`../00-monolith`) `order` bounded
context -- the god `place_order()` plus its four saga reactions -- extracted
onto a standalone **FastAPI** service on **`:8088`**, built **CQRS from day
one**: a command side (the write aggregate + this service's own transactional
outbox) and a read side (`order_view`, projected in the SAME local
transaction as every write -- every `GET` is served from `order_view` only,
never from the write tables).

This is the LAST extraction in the series, and it is deliberately the
hardest: `order` was the one context every other extraction (`inventory`,
`payment`, `shipping`) had to leave a seam for. By r07, every one of those
seams already exists --

- `app/inventory_client.py` is a **gRPC CLIENT** of `04-inventory-service`
  (`grpc.aio`, never a listener): `Reserve`/`Release`/`GetStock`, the same
  anti-corruption-layer contract `00-monolith/order/inventory_client.py`
  already established, re-authored async for FastAPI's event loop.
- `app/consumer.py` consumes the SAME four topics
  `00-monolith/order/management/commands/order_saga_listener.py` does --
  `payment.captured`/`payment.declined`/`shipment.dispatched`/
  `shipment.failed` -- in one consumer group (`order-service`).
- `app/relay.py` produces `order.placed` via this service's OWN
  transactional outbox, the same frozen contract `05-payment-service`'s own
  `order.placed` consumer already reacts to.

So this service is not inventing new collaborators; it is the LAST piece
that makes every existing seam real, end to end.

See `MIGRATION.md` for the lift-and-reshape write-up (including why this is
a CQRS rewrite with no two-phase lift), `EVENTS.md` for the full event
contracts (produced and consumed), `CUTOVER.md` for how this fits into the
overall strangler cutover, and `AGENTS.md` for agent-facing structure notes.

## Why CQRS, and why no Phase A

Every prior lane in this series followed the project's two-phase policy
(Phase A: a thin FastAPI shim reusing the monolith's Django ORM for reads;
Phase B: the idiomatic rewrite). This lane skips Phase A outright, for a
reason specific to CQRS: Phase A's entire premise is "the read surface can
be served by querying the monolith's existing table shape through a thin
shim." That premise does not hold here, because the read surface THIS
service ships (`order_view`, a denormalized projection with inline JSON
items) has no equivalent shape in the monolith's `orders`/`order_items`
tables to shim against -- there is nothing non-trivial for an illustrative
Phase A to demonstrate beyond "query two joined tables," which teaches
nothing about the CQRS split this lane exists to build. The command side has
the same story every choreographed/orchestrated lane's Phase A already had
(`05-payment-service`/`06-shipping-service`): there is no synchronous
Django original for an async, gRPC-reserving, outbox-writing checkout to
lift.

## The write/read split

- **Write** (`app/models.py`): `customers` (OWNED master data -- see
  "Customer FK -> snapshot" below), `orders` (the aggregate root),
  `order_items` (sku/quantity/unit_price_cents snapshots, no FK to
  inventory), `outbox` (this service's own transactional outbox).
- **Read** (`app/models.py::OrderView`): `order_view`, ONE row per order,
  upserted -- never appended to -- in the SAME local transaction as every
  write to the aggregate. `app/routes.py`'s `GET` handlers query ONLY this
  table. `app/service.py::rebuild_order_view` proves the projection is
  rebuildable from the aggregate at any time, never a second source of
  truth.

Every write path in this service (`app/repository.py::
create_order_with_outbox_and_view`, `transition_order_status_with_view`)
upserts `order_view` in the SAME transaction as the aggregate mutation it is
paired with -- the acceptance guarantee this lane's test suite proves
directly (`tests/unit/test_place_order.py::
test_read_model_goes_stale_if_the_projection_is_skipped`, the
projection-disabled negative).

## Customer FK -> snapshot

`00-monolith/order/models.py::Order.customer` is a hard FK into the shared
`common.Customer` table (SMELL[ch.18]). This service owns a forward-filled
COPY of that table (`order_svc.customers`, seeded by `migrations/versions/
0002_seed_customers.py` with the same Ada/Grace rows the monolith's own seed
creates) -- `place_order()`'s customer validation queries THIS table, never
the monolith's, over any protocol. `orders.customer_id` is a real FK, but
into this OWNED table; `orders.customer_email` is ADDITIONALLY captured as
its own point-in-time snapshot (the `order.placed` event's `customerEmail`
field needs it) so a later change to `customers.email` never rewrites a
historical order's outbox payload.

## Checkout contract

`POST /api/orders` reserves every line over gRPC OUTSIDE any local
transaction, then persists the aggregate + `order_view` + the `order.placed`
outbox row in ONE transaction, and returns **`202 Accepted`** with a
`Location` header, status `PENDING` -- never `201`. There is no synchronous,
in-process confirm-in-one-request path: confirmation happens later, off the
saga reactions below.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/orders` | `{customerId, items:[{sku,quantity}], paymentMethod, shippingAddress}` -> `202` + `Location`, body = the `PENDING` `order_view` row |
| `GET` | `/api/orders/{id}` | served from `order_view`; `404 NOT_FOUND` for an unknown id |
| `GET` | `/api/orders` | served from `order_view`, ordered by id |

## The four saga reactions

This service's `aiokafka` consumer (`app/consumer.py`) drives the SAME
four-stage saga `00-monolith`'s `order_saga_listener` does, matching the
ORCHESTRATED-shipping flavor (`SHIPPING_MODE=orchestrated`) exactly:

| Event | Guard | Transition | Compensation |
|---|---|---|---|
| `payment.captured` | `status == PENDING` | `-> AWAITING_SHIPMENT` | none |
| `payment.declined` | `status == PENDING` | `-> PAYMENT_DECLINED` | gRPC Release, every line, stable key |
| `shipment.dispatched` | `status == AWAITING_SHIPMENT` | `-> CONFIRMED` | none |
| `shipment.failed` | `status == AWAITING_SHIPMENT` | `-> SHIPPING_FAILED` | gRPC Release, every line, stable key |

Every transition upserts `order_view` in the SAME transaction
(`app/repository.py::transition_order_status_with_view`) and is idempotent
via an atomic conditional `UPDATE ... WHERE status = <expected>` -- a
redelivered event for an order that already left the expected status is a
safe no-op, proven directly by `tests/unit/test_reactions.py`.

**Refund note:** a payment that captured and then hits `shipment.failed` is
refunded by `05-payment-service`'s OWN `shipment.failed` consumer
(r06/DRQ-054) reacting to the SAME event this service's
`handle_shipment_failed` does. This service has no payment collaborator to
call -- its responsibility ends at releasing inventory and transitioning the
order.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **Alembic 1.20.0**,
  **aiokafka 0.14.0**, **grpcio 1.84.0** + **protobuf 7.36.2** (the
  inventory gRPC CLIENT -- `grpc.aio`, never a server). Dev-only: **pytest
  9.1.1** + **pytest-asyncio 1.4.0**, **httpx 0.28.1**, **ruff 0.17.1**,
  **testcontainers 4.15.0**, **grpcio-tools 1.84.0** (stub regeneration
  only).

## Commands

```sh
uv sync --group dev

# One-time: creates the order_svc schema + all 5 tables + seeds customers
# (Ada id=1, Grace id=2, matching the monolith's seed):
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8088
uv run ruff check .
uv run pytest -m "not integration"   # needs a reachable, migrated Postgres, no Kafka, no gRPC server
uv run pytest -m integration         # Testcontainers Kafka+Postgres + an in-process fake gRPC inventory server
```

`DATABASE_URL` (same convention as every other service in this project,
default `postgresql://monolith:monolith@localhost:5432/monolith`) is
normalized onto the asyncpg driver scheme by `app/db.py::resolve_database_url`.
`KAFKA_BOOTSTRAP_SERVERS` defaults to `localhost:9092`.
`INVENTORY_GRPC_TARGET` defaults to `localhost:9004` -- the SAME default
`00-monolith/config/settings.py::INVENTORY_GRPC_TARGET` uses, so this
service points at `04-inventory-service` out of the box. All settings are
read via `app/config.py::Settings.from_env()`.

## Structure

- `app/main.py` -- FastAPI app factory + lifespan (engine/session factory,
  starts the saga consumer AND the outbox relay as background tasks),
  `redirect_slashes=False`, `/health` (consumer partition-assignment).
- `app/routes.py` -- `POST /api/orders` (202+Location), `GET /api/orders[/{id}]`
  (`order_view` only).
- `app/service.py` -- `place_order` (the command) + the four `handle_*`
  reactions + `rebuild_order_view`.
- `app/repository.py` -- all persistence: the three-way one-transaction
  write (`create_order_with_outbox_and_view`), the atomic conditional-UPDATE
  transition (`transition_order_status_with_view`), `order_view` reads, and
  the relay's outbox queries.
- `app/inventory_client.py` -- `AsyncInventoryClient`, the `grpc.aio`
  anti-corruption layer onto `app/grpc_gen/` (vendored stubs, generated from
  `proto/dev/patterncatalyst/inventory/v1/inventory.proto`, byte-identical
  to `04-inventory-service`'s canonical copy).
- `app/consumer.py` / `app/relay.py` -- the `aiokafka` consumer (4 topics,
  1 group) and the outbox relay (1 topic: `order.placed`).
- `app/models.py` -- the 5-table CQRS mapping onto `order_svc` (see
  `app/db.py`'s docstring for the schema-name choice).
- `app/schemas.py` -- Pydantic v2 camelCase contracts + the 4 consumed event
  shapes + the 1 produced event shape.
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  plus `InsufficientStock` (409) / `InventoryServiceUnavailable` (503).
- `migrations/` -- Alembic, async, `version_table_schema="order_svc"`.
- `tests/unit/` -- `fakes.py` (a Kafka-free, gRPC-free `FakeInventoryClient`),
  REST contract tests, `place_order` atomicity/compensation proofs, the four
  reactions' idempotency proofs, and the CQRS projection-disabled negative.
- `tests/integration/` -- Testcontainers Kafka+Postgres, plus a REAL
  `grpc.aio` server implementing the inventory contract in-process (not
  mocked away) -- proves checkout, the saga transitions, and the
  exactly-once `order.placed` publish end to end.

## Contract notes (don't "fix" these -- they match the design intent on purpose)

- JSON is **camelCase**, no trailing slash, same uniform error body as every
  other service in this project.
- `POST /api/orders` is **`202`**, not `201` -- there is no synchronous
  confirm path left in this service.
- Reads are served from `order_view` EXCLUSIVELY -- `app/routes.py` never
  imports `Order`/`OrderItem` from `app/models.py`.
- The schema is `order_svc`, not `order` -- see `app/db.py`'s docstring for
  why (`order` is a SQL-reserved word).
