# inventory-service -- Migration Notes (ch.19 Phase A -> Phase B, DRQ-009/DRQ-027/DRQ-039/DRQ-041/DRQ-042/DRQ-044)

This file is the measured record of the inventory extraction required by the
r04 build plan and follows `examples/02-review-service/MIGRATION.md` +
`examples/03-notification-service/MIGRATION.md`'s template so ch.19 can cite
real numbers instead of placeholders.

**This extraction is a hybrid of review-service's and notification-service's
stories, not a clean match for either:**

- The **REST read surface** (`GET /api/inventory`, `GET /api/inventory/{sku}`)
  DOES have a monolith original to lift -- `inventory/views.py::
  InventoryListView`/`InventoryDetailView` + `inventory/services.py` --
  same shape as review-service's Phase A/B split.
- The **gRPC mutating surface** (`CheckStock`/`Reserve`/`Release`/`GetStock`)
  has **NO monolith original at all** -- the monolith's `reserve` concern
  (SMELL[ch.18]'s cross-context in-process stock decrement) lived against a
  pessimistic-lock derived query inside the SAME Django transaction as the
  rest of checkout, a fundamentally different mechanism from a server-side
  atomic conditional `UPDATE` exposed over a separate network protocol. Same
  "you cannot lift code that never existed" framing as notification-
  service's `OrderPlacedConsumer` and the Java sibling's own
  `InventoryGrpcServiceImpl` (DRQ-044).

## Per DRQ-009/DRQ-027: no Django-compat shim, Phase A documented not shipped

Per this project's two-phase policy (DRQ-009) and the precedent review-
service/notification-service set (DRQ-027: Phase A documented in
`MIGRATION.md`, never shipped as code), Phase A here would be a thin FastAPI
layer reusing the monolith's Django ORM for the read surface only:

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

@app.get("/api/inventory")
async def list_inventory():
    from inventory.models import InventoryItem
    from asgiref.sync import sync_to_async
    items = await sync_to_async(list)(InventoryItem.objects.all())
    return [StockOut.model_validate(i, from_attributes=True) for i in items]

# There is no faithful Phase A sketch for Reserve/Release/CheckStock/GetStock
# at all -- see "Why the gRPC surface has no Phase A" below.
```

The same two problems review-service's and notification-service's Phase A
sketches surfaced apply here, unchanged:

1. **Django's ORM is synchronous** -- every query needs `sync_to_async(...)`,
   a real latency/concurrency cost under FastAPI's async event loop.
2. **The dependency direction is backwards** -- a service meant to decouple
   `inventory` from the monolith would gain a hard *build-time* dependency on
   the monolith's entire codebase just to reach one model.

### Why the gRPC surface has no Phase A

A faithful Phase A `Reserve` would have to call into the monolith's actual
in-process reservation logic (its pessimistic-lock derived query, running
inside the SAME Django transaction as order/payment/shipping writes) from a
separate FastAPI process over a network call -- which is incoherent: the
monolith's mechanism is specifically "stay in one transaction," and a gRPC
call from a different process cannot join that transaction. There is no
smaller, less-idiomatic version of "atomic check-and-decrement exposed over
gRPC" to lift; the mutating surface is Phase-B-idiomatic by construction, the
same conclusion notification-service's `MIGRATION.md` reached for its
consumer. The measurements below therefore only cover the READ surface's
Phase A vs. Phase B comparison (same scope review-service's and
notification-service's numbers cover) -- the gRPC server's cost is reflected
honestly in Phase B's "running server RSS" since it is live and bound in
that measurement, with nothing to compare it against on the Phase A side.

## Per-component refactor (A -> B), as designed (not built)

| Component | Phase A (Django-ORM lift, illustrative, read-only) | Phase B (idiomatic, shipped) |
|---|---|---|
| HTTP layer | FastAPI routes calling into Django ORM via `sync_to_async` | `app/routes.py` -- native `async`/`await` SQLAlchemy via `app/service.py`/`app/repository.py` |
| Data access | `inventory.models.InventoryItem` (Django ORM, imported from the monolith) | `app/models.py` -- independent SQLAlchemy 2.x mapping onto this service's OWN `inventory` schema, zero import from `00-monolith` |
| Schema ownership | Shared (reads the monolith's `public.inventory_items` table directly) | **Owned** -- this service's own `inventory` Postgres schema, created/migrated/seeded by Alembic (DRQ-044, same posture as notification-service's DRQ-035) |
| Serialization | DRF `InventoryItemSerializer`, reused directly | `app/schemas.py` -- independent Pydantic v2 `StockOut`, camelCase via `Field(alias=...)` |
| Exception mapping | Hand-adapt DRF's `api_exception_handler` output shape | `app/errors.py` -- native FastAPI `@app.exception_handler(...)` registrations, ported from review-service/notification-service, same `{"error","message","timestamp"}` body |
| Mutating surface (`Reserve`/`Release`/`CheckStock`/`GetStock`) | *(did not exist as a liftable concern -- see "Why the gRPC surface has no Phase A" above)* | **Net-new** `app/grpc_server.py::InventoryGrpcServiceServicer` over `grpc.aio`, backed by `app/repository.py`'s single atomic conditional/unconditional `UPDATE` statements (DRQ-041/DRQ-042) |
| Transition sync | *(not applicable)* | **Net-new, transition-only** `app/cdc_consumer.py` -- flag-gated `aiokafka` Debezium consumer, OFF by default, retired after cutover (`CUTOVER.md`) |
| Process model | `django.setup()` in `lifespan`, loading all 6 monolith apps' registries just to reach 1 model | No Django import anywhere; only this service's own owned table is mapped |
| Build dependency | `uv` path dependency on `../00-monolith` | None -- `pyproject.toml` depends only on FastAPI/SQLAlchemy/asyncpg/Pydantic/Alembic/grpcio/protobuf/aiokafka |
| Concurrency | Every DB call threaded via `sync_to_async` (Django ORM is sync-only) | Native `async`/`await` all the way to the driver (`asyncpg`) on BOTH protocol surfaces, sharing one engine/session factory |

## Reserve/Release: atomic, concurrency-safe, and an honest limitation

See `README.md`'s "The gRPC contract IS the anti-corruption layer" section
for the full mechanism. Summary:

- **`Reserve`** -- a single conditional `UPDATE ... WHERE sku = :sku AND
  quantity_on_hand >= :qty`, concurrency-safe on Postgres's own row-level
  write lock, NOT a read-then-write. Proven by
  `tests/test_inventory_grpc.py::test_reserve_concurrent_requests_for_last_unit_exactly_one_succeeds`:
  two concurrent `Reserve(sku, 1)` calls racing a sku with exactly 1 unit on
  hand yield exactly one `reservation_ok=true`, never both.
- **`Release`** -- a single unconditional `UPDATE`, intentionally
  non-idempotent (documented, not solved, deferred to a later
  choreographed-saga chapter per this project's scope discipline).

## Verification

- `uv run alembic upgrade head` against a throwaway `postgres:18.6-alpine`:
  creates the `inventory` schema, the `inventory_items` table, and the
  unique index `uq_inventory_items_sku`, then seeds the 3 demo skus
  (`SKU-WIDGET-001`/100, `SKU-GADGET-002`/50, `SKU-GIZMO-003`/5) -- confirmed
  via `psql`'s `\dn`/`\dt`/`SELECT`. Re-running `alembic upgrade head`
  against an already-migrated-and-seeded database is a correct no-op
  (confirmed both directly and via the Containerfile's own build-time run).
- `uv run pytest`: **16 passed** -- 5 REST contract tests (camelCase list,
  seed-value match, camelCase single-item get, 404-uniform-body for an
  unknown sku, no-trailing-slash) + 11 gRPC servicer tests
  (`CheckStock` sufficient/insufficient/unknown-sku, `GetStock` known/unknown,
  `Reserve` sufficient/insufficient/sequential-over-reserve, `Release`
  restores/unknown-sku, and the **concurrency race test** -- two concurrent
  `Reserve` calls for the last unit of `SKU-GIZMO-003`, exactly one
  succeeds, confirmed stable across 5 repeated runs). No Kafka broker
  required anywhere in this suite (the CDC consumer is flag-gated off; gRPC
  tests call `InventoryGrpcServiceServicer`'s coroutine methods directly).
- `uv run ruff check .`: **All checks passed.**
- Live run on `:8084`/`:9004` against a throwaway Postgres:
  - `GET /health` -> `200`, `{"status":"ok","grpcServerListening":true}`.
  - `GET /api/inventory` -> `200`, 3 camelCase items matching the monolith's
    seed values exactly.
  - `GET /api/inventory/NOPE` -> `404`,
    `{"error":"NOT_FOUND","message":"No inventory item with sku NOPE",...}`.
  - gRPC (`grpc.insecure_channel` + the generated stub, real network calls,
    not in-process): `Reserve(SKU-WIDGET-001, 5)` ->
    `reservation_ok: true, on_hand_qty: 95`; `Release(SKU-WIDGET-001, 5)` ->
    `reservation_ok: true, on_hand_qty: 100` (restored exactly to baseline);
    `Reserve(SKU-GIZMO-003, 999)` -> `reservation_ok` omitted (protobuf text
    format elides default/`false` values) with `on_hand_qty: 5` -- unchanged,
    no partial decrement on insufficient stock; `GetStock(SKU-GIZMO-003)` ->
    `available: true, on_hand_qty: 5`.
  - `GET /api/inventory` re-read after the gRPC round trip confirmed
    `quantityOnHand` back at the original seed values for all three skus.
- Containerfile: `docker build -f Containerfile -t mea-inventory-service:r04 .`
  -- builds successfully (UBI 10 multi-stage, non-root, both deps and app
  installed via `uv sync --locked`). A live container run (`--network host`,
  override `DATABASE_URL` to a fresh throwaway Postgres) confirmed the
  image's `CMD` (`alembic upgrade head && exec uvicorn ...`) ran the
  migration+seed, then served `GET /health` -> `grpcServerListening: true`
  and `GET /api/inventory` -> the 3 seeded items, inside the container.

## Before / after metrics

Method: real runs on this machine (not estimates), same method notification-
service's `MIGRATION.md` established. "Phase A" numbers are the measured
proxy: `django.setup()` against `00-monolith`'s actual `config.settings`
(all six Django apps installed) plus a real `import fastapi, uvicorn` in the
same process, via `uv run --with fastapi==0.143.2 --with uvicorn==0.54.0`
from `00-monolith`'s own directory (so the proxy measurement never adds a
real dependency to either service's `pyproject.toml`) -- not a running
server, since Phase A code was never built. "Phase B" numbers are this
service's actual shipped `app/main.py` import graph, which also imports
`grpc` and `aiokafka` (Phase A's proxy deliberately imports neither --
messaging and gRPC are Phase-B-only capability, same framing as
notification-service's `aiokafka`-only delta). Import timing is
`time.perf_counter()` around a bare `import app.main` (4 runs each, warm
filesystem cache; the first run discarded as resolver/cold-cache noise). RSS
is `resource.getrusage(...).ru_maxrss` (import-only) or `ps -o rss` on the
real running uvicorn worker process (not the `uv run` wrapper process).

| Metric | Phase A (proxy: `django.setup()` + `import fastapi, uvicorn`) | Phase B (shipped `app/main.py`, includes `grpc` + `aiokafka`) |
|---|---|---|
| Cold interpreter floor (`python -I -c "pass"`) | 0.01 s | 0.01 s |
| Import/startup time (3-run avg, warm cache; first run discarded) | 0.264 s | 0.312 s |
| Import-only RSS (`ru_maxrss`) | 76,088 KB (~74.3 MB) | 92,493 KB (~90.3 MB) |
| Running server RSS (actual uvicorn worker, after 20 requests, gRPC server also bound) | not measured (no server built) | 108,360 KB (~105.8 MB) |

**Reading the numbers honestly:** unlike review-service's near-wash finding,
and more in line with notification-service's reading, Phase B costs
noticeably more at both the import stage (+~16 MB, +~0.05 s, `grpc`'s own
C-extension and `aiokafka`'s import graph) and the running-server stage
(~105.8 MB vs. ~90.3 MB import-only -- the gap being the bound gRPC server's
own buffers/thread pool plus the live asyncpg connection pool). This is not
a regression to chase down: Phase A's proxy measures a read-only surface
with no gRPC capability at all, while Phase B's running number reflects a
SEPARATE live network server actually bound and accepting connections on
`:9004` alongside the HTTP surface on `:8084` -- real capability Phase A
never had, matching the Java sibling's own Phase A -> Phase B reading for
this exact service (`~/Dev/modernizing-enterprise-applications/examples/04-inventory-service/MIGRATION.md`,
whose packaged-JVM RSS actually DROPPED Phase A -> Phase B for different,
JVM-specific reasons -- removing three Spring-compat extensions cost more at
JVM boot than one more gRPC server; Python has no equivalent compat-shim
removal to offset against, so the honest reading here is a straightforward
"real capability costs real memory," not a wash or a win).
