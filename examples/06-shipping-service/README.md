# 06-shipping-service

**r06 -- orchestrated shipping.** The monolith's (`../00-monolith`) `shipping`
bounded context, extracted onto a standalone **FastAPI** service on
**`:8087`**. Like every other standalone service in this project, there is
**no Django original for the write path**: the monolith still dispatches
shipping synchronously, in-process, as part of `order.services.place_order`'s
checkout transaction (when `SHIPPING_MODE=inprocess`, the default). This
service is an **orchestrated saga coordinator** -- no gRPC, no Camel, a
hand-rolled DB-backed state machine adapted from
`~/Dev/cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/main.py`
-- authored idiomatic-from-the-start:

- An **idempotent `aiokafka` consumer** of the frozen `payment.captured`
  topic (`05-payment-service`'s own outbox-published outcome event), starting
  one **saga** per order into this service's **OWN `shipping` Postgres
  schema**. Migrated with **Alembic**, same own-schema posture every other
  standalone service establishes.
- A **four-step orchestrated saga** (`enrich -> dispatch -> book_carrier ->
  emit`), driven by `app/orchestrator.py`: each step runs in its own
  transaction, with a `SELECT ... FOR UPDATE` row lock and an idempotent
  "not RUNNING -> no-op" guard -- so a crash between any two steps leaves the
  saga in a well-defined, resumable state. On a failure (the deterministic
  `SHIP-FAIL` sentinel), it **compensates** in reverse order over only the
  steps that actually completed.
- A **startup crash-resume scan** (`app/orchestrator.py::resume_running_sagas`):
  every saga still `RUNNING`/`COMPENSATING` when the process last stopped
  gets its engine kicked again, picking up from its persisted `step_index`
  and `context` -- proven by `tests/integration/test_crash_resume.py`.
- This service's **OWN transactional outbox** (`shipping.outbox`) and **OWN
  relay** (`app/relay.py`), publishing `shipment.dispatched` /
  `shipment.failed` -- written atomically with the saga's own terminal
  `COMPLETED`/`COMPENSATED` state transition (never a saga marked done with
  no outcome event queued, or vice versa).
- `GET /api/shipments[?orderId=]` / `GET /api/shipments/{id}` -- the lifted
  read surface, matching the monolith's `shipping/views.py` contract
  byte-for-byte.

See `MIGRATION.md` for the two-phase write-up (and the crash-resume
durability upgrade over the Java sibling's in-memory saga coordinator),
`EVENTS.md` for the full event contracts (consumed, enriched, and produced),
and `AGENTS.md` for agent-facing structure notes.

## Why orchestration, not choreography (contrast with `05-payment-service`)

`05-payment-service` (r05) is deliberately **choreographed**: it reacts to
one event and emits one outcome event, with no coordinator and no
multi-step state to track. This saga is different in kind -- it has FOUR
steps (`enrich`, `dispatch`, `book_carrier`, `emit`), one of which
(`dispatch`) needs a semantic inverse (`cancel_shipment`) if a LATER step
fails, and it reaches out to a THIRD system (the monolith's `GET
/api/orders/{id}`) partway through. That shape -- multiple steps, a defined
compensation order, cross-step data flowing through accumulated context --
is exactly what an **orchestrator** is for:

- **One component owns the whole sequence.** `app/orchestrator.py` is the
  only place that knows the step order and which step compensates which --
  `app/steps.py`'s individual step functions know nothing about each other
  or about what comes next.
- **State lives in the database, not memory.** `shipping.sagas` holds
  `status`/`step_index`/`context` per in-flight saga instance -- a crash
  loses nothing, because the NEXT `advance()` call (from a resumed process,
  or a retried request) picks up exactly where the last one committed. See
  `_docs/17-appendix-d-sagas.md`'s Figure D.1 for the general pattern this
  implements.
- **Compensation is centrally defined, not scattered.** `cancel_shipment`
  runs in reverse order over only the steps that actually completed
  (`app/orchestrator.py::compensate`) -- a rule enforced in one place, not
  duplicated across every service that might need to react to a failure.

Contrast with the monolith's original in-process `shipping.services.dispatch`
(SMELL[ch.22]): that version got a free, implicit "saga" for the price of one
Postgres `transaction.atomic()` block, because every bounded context shared
one database. The moment shipping becomes its own service with its own
schema, that free rollback is gone -- this orchestrator is what rebuilding it
explicitly looks like.

## Durability upgrade over the Java sibling

The Java sibling
(`~/Dev/modernizing-enterprise-applications/examples/06-shipping-service`)
implements this same four-step saga as a **Camel Saga EIP** route -- correct,
but its coordinator tracks in-flight saga state **in memory**
(`CamelSagaService`); a pod restart mid-saga loses track of where that saga
was. This service's DB-backed orchestrator is a **durability upgrade**: saga
state is a row in `shipping.sagas`, so a crash at any point is recoverable by
the startup resume scan, not just a correctness gap documented and deferred.
See `MIGRATION.md` for the measured proof.

## Idempotency

The `payment.captured` publisher (`05-payment-service`'s own outbox relay) is
**at-least-once**. Two layers guarantee a redelivered event starts at most
one saga per order:

1. **Application-level check-then-insert** --
   `app/service.py::handle_payment_captured` looks up `get_saga_by_order_id`
   first; if a saga already exists for that order, it is a no-op.
2. **Database-level unique index** -- `uq_sagas_order_id` (UNIQUE on
   `order_id`, created by
   `migrations/versions/0001_create_shipping_schema.py`), the backstop for
   two deliveries racing concurrently (caught as an `IntegrityError` and
   discarded as a duplicate).

The orchestrator's own `advance()`/`compensate()` are SEPARATELY idempotent,
via the `SELECT ... FOR UPDATE` row lock plus the "not RUNNING (or not
COMPENSATING)" no-op guard -- the same mechanism that makes the startup
crash-resume scan safe to call on a saga that, in fact, already finished
just before the crash.

Proven by `tests/unit/test_orchestrator.py` (happy path, the SHIP-FAIL abort,
and redelivery, all Kafka-free against a real schema) and
`tests/integration/test_shipping_saga.py`/`test_crash_resume.py` (a real
Kafka broker + Postgres via Testcontainers).

## Endpoints

CamelCase JSON, **no trailing slash** (`redirect_slashes=False`, same
contract posture as every other standalone service). No write endpoint: the
only write path is the orchestrated saga.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/shipments?orderId=` | required query param; `400 VALIDATION_FAILED` if missing |
| GET | `/api/shipments/{id}` | `404 NOT_FOUND` if unknown |
| GET | `/health` | reports Kafka consumer partition-assignment AND startup crash-resume completion |

Response body: `{id, orderId, address, status, createdAt}` -- matches
`shipping.serializers.ShipmentSerializer`'s field list exactly. Error body
(every non-2xx response): `{"error": "<CODE>", "message": ...,
"timestamp": ...}`.

## Persistence: owned schema, Alembic-migrated

This service owns a separate Postgres **schema** (`shipping`), in the SAME
Postgres **instance** every example in this project shares by default
(`DATABASE_URL`, default
`postgresql://monolith:monolith@localhost:5432/monolith`). `app/db.py` sets
`search_path=shipping,public` on every connection AND every model in
`app/models.py` declares `schema="shipping"` explicitly -- the search path is
a convenience, the explicit schema is the correctness guarantee. Four
tables: `shipments`, `outbox` (this service's own transactional outbox),
`sagas`, and `saga_log` (the orchestrator's own state).

## Quickstart

```sh
uv sync --group dev

# One-time: create this service's own `shipping` schema + 4 tables + indexes.
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8087
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`,
`KAFKA_BOOTSTRAP_SERVERS=localhost:9092` (the INFRA lane's compose stack), and
`MONOLITH_BASE_URL=http://localhost:8000` (the enrich step's target). A quick
standalone Postgres for local use:

```sh
docker run -d --name mea-shipping-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

### Try it

Run the monolith (`cd ../00-monolith && uv run python manage.py runserver
0.0.0.0:8000`) and publish a `payment.captured` event (e.g. with `kcat`, or by
checking out an order through the monolith with `PAYMENT_MODE=choreographed`
and letting `05-payment-service` emit it for real), then:

```sh
curl "http://localhost:8087/api/shipments?orderId=555123"
curl -i "http://localhost:8087/api/shipments"   # 400, missing orderId
curl "http://localhost:8087/health"             # consumer readiness + resume status
```

An order whose `shippingAddress` contains `SHIP-FAIL` (e.g. `"1 SHIP-FAIL
Lane"`) yields a `CANCELLED` shipment and a published `shipment.failed`
event instead of `shipment.dispatched` -- see `EVENTS.md`.

## Testing

```sh
uv run pytest -m "not integration"   # Layer 1 -- needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Layer 2 -- Testcontainers-managed Kafka + Postgres, needs Docker
uv run ruff check .
```

See `AGENTS.md` for the exact setup commands for each layer.

## Container

```sh
docker build -f Containerfile -t mea-shipping-service:r06 .
docker run --rm -p 8087:8087 \
  -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith \
  -e KAFKA_BOOTSTRAP_SERVERS=<host>:9092 \
  -e MONOLITH_BASE_URL=http://<host>:8000 \
  mea-shipping-service:r06
```

UBI 10 (`ubi10/python-314-minimal`, the same verified tag every other service
in this project uses), multi-stage `uv sync`, non-root (UID 1001, GID 0). The
container's `CMD` runs `alembic upgrade head` before starting uvicorn -- there
is no separate init-container step in this project's compose/CRC stacks.

## Structured logging

Rotating file logs land in `logs/shipping-service.log` alongside console
output (see `app/main.py::_configure_logging`), same convention as the rest
of this project's standalone services.
