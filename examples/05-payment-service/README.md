# 05-payment-service

**r05 -- choreographed payment.** The monolith's (`../00-monolith`) `payment`
bounded context, extracted onto a standalone **FastAPI** service on
**`:8085`**. Like `../03-notification-service`, there is **no Spring/Django
original for the write path**: the monolith still charges payment
synchronously, in-process, inside the SAME `transaction.atomic()` as the
inventory reservation (`00-monolith/payment/services.py::charge`). This
service is a **choreographed saga participant** -- no orchestrator, no gRPC --
authored idiomatic-from-the-start:

- An **idempotent `aiokafka` consumer** of the frozen `order.placed` topic,
  capturing (or declining) payment and recording a `Payment` row into this
  service's **OWN `payment` Postgres schema**. Migrated with **Alembic**,
  same own-schema posture `03-notification-service` established.
- This service's **OWN transactional outbox** (`payment.outbox`) and **OWN
  relay** (`app/relay.py`), publishing `payment.captured` / `payment.declined`
  -- the half of the outbox pattern notification-service never needed (it
  only ever consumes; it never publishes). The relay mirrors the monolith's
  proven `common/management/commands/outbox_relay.py` polling shape.
- `GET /api/payments[?orderId=]` / `GET /api/payments/{id}` -- the lifted
  read surface, matching the monolith's `payment/views.py` contract
  byte-for-byte.

See `MIGRATION.md` for the two-phase write-up, `EVENTS.md` for the full event
contracts (consumed and produced), and `AGENTS.md` for agent-facing structure
notes.

## Why choreography, not orchestration

This step deliberately has **no saga orchestrator and no gRPC**: payment
reacts to `order.placed` and emits its own outcome event
(`payment.captured`/`payment.declined`) for whatever consumes it next (a
future order-saga reaction is out of scope for this lane). That is
choreography -- each service reacts to events it observes, with no central
coordinator directing the sequence. Contrast with any future orchestrated
step in this project that calls payment synchronously (HTTP/gRPC) from a
coordinating service.

## Why own schema, own outbox (contrast with notification-service)

Same reasoning as `03-notification-service`'s own-schema decision: this
service is event-driven (consumes `order.placed` off Kafka asynchronously),
so sharing the upstream aggregate's table would mean two writers (the
monolith's synchronous checkout path and this service's consumer) racing on
related rows with no way to reconcile them. Owning the table from the start
avoids that split-brain entirely.

Unlike notification-service, this service also **produces** events
(`payment.captured`/`payment.declined`), so it needs its own transactional
outbox AND its own relay -- notification-service only ever reads the
monolith's outbox-fed topic, it never writes one of its own.

## Deterministic demo decline rule

Lifted byte-for-byte from the monolith's `payment.services.charge`: any
`method` value containing `DECLINE` (case-insensitive) is declined,
everything else captures. See `EVENTS.md` for the full rule, including the
forward-compatibility fallback for a missing `paymentMethod`.

## Idempotency

The `order.placed` publisher (the monolith's outbox relay, once it carries a
payment method) is **at-least-once**. Two layers guarantee a redelivered
event yields exactly one `Payment` row and exactly one outbox event:

1. **Application-level check-then-insert** --
   `app/service.py::process_order_placed` looks up `get_by_order_id` first;
   if a payment already exists for that order, it is a no-op.
2. **Database-level unique index** -- `uq_payments_order_id` (UNIQUE on
   `order_id`, created by
   `migrations/versions/0001_create_payment_schema.py`), the backstop for
   two deliveries racing concurrently (caught as an `IntegrityError` and
   discarded as a duplicate).

The outbox relay's OWN publish side is separately at-least-once (publish,
then stamp `published_at`) -- see `EVENTS.md`'s "Delivery guarantees"
section.

Proven by `tests/integration/test_payment_choreography.py` (a real Kafka
broker + Postgres via Testcontainers) and
`tests/unit/test_service.py::test_process_order_placed_is_idempotent_on_redelivery`
(Kafka-free, function-call level).

## Endpoints

CamelCase JSON, **no trailing slash** (`redirect_slashes=False`, same
contract posture as notification-/review-service). No write endpoint: the
only write path is the `order.placed` consumer.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/payments?orderId=` | required query param; `400 VALIDATION_FAILED` if missing |
| GET | `/api/payments/{id}` | `404 NOT_FOUND` if unknown |
| GET | `/health` | reports Kafka consumer partition-assignment (CI readiness signal) |

Response body: `{id, orderId, amountCents, method, status, createdAt}` --
matches `payment.serializers.PaymentSerializer`'s field list exactly. Error
body (every non-2xx response): `{"error": "<CODE>", "message": ...,
"timestamp": ...}`.

## Persistence: owned schema, Alembic-migrated

This service owns a separate Postgres **schema** (`payment`), in the SAME
Postgres **instance** every example in this project shares by default
(`DATABASE_URL`, default
`postgresql://monolith:monolith@localhost:5432/monolith`). `app/db.py` sets
`search_path=payment,public` on every connection AND every model in
`app/models.py` declares `schema="payment"` explicitly -- the search path is
a convenience, the explicit schema is the correctness guarantee.

## Quickstart

```sh
uv sync --group dev

# One-time: create this service's own `payment` schema + tables + indexes.
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8085
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`
and `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` (the INFRA lane's compose
stack). A quick standalone Postgres for local use:

```sh
docker run -d --name mea-payment-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

### Try it

Publish an `order.placed` event (e.g. with `kcat`, or from the monolith's
`outbox_relay` management command), then:

```sh
curl "http://localhost:8085/api/payments?orderId=555123"
curl -i "http://localhost:8085/api/payments"   # 400, missing orderId
curl "http://localhost:8085/health"            # consumer readiness
```

A `paymentMethod` containing `DECLINE` (e.g. `"CARD-DECLINE"`) on the
triggering `order.placed` event yields a `DECLINED` payment and a published
`payment.declined` event instead of `payment.captured` -- see `EVENTS.md`.

## Testing

```sh
uv run pytest -m "not integration"   # Layer 1 -- needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Layer 2 -- Testcontainers-managed Kafka + Postgres, needs Docker
uv run ruff check .
```

See `AGENTS.md` for the exact setup commands for each layer.

## Container

```sh
docker build -f Containerfile -t mea-payment-service:r05 .
docker run --rm -p 8085:8085 \
  -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith \
  -e KAFKA_BOOTSTRAP_SERVERS=<host>:9092 \
  mea-payment-service:r05
```

UBI 10 (`ubi10/python-314-minimal`, the same verified tag every other service
in this project uses), multi-stage `uv sync`, non-root (UID 1001, GID 0). The
container's `CMD` runs `alembic upgrade head` before starting uvicorn -- there
is no separate init-container step in this project's compose/CRC stacks.

## Structured logging

Rotating file logs land in `logs/payment-service.log` alongside console
output (see `app/main.py::_configure_logging`), same convention as the rest
of this project's standalone services.
