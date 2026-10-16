# AGENTS.md -- 05-payment-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r05 **choreographed** extraction of the `payment` bounded context off
`../00-monolith` onto a standalone FastAPI service, `:8085`. No orchestrator,
no gRPC -- payment reacts to `order.placed` and emits its own outcome event.
Unlike `../03-notification-service` (which only ever CONSUMES), this service
sits on BOTH sides of Kafka: it consumes `order.placed` and PRODUCES
`payment.captured`/`payment.declined` via its own transactional outbox + its
own relay. This is the Python sibling of the role played by
`~/Dev/modernizing-enterprise-applications/examples/05-payment-service`
(Java/Quarkus) -- same chapter intent -- but its own independent
implementation (aiokafka instead of SmallRye Reactive Messaging).

There is **no monolith original for the write path**: the monolith still
charges in-process, synchronously, inside the same `transaction.atomic()` as
the inventory reservation (`00-monolith/payment/services.py::charge`). Only
the DECLINE rule and the `GET /api/payments` read surface have a monolith
original to match byte-for-byte; the consumer, the idempotent write path, and
the outbox+relay are authored idiomatic-from-the-start.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **aiokafka 0.14.0**,
  **Alembic 1.20.0**. Dev-only: **pytest 9.1.1** + **pytest-asyncio 1.4.0** +
  **httpx 0.28.1**, **ruff 0.17.1**, **testcontainers 4.15.0**. **No
  grpcio** -- this service never calls, and is never called via, gRPC; the
  monolith issues any compensating action (e.g. a future inventory Release)
  itself off the published outcome event.

## Commands

```sh
uv sync --group dev

# One-time, this service's own migration (creates the `payment` schema):
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8085
uv run ruff check .
uv run pytest -m "not integration"   # needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Testcontainers-managed Kafka + Postgres, needs Docker
```

`DATABASE_URL` (same convention as every other service in this project,
default `postgresql://monolith:monolith@localhost:5432/monolith`) is
normalized onto the asyncpg driver scheme by `app/db.py::resolve_database_url`.
`KAFKA_BOOTSTRAP_SERVERS` defaults to `localhost:9092`. All settings are read
via `app/config.py::Settings.from_env()` -- see that module for the full
list (`HTTP_PORT`, `ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`,
`PAYMENT_DECLINED_TOPIC`, `CONSUMER_GROUP`, `OUTBOX_POLL_MS`).

## Structure

- `app/main.py` -- FastAPI app factory + lifespan (creates the async
  engine/session factory AND starts BOTH the `order.placed` consumer and the
  outbox relay as background `asyncio.Task`s, cancels both on shutdown),
  structured file logging setup, `redirect_slashes=False`, `/health`
  (consumer partition-assignment for CI readiness waits).
- `app/routes.py` -- `GET /api/payments[?orderId=]` / `GET /api/payments/{id}`.
- `app/consumer.py` -- `OrderPlacedConsumer`, an `aiokafka` consumer
  lifecycle wrapper (`group_id=payment-service`, `auto_offset_reset=earliest`),
  delegating capture-and-emit to `app/service.py`.
- `app/relay.py` -- `OutboxRelay`, an `aiokafka` producer lifecycle wrapper
  polling `payment.outbox` on a background task, publishing to
  `payment.captured`/`payment.declined` per row's `event_type`, keyed by
  `orderId`, at-least-once (mirrors the monolith's
  `common/management/commands/outbox_relay.py`).
- `app/service.py` -- `process_order_placed`, the single owner of the
  idempotent write path (check-then-insert, dedupe by `order_id`) AND
  `charge`, the deterministic DECLINE-rule function (never raises). Also
  builds the outbox event payload matching each `Payment` row.
- `app/schemas.py` -- Pydantic v2 models: `PaymentOut` (response, camelCase
  via `Field(alias=...)`) and `OrderPlacedEvent` (this service's own copy of
  the consumed Kafka payload shape, including the optional `paymentMethod`).
