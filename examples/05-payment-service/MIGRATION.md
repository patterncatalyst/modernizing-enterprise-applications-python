# payment-service -- Migration Notes (Phase A -> Phase B)

This file is the measured record of the payment extraction, following
`examples/03-notification-service/MIGRATION.md`'s template so the numbers
below are real, not placeholders.

**This extraction differs from notification-service's in one important way:**
notification-service's write path is net-new because the monolith never
consumed its own `order.placed` event. Payment's write path is net-new for a
different reason -- the monolith DOES charge payment today, but
**synchronously, in-process**, inside the same `transaction.atomic()` as the
inventory reservation (`00-monolith/payment/services.py::charge`). A
choreographed, asynchronous consumer reacting to `order.placed` has no
synchronous original to lift: the control flow (idempotent dedupe, never
raising, emitting an outbox event instead of an HTTP 402) is authored fresh,
even though the underlying DECLINE rule is lifted byte-for-byte.

## Per DRQ-009/DRQ-027-equivalent: no Django-compat shim, Phase A documented not shipped

Per this project's two-phase policy and the precedent notification-/
review-service set, Phase A here would be a thin FastAPI layer reusing the
monolith's Django ORM for the read surface only:

```python
# app/main.py -- Phase A (illustrative, not committed)
import django
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

@asynccontextmanager
async def lifespan(app: FastAPI):
    django.setup()  # loads ALL SIX monolith apps' model/admin/app registries
    yield

app = FastAPI(lifespan=lifespan, redirect_slashes=False)

@app.get("/api/payments")
async def list_payments(orderId: int | None = None):
    if orderId is None:
        raise HTTPException(status_code=400, detail="orderId is required")
    from payment.models import Payment
    from asgiref.sync import sync_to_async
    payments = await sync_to_async(list)(
        Payment.objects.filter(order_id=orderId).order_by("id")
    )
    return [PaymentOut.model_validate(p, from_attributes=True) for p in payments]
```

The same problems notification-/review-service's Phase A sketches surfaced
apply here, unchanged:

1. **Django's ORM is synchronous** -- every query needs `sync_to_async(...)`.
2. **The dependency direction is backwards** -- a service meant to decouple
   `payment` from the monolith would gain a hard *build-time* dependency on
   the monolith's entire codebase just to reach one model.
3. **There is nothing for Phase A's write path to lift, in a different way
   than notification's case.** The monolith's real write path
   (`payment.services.charge`) exists and could technically be imported, but
   it runs SYNCHRONOUSLY inside the checkout request's own transaction, with
   no Kafka consumer wrapping it. Lifting it as-is would mean calling
   synchronous, Django-ORM-coupled code from an async consumer loop -- not a
   meaningfully different exercise than writing the idiomatic version
   directly. Given that, and since the acceptance bar is "Phase B is the
   final, live code, Phase A is documented," the team did not spend
   implementation/CI surface on a Phase A module whose only non-trivial
   component (the consumer + outbox) would have to be Phase-B-idiomatic
   anyway.

## Per-component refactor (A -> B), as designed (not built)

