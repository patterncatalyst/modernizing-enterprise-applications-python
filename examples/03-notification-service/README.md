# 03-notification-service

**ch.17, DRQ-035 -- r03 S5.** The monolith's (`../00-monolith`) `notification`
bounded context, extracted onto a standalone **FastAPI** service on
**`:8002`**. Unlike `../02-review-service` (a lift-and-reauthor of an
existing synchronous REST surface), this extraction is **net-new**: the
monolith never consumed its own `order.placed` outbox event (it only ever
sent the order confirmation synchronously, in-process, from
`order.services.place_order()`), so there is no Django original for the
write path to lift. This service is authored idiomatic-from-the-start:

- An **idempotent `aiokafka` consumer** of the frozen `order.placed` topic
  (see "Event contract" below), recording a `Notification` row into this
  service's **OWN `notification` Postgres schema** -- the **first owned
  schema in this project** (contrast with review-service's shared-schema
  posture, DRQ-028). Migrated with **Alembic**.
- `GET /api/notifications?customerId=` -- the lifted read surface, matching
  the monolith's `notification/views.py::NotificationListView` contract
  byte-for-byte.

See `MIGRATION.md` for the full two-phase write-up and `AGENTS.md` for
agent-facing structure notes.

## Why own schema, not shared (contrast with review-service)

Review only ever *reads* a synchronously-consistent REST contract, so it
could stay in the monolith's shared schema (`../02-review-service/README.md`).
Notification is event-driven: it consumes `order.placed` off Kafka
asynchronously. Sharing the upstream aggregate's table would mean two writers
racing on the same rows (the monolith's synchronous path and this service's
consumer) with no way to reconcile them. Owning the table from the start
avoids that split-brain entirely -- the honest teaching point of DRQ-035's
own-schema decision.

## Event contract (frozen, STEP 0 of the r03 build)

Topic `order.placed`, key = `orderId` (string). JSON value, camelCase:

```json
{
  "orderId": 555123,
  "customerId": 777456,
  "customerEmail": "customer@example.com",
  "totalCents": 4999,
  "confirmationMessage": "Order #555123 confirmed, total $49.99",
  "placedAt": "2026-10-16T05:26:45.253590+00:00"
}
```

There is no shared module between the monolith and this service (each is an
independently deployable project in this repo) -- `app/schemas.py`'s
`OrderPlacedEvent` is this service's own hand-maintained copy of that shape.
That duplication is the honest cost of a JSON wire contract with no schema
registry until ch.28/Apicurio (DRQ-036).

## Idempotency

The monolith's outbox relay is an **at-least-once** publisher -- a crash
between the Kafka send and marking the outbox row published republishes the
identical event. Two layers guarantee a redelivered `order.placed` event
yields exactly one `Notification` row:

1. **Application-level check-then-insert** --
   `app/service.py::record_order_placed` looks up `get_by_order_id` first;
   if a row already exists, it is a no-op.
2. **Database-level partial unique index** -- `uq_notifications_order_id`
   (`UNIQUE (order_id) WHERE order_id IS NOT NULL`, created by
   `migrations/versions/0001_create_notification_schema.py`), the backstop
   for two deliveries racing concurrently (caught as an `IntegrityError` and
   discarded as a duplicate).

Proven by `tests/integration/test_consumer_idempotency.py`: the identical
event is published twice through a real Kafka broker (Testcontainers), and
the notification count for that order id is asserted at exactly one.
`tests/unit/test_service.py` proves the same guarantee at the
function-call level (no Kafka broker, faster).

## Endpoints

CamelCase JSON, **no trailing slash** (`redirect_slashes=False`, same
contract posture as review-service).

| Method | Path | Notes |
|---|---|---|
| GET | `/api/notifications?customerId=` | required query param; `400 VALIDATION_FAILED` if missing |
| GET | `/health` | reports Kafka consumer partition-assignment (CI readiness signal) |

Response body: `{id, customerId, orderId, channel, message, sentAt}` --
matches `notification.serializers.NotificationSerializer`'s field list
exactly. Error body (every non-2xx response):
`{"error": "<CODE>", "message": ..., "timestamp": ...}` -- the same uniform
shape as the monolith's `common/exceptions.py` and review-service's
`app/errors.py`.

There is no write endpoint and no auth gate: this service's only HTTP
surface is a read: the write path is the Kafka consumer.

## Persistence: owned schema, Alembic-migrated

Unlike review-service (no Alembic setup, reads the monolith's shared
schema), this service owns a separate Postgres **schema** (`notification`),
in the SAME Postgres **instance** every example in this project shares by
default (`DATABASE_URL`, default
`postgresql://monolith:monolith@localhost:5432/monolith`). `app/db.py` sets
`search_path=notification,public` on every connection AND every model in
`app/models.py` declares `schema="notification"` explicitly -- the search
path is a convenience, the explicit schema is the correctness guarantee.

## Quickstart

```sh
uv sync --group dev

# One-time: create this service's own `notification` schema + table.
uv run alembic upgrade head

uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`
and `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` (the INFRA lane's compose
stack). A quick standalone Postgres for local use:

```sh
docker run -d --name mea-notification-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

### Try it

Publish an `order.placed` event (e.g. with `kcat`, or from the monolith's
`outbox_relay` management command once `../00-monolith` ships it), then:

```sh
curl "http://localhost:8002/api/notifications?customerId=777456"
curl -i "http://localhost:8002/api/notifications"   # 400, missing customerId
curl "http://localhost:8002/health"                  # consumer readiness
```

## Cutover

Once this service is verified, the strangler proxy (`../01-strangler-proxy`)
flips `STRANGLER_NOTIFICATION_ENABLED=true` so `/api/notifications*` routes
here instead of the monolith.

## Testing

```sh
uv run pytest -m "not integration"   # Layer 1 -- needs a reachable, migrated Postgres, no Kafka
uv run pytest -m integration         # Layer 2 -- Testcontainers-managed Kafka + Postgres, needs Docker
uv run ruff check .
```

See `AGENTS.md` for the exact setup commands for each layer.

## Container

```sh
docker build -f Containerfile -t mea-notification-service:r03 .
docker run --rm -p 8002:8002 \
  -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith \
  -e KAFKA_BOOTSTRAP_SERVERS=<host>:9092 \
  mea-notification-service:r03
```

UBI 10 (`ubi10/python-314-minimal`, the same verified tag `../00-monolith`
and `../02-review-service` use), multi-stage `uv sync`, non-root (UID 1001,
GID 0). The container's `CMD` runs `alembic upgrade head` before starting
uvicorn -- there is no separate init-container step in this project's
compose/CRC stacks.

## Structured logging

Rotating file logs land in `logs/notification-service.log` alongside console
output (see `app/main.py::_configure_logging`), same convention as
review-service.
