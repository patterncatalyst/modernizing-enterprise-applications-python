# 02-review-service

**ch.15, DRQ-009 Phase B ("make it idiomatic") -- r02 S9.** The monolith's
(`../00-monolith`) `review` bounded context, extracted onto a standalone
**FastAPI** service on **`:8001`**, in two phases:

- **Phase A** ("lift onto FastAPI") -- a thin FastAPI app that reuses the
  monolith's own Django ORM (via a `uv` path dependency on `../00-monolith`
  and `django.setup()` run once in the app's `lifespan`), plus DRF's
  `BasicAuthentication` for the write endpoint. Behavior-preserving, minimal
  diff from the monolith's own `review/` app -- but it still carries a
  runtime dependency on the monolith's codebase and its full Django app
  registry (all six bounded contexts) just to reach one ORM model. **Not
  shipped as code in this directory** -- see `MIGRATION.md` for the real
  snippets and the measured cost of that coupling.
- **Phase B (this step, the live code under `app/`)** -- idiomatic FastAPI:
  Pydantic v2 schemas, **async SQLAlchemy 2.x + asyncpg** against the SAME
  shared Postgres schema, and HTTP Basic auth verified directly against the
  shared `auth_user` table via `passlib`'s `django_pbkdf2_sha256` scheme (no
  Django import anywhere in this service). Same external HTTP contract as
  Phase A and as the monolith.

See `MIGRATION.md` for the full Phase A -> Phase B story, including the
"why Phase A isn't just the better starting point" finding and real
before/after numbers.

## Why Option B (per-endpoint Basic auth, not a shared gateway)

`review` has no runtime dependency on order/inventory/payment/shipping/
notification (REST-only, no synchronous collaborator -- see the monolith's
`review/models.py`), yet its write endpoint was wired to the monolith's
shared Django auth machinery anyway (SMELL[ch.15]). Per the r02 plan, this
service keeps that same contract (`POST /api/reviews` needs HTTP Basic;
`GET` stays open) rather than inventing a new auth scheme or deferring to an
API gateway that doesn't exist yet in this build -- the point of r02 is
behavior-equivalence through the cutover, not redesigning the auth story.

## Endpoints

CamelCase JSON, **no trailing slash** (`redirect_slashes=False` -- a
trailing-slash request 404s rather than 307-redirecting, which would risk
turning a `POST` into a `GET` in some clients and break the contract either
way).

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/reviews` | none | optional `?sku=` filter |
| GET | `/api/reviews/{id}` | none | 404 `NOT_FOUND` if missing |
| POST | `/api/reviews` | HTTP Basic | 201 + `Location: /api/reviews/{id}` + camelCase echo; 401 on missing/bad creds; 400 `VALIDATION_FAILED` on e.g. `rating` outside 1..5 |

Response body: `{id, customerId, sku, rating, comment, createdAt}`. Error
body (every non-2xx response): `{"error": "<CODE>", "message": ..., "timestamp": ...}`
-- the same uniform shape as the monolith's `common/exceptions.py`.

Demo credentials for `POST`: `reviewer` / `review-pw-r02` (the fixed demo
user `00-monolith`'s `manage.py seed` creates in the shared `auth_user`
table -- see `common/management/commands/seed.py` there).

## Persistence: shared schema, no migrations of its own

This service does **not** own a schema. It reads/writes the SAME Postgres
database the monolith uses (`DATABASE_URL`, default
`postgresql://monolith:monolith@localhost:5432/monolith`) -- specifically the
`reviews` table, plus read-only lookups against `customers`,
`inventory_items`, and `auth_user`. The schema is created exclusively by
`00-monolith`'s `manage.py migrate` (+ `manage.py seed` for demo data,
including the `reviewer` auth user); this service has no Alembic setup and
never should, until the data-across-the-seam chapters (ch.18/19) give review
its own database. `app/db.py` normalizes the monolith's `postgresql://`
`DATABASE_URL` convention onto the `postgresql+asyncpg://` scheme SQLAlchemy's
async engine needs, so the exact same env var works for both services
unmodified.

## Quickstart

```sh
uv sync --group dev

# One-time: create + seed the shared schema (from 00-monolith; only needed
# once per database -- this service never migrates it).
(cd ../00-monolith && uv run python manage.py migrate && uv run python manage.py seed)

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`
(the INFRA lane's compose stack). A quick standalone Postgres for local use:

```sh
docker run -d --name mea-review-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

### Try it

```sh
curl "http://localhost:8001/api/reviews?sku=SKU-WIDGET-001"

curl -i -X POST http://localhost:8001/api/reviews \
  -u reviewer:review-pw-r02 -H 'Content-Type: application/json' \
  -d '{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "Great"}'
```

## Cutover

Once this service is verified, the strangler proxy (`../01-strangler-proxy`)
flips `STRANGLER_REVIEW_ENABLED=true` so `/api/reviews*` routes here instead
of the monolith -- see `../01-strangler-proxy/CUTOVER.md`. The behavior-
equivalence Newman suite is what proves the cutover is safe either way: same
collection, same assertions, pointed at whichever backend is live.

## Testing

```sh
uv run pytest     # needs a reachable, already-migrated-and-seeded Postgres
uv run ruff check .
```

Tests assume the SAME shared, pre-seeded database described above (same
convention as `00-monolith`'s own pytest-django suite) -- there is no
separate per-service test schema to create, since this service owns none.

## Container

```sh
docker build -f Containerfile -t mea-review-service:r02 .
docker run --rm -p 8001:8001 -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith mea-review-service:r02
```

UBI 10 (`ubi10/python-314-minimal`, the same verified tag `../00-monolith`
uses), multi-stage `uv sync`, non-root (UID 1001, GID 0 -- OpenShift/
arbitrary-UID compatible).

## Structured logging

Rotating file logs land in `logs/review-service.log` alongside console
output (see `app/main.py`'s `_configure_logging()`), so an agent or a
developer can grep the log after a crash or a failed test run even once the
console output has scrolled away.
