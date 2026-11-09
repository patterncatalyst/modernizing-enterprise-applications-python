---
title: "Extraction 1: Review Service"
order: 15
part: "The Strangler Fig in Practice"
description: "The first extraction end to end: capture the equivalence gate, stand up a FastAPI service on the shared tables, cut over behind the flag, keep the fallback."
duration: 45 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why Review is the right first context to extract: REST-only, no synchronous collaborator.
- Capture the Newman equivalence collection before any code moves, and use it as the check that turns "behaves the same" into a yes or no.
- Stand up `examples/02-review-service` on the monolith's own Postgres tables, so the strangler proxy flag cuts traffic over with no migration in the loop.
- Run the two-phase migration: document a Phase A that bridges the Django ORM with `sync_to_async`, ship Phase B with independent SQLAlchemy mappings and a `passlib` check of Django's password hash.
- Measure Phase A's cost through an import and startup proxy, and explain why the win is structural, not a startup number.
- Cut over behind the flag in both directions (58/58 assertions) and read the negative check as proof the equivalence suite tests this service's presence.

## Why this matters

The strangler proxy can hand any request to a different backend without the client noticing. This is the first real use: pull the `review` bounded context out of the Django monolith onto its own FastAPI service and prove the whole loop. Capture the contract, stand up the seam, migrate the implementation in two measured phases, cut traffic over, leave the fallback in place. Every later extraction repeats this loop against harder dependencies, and this one proves it on the easiest case. The code is in `examples/02-review-service/`; run it with `uv run uvicorn app.main:app --host 0.0.0.0 --port 8001`. Its `README.md` covers the rest.

## Why Review leaves first

Extraction order is a design decision. `review/models.py` states the reason:

> Note what review does NOT depend on: order, payment, shipping, or notification.

Review is the least-coupled context: a REST leaf that clients read and write, which nothing calls synchronously and which calls nothing. The other contexts carry the hard problems. `order/services.py` is a god service reaching into four contexts inside one ACID transaction and is extracted last. `notification` has a dual-write hazard between a database write and an external call, cured by a transactional outbox. Every context shares one Postgres schema with cross-context foreign keys, cured by moving to owned data. Review has none of that, so it proves the extraction mechanism (equivalence gate, flag, cutover, two-phase migration) without a distributed-transaction problem in the same step.

It does have one smell worth curing: despite no runtime dependency on another context, its write endpoint borrows the monolith's shared `django.contrib.auth`, the same `auth_user` table and `BasicAuthentication` class every context would reach for. `review/views.py` says so:

> Review has no runtime dependency on order/inventory/payment/shipping/
> notification ... yet here it is, borrowing that machinery anyway.

The service keeps the same external contract (`POST /api/reviews` needs HTTP Basic, `GET` stays open) and verifies the same password hash format on its own terms. The service README calls this Option B: keep the contract, stop borrowing the mechanism.

## The equivalence suite comes first

Before a line of the service existed, the contract it must match did: `tooling/newman/mea.postman_collection.json`, captured against the monolith and frozen as the observable behavior every extraction is held to. It specifies exact status codes, exact JSON shapes (camelCase fields, the `{"error", "message", "timestamp"}` error envelope) and exact headers (`Location: /api/reviews/{id}` as a relative path). None of it was adjusted afterward to make the new service's output look right. Without a suite frozen ahead of time, "behaves the same" drifts into "close enough that nobody noticed". The definition of "equivalent" exists before the thing it defines.

## The seam: same database, one driver translation

The service is FastAPI on `:8001` and owns no schema. `app/db.py` points at the same database and tables (`reviews`, `customers`, `inventory_items`, `auth_user`) that the monolith's `manage.py migrate` and `manage.py seed` create. Owned data is a later step; here the goal is behavioral equivalence through a safe cutover, and sharing tables is what lets the proxy flip `STRANGLER_REVIEW_ENABLED` with no migration. The only job of `app/db.py` is translating the connection string onto the asyncpg driver, so one `DATABASE_URL` works for both services:

```python
def resolve_database_url(raw: str | None = None) -> str:
    """Normalize the monolith's psycopg-style `DATABASE_URL`
    (`postgresql://...`) onto the asyncpg driver SQLAlchemy's async engine
    needs (`postgresql+asyncpg://...`). Accepts either scheme as input so
    the same `DATABASE_URL` env var works unmodified for both services.
    """
    value = raw if raw is not None else os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://") :]
    return value
```

## Phase A: lift via the Django ORM (documented, not shipped)

The textbook first move is lift and shift: put the new runtime in front and reuse the old implementation to keep the behavioral diff small. For Django that means calling `review.models.Review` from FastAPI. `examples/02-review-service/MIGRATION.md` documents it:

```python
# app/main.py -- Phase A (illustrative, never committed)
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

@app.get("/api/reviews")
async def list_reviews(sku: str | None = None):
    from review.models import Review          # Django ORM, sync under the hood
    from asgiref.sync import sync_to_async
    qs = Review.objects.select_related("inventory_item")
    if sku:
        qs = qs.filter(inventory_item__sku=sku)
    reviews = await sync_to_async(list)(qs.order_by("id"))
    return [ReviewOut.model_validate(r, from_attributes=True) for r in reviews]
```

It costs two things, and they are the argument for not shipping it. A `uv` path dependency on `../00-monolith` pulls in Django, DRF and all six bounded-context apps to reach one model. And `django.setup()` in the `lifespan` loads that whole app registry before the first request.

1. **The Django ORM is synchronous.** Every query needs `sync_to_async(...)`, a hand-off to a thread-pool executor, paid on every request under FastAPI's event loop.
2. **The dependency direction is backwards.** Extraction exists to decouple review from the monolith, and Phase A would give the service a build-time dependency on the monolith's whole codebase. A Django upgrade, or a change to an unrelated app like `payment`, could break this service's build.

Phase A was not built, because a module written only to be deleted costs implementation and CI surface for nothing. Its cost is measured instead through a proxy, in the numbers below.

{% include excalidraw.html file="review-phase-a-vs-phase-b" alt="Side by side comparison of Phase A (FastAPI routes calling the Django ORM via sync_to_async, behind a path dependency on the monolith) and Phase B (FastAPI routes calling native async SQLAlchemy and asyncpg directly, with no Django import), both reading and writing the same shared Postgres schema" caption="Figure 15.1: Phase A (illustrative) and Phase B (shipped)" %}

## Phase B: the idiomatic FastAPI service

Phase B replaces each Django dependency with its native equivalent and keeps the external contract. It is the code under `examples/02-review-service/app/`.

### Data access: independent SQLAlchemy mappings

`app/models.py` declares SQLAlchemy 2.x `DeclarativeBase` mappings onto the same four tables, with no import from `00-monolith`:

```python
class Review(Base):
    """`review.Review`, table `reviews` -- the one table this service owns
    writes to (via `POST /api/reviews`)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"))
    inventory_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory_items.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

Only the columns the service touches are mapped. `AuthUser` carries `id`, `username`, `password` and `is_active`, all a Basic-auth check needs. `Customer` and `InventoryItem` are read, to validate `customerId` and resolve `sku`, and never written. `Review` is the one table written. `app/repository.py` holds every query with its joins written out instead of relying on relationship traversal:

```python
_REVIEW_COLUMNS = (
    Review.id,
    Review.customer_id,
    InventoryItem.sku,
    Review.rating,
    Review.comment,
    Review.created_at,
)


def _review_query():
    return select(*_REVIEW_COLUMNS).join(
        InventoryItem, InventoryItem.id == Review.inventory_item_id
    )
```

`InventoryItem` backs `sku` and `Customer` backs `customerId` validation, matching the monolith's direct cross-context foreign keys (SMELL[ch.18], the shared-schema smell that moving to owned data cures). There is no `Review.inventory_item` relationship to traverse lazily. A reader can see which join backs each field, which matters once those foreign keys stop pointing into the same database.

`create_review` is the one write path:

```python
async def create_review(
    session: AsyncSession,
    *,
    customer_id: int,
    inventory_item_id: int,
    rating: int,
    comment: str,
) -> Review:
    review = Review(
        customer_id=customer_id,
        inventory_item_id=inventory_item_id,
        rating=rating,
        comment=comment,
        created_at=datetime.now(UTC),
    )
    session.add(review)
    await session.flush()  # populates review.id via INSERT ... RETURNING
    await session.commit()
    return review
```

`created_at` is set in Python, not by a Postgres `DEFAULT now()`, matching the monolith's `default=timezone.now`, which is also Django-side. A server-side default would still produce a timestamp, but not necessarily one consistent with what the equivalence suite recorded. `flush()` rather than only `add()` is what issues the `INSERT ... RETURNING` and populates `review.id`, which the response and the `Location` header both need.

### Contracts: Pydantic with explicit aliases

`app/schemas.py` is the FastAPI sibling of the monolith's camelCase DRF serializers:

```python
class ReviewCreate(BaseModel):
    customer_id: int = Field(alias="customerId")
    sku: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None)


class ReviewOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    customer_id: int = Field(alias="customerId")
    sku: str
    rating: int
    comment: str
    created_at: datetime = Field(alias="createdAt")
```

Every field maps through an explicit `Field(alias=...)`, as the monolith's serializers use `source=`. A camelCase-rename middleware would be shorter, but the per-field alias is greppable: it states the wire contract of one field without a global transformation rule to reason about. `Field(ge=1, le=5)` is FastAPI's idiom for DRF's `min_value=1, max_value=5`.