| Component | Phase A (Django-ORM lift, illustrative, read-only) | Phase B (idiomatic, shipped) |
|---|---|---|
| HTTP layer | FastAPI route calling into Django ORM via `sync_to_async` | `app/routes.py` -- native `async`/`await` SQLAlchemy via `app/repository.py` |
| Data access | `payment.models.Payment` (Django ORM, imported from the monolith, `order` is a hard FK) | `app/models.py` -- independent SQLAlchemy 2.x mapping onto this service's OWN `payment` schema; `order_id` is a plain value, zero import from `00-monolith` |
| Schema ownership | Shared (reads the monolith's `public.payments` table, FK-joined to `orders`) | **Owned** -- this service's own `payment` Postgres schema, created/migrated by Alembic |
| Serialization | DRF `PaymentSerializer`, reused directly | `app/schemas.py` -- independent Pydantic v2 `PaymentOut`, camelCase via `Field(alias=...)` |
| Charge logic | `payment.services.charge` -- synchronous, raises `PaymentDeclined`, called in-process from checkout's own transaction | `app/service.py::charge` -- same DECLINE rule, never raises, returns a status so a `Payment` row (and an event) exists either way |
| Write path | Synchronous, in-process, inside checkout's `transaction.atomic()` -- no consumer | **Net-new** `app/consumer.py::OrderPlacedConsumer` + `app/service.py::process_order_placed` -- idempotent `aiokafka` consumer of `order.placed`, choreographed, no orchestrator |
| Outcome notification | None -- a decline is an HTTP 402 to the checkout caller; a capture is silent | **Net-new** -- this service's OWN transactional outbox (`app/models.py::OutboxEvent`) + relay (`app/relay.py`), publishing `payment.captured`/`payment.declined` |
| Idempotency | Not applicable -- synchronous, exactly-once by construction (one HTTP request, one DB transaction) | **Net-new** -- check-then-insert dedupe by `order_id` + a database-level unique index backstop, required because the choreography's `order.placed` trigger is at-least-once |
| Exception mapping | Hand-adapt DRF's `api_exception_handler` output shape | `app/errors.py` -- native FastAPI `@app.exception_handler(...)` registrations, ported from notification-/review-service |
| Process model | `django.setup()` in `lifespan`, loading all 6 monolith apps' registries just to reach 1 model | No Django import anywhere; only this service's own owned tables are mapped |
| Build dependency | `uv` path dependency on `../00-monolith` | None -- `pyproject.toml` depends only on FastAPI/SQLAlchemy/asyncpg/Pydantic/aiokafka/Alembic. No grpcio: this service never calls, or is called via, gRPC |
| Concurrency | Every DB call threaded via `sync_to_async` (Django ORM is sync-only) | Native `async`/`await` all the way to the driver (`asyncpg`), plus a fully async Kafka consumer AND producer (`aiokafka`) running concurrently |

## Idempotency mechanism

The `order.placed` publisher is, like every outbox relay in this project,
**at-least-once**. Two layers guarantee a redelivered event yields exactly
one `Payment` row and exactly one outbox event:

1. **Application-level check-then-insert** --
   `app/service.py::process_order_placed` looks up `get_by_order_id` first;
   if a payment already exists, it is a no-op.
2. **Database-level unique index** -- `uq_payments_order_id` (UNIQUE on
   `order_id`, `migrations/versions/0001_create_payment_schema.py`), the
   backstop for two deliveries racing concurrently (caught in
   `app/service.py` as an `IntegrityError` and discarded as a duplicate).

This service's OWN outbox relay (`app/relay.py`) has a second,
independent at-least-once guarantee on the PUBLISH side: the Kafka send and
the `published_at` stamp are two separate operations, so a crash between
them republishes the identical payload on the next poll.

Proven two ways:

- `tests/unit/test_service.py::test_process_order_placed_is_idempotent_on_redelivery`
  -- calls `process_order_placed` with the identical event twice directly
  (no Kafka broker), asserts exactly one `Payment` row and one outbox row.
- `tests/integration/test_payment_choreography.py::test_redelivered_order_placed_event_yields_exactly_one_payment_and_outbox_row`
  -- publishes the identical event twice through a REAL Kafka broker
  (Testcontainers) and the real `OrderPlacedConsumer`, asserts exactly one
  row of each after both deliveries are processed.

Verified live during this build too (manual `aiokafka` producer against a
throwaway Postgres + Kafka pair, not Testcontainers): publishing the same
`order.placed` payload (normal method) twice yielded exactly one `CAPTURED`
payment row, with the service log showing the second delivery hit the
`"already has a payment recorded, skipping (idempotent no-op)"` path. A
separate `order.placed` event with a `CARD-DECLINE` method yielded exactly
one `DECLINED` payment row and one published `payment.declined` record
(including a `reason`); the normal-method event's `payment.captured` record
was also confirmed on the wire via a raw consumer, matching the
`EVENTS.md`-documented shape exactly (`orderId`, `paymentId`, `amountCents`,
`method`, `status`, `occurredAt`, plus `reason` only on the declined one).

## Verification

- `uv run pytest`: **16 passed** -- 9 REST contract + `app.service` unit
  tests (camelCase list, filter-by-order, empty-array-for-unknown-order,
  missing-orderId-400, 404-by-id, camelCase get-by-id, no-trailing-slash,
  `charge()` capture/decline/null-method-captures) + 4 `app.service`
  idempotency/outbox-atomicity unit tests (capture-writes-matching-outbox,
  decline-writes-matching-outbox, null-method-never-crashes,
  redelivery-is-idempotent) + 3 Testcontainers integration tests (Kafka +
  Postgres: capture-and-publish, decline-and-publish,
  redelivery-yields-exactly-one-payment-and-outbox-row).
- `uv run ruff check .`: **All checks passed.**
- `alembic upgrade head` against a throwaway `postgres:18.6-alpine`: creates
  the `payment` schema, the `payments` table + unique `uq_payments_order_id`
  index, and the `outbox` table + partial `idx_payment_outbox_unpublished`
  index -- confirmed via `psql`'s `\dn`/`\dt`/`\di`. Re-running against an
  already-migrated database is a correct no-op (confirmed via the
  Containerfile build's live run).
- Live run on `:8085` against a throwaway Postgres + a real single-node Kafka
  broker (manual `aiokafka` producer, not Testcontainers), verified with
  `curl` and a raw Kafka consumer:
  - `GET /health` -> `200`, `{"status":"ok","consumerPartitionsAssigned":true}`
    once the consumer group join completes.
  - Normal-method `order.placed` -> `GET /api/payments?orderId=...` ->
    `200`, one `CAPTURED` payment; `payment.captured` observed on the wire
    with the exact documented shape.
  - `CARD-DECLINE`-method `order.placed` -> one `DECLINED` payment;
    `payment.declined` observed on the wire, including `reason`.
  - Redelivering the normal-method event a second time -> still exactly one
    payment row (no duplicate insert, idempotent no-op logged).
  - `GET /api/payments` (no `orderId`) -> `400`,
    `{"error":"VALIDATION_FAILED",...}`.
  - `GET /api/payments/{unknown id}` -> `404`, `{"error":"NOT_FOUND",...}`.
  - `GET /api/payments/` (trailing slash) -> `404`, not a 307 redirect.
- Containerfile: `docker build -f Containerfile -t mea-payment-service:r05 .`
  -- builds successfully (UBI 10 multi-stage, non-root). The built image was
  then run live (not just built) against the same throwaway Postgres +
  Kafka pair on a shared Docker network: `alembic upgrade head` ran and
  no-op'd correctly, the consumer joined its group, the relay published both
  outcome events, and `/health`/`/api/payments` responded correctly from
  inside the container.

## Before / after metrics

Method: real runs on this machine (not estimates), same methodology as
`03-notification-service/MIGRATION.md`. "Phase A" numbers are the measured
proxy: `django.setup()` against `00-monolith`'s actual `config.settings`
(all six Django apps installed) plus a real `import fastapi, uvicorn` in the
same process, via `uv run --with fastapi==0.143.2 --with uvicorn==0.54.0`
from `00-monolith`'s own directory (so the proxy measurement never adds a
real dependency to either service's `pyproject.toml`) -- not a running
server, since Phase A code was never built. "Phase B" numbers are this
service's actual shipped `app/main.py`, which also imports `aiokafka`.
Import timing is `/usr/bin/time -f '%e'` around a bare import (4 runs each,
warm filesystem cache; the first run of each is discarded as
resolver/cold-cache noise). RSS is `resource.getrusage(...).ru_maxrss`
(import-only) or `ps -o rss` on the real running uvicorn worker process
(after 20 requests), not the `uv run` wrapper process.

| Metric | Phase A (proxy: `django.setup()` + `import fastapi, uvicorn`) | Phase B (shipped `app/main.py`, includes `aiokafka`) |
|---|---|---|
| Cold interpreter floor (`python -I -c "pass"`) | 0.01 s | 0.01 s |
| Import/startup time (3-run avg, warm cache; first run discarded) | 0.42 s | 0.43 s |
| Import-only RSS (`ru_maxrss`) | 76,004 KB (~74.2 MB) | 78,068 KB (~76.2 MB) |
| Running server RSS (actual uvicorn worker, after 20 requests) | not measured (no server built) | 92,680 KB (~90.5 MB) |

**Reading the numbers honestly:** like notification-service's finding,
import-time and import-RSS are close between the two phases -- FastAPI/
Pydantic v2's own import graph dominates both, and `aiokafka`'s added import
cost (Phase B only) is modest relative to that baseline. Phase B's *running*
RSS (~90 MB) reflects something Phase A's proxy cannot measure at all: a
live `aiokafka` consumer AND producer, each with their own broker
connection, buffers, and (for the consumer) consumer-group membership,
running continuously in the background -- real capability Phase A (a
synchronous, in-process charge with no messaging at all) never had. That gap
is the honest cost of the choreography actually running, not a regression to
be optimized away.
