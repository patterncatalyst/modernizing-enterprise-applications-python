# AGENTS.md -- 02-review-service

Context for an AI agent (or a human) picking this module up.

## What this is

The r02 extraction of the `review` bounded context off `../00-monolith` onto
a standalone FastAPI service, `:8001`. Two-phase migration (ch.15, DRQ-009):
**Phase A** (lift onto FastAPI via the monolith's own Django ORM) is
documented, not shipped as code -- see `MIGRATION.md`. **Phase B** (idiomatic
FastAPI + async SQLAlchemy/asyncpg + passlib) is the only code in `app/`, and
is the final state. Don't go looking for a Phase A module; it was
deliberately never committed here, only measured and written up.

This is the Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/02-review-service`
(Java/Quarkus) -- same role in the book, same chapter, same two-phase
structure -- but it is its own independent implementation, not a port of that
code.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **SQLAlchemy[asyncio]
  2.1.4** + **asyncpg 0.32.0**, **Pydantic 2.14.1**, **passlib 1.7.4**.
  Dev-only: **pytest 9.1.1** + **pytest-asyncio 1.4.0** + **httpx 0.28.1**,
  **ruff 0.17.1**.

## Commands

```sh
uv sync --group dev

# One-time, from 00-monolith -- this service owns no schema of its own:
(cd ../00-monolith && uv run python manage.py migrate && uv run python manage.py seed)

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
uv run ruff check .
uv run pytest        # needs the same reachable, migrated+seeded Postgres
```

`DATABASE_URL` (same convention as `00-monolith`, default
`postgresql://monolith:monolith@localhost:5432/monolith`) is normalized onto
the asyncpg driver scheme by `app/db.py::resolve_database_url` -- the SAME
env var value works unmodified for both services.

## Structure

- `app/main.py` -- FastAPI app factory + lifespan (creates the async engine/
  session factory once at startup, disposes it at shutdown), structured file
  logging setup, `redirect_slashes=False`.
- `app/routes.py` -- the three `/api/reviews*` endpoints.
- `app/schemas.py` -- Pydantic v2 request/response models, camelCase via
  `Field(alias=...)` (explicit per-field mapping, same convention as the
  monolith's DRF `source=`).
- `app/repository.py` -- async SQLAlchemy queries; no ORM relationship
  traversal, every cross-table join written out explicitly.
- `app/auth.py` -- HTTP Basic dependency for `POST /api/reviews` only,
  verified against the shared `auth_user` table via passlib's
  `django_pbkdf2_sha256` scheme.
- `app/models.py` -- SQLAlchemy declarative mappings for `reviews`,
  `auth_user`, `customers`, `inventory_items` -- matching the monolith's
  `db_table`s exactly. No `Base.metadata.create_all()` anywhere: this
  service never creates or alters these tables.
- `app/db.py` -- async engine/session factory, `DATABASE_URL` normalization.
  No Alembic, no migrations directory -- intentional (see README.md).
- `app/errors.py` -- the uniform `{"error","message","timestamp"}` body,
  wired via FastAPI exception handlers for the domain `ApiError` hierarchy,
  `RequestValidationError` (-> 400 `VALIDATION_FAILED`, not FastAPI's
  default 422), and the catch-all `StarletteHTTPException`.
- `tests/` -- pytest + `fastapi.testclient.TestClient`, run against the
  shared seeded database (no mocking of Postgres).

## Contract notes (don't "fix" these -- they match the monolith on purpose)

- JSON is **camelCase**, no trailing slash, same uniform error body as
  `00-monolith`'s `common/exceptions.py` -- see `README.md`'s endpoint table.
- `POST /api/reviews`'s 401 uses error code `"ERROR"`, not a dedicated
  `"UNAUTHORIZED"` code -- that's what the monolith's DRF exception handler
  actually produces for an auth failure (its generic catch-all branch, not a
  domain `ApiError`). Matching it byte-for-byte means keeping that
  (slightly surprising) code, not "improving" it.
- `comment` is always a string, never `null`, on read -- the underlying
  Django `CharField` is `blank=True, default=""`, not nullable.
- Rating validation (`1..5`) happens via Pydantic's `Field(ge=1, le=5)` on
  `ReviewCreate` -- a constraint violation becomes `RequestValidationError`,
  remapped by `app/errors.py` to `400 VALIDATION_FAILED` (FastAPI's default
  would be 422; that default is the wrong contract here).
- Auth is checked against `auth_user.password` using passlib's
  `django_pbkdf2_sha256` scheme -- never hand-roll PBKDF2 verification here;
  getting the iteration count, salt format, or comparison timing wrong is a
  real, easy mistake (see `app/auth.py`'s docstring).

## Testing

Needs a reachable Postgres with `00-monolith`'s schema already migrated and
seeded (the `reviewer` / `review-pw-r02` auth user included) -- there is no
separate throwaway schema for this service to create itself:

```sh
docker run -d --name mea-review-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
(cd ../00-monolith && uv run python manage.py migrate && uv run python manage.py seed)
uv run pytest
```
