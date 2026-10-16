# shipping-service -- Migration Notes (Phase A -> Phase B)

This file is the measured record of the shipping extraction, following
`examples/05-payment-service/MIGRATION.md`'s template so the numbers below
are real, not placeholders.

**This extraction differs from every prior lane's in one important way:**
it is the first ORCHESTRATED saga in this project (r01-r05 are all either
synchronous-in-process or choreographed). The monolith DOES dispatch
shipping today, but **synchronously, in-process**, inside
`order.services.handle_payment_captured` (itself already reacting to
`05-payment-service`'s `payment.captured` event when `PAYMENT_MODE=
choreographed`, or inline inside checkout's own `transaction.atomic()` when
`PAYMENT_MODE=synchronous`). A multi-step, DB-backed, orchestrated saga
reacting to that same event has no synchronous original to lift: the whole
engine (`app/orchestrator.py`, `app/steps.py`) is authored fresh, even though
the underlying `SHIP-FAIL` rule is lifted byte-for-byte from
`shipping.services.dispatch`.

## Per DRQ-009/DRQ-027-equivalent: no Django-compat shim, Phase A documented not shipped

Per this project's two-phase policy and the precedent every prior lane set,
Phase A here would be a thin FastAPI layer reusing the monolith's Django ORM
for the read surface only:

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

@app.get("/api/shipments")
async def list_shipments(orderId: int | None = None):
    if orderId is None:
        raise HTTPException(status_code=400, detail="orderId is required")
    from shipping.models import Shipment
    from asgiref.sync import sync_to_async
    shipments = await sync_to_async(list)(
        Shipment.objects.filter(order_id=orderId).order_by("id")
    )
    return [ShipmentOut.model_validate(s, from_attributes=True) for s in shipments]
```

The same problems every other standalone service's Phase A sketch surfaced
apply here, unchanged, PLUS a new one unique to this lane:

1. **Django's ORM is synchronous** -- every query needs `sync_to_async(...)`.
2. **The dependency direction is backwards** -- a service meant to decouple
   `shipping` from the monolith would gain a hard *build-time* dependency on
   the monolith's entire codebase just to reach one model.
3. **There is nothing for Phase A's write path to lift, for the same reason
   `05-payment-service`'s Phase A had nothing to lift** -- the monolith's
   real write path (`shipping.services.dispatch`) runs SYNCHRONOUSLY inside
   the checkout/saga-listener's own transaction, with no Kafka consumer or
   saga state machine wrapping it.
4. **Net-new for THIS lane: there is no "simple consumer" shape to even
   approximate.** Every prior choreographed service's Phase A gap was "the
   write path is net-new"; here the ENGINE ITSELF (multi-step orchestration,
   compensation, crash-resume) has no single-function equivalent to sketch
   at all -- a Phase A "orchestrator" would just be this service's actual
   Phase B code with the words removed, so there was nothing non-trivial for
   a separate illustrative module to demonstrate.

Given that, and since the acceptance bar is "Phase B is the final, live
code, Phase A is documented," the team did not spend implementation/CI
surface on a Phase A module.

## Per-component refactor (A -> B), as designed (not built)

