# AGENTS.md -- 06-shipping-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r06 **orchestrated** extraction of the `shipping` bounded context off
`../00-monolith` onto a standalone FastAPI service, `:8087`. A DB-backed saga
orchestrator -- no gRPC, no Camel -- triggered by `05-payment-service`'s own
`payment.captured` event, driving a four-step saga
(`enrich -> dispatch -> book_carrier -> emit`) with compensation on failure.
This is the Python sibling of the role played by
`~/Dev/modernizing-enterprise-applications/examples/06-shipping-service`
(Java/Quarkus, a Camel Saga EIP route) -- same chapter intent, same four
steps, same deterministic `SHIP-FAIL` failure injection -- but its own
independent implementation, adapted from
`~/Dev/cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/main.py`'s
raw-asyncpg orchestrator onto this project's async SQLAlchemy stack, and a
DURABILITY upgrade over the Java sibling's in-memory saga coordinator (see
`MIGRATION.md`).

There is **no monolith original for the write path**: the monolith still
dispatches shipping in-process, synchronously
(`shipping.services.dispatch`, when `SHIPPING_MODE=inprocess`, the default).
Only the `SHIP-FAIL` rule and the `GET /api/shipments` read surface have a
monolith original to match byte-for-byte; the consumer, the saga engine, and
the outbox+relay are authored idiomatic-from-the-start.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **aiokafka 0.14.0**,
  **Alembic 1.20.0**, **httpx 0.28.1** (the `enrich` step's HTTP client --
  this service's only outbound call to another HTTP service), **tenacity
  9.2.1** (retry + timeout around that call, ch.25's resilience anchor). Dev:
  **pytest 9.1.1** + **pytest-asyncio 1.4.0**, **ruff 0.17.1**,
  **testcontainers 4.15.0**. **No grpcio** -- this service never calls, and
  is never called via, gRPC.

## Commands

```sh
uv sync --group dev

# One-time, this service's own migration (creates the `shipping` schema):
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8087
uv run ruff check .
uv run pytest -m "not integration"   # needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Testcontainers-managed Kafka + Postgres, needs Docker
```

`DATABASE_URL` (same convention as every other service in this project,
default `postgresql://monolith:monolith@localhost:5432/monolith`) is
normalized onto the asyncpg driver scheme by `app/db.py::resolve_database_url`.
`KAFKA_BOOTSTRAP_SERVERS` defaults to `localhost:9092`. `ORDER_BASE_URL`
defaults to `http://localhost:8088` -- the `enrich` step's target (r07
re-point; order-service's `order_view` serves the same `shippingAddress`
field the monolith used to). `MONOLITH_BASE_URL` (default
`http://localhost:8000`) is kept as a documented, operator-only fallback --
see `app/config.py`'s module docstring -- but is not read by `enrich()`. All
settings are read via `app/config.py::Settings.from_env()`.

## Structure

- `app/main.py` -- FastAPI app factory + lifespan (creates the async
  engine/session factory, starts the `payment.captured` consumer AND the
  outbox relay as background `asyncio.Task`s, runs the startup crash-resume
  scan BEFORE reporting ready, cancels both tasks on shutdown), structured
  file logging setup, `redirect_slashes=False`, `/health` (consumer
  partition-assignment + resume-complete flag for CI readiness waits).
- `app/routes.py` -- `GET /api/shipments[?orderId=]` / `GET /api/shipments/{id}`.
- `app/consumer.py` -- `PaymentCapturedConsumer`, an `aiokafka` consumer
  lifecycle wrapper (`group_id=shipping-service`, `auto_offset_reset=earliest`),
  delegating saga-start to `app/service.py`.
- `app/service.py` -- `handle_payment_captured`: the ONE place that decides
  "does a saga already exist for this order" (check-then-insert, dedupe by
  `order_id`, `IntegrityError`-safe), then kicks `app/orchestrator.py::advance`
  once.
- `app/orchestrator.py` -- the saga engine: `STEPS` (the four-step table,
  each naming its one compensation or `None`), `advance()`/`_advance_one_step()`
  (one step per transaction, `SELECT ... FOR UPDATE` + idempotent guard,
  recurses until `COMPLETED` or hands off to `compensate()`), `compensate()`
  (reverse-order inverses over only-completed steps, then the terminal
  `shipment.failed` write + `COMPENSATED` transition, atomically), and
  `resume_running_sagas()` (the startup crash-resume scan).
- `app/steps.py` -- the four forward step bodies (`enrich`, `dispatch`,
  `book_carrier`, `emit`) plus `dispatch`'s one compensation
  (`cancel_shipment`). Each has the same `(session, settings, order_id,
  context) -> dict` signature; the returned dict is folded into the saga's
  persisted `context` by the orchestrator.
- `app/enrich_client.py` -- the `enrich` step's HTTP client: `httpx` +
  `tenacity` retry-with-timeout around `GET
  {ORDER_BASE_URL}/api/orders/{orderId}`, reading back `shippingAddress`
  (r07 re-point, from order-service's `order_view` -- see `app/config.py`).
- `app/relay.py` -- `OutboxRelay`, an `aiokafka` producer lifecycle wrapper
  polling `shipping.outbox` on a background task, publishing to
  `shipment.dispatched`/`shipment.failed` per row's `event_type`, keyed by
  `orderId`, at-least-once.
- `app/schemas.py` -- Pydantic v2 models: `ShipmentOut` (response, camelCase
  via `Field(alias=...)`) and `PaymentCapturedEvent` (this service's own copy
  of the consumed Kafka payload shape).
- `app/repository.py` -- async SQLAlchemy queries/writes against the owned
  schema: shipment reads (`app/routes.py`), saga persistence + the `SELECT
  ... FOR UPDATE` row lock (`app/orchestrator.py`), shipment/outbox writes
  (`app/steps.py`), and the relay's unpublished-batch poll/mark-published
  queries. Write functions do NOT commit internally -- the saga engine owns
  the transaction boundary (see the module docstring).
- `app/models.py` -- SQLAlchemy declarative mapping for `shipping.shipments`,
  `shipping.outbox`, `shipping.sagas` (`order_id` UNIQUE, `context` JSONB),
  and `shipping.saga_log` (a real FK to `sagas.id` -- both tables are owned
  by this service).
- `app/db.py` -- async engine/session factory; sets
  `search_path=shipping,public` on every connection.
- `app/config.py` -- `Settings.from_env()`, read at call time (not frozen at
  import), so tests can override env vars before building an
  app/consumer/relay/orchestrator call.
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  ported from every other standalone service's `app/errors.py`.
- `migrations/` -- Alembic, async (`Connection.run_sync`),
  `version_table_schema="shipping"`.
  `versions/0001_create_shipping_schema.py` creates the schema, all 4
  tables, and every index (`uq_sagas_order_id` UNIQUE,
  `idx_shipping_outbox_unpublished` partial, `idx_shipments_order_id`,
  `idx_saga_log_saga_id`).
- `tests/unit/` -- REST contract tests + Kafka-free orchestrator tests
  (happy path, the SHIP-FAIL compensation path, idempotent redelivery)
  against a real, already-migrated Postgres, with the monolith's enrich call
  monkeypatched.
- `tests/integration/` -- Testcontainers (Kafka + Postgres): the full saga
  round trip through a real broker (`test_shipping_saga.py`) and the
  crash-resume proof (`test_crash_resume.py`), which seeds a `RUNNING` saga
  row with a partial `step_index` directly (simulating a crashed process)
  and asserts `resume_running_sagas()` picks up where it left off without
  re-running the already-completed step.

## Contract notes (don't "fix" these -- they match the monolith/design intent on purpose)

- JSON is **camelCase**, no trailing slash, same uniform error body as
  `00-monolith`'s `common/exceptions.py` -- see `README.md`'s endpoint table.
- The `SHIP-FAIL` rule (`app/steps.py::SHIP_FAIL_SENTINEL = "SHIP-FAIL"`) is
  lifted byte-for-byte from `00-monolith/shipping/services.py::dispatch`'s
  `SHIP_FAIL_SENTINEL`. It fires in `book_carrier` (step 3), AFTER `dispatch`
  (step 2) has already persisted a `Shipment` row -- that ordering is load
  bearing: it's what gives `cancel_shipment` something real to compensate.
- `dispatch` persists the `Shipment` row as `DISPATCHED` directly (not
  `PENDING` first) -- `PENDING` stays declared in `app/models.py`'s status
  enum for schema completeness but this saga never writes it. Don't "clean
  up" the unused enum value; see that module's docstring.
- The `shipment.failed` wire event's `status` field is ALWAYS the literal
  `"FAILED"`, even though the underlying `Shipment` row (when one exists) is
  marked `CANCELLED` -- the event describes the saga's outcome, the row
  describes the aggregate's state. Don't make these match; see `EVENTS.md`.
- `GET /api/shipments` with no `orderId` -> `400 VALIDATION_FAILED`;
  `GET /api/shipments/{id}` with an unknown id -> `404 NOT_FOUND`.
- Idempotency is **check-then-insert plus a DB unique index**
  (`uq_sagas_order_id`), same shape as `05-payment-service`'s
  `uq_payments_order_id` -- see `README.md`'s "Idempotency" section.
- The terminal outbox write (`shipment.dispatched` or `shipment.failed`)
  happens in the SAME transaction as the saga's own `COMPLETED`/`COMPENSATED`
  status update -- never a saga marked done with no outcome event queued, or
  vice versa. This is enforced in `app/orchestrator.py`, not left to
  `app/steps.py` discipline alone.

## Testing

Two independent layers, deliberately NOT requiring the same infrastructure:

```sh
# Layer 1 -- REST contract + orchestrator happy/SHIP-FAIL/idempotency paths
# (no Kafka needed, enrich call monkeypatched):
docker run -d --name mea-shipping-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
uv run alembic upgrade head
uv run pytest -m "not integration"

# Layer 2 -- end-to-end saga through a REAL Kafka broker, plus the
# crash-resume proof (Testcontainers manages its own isolated Kafka +
# Postgres, independent of the throwaway Postgres above):
uv run pytest -m integration
```

`tests/integration/conftest.py`'s `KafkaContainer` fixture calls
`.with_kraft()` explicitly -- `confluentinc/cp-kafka:8.3.2` dropped the
legacy ZooKeeper boot path entirely; `testcontainers`' `KafkaContainer` still
defaults to ZooKeeper configuration unless told otherwise.