### Auth: verifying Django's password hash without Django

`app/auth.py` checks Basic credentials against the same `auth_user` table without DRF's `BasicAuthentication` and without importing Django:

```python
_password_context = CryptContext(schemes=["django_pbkdf2_sha256"])

_DUMMY_HASH = _password_context.hash("not-a-real-password")

_security = HTTPBasic(auto_error=False)


async def require_basic_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
    session: AsyncSession = Depends(get_session),
) -> str:
    if credentials is None:
        raise Unauthorized("Authentication credentials were not provided.")

    user = await get_auth_user_by_username(session, credentials.username)
    if user is None:
        _password_context.verify(credentials.password, _DUMMY_HASH)
        raise Unauthorized("Invalid username/password.")

    if not user.is_active or not _password_context.verify(credentials.password, user.password):
        raise Unauthorized("Invalid username/password.")

    return credentials.username
```

- **`passlib`'s `django_pbkdf2_sha256` scheme.** `auth_user.password` stores `pbkdf2_sha256$<iterations>$<salt>$<base64 hash>`. Matching it needs the exact iteration count, salt encoding and a constant-time comparison. Getting any wrong by hand is an easy mistake (CWE-327 territory: comparing with `==`, or recomputing with the wrong iterations and always failing or always passing). The scheme matches Django's hasher byte for byte and was checked against a hash from Django's own `make_password()`.
- **The dummy-hash verify on a lookup miss.** An unknown username still runs `verify(credentials.password, _DUMMY_HASH)` before raising. Skipping it would make an unknown-username response measurably faster than a wrong-password one, the timing signal a username-enumeration attack looks for. The cost is one extra `verify()` per miss.
- **`auto_error=False` on `HTTPBasic`.** By default the dependency raises its own 401 with Starlette's `{"detail": ...}` body before this function runs. Disabling it lets `require_basic_auth` raise `Unauthorized`, so a missing header gets the same `{"error", "message", "timestamp"}` body (via `app/errors.py`) as a wrong password: one error shape for every authentication failure.
- **Wired per route.** `require_basic_auth` is a dependency of the `POST` handler only. `GET /api/reviews` and `GET /api/reviews/{id}` carry none, mirroring the monolith's `get_permissions()` (`IsAuthenticated()` on `POST`, `AllowAny()` on `GET`), so a malformed `Authorization` header on a read never produces a 401.

{% include codetabs.html langs="Monolith (Django/DRF)|review-service (FastAPI, Phase B)" %}

```python
# review/views.py -- the monolith's per-view auth gate (SMELL[ch.15])
class ReviewListCreateView(APIView):
    authentication_classes = [BasicAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def post(self, request):
        command = ReviewCreateSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        ...
```

```python
# app/routes.py -- the FastAPI sibling, auth as a per-route dependency
@router.get("/api/reviews", response_model=list[ReviewOut])
async def list_reviews(
    sku: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewOut]:
    rows = await repository.list_reviews(session, sku=sku)
    return [ReviewOut.model_validate(row) for row in rows]


@router.post("/api/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    payload: ReviewCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _authenticated_username: str = Depends(require_basic_auth),
) -> ReviewOut:
    ...
```

Same contract, each framework's own idiom: DRF's class-based `get_permissions()` override against FastAPI's `Depends(...)` on the route signature.

### Errors, wiring and routes

`app/errors.py` mirrors the monolith's `common/exceptions.py`: every non-2xx response is `{"error": "<CODE>", "message": ..., "timestamp": ...}`.

```python
@app.exception_handler(RequestValidationError)
async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI's own default is 422; the monolith's contract (DRF's generic
    # 400-status-code -> VALIDATION_FAILED rule) uses 400, so this handler
    # remaps BOTH the status code and the body shape.
    return JSONResponse(status_code=400, content=_error_body("VALIDATION_FAILED", exc.errors()))
```

FastAPI's default for a Pydantic validation failure is `422 Unprocessable Entity`, arguably better HTTP semantics. The monolith returns 400, and the equivalence suite was captured against the monolith, so shipping the better default would be exactly the behavioral difference the equivalence suite exists to catch. `Unauthorized` (401) maps to the generic `"ERROR"` code for the same reason: it is what DRF produces on the monolith side, and the service matches the actual contract, not the one a cleaner design would pick.

`lifespan` is the whole startup and shutdown sequence: one `AsyncEngine`, one `async_sessionmaker` kept on `app.state`, disposed on shutdown.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = db.create_engine()
    app.state.engine = engine
    app.state.session_factory = db.create_session_factory(engine)
    logger.info("review-service started, DATABASE_URL=%s", db.resolve_database_url())
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("review-service shut down")
```

The `get_session` dependency in `app/db.py` opens one session per request from that factory:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
```