| Component | Phase A (Django-ORM lift, illustrative, read-only) | Phase B (idiomatic, shipped) |
|---|---|---|
| HTTP layer | FastAPI route calling into Django ORM via `sync_to_async` | `app/routes.py` -- native `async`/`await` SQLAlchemy via `app/repository.py` |
| Data access | `shipping.models.Shipment` (Django ORM, imported from the monolith, `order` is a hard FK) | `app/models.py` -- independent SQLAlchemy 2.x mapping onto this service's OWN `shipping` schema; `order_id` is a plain value, zero import from `00-monolith` |
| Schema ownership | Shared (reads the monolith's `public.shipments` table, FK-joined to `orders`) | **Owned** -- this service's own `shipping` Postgres schema (4 tables), created/migrated by Alembic |
| Serialization | DRF `ShipmentSerializer`, reused directly | `app/schemas.py` -- independent Pydantic v2 `ShipmentOut`, camelCase via `Field(alias=...)` |
| Dispatch/SHIP-FAIL logic | `shipping.services.dispatch` -- synchronous, raises `ShippingFailed`, called in-process from checkout's/the saga listener's own transaction | `app/steps.py::dispatch`/`book_carrier` -- same `SHIP-FAIL` rule, split across two saga steps so a failure after persistence can be compensated instead of relying on a transaction rollback |
| Orchestration | None -- shipping is one function call inside a larger synchronous/choreographed flow | **Net-new** `app/orchestrator.py` -- a DB-backed saga state machine (`sagas`/`saga_log`), adapted from the CNDP `17-sagas` Python orchestrator |
| Enrichment | Direct Python attribute access (`order.shipping_address`, same process, same transaction) | **Net-new** `app/enrich_client.py` -- an HTTP call (`tenacity` retry + timeout) to the monolith's `GET /api/orders/{id}`, now a genuinely separate process/deployment |
| Write path | Synchronous, in-process, inside checkout's/the saga listener's transaction -- no consumer, no saga state | **Net-new** `app/consumer.py::PaymentCapturedConsumer` + `app/service.py::handle_payment_captured` -- idempotent `aiokafka` consumer of `payment.captured`, starting an ORCHESTRATED saga, no gRPC |
| Outcome notification | None -- shipping success/failure is just part of the order's own status; the monolith never emits an event about it | **Net-new** -- this service's OWN transactional outbox (`app/models.py::OutboxEvent`) + relay (`app/relay.py`), publishing `shipment.dispatched`/`shipment.failed` |
| Crash recovery | Not applicable -- synchronous, exactly-once by construction (one request, one DB transaction); a mid-flight crash just fails the whole checkout and nothing is in an ambiguous state | **Net-new** -- `app/orchestrator.py::resume_running_sagas()`, a startup scan that re-drives any `RUNNING`/`COMPENSATING` saga from its persisted `step_index`/`context` |
| Idempotency | Not applicable -- synchronous, exactly-once by construction | **Net-new** -- check-then-insert dedupe by `order_id` + a database-level unique index backstop (`uq_sagas_order_id`), required because the saga's `payment.captured` trigger is at-least-once |
| Exception mapping | Hand-adapt DRF's `api_exception_handler` output shape | `app/errors.py` -- native FastAPI `@app.exception_handler(...)` registrations, ported from every other standalone service |
| Process model | `django.setup()` in `lifespan`, loading all 6 monolith apps' registries just to reach 1 model | No Django import anywhere; only this service's own owned tables are mapped |
| Build dependency | `uv` path dependency on `../00-monolith` | None -- `pyproject.toml` depends only on FastAPI/SQLAlchemy/asyncpg/Pydantic/aiokafka/Alembic/httpx/tenacity. No grpcio: this service never calls, or is called via, gRPC |
| Concurrency | Every DB call threaded via `sync_to_async` (Django ORM is sync-only) | Native `async`/`await` all the way to the driver (`asyncpg`), plus a fully async Kafka consumer AND producer (`aiokafka`) and a fully async HTTP client (`httpx`), all running concurrently |

## The durability upgrade over the Java sibling (Camel Saga EIP, in-memory)

The Java sibling
(`~/Dev/modernizing-enterprise-applications/examples/06-shipping-service`)
implements the identical four-step saga
(`enrich -> dispatch -> book_carrier -> emit`, with `cancel_shipment` as
`dispatch`'s compensation, and the identical `SHIP-FAIL` ordering constraint)
as a **Camel Saga EIP** route. Camel's `CamelSagaService` coordinator tracks
which saga is in which step **in memory** -- correct while the process is
alive, but a pod restart mid-saga loses that tracking entirely; there is no
documented resume path in that implementation.

This service's orchestrator persists the identical state (`status`,
`step_index`, `context`) as a row in `shipping.sagas` instead, and
`app/orchestrator.py::resume_running_sagas()` re-drives every
`RUNNING`/`COMPENSATING` row on startup. That is not a theoretical
improvement -- `tests/integration/test_crash_resume.py` seeds a `RUNNING`
saga row with `step_index=1` (simulating a process that died after `enrich`
committed but before `dispatch` ran), calls `resume_running_sagas()`
directly, and asserts: (1) `enrich` is never re-invoked (proving the
persisted `step_index`/`context` were actually honored, not recomputed from
scratch), and (2) the saga still reaches `COMPLETED` with a `DISPATCHED`
shipment and exactly one `shipment.dispatched` outbox row. The Java sibling
has no equivalent test, because its coordinator has no equivalent recovery
path to test.

## Idempotency mechanism

The `payment.captured` publisher is, like every outbox relay in this
project, **at-least-once**. Two layers guarantee a redelivered event starts
at most one saga per order:

1. **Application-level check-then-insert** --
   `app/service.py::handle_payment_captured` looks up `get_saga_by_order_id`
   first; if a saga already exists, it is a no-op.
2. **Database-level unique index** -- `uq_sagas_order_id` (UNIQUE on
   `order_id`, `migrations/versions/0001_create_shipping_schema.py`), the
   backstop for two deliveries racing concurrently (caught in
   `app/service.py` as an `IntegrityError` and discarded as a duplicate).

This service's OWN outbox relay (`app/relay.py`) has a second, independent
at-least-once guarantee on the PUBLISH side: the Kafka send and the
`published_at` stamp are two separate operations, so a crash between them
republishes the identical payload on the next poll.

Proven three ways:

- `tests/unit/test_orchestrator.py::test_handle_payment_captured_is_idempotent_on_redelivery`
  -- calls `handle_payment_captured` with the identical event twice directly
  (no Kafka broker), asserts exactly one `Saga` row, one `Shipment` row, and
  one outbox row.
- `tests/integration/test_shipping_saga.py` -- publishes `payment.captured`
  through a REAL Kafka broker (Testcontainers) and asserts the matching
  `shipment.dispatched`/`shipment.failed` record lands on the wire with the
  documented shape.
- `tests/integration/test_crash_resume.py` -- the saga-level durability
  proof described above.

## Verification

- `uv run pytest`: **13 passed** -- 6 REST contract tests
  (`tests/unit/test_shipments.py`: camelCase list, filter-by-order,
  empty-array-for-unknown-order, missing-orderId-400, 404-by-id,
  no-trailing-slash) + 3 orchestrator unit tests
  (`tests/unit/test_orchestrator.py`: happy-path dispatch+emit->COMPLETED,
  SHIP-FAIL->compensate->CANCELLED+`shipment.failed`-no-dispatched,
  idempotent-redelivery->one-saga) + 2 Testcontainers Kafka-round-trip
  integration tests (`tests/integration/test_shipping_saga.py`:
  capture->dispatch->publish, SHIP-FAIL->compensate->publish) + 2
  Testcontainers crash-resume integration tests
  (`tests/integration/test_crash_resume.py`: resumes a seeded RUNNING saga
  from its persisted `step_index` without re-invoking the already-completed
  `enrich` step, and a no-op when nothing is in flight).
- `uv run ruff check .`: **All checks passed.**
- `alembic upgrade head` against a throwaway `postgres:18.6-alpine`: creates
  the `shipping` schema, all 4 tables (`shipments`, `outbox`, `sagas`,
  `saga_log`), and every index (`idx_shipments_order_id`,
  `idx_shipping_outbox_unpublished` partial, `uq_sagas_order_id` unique,
  `idx_saga_log_saga_id`) -- confirmed via `psql`'s `\dn`/`\dt`/`\di`.
  Re-running against an already-migrated database is a correct no-op.
- Containerfile: `docker build -f Containerfile -t mea-shipping-service:r06 .`
  -- builds successfully (UBI 10 multi-stage, non-root). The built image was
  then run LIVE (not just built) on a Docker bridge network against the same
  throwaway Postgres, a real single-node KRaft Kafka broker
  (`apache/kafka:4.3.1`), and a minimal stand-in HTTP server for the
  monolith's `GET /api/orders/{id}` enrichment call:
  - `GET /health` -> `200`,
    `{"status":"ok","consumerPartitionsAssigned":true,"resumeComplete":true,"resumedSagaCount":0}`.
  - A normal-address `payment.captured` event -> saga reached `COMPLETED`;
    `GET /api/shipments?orderId=...` -> `200`, one `DISPATCHED` shipment;
    `shipment.dispatched` observed on the real topic with the exact
    documented shape (`orderId`, `shipmentId`, `address`, `status`,
    `occurredAt`).
  - A `SHIP-FAIL`-address `payment.captured` event -> saga reached
    `COMPENSATED`; the shipment row flipped to `CANCELLED` (never deleted);
    `shipment.failed` observed on the wire with `status="FAILED"` and a
    `reason` naming the sentinel.
  - `GET /api/shipments/{unknown id}` -> `404`,
    `{"error":"NOT_FOUND",...}`; `GET /api/shipments` (no `orderId`) ->
    `400`, `{"error":"VALIDATION_FAILED",...}`; `GET /api/shipments/`
    (trailing slash) -> `404`, not a 307 redirect.
  - **The crash-resume proof, reproduced live (not just in the
    Testcontainers test):** a `RUNNING` saga row was inserted directly into
    the running container's Postgres with `step_index=1` and
    `context={"enrich": {"address": ...}}` -- simulating a process that died
    right after `enrich` committed. The container was then `docker restart`ed.
    The startup log showed `resuming saga <id> (status=RUNNING)` followed
    immediately by `dispatch`/`emit` -- with NO new `GET
    /api/orders/{id}` HTTP request logged for that order, proving `enrich`
    was not re-run -- and `/health` reported `resumedSagaCount: 1` after
    restart. The saga reached `COMPLETED` with a `DISPATCHED` shipment,
    exactly matching `tests/integration/test_crash_resume.py`'s assertions
    against a live, restarted container instead of a Testcontainers Postgres.

## Before / after metrics

Not applicable in the way `05-payment-service/MIGRATION.md` measures it:
this lane has no Phase A implementation to import-time/RSS-compare against
(see "Per DRQ-009/DRQ-027-equivalent" above -- there was nothing non-trivial
for an illustrative Phase A module to demonstrate). The honest comparison for
this lane is qualitative, not a before/after import-time table: a
`Shipment` row written by the monolith's in-process `dispatch()` costs
nothing extra and cannot survive a process crash mid-saga by construction
(there is no multi-step saga to crash mid-way through); this service's saga
costs a handful of extra Postgres round trips per order (one transaction per
step, typically four) and a background consumer + relay + HTTP client
running continuously, in exchange for a saga that is provably resumable
after a crash (see `tests/integration/test_crash_resume.py`) -- a capability
the monolith's synchronous dispatch never needed, and the Java sibling's
in-memory coordinator does not have either.
