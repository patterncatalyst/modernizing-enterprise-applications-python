---
title: "Extraction 1: Review Service"
order: 15
part: "The Strangler Fig in Practice"
description: "REST-only, HTTP Basic auth, no sync dependency; proving the full loop: ACL, FastAPI scaffold, equivalence gate pass, flag-gated cutover, decommission."
duration: 45 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why Review is the right first bounded context to extract (REST-only, no synchronous collaborator) and how that ordering proves the extraction mechanism before harder chapters add distributed-transaction problems on top of it.
- Capture the Newman equivalence collection *before* any code moves, and use it as the gate that turns "the extracted service behaves the same" into a checkable yes/no answer rather than a judgment call.
- Stand up `examples/02-review-service` against the monolith's own shared Postgres tables, so ch.14's strangler proxy flag can cut traffic over without a migration step in the loop.
- Run the two-phase migration template: document (never ship) a Phase A that bridges the Django ORM via `sync_to_async`, then ship Phase B's idiomatic FastAPI service with independent SQLAlchemy mappings (`app/models.py`) and `passlib`'s `django_pbkdf2_sha256` auth check.
- Measure Phase A's cost through a faithful import/startup proxy rather than a shipped server, and explain why Python's real win (no `sync_to_async` tax, no build-time dependency on the monolith) doesn't show up as a startup-time number the way a native-image comparison would.
- Perform the flag-gated, reversible cutover (58/58 assertions in both directions) and read the negative check, service killed, every assertion failing through the proxy's own 502, as proof the equivalence gate tests this service's actual presence.

## Why this matters

