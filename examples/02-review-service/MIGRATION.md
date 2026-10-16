# review-service -- Migration Notes (ch.15 Phase A -> Phase B, DRQ-009)

This file is the measured record of the two-phase Review extraction required
by the r02 walking-skeleton plan and the Python sibling of the Java build's
two-phase migration strategy (`modernizing-enterprise-applications/examples/02-review-service/MIGRATION.md`).
It exists so the chapter can cite real numbers instead of placeholders, the
same convention that project uses.

**Important difference from the Java sibling:** there, Phase A was a real,
previously-committed build (a distinct git commit, `5479d49`) that could be
checked out and measured directly. Here, Phase A is **documented but never
committed as code** -- see "Why Phase A isn't shipped as code" below. Its
numbers in this file are therefore measured via a faithful proxy (the real
import/startup cost its approach would carry), not a full separately-running
server. That's called out explicitly at each measurement, not glossed over.

## Why Phase A isn't shipped as code

Phase A's whole point ("lift behavior-preserving onto the new runtime with
minimal diff") is to reuse the monolith's existing Django ORM rather than
write new persistence code. Concretely, that means:

- A `uv` **path dependency** on `../00-monolith` in `pyproject.toml`
  (`mea-monolith = { path = "../00-monolith" }`), pulling in Django, DRF, and
  the entire monolith package (all six bounded-context apps) as this
  service's own dependency.
- `django.setup()` called once in the FastAPI app's `lifespan`, before the
  app starts serving, so `review.models.Review` (and its DRF serializers)
  become usable from inside otherwise-ordinary FastAPI route handlers.
- DRF's `BasicAuthentication` reused directly for the write endpoint's auth
  check, since it already knows how to verify against `auth_user`.

Illustrative sketch of what that `lifespan` looks like (never committed --
this is the shape, not a tested module):

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

```python
# app/auth.py -- Phase A (illustrative, not committed)
from rest_framework.authentication import BasicAuthentication
from asgiref.sync import sync_to_async

async def require_basic_auth(request: Request) -> str:
    auth = BasicAuthentication()
    django_request = build_drf_request(request)   # adapt ASGI Request -> DRF-compatible
    result = await sync_to_async(auth.authenticate)(django_request)
    if result is None:
        raise Unauthorized("Authentication credentials were not provided.")
    user, _ = result
    return user.username
```

Two real problems with actually shipping that, found by sketching it out
(not speculative -- these are concrete, not "maybe someday" concerns):

1. **Django's ORM is synchronous.** Every query needs `sync_to_async(...)`,
   which hands the call to a thread-pool executor -- a real latency and
   concurrency cost under FastAPI's async event loop that Phase B's native
   `async`/`await` SQLAlchemy calls simply don't pay.
2. **The dependency direction is backwards for an extraction.** A service
   that exists to decouple `review` from the monolith would, in Phase A,
   gain a hard *build-time* dependency ON the monolith's entire codebase
   (via the path dependency) just to reach one model. Any change to
   `00-monolith`'s `pyproject.toml`, Django version, or unrelated app
   (payment, shipping, ...) could break this service's build. That is the
   opposite of what ch.15 is trying to demonstrate.

Given those two findings, and since the acceptance bar for r02 is "Phase B
is the final, live code, Phase A is documented," the team decided NOT to
spend the extra implementation and CI surface on a module that exists only
to be deleted in the same iteration. The measurements below instead use a
faithful proxy for Phase A's cost: the real combined import/startup weight
of `django.setup()` (against the monolith's actual `config.settings`, with
all six apps installed) plus FastAPI/uvicorn's own import, run for real on
this machine -- not an estimate.

## Per-component refactor (A -> B), as designed (not built)