The engine and its pool outlive every request; each session lives for exactly one. The app itself turns off slash redirects:

```python
app = FastAPI(
    title="review-service",
    version="0.1.0",
    redirect_slashes=False,
    lifespan=lifespan,
)
```

With `redirect_slashes=False`, `/api/reviews/` returns 404 instead of Starlette's default 307. A 307 on a `POST` can turn into a `GET` in some clients and drop the body, and the monolith's routes have no trailing slash.

## What Phase A would have cost

Phase A's cost is measured through a faithful proxy: the on-machine import and startup weight of `django.setup()` against the monolith's real `config.settings` (all six apps) plus `import fastapi, uvicorn`. The Phase B column is the shipped `app/main.py`. Figures are from `MIGRATION.md`.

| Metric | Phase A (proxy) | Phase B (shipped) |
|---|---|---|
| Cold interpreter floor (`python -I -c "pass"`) | 0.01 s | 0.01 s |
| Import and startup time (3-run average, warm cache) | 0.32 to 0.35 s | 0.35 to 0.36 s |
| Import-only RSS (`ru_maxrss`) | about 73.5 MB | about 72.3 MB |
| Running server RSS (uvicorn worker) | not measured, no server built | about 88.0 MB |
| `GET /api/reviews?sku=...` latency (n=20) | n/a | min 1.33 ms, p50 2.12 ms, max 6.51 ms |

The import-time and import-RSS numbers are statistically indistinguishable, which was not the expected result. FastAPI and Pydantic v2 dominate both columns (`pydantic-core` is a large compiled extension), so swapping Django's ORM for SQLAlchemy barely moves startup.

What Phase B buys is structural, and no startup stopwatch shows it: no `sync_to_async` bridge on every request for as long as the service runs, and no build-time dependency on the monolith's codebase. Both compound with scale and time. The payoff is a structural win, not a performance one.

## The flag cutover and the negative check

With the service verified against the Newman collection directly on `:8001`, the proxy's `STRANGLER_REVIEW_ENABLED` flag makes the cutover a configuration change, not a deploy. The evidence trail in `examples/01-strangler-proxy/CUTOVER.md` is this cutover's evidence:

- **Flag off to on:** 58/58 assertions green, reviews served by this service, identical in shape to the baseline.
- **Flag back to off:** 58/58 green. The monolith's `review` module is still present, unused and correct, so reverting costs a restart.
- **Negative check:** flag on, service killed, Review folder only. Every assertion fails with exit code 1, the proxy's 502 surfacing instead of a masked pass. Restarted: 16/16 green.

The negative check shows the equivalence suite tests this service's presence, not a code path that returns something plausible either way.

> **Decision**
>
> Extract the context with no synchronous collaborator first. Freeze the equivalence suite before writing the service, keep the external contract exactly (including quirks like 400 for validation), and leave the monolith's code in place until the cutover has been proven in both directions.

> **🤖 Explore with your agent**
>
> "In `examples/02-review-service`, add a validation rule to `POST /api/reviews` while keeping the monolith's contract: camelCase aliases, the `{error, message, timestamp}` envelope and a 400 for validation failures. Then run the Newman collection from `tooling/newman` against `:8001` and against the monolith through the strangler proxy, and tell me which assertions diverge."
>
> Check: the collection still passes 58/58 through the proxy with `STRANGLER_REVIEW_ENABLED` on and off, and a deliberate change to a status code makes it fail.

## Build, run, observe

```bash
cd examples/02-review-service
uv sync --group dev

# one-time: create + seed the shared schema (from 00-monolith)
(cd ../00-monolith && uv run python manage.py migrate && uv run python manage.py seed)

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

```bash
curl "http://localhost:8001/api/reviews?sku=SKU-WIDGET-001"

curl -i -X POST http://localhost:8001/api/reviews \
  -u reviewer:review-pw-r02 -H 'Content-Type: application/json' \
  -d '{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "Great"}'
```

The demo credentials (`reviewer` and `review-pw-r02`) belong to the fixed user `manage.py seed` creates in the shared `auth_user` table. Both services verify against that row, so the monolith accepts them too. `uv run pytest` needs a reachable, migrated and seeded Postgres, because the service owns no test schema.

- **Return 422 for validation errors:** drop the `RequestValidationError` handler and the equivalence collection fails on the status code.
- **Stop the service** with the flag on: every `/api/reviews*` request through `:8888` gets the proxy's 502.
- **Switch the flag off:** requests go back to the monolith, which still passes 58/58.

## For deeper coverage

The service's `MIGRATION.md` records the Phase A analysis and the measurements, and `examples/01-strangler-proxy/CUTOVER.md` the cutover runs. The `passlib` documentation covers the `django_pbkdf2_sha256` scheme, and the FastAPI documentation covers `Depends` and exception handlers. The bibliography page lists the books.