- `app/repository.py` -- async SQLAlchemy queries against the owned schema,
  including `create_payment_with_outbox_event` (writes both rows in ONE
  transaction -- the outbox atomicity guarantee) and the relay's
  unpublished-batch poll/mark-published queries.
- `app/models.py` -- SQLAlchemy declarative mapping for `payment.payments`
  (unique index on `order_id`) and `payment.outbox` (partial index on
  unpublished rows).
- `app/db.py` -- async engine/session factory; sets
  `search_path=payment,public` on every connection.
- `app/config.py` -- `Settings.from_env()`, read at call time (not frozen at
  import), so tests can override env vars before building an app/consumer/relay.
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  ported from notification-/review-service's `app/errors.py`, plus
  `ResourceNotFound` for the 404-by-id route.
- `migrations/` -- Alembic, async (`Connection.run_sync`),
  `version_table_schema="payment"`.
  `versions/0001_create_payment_schema.py` creates the schema, both tables,
  and all three indexes.
- `tests/unit/` -- REST contract tests + Kafka-free `app.service` tests
  (capture, decline, null-method-captures, idempotent-redelivery), against a
  real, already-migrated Postgres.
- `tests/integration/` -- Testcontainers (Kafka + Postgres) proof of the
  full round trip: capture + publish, decline + publish, and
  redelivery-yields-exactly-one-row for both the `payments` and `outbox`
  tables.

## Contract notes (don't "fix" these -- they match the monolith/design intent on purpose)

- JSON is **camelCase**, no trailing slash, same uniform error body as
  `00-monolith`'s `common/exceptions.py` -- see `README.md`'s endpoint table.
- The DECLINE rule (`app/service.py::DECLINE_SENTINEL = "DECLINE"`) is
  lifted byte-for-byte from `00-monolith/payment/services.py::charge`. The
  control flow around it is NOT lifted: the monolith's version raises and
  aborts a local transaction; this service's `charge()` never raises -- it
  always returns a status, because the choreography needs a `Payment` row
  (and an emitted event) for a decline too.
- `paymentMethod` on the consumed `order.placed` event is OPTIONAL
  (net-new in r05). A missing/`null` value substitutes
  `app/service.py::UNSPECIFIED_METHOD` (`"CARD-UNSPECIFIED"`) and always
  captures -- never crashes, never silently declines. See `EVENTS.md`.
- `GET /api/payments` with no `orderId` -> `400 VALIDATION_FAILED`;
  `GET /api/payments/{id}` with an unknown id -> `404 NOT_FOUND`. Both via
  FastAPI/`app/errors.py`, matching the monolith's DRF behavior.
- Idempotency is **check-then-insert plus a DB unique index**, not just one
  or the other -- see `README.md`'s "Idempotency" section.
- The outbox write (`Payment` + `OutboxEvent`) happens in ONE transaction
  (`repository.py::create_payment_with_outbox_event`) -- never persist a
  `Payment` without its matching outbox row, or vice versa.

## Testing

Two independent layers, deliberately NOT requiring the same infrastructure:

```sh
# Layer 1 -- REST contract + service capture/decline/idempotency (no Kafka needed):
docker run -d --name mea-payment-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
uv run alembic upgrade head
uv run pytest -m "not integration"

# Layer 2 -- end-to-end choreography through a REAL Kafka broker
# (Testcontainers manages its own isolated Kafka + Postgres, independent of
# the throwaway Postgres above):
uv run pytest -m integration
```

`tests/integration/conftest.py`'s `KafkaContainer` fixture calls
`.with_kraft()` explicitly -- `confluentinc/cp-kafka:8.3.2` dropped the
legacy ZooKeeper boot path entirely (it fails fast with
`"KAFKA_PROCESS_ROLES is not set"` without it); `testcontainers`'
`KafkaContainer` still defaults to ZooKeeper configuration unless told
otherwise.