| Component | Phase A (Django-ORM lift, illustrative) | Phase B (idiomatic, shipped) |
|---|---|---|
| HTTP layer | FastAPI routes calling into Django ORM via `sync_to_async` | FastAPI routes calling `app/repository.py`'s native `async`/`await` SQLAlchemy queries |
| Data access | `review.models.Review`, `common.models.Customer`, `inventory.models.InventoryItem` (Django ORM, imported straight from the monolith path dependency) | `app/models.py` -- independent SQLAlchemy 2.x `DeclarativeBase` mappings onto the SAME tables, owned by this service, zero import from `00-monolith` |
| Serialization | DRF serializers (`ReviewSerializer`/`ReviewCreateSerializer`), reused directly from the monolith | `app/schemas.py` -- independent Pydantic v2 models, camelCase via `Field(alias=...)` |
| Auth | DRF `BasicAuthentication`, reused directly (knows how to check Django's `auth_user` already) | `app/auth.py` -- FastAPI `HTTPBasic` dependency + `passlib`'s `django_pbkdf2_sha256` scheme, verifying the SAME `auth_user` table without any Django import |
| Exception mapping | Hand-adapt DRF's `api_exception_handler` output shape inside FastAPI exception handlers | `app/errors.py` -- native FastAPI `@app.exception_handler(...)` registrations, same `{"error","message","timestamp"}` body |
| Process model | `django.setup()` in `lifespan`, loading all 6 monolith apps' registries just to reach 1 model | No Django import anywhere; only the 4 tables this service actually touches are mapped |
| Build dependency | `uv` path dependency on `../00-monolith` (whole monolith become this service's dependency) | None -- `pyproject.toml` depends only on FastAPI/SQLAlchemy/asyncpg/Pydantic/passlib |
| Concurrency | Every DB call threaded via `sync_to_async` (Django ORM is sync-only) | Native `async`/`await` all the way to the driver (`asyncpg`) |

## Passlib / Django password-hash note (Phase B)

`auth_user.password` is Django's own hash format,
`pbkdf2_sha256$<iterations>$<salt>$<base64 hash>`. Verifying it correctly
requires matching Django's exact iteration count, salt encoding, and
constant-time comparison -- getting any of those wrong by hand is a real,
easy mistake (CWE-327 territory: a naive re-implementation that compares
with `==` instead of a constant-time compare, or recomputes with the wrong
iteration count and silently always fails/succeeds). `passlib`'s
`django_pbkdf2_sha256` scheme (`CryptContext(schemes=["django_pbkdf2_sha256"])`)
is purpose-built to match Django's hasher byte-for-byte and verifies in
constant time -- confirmed locally against a real hash generated by Django's
own `make_password()` during this build:

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

`app/auth.py` also verifies against a fixed dummy hash when the username
isn't found, so a lookup miss costs about the same wall-clock time as a
wrong password -- cheap insurance against timing-based username enumeration.

## Gotcha found while measuring

`fastapi.testclient.TestClient` (used by `tests/test_reviews.py`) emits a
`StarletteDeprecationWarning` on Starlette 1.8.0 pinned here: *"Using `httpx`
with `starlette.testclient` is deprecated; install `httpx2` instead."*
`httpx2` does not exist as a published stable release at the time of this
build (pinned `httpx==0.28.1` is upstream's current stable) -- this is
Starlette signaling a future direction, not something actionable today.
Left as a warning, not suppressed, so it resurfaces naturally once `httpx2`
actually ships and this pin needs revisiting.

## Verification

- `uv run pytest`: **11 passed** (list/filter/get/404/401-no-auth/
  401-bad-creds/201-with-auth/400-invalid-rating/404-unknown-sku/
  garbage-auth-header-still-serves/no-trailing-slash-redirect), run against
  a real throwaway `postgres:18.6-alpine` container with `00-monolith`'s
  `manage.py migrate && manage.py seed` applied first.
- `uv run ruff check .`: **All checks passed** (one deliberate, documented
  lint suppression: `B008` for FastAPI's idiomatic `Depends(...)` default-
  argument pattern -- see `pyproject.toml`).
- Live run on `:8001` against that same seeded database, verified with
  `curl`:
  - `GET /api/reviews?sku=SKU-WIDGET-001` -> `200`, camelCase array.
  - `GET /api/reviews/1` -> `200`.
  - `GET /api/reviews/999999` -> `404`, `{"error":"NOT_FOUND",...}`.
  - `POST /api/reviews` (no creds) -> `401`, `{"error":"ERROR",...}`.
  - `POST /api/reviews` (`-u reviewer:review-pw-r02`, valid body) -> `201` +
    `Location: /api/reviews/4` + camelCase echo.
  - `POST /api/reviews` (valid creds, `rating: 99`) -> `400`,
    `{"error":"VALIDATION_FAILED",...}`.

## Before / after metrics

Method: real runs on this machine (not estimates), against a throwaway
`postgres:18.6-alpine` container with the monolith's shared schema migrated
and seeded. "Phase A" numbers are the measured proxy described above (real
`django.setup()` against the monolith's actual `config.settings`, with all
six apps installed, plus a real `import fastapi, uvicorn` in the SAME
process) -- not a running server, since Phase A code was never built (see
above). "Phase B" numbers are this service's actual shipped `app/main.py`.
Import timing is `/usr/bin/time -f '%e'` around a bare `python -c "import ..."`
(3 runs each, after a warm filesystem cache; first-run numbers were
discarded as cold-cache noise -- see raw data below). RSS is
`resource.getrusage(...).ru_maxrss` (import-only, no server loop running) or
`ps -o rss` (the real running uvicorn worker). Latency is `curl -w
'%{time_total}'`, 20 requests, against the live `:8001` service.

| Metric | Phase A (proxy: `django.setup()` + `import fastapi, uvicorn`) | Phase B (shipped `app/main.py`) |
|---|---|---|
| Cold interpreter floor (`python -I -c "pass"`) | 0.01 s | 0.01 s |
| Import/startup time (3-run avg, warm cache) | 0.32-0.35 s | 0.35-0.36 s |
| Import-only RSS (`ru_maxrss`) | 75,288 KB (~73.5 MB) | 73,992 KB (~72.3 MB) |
| Running server RSS (actual uvicorn worker, after serving requests) | not measured (no server built) | 90,128 KB (~88.0 MB) |
| `GET /api/reviews?sku=...` latency (n=20) | n/a | min 1.33 ms / p50 2.12 ms / max 6.51 ms / avg 2.26 ms |

**Reading the numbers honestly:** unlike the Java sibling, where Phase A ->
Phase B showed a real (if modest) JVM win and a dramatic native-image win,
the Python Phase A -> Phase B import-time and import-RSS numbers are
**statistically indistinguishable** (within run-to-run noise) at the proxy
level. That's not the result expected going in, and it's reported as found,
not adjusted to tell a cleaner story: FastAPI + Pydantic v2's own import
graph (pydantic-core is a sizable compiled extension) dominates both
columns, so swapping Django's ORM for SQLAlchemy barely moves the needle at
process-startup granularity. The real Phase A -> Phase B win this project
cares about isn't raw import time -- it's the **structural** costs Phase A
would carry at runtime and in the build graph, laid out in the "Why Phase A
isn't shipped as code" section above: a synchronous ORM bridged into an
async framework via `sync_to_async` on every query, and a hard build-time
dependency on the entire monolith just to reach one model. Those are the
costs ch.15 exists to cure, and they don't show up in a startup-time number
either in Python or in the Java sibling's own writeup (which measured its
dramatic win on a completely different axis -- native image vs JVM, a
distinction with no Python equivalent).