ch.14 built the machinery: a reversible, flag-gated proxy that can hand any
request to a different backend without the client noticing. This chapter
puts it to work on the first real extraction: pulling the `review`
bounded context out of the Django monolith and onto its own FastAPI
service, and in doing so proves the whole loop end to end: capture the
contract, stand up the seam, migrate the implementation in two clearly
measured phases, cut traffic over, and leave the fallback in place. Everything
after this chapter (ch.17's Notification extraction, ch.19's Inventory,
and the rest of Part 5 through ch.26's Order) is the same loop, repeated
against harder dependencies. This is the one where the loop gets proven
against the easiest case there is.

The code is in `examples/02-review-service/`. The run script there (`uv run
uvicorn app.main:app --host 0.0.0.0 --port 8001`) sets up and runs it; its
`README.md` covers what it does and how to drive it.

## Why Review leaves first

Extraction order is a design decision, not an accident, and `review` was
chosen as the first seam to cut because of what's true about it, not despite
anything inconvenient. `review/models.py` states the reason directly:

> Note what review does NOT depend on: order, payment, shipping, or
> notification.

It's the least-coupled context in the monolith: REST-only, with no
synchronous collaborator.

Compare that to the smells ch.09 planted everywhere else: `order/services.py`
is a god service reaching synchronously into four other contexts inside one
ACID transaction (smell #1/#2, the hardest extraction in this book, saved
for ch.26); `notification` has a dual-write hazard between a DB write and
an external call (smell #6, cured by ch.17's transactional outbox); every
context shares one Postgres schema with direct cross-context foreign keys
(smell #3/#4, cured starting ch.18). `review` has none of that. It's a REST
leaf: clients read and write reviews, and nothing else in the system calls
into `review` synchronously, or needs `review` to call out to it. That
makes it the right chapter to prove the *mechanism* of extraction: the
equivalence gate, the flag, the cutover, the two-phase migration, without
also having to solve a distributed-transaction problem in the same chapter.
The hard problems (shared data, sagas, event-driven coordination) get their
own chapters once this one has shown the baseline loop actually works.

`review` does still have one thing worth extracting *for*, not just
extracting *despite*: SMELL #7. Despite having no runtime
dependency on any other context, `review`'s write endpoint borrows the
monolith's shared `django.contrib.auth` machinery: the same `auth_user`
table and `BasicAuthentication` class every other context would reach for.
`review/views.py` names this directly:

> Review has no runtime dependency on order/inventory/payment/shipping/
> notification ... yet here it is, borrowing that machinery anyway.

That's not a bug: the monolith's behavior there is intentional, planted to
be realized and then cured. This chapter's service keeps the *same external
contract* (`POST /api/reviews` needs HTTP Basic; `GET` stays open) while
giving `review` its own, independent verification path against that same
shared table, no longer reusing Django's authentication class, just
verifying the same password hash format on its own terms. That's "Option
B" in the service's own README: keep the contract, stop borrowing the
mechanism.

## The gate comes first: capturing the equivalence suite before any code moves

Before a single line of the new service existed, the contract it would
have to match already did: `tooling/newman/mea.postman_collection.json`,
captured against the monolith and frozen as the externally-observable
behavior every later extraction is held to. ch.14 said this already for the
proxy's own cutover; it's worth restating here because it's the actual
order of operations this chapter follows, not a retrospective justification:
**the test that defines "equivalent" exists before the thing it will test.**
`examples/02-review-service` was built against a collection that already
specified exact status codes, exact JSON shapes (camelCase fields, the
`{"error", "message", "timestamp"}` error envelope), and exact header
behavior (`Location: /api/reviews/{id}` as a relative path, not absolute),
none of which were invented or adjusted after the fact to make the new
service's actual output look correct.

This matters because of what it rules out. Without a gate frozen ahead of
time, it's easy for "the extracted service behaves the same" to quietly
become "the extracted service behaves close enough that nobody noticed":
the collection is what turns that into a yes/no question with a real
answer, not a judgment call.

## Standing up the seam: the shape of the new service

`examples/02-review-service` is FastAPI on `:8001`. It owns no schema of
its own: `app/db.py` points at the exact same Postgres database and the
exact same tables (`reviews`, `customers`, `inventory_items`, `auth_user`)
the monolith's `manage.py migrate`/`manage.py seed` create, because giving
`review` its own database is a later chapter's problem (ch.18's shared-data-
to-owned-data, ch.19's CDC backfill). For the walking skeleton, the goal
is behavioral equivalence through a safe cutover, not a fully decoupled
data store yet. Reading and writing the same tables the monolith already
uses is what lets the strangler proxy flip `STRANGLER_REVIEW_ENABLED`
without a migration step in the loop.

`app/db.py`'s one real job is a URL-scheme translation, because the two
services need different driver conventions against the same connection
string:

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

The same `DATABASE_URL` environment variable the monolith's Django settings
already read works unmodified for this service too: one fewer thing an
operator has to remember differs between the two.

## Phase A: lift onto FastAPI via the Django ORM (documented, never shipped)

The textbook first move in a strangler extraction is "lift and shift": put
the new runtime in front, but reuse as much of the old implementation as
possible, so the diff from the monolith's own behavior stays small. For a
Python/Django monolith, that means reusing the Django ORM itself,
`review.models.Review`, from inside a FastAPI app. `examples/02-review-service/MIGRATION.md`
documents exactly what that would look like:

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

Getting this far costs two concrete things, and they're the actual argument
for not shipping it: a `uv` **path dependency**
on `../00-monolith` in Phase A's `pyproject.toml`, pulling in Django, DRF,
and the entire monolith package (all six bounded-context apps) just to
reach one ORM model; and `django.setup()` run once in the FastAPI app's
`lifespan`, which loads that entire app registry before the service can
serve its first request.

Both problems are concrete, not speculative, which is why `MIGRATION.md`
names them directly rather than hand-waving past them:

1. **The Django ORM is synchronous.** Every single query under this
   approach needs `sync_to_async(...)`, handing the call off to a
   thread-pool executor: a real latency and concurrency cost under
   FastAPI's async event loop, paid on every request, that an ORM built
   for async from the start simply doesn't incur.
2. **The dependency direction is backwards for an extraction.** The whole
   point of pulling `review` out is to decouple it from the monolith. Phase
   A would instead give this service a hard *build-time* dependency ON the
   monolith's entire codebase, just to reach one model. A change to
   `00-monolith`'s Django version, or to an unrelated app like `payment` or
   `shipping`, could break this service's build: the opposite of what an
   extraction is supposed to buy.

Given that the acceptance bar for this chapter's build was "Phase B is the
live code, Phase A is documented," the decision was not to spend
implementation and CI surface on a module built only to be deleted in the
same iteration. Phase A's cost is still measured, though, not estimated,
using a faithful proxy for its real weight: the actual combined import/
startup cost of `django.setup()` against the monolith's real
`config.settings` (all six apps installed) plus `import fastapi, uvicorn`,
measured on the same machine. Those numbers appear in the "What Phase A
would have cost" section below, measured, not guessed.

{% include excalidraw.html file="review-phase-a-vs-phase-b" alt="Side by side comparison of Phase A (FastAPI routes calling the Django ORM via sync_to_async, behind a path dependency on the monolith) and Phase B (FastAPI routes calling native async SQLAlchemy and asyncpg directly, with no Django import), both reading and writing the same shared Postgres schema" caption="Figure 15.1: Phase A (illustrative) vs Phase B (shipped)" %}

## Phase B: the idiomatic FastAPI service (this is the live code)

Phase B replaces every Django-ORM dependency with its native equivalent,
one layer at a time, while keeping the exact same external contract. This
is the code actually under `examples/02-review-service/app/`.

### Data access: independent SQLAlchemy mappings, not a shared ORM

`app/models.py` declares SQLAlchemy 2.x `DeclarativeBase` mappings onto the
same four tables, owned by this service, with zero import from
`00-monolith`:

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

Only the columns this service actually touches get mapped: `AuthUser`
carries just `id`, `username`, `password`, and `is_active`, because that's
all a Basic-auth check needs, not Django's full user model. `Customer` and
`InventoryItem` are similarly narrow: this service reads them (to validate
`customerId` and resolve `sku`), it doesn't own or write them. `Review` is
the one table this service writes to.

`app/repository.py` is where every query lives, written out explicitly
rather than relying on ORM relationship traversal, so a reader can see
exactly which join backs each field:

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

Every join is written out by hand: `InventoryItem` for `sku`, `Customer`
for `customerId` validation, matching the monolith's own direct
cross-context foreign keys (SMELL[ch.18], the shared-schema smell ch.18
exists to cure). There's no `Review.inventory_item` relationship attribute
to lazily traverse; the query says exactly what it joins and why, which
matters once this table's foreign keys stop pointing at tables in the same
database.

`create_review` is the one write path, and it's worth reading end to end
for what it says about where responsibility lives:

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

`created_at` is set here, in Python, rather than left to a database
server-side default, matching the monolith's own `default=timezone.now`,
which is also a Django-side default rather than a DB-side one. Getting that
detail wrong (switching to a Postgres `DEFAULT now()`) would still produce
a timestamp, just not necessarily one that matches what the equivalence
suite recorded when it captured the monolith's behavior down to the second
it ran. `session.flush()` (not just `session.add()`) is what makes
`review.id` available before `commit()`: SQLAlchemy's async session needs
an explicit flush to issue the `INSERT ... RETURNING` and populate the
autogenerated primary key on the Python object, which the response (and
the `Location` header) both need.

### Request/response contracts: Pydantic v2, explicit field aliases

`app/schemas.py` is the FastAPI sibling of the monolith's camelCase DRF
serializers:

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

Every field maps explicitly via `Field(alias=...)`, the same convention the
monolith's serializers use with `source=`. That's a deliberate choice, not
an oversight: it would be possible to reach for a camelCase-rename
middleware that transforms every response automatically, but the explicit
per-field alias is what a reader can grep to find the exact wire contract
for one field, without having to reason about a global transformation
rule. `rating: int = Field(ge=1, le=5)` is the FastAPI-native expression of
DRF's `min_value=1, max_value=5`: same constraint, same 1..5 bound, a
different framework's idiom for stating it.

### Auth: verifying Django's own password hash, without Django

This is where the chapter's smell #7 gets realized and then given its
independent cure. `app/auth.py` verifies submitted HTTP Basic credentials
against the exact same `auth_user` table the monolith seeds, but without
reusing DRF's `BasicAuthentication` class or importing Django at all:

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

Four things here are each doing real work, not decoration:

- **`passlib`'s `django_pbkdf2_sha256` scheme**, not a hand-rolled
  verification. Django's `auth_user.password` column stores
  `pbkdf2_sha256$<iterations>$<salt>$<base64 hash>`; matching that format
  correctly requires the exact iteration count, the exact salt encoding,
  and a constant-time comparison. Getting any of those wrong by hand is a
  real, easy mistake (CWE-327 territory: comparing hashes with `==` instead
  of constant time, or recomputing with the wrong iteration count and
  silently always failing or always succeeding). `passlib`'s scheme is
  purpose-built to match Django's hasher byte-for-byte, and it was
  confirmed locally against a hash generated by Django's own
  `make_password()` during this build:

  ```
  $ python -c "
  from passlib.hash import django_pbkdf2_sha256
  h = django_pbkdf2_sha256.hash('review-pw-r02')
  print(h)
  print(django_pbkdf2_sha256.verify('review-pw-r02', h))   # True
  print(django_pbkdf2_sha256.verify('wrong', h))            # False
  "
  pbkdf2_sha256$29000$oYYfb1A5reZi$6onH9i8Kx2gGh02D6MsERH6MUE/ikkpeN9VtUPO94lw=
  True
  False
  ```

- **The dummy-hash verify on a lookup miss.** When `credentials.username`
  doesn't match any row, the function still calls
  `_password_context.verify(credentials.password, _DUMMY_HASH)` before
  raising `Unauthorized`, spending roughly the same wall-clock time a real
  wrong-password check would cost. Skipping that call when the username is
  unknown would make a nonexistent-username response measurably faster
  than a wrong-password response, which is exactly the kind of timing
  signal a username-enumeration attack looks for. It's cheap insurance: one
  extra `verify()` call against a hash that can never match, paid on every
  miss.
- **`auto_error=False` on `HTTPBasic`.** FastAPI's `HTTPBasic` dependency
  raises its own 401 with Starlette's default `{"detail": ...}` body the
  moment credentials are missing or malformed: before this function's body
  ever runs. Disabling that default lets `require_basic_auth` raise its own
  `Unauthorized` instead, so a missing `Authorization` header gets the
  *same* uniform error body (`{"error", "message", "timestamp"}`, via
  `app/errors.py`) a wrong password would: one error shape for every
  authentication failure, not two different ones depending on which part
  of the stack caught it.
- **Wired per-route, not globally.** `app/routes.py` attaches
  `require_basic_auth` only to the `POST` handler's `Depends(...)` list:
  `GET /api/reviews` and `GET /api/reviews/{id}` carry no auth dependency
  at all. That mirrors the monolith's own `get_permissions()` gate
  (`IsAuthenticated()` on `POST`, `AllowAny()` on `GET`), which is itself
  there specifically so a malformed `Authorization` header on a *read*
  never produces a 401 a read was never supposed to require.

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

Same shape, same contract (`GET` wide open, `POST` gated), expressed in
each framework's own idiom: Django/DRF's class-based `get_permissions()`
override versus FastAPI's `Depends(...)` composition on the route function
signature itself. Neither reaches for the other framework's trick; each
uses the tool its own ecosystem gives it for "this one endpoint needs a
different gate than its siblings."

### Error mapping: the same uniform body, native FastAPI handlers

`app/errors.py` is the FastAPI sibling of the monolith's
`common/exceptions.py`: every non-2xx response this service returns is
`{"error": "<CODE>", "message": ..., "timestamp": ...}`, the same shape the
Newman equivalence suite asserts on request by request:

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

That status-code remap is a detail easy to miss and expensive to get
wrong: FastAPI's own default for a Pydantic validation failure is `422
Unprocessable Entity`, which is the more "correct" HTTP semantics by some
readings, but it isn't what the monolith returns, and the equivalence
suite was captured against the monolith. Shipping the "more correct"
default here would be a real behavioral difference an equivalence gate
exists specifically to catch. `Unauthorized` (401) maps to the
catch-all `"ERROR"` code rather than a dedicated one, because that's what
DRF's generic exception handling produces for an authentication failure on
the monolith side, matching the *actual* contract, not the contract a
cleaner design might have chosen.

### Wiring: one engine, one session factory, one request-scoped session

`app/main.py`'s `lifespan` is the service's entire startup/shutdown
sequence:

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

One `AsyncEngine`, created once; one `async_sessionmaker` built from it,
stashed on `app.state`; disposed cleanly on shutdown. `app/db.py`'s
`get_session` dependency opens one session per request from that shared
factory:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
```

That's the FastAPI-idiomatic version of "one connection pool for the
process, one session per request": the engine (and the pool underneath it)
outlives every individual request; the session is scoped to exactly one.

One more wiring detail is easy to miss, and the Newman suite would have
caught it immediately if it had been wrong:

```python
app = FastAPI(
    title="review-service",
    version="0.1.0",
    redirect_slashes=False,
    lifespan=lifespan,
)
```

`redirect_slashes=False` means a trailing-slash request (`/api/reviews/`)
404s instead of Starlette's default 307 redirect to the non-slash path.
That matters because a 307 redirect on a `POST` can, in some HTTP clients,
turn into a `GET` on the redirected request, silently dropping the
request body and changing the method, which would break the contract
either way. The monolith's own routes have no trailing slash; this service
matches that exactly rather than accepting the friendlier-looking default.

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

The demo credentials (`reviewer` / `review-pw-r02`) are the fixed user
`00-monolith`'s `manage.py seed` creates in the shared `auth_user` table:
the same credentials the monolith itself accepts for `POST /api/reviews`,
because both services verify against the same row.

## What Phase A would have cost: the measured numbers

This project's Phase A was never shipped as code (see above). Its cost is
measured here via a faithful proxy instead: the real, on-this-machine
import/startup weight of `django.setup()` against the monolith's actual
`config.settings` (all six apps installed) plus a real `import fastapi,
uvicorn` in the same process, not an estimate, but not a running server
either, since no Phase A server was ever built. "Phase B" numbers come from
this service's actual shipped `app/main.py`, measured directly.

| Metric | Phase A (proxy measurement) | Phase B (shipped) |
|---|---|---|
| Cold interpreter floor (`python -I -c "pass"`) | 0.01 s | 0.01 s |
| Import/startup time (3-run avg, warm cache) | 0.32-0.35 s | 0.35-0.36 s |
| Import-only RSS (`ru_maxrss`) | ~73.5 MB | ~72.3 MB |
| Running server RSS (actual uvicorn worker) | not measured (no server built) | ~88.0 MB |
| `GET /api/reviews?sku=...` latency (n=20) | n/a | min 1.33 ms / p50 2.12 ms / max 6.51 ms |

**Reading these numbers as measured, not adjusted to tell a cleaner story:**
Phase A and Phase B's import-time and import-RSS numbers are statistically
indistinguishable at the proxy level: that's not the result expected going
in. FastAPI and Pydantic v2's own import graph (`pydantic-core` is a
sizable compiled extension) dominates both columns, so swapping Django's
ORM for SQLAlchemy barely moves process-startup granularity at all.

So what did Phase B actually buy, if not a faster cold start? The
**structural** costs documented in "Phase A: lift onto FastAPI" above,
which don't show up in a startup-time number at all: every Django ORM query
bridged through `sync_to_async` on
every single request under FastAPI's async event loop, forever, for as
long as Phase A kept running; and a hard build-time dependency on the
entire monolith's codebase just to reach one model, so that an unrelated
change to `payment` or `shipping` could break this service's build.
Those costs are real and they compound with scale and time, even though
they don't move a startup-time stopwatch. That's the real shape of this
migration's payoff: a structural win, not a perf fireworks show.

## The flag cutover, reversibility, and the negative check

Once this service was verified against the Newman collection directly on
`:8001`, the proxy's `STRANGLER_REVIEW_ENABLED` flag made the cutover a
configuration change, not a deploy: ch.14's evidence trail *is* this
chapter's cutover evidence, because Review is the one seam that trail
documents.

- Flag off → flag on: **58/58 assertions green**, reviews now served by
  this service instead of the monolith, byte-identical in shape to the
  baseline run.
- Flag back to off: **58/58 green again**: the monolith's `review` module
  is still present, unused, and still correct, so reverting costs nothing
  but a restart.
- Negative check: flag on, this service killed, only the Review folder run:
  **every assertion fails, exit code 1**, the proxy's own `502` surfacing
  through rather than a masked pass. Restarted: **16/16 green** again.

That negative check is specifically this chapter's proof, not just ch.14's:
it demonstrates that the equivalence gate is actually testing *this*
service's presence, not just exercising a code path that happens to return
something plausible either way.

## What you learned

- Extraction order is a design decision: `review` went first because it's
  the least-coupled context in the monolith (REST-only, no synchronous
  collaborator), which makes it the right chapter to prove the
  extraction *mechanism* before harder chapters add distributed-transaction
  problems on top of it.
- The equivalence suite is captured before the new service is written, and
  it never changes per extraction: only {% raw %}`{{baseUrl}}`{% endraw %} moves. That ordering
  is what keeps "equivalent" an answerable yes/no question.
- A two-phase migration can document a phase it never ships accurately: Phase
  A's real costs (a synchronous ORM bridged into an async framework, a
  build-time dependency on the entire monolith) are documented and
  measured by proxy, not glossed over because the code was never written.
- Verifying someone else's password hash format correctly (Django's
  `pbkdf2_sha256`) is a job for a purpose-built library, not a hand-rolled
  reimplementation, and a lookup miss should cost the same wall-clock time
  as a wrong password, or the response timing itself becomes a username
  oracle.
- A structural win (no sync-to-async bridging, no build-time coupling to
  the monolith) can be real and worth having even when it doesn't show up
  as a faster number on a stopwatch.

Next: ch.16 generalizes what this chapter built into content-based routing
and an anti-corruption layer, the pattern every later extraction in Part 5
reuses to cut its own seam.
