# AGENTS.md -- 03-notification-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r03 extraction of the `notification` bounded context off
`../00-monolith` onto a standalone FastAPI service, `:8002` (ch.17,
DRQ-035). Unlike `../02-review-service` (lift-and-reauthor of an existing
Django view), there is **no Spring/Django original for the write path**: the
monolith never consumed its own `order.placed` event, so the `aiokafka`
consumer and the idempotent write path are authored idiomatic-from-the-start.
Only the `GET /api/notifications?customerId=` read surface has a monolith
original to match byte-for-byte.

This is the Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/03-notification-service`
(Java/Quarkus) -- same role in the book, same chapter -- but it is its own
independent implementation (aiokafka instead of SmallRye Reactive Messaging,
no WebSocket push lane -- DRQ-037 defers that).

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **aiokafka 0.14.0**,
  **Alembic 1.20.0**. Dev-only: **pytest 9.1.1** + **pytest-asyncio 1.4.0** +
  **httpx 0.28.1**, **ruff 0.17.1**, **testcontainers 4.15.0**.

## Commands

```sh
uv sync --group dev

# One-time, this service's own migration (creates the `notification` schema):
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
uv run ruff check .
uv run pytest -m "not integration"   # needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Testcontainers-managed Kafka + Postgres, needs Docker
```

`DATABASE_URL` (same convention as `00-monolith`/`02-review-service`,
default `postgresql://monolith:monolith@localhost:5432/monolith`) is
normalized onto the asyncpg driver scheme by `app/db.py::resolve_database_url`.
`KAFKA_BOOTSTRAP_SERVERS` defaults to `localhost:9092`. Both, plus
`ORDER_PLACED_TOPIC`/`CONSUMER_GROUP`, are read via `app/config.py::Settings.from_env()`.

## Structure

- `app/main.py` -- FastAPI app factory + lifespan (creates the async
  engine/session factory AND starts the `order.placed` consumer as a
  background `asyncio.Task`, cancels it on shutdown), structured file
  logging setup, `redirect_slashes=False`, `/health` (consumer
  partition-assignment for CI readiness waits).
- `app/routes.py` -- the one `/api/notifications` endpoint.
- `app/consumer.py` -- `OrderPlacedConsumer`, an `aiokafka` consumer
  lifecycle wrapper (`group_id=notification-service`,
  `auto_offset_reset=earliest`), delegating persistence to `app/service.py`.
- `app/service.py` -- `record_order_placed`, the single owner of the
  idempotent write path (check-then-insert, dedupe by `order_id`).
- `app/schemas.py` -- Pydantic v2 models: `NotificationOut` (response,
  camelCase via `Field(alias=...)`) and `OrderPlacedEvent` (this service's
  own copy of the frozen Kafka payload shape).
- `app/repository.py` -- async SQLAlchemy queries against the owned schema.
- `app/models.py` -- SQLAlchemy declarative mapping for `notification.notifications`,
  including the partial unique index on `order_id`.
- `app/db.py` -- async engine/session factory; sets
  `search_path=notification,public` on every connection.
- `app/config.py` -- `Settings.from_env()`, read at call time (not frozen at
  import), so tests can override env vars before building an app/consumer.
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  ported from review-service's `app/errors.py`.
- `migrations/` -- Alembic, async (`Connection.run_sync`), `version_table_schema="notification"`.
  `versions/0001_create_notification_schema.py` creates the schema, table,
  and both indexes (customer_id lookup + the idempotency backstop).
- `tests/unit/` -- REST contract tests + a Kafka-free `app.service` idempotency
  test, against a real, already-migrated Postgres.
- `tests/integration/` -- Testcontainers (Kafka + Postgres) proof that
  redelivering the identical `order.placed` event yields exactly one row.

## Contract notes (don't "fix" these -- they match the monolith on purpose)

- JSON is **camelCase**, no trailing slash, same uniform error body as
  `00-monolith`'s `common/exceptions.py` -- see `README.md`'s endpoint table.
- `orderId` is nullable in the response/model (matches the monolith's
  `Notification.order` being `null=True`) even though every row this
  service's own consumer writes has one set -- the schema leaves room for a
  future non-order-originated notification without a migration.
- `GET /api/notifications` with no `customerId` -> `400 VALIDATION_FAILED`,
  via FastAPI's required `Query(...)` raising `RequestValidationError`
  (remapped by `app/errors.py`), matching DRF's generic 400 rule the
  monolith's `NotificationListView` relies on.
- Idempotency is **check-then-insert plus a DB partial unique index**, not
  just one or the other -- see `README.md`'s "Idempotency" section for why
  both layers exist (application-level dedupe is the common case, the index
  is the concurrent-redelivery backstop).

## Testing

Two independent layers, deliberately NOT requiring the same infrastructure:

```sh
# Layer 1 -- REST contract + service idempotency (no Kafka needed):
docker run -d --name mea-notification-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
uv run alembic upgrade head
uv run pytest -m "not integration"

# Layer 2 -- end-to-end consumer idempotency through a REAL Kafka broker
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
