# AGENTS.md -- 00-monolith

Context for an AI agent (or a human) picking this module up.

## What this is

The r01 "before" picture: a Django 5.2 LTS + DRF monolith with all six bounded
contexts (order, inventory, payment, shipping, notification, review) living in
one Django project, sharing one Postgres schema, orchestrated synchronously by
one god checkout function. It is the Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/00-monolith` (Java/Spring
Boot), built to the SAME original schema/seed/smell intent -- not that
project's later, decomposed `main` state.

**FROZEN as of r07** -- all six contexts are now extracted
(`02`-`07-order-service`); the strangler proxy is a flagless edge router with
no monolith fallback; this module is decommissioned from the running
topology (`compose.yaml`/`scripts/`/`demos/` no longer start it or its
`outbox_relay`/`order_placed_consumer`/`order_saga_listener` commands) but
kept in-repo as the golden-baseline referent and a break-glass fallback --
see `README.md`'s "FROZEN STATUS (r07)" section for the full picture, and
`SMELLS.md` for the two smells this decommission strikes (#1, #2). An agent
picking this module up going forward should treat it as read-mostly history,
not a module to keep extending.

Every smell is intentional. See `SMELLS.md` and `grep -rn 'SMELL\[ch\.' .`
before "fixing" anything that looks like bad design -- it is bad design, on
purpose, planted as teaching material for the chapters that later cure it.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile. Never run
  bare `pip`/`python -m venv` in this project.
- **Python 3.14**, pinned via `.python-version` and `requires-python` in
  `pyproject.toml`.
- **Django 5.2.18 + DRF 3.18.3**, **psycopg[binary] 3.3.6**, **gunicorn
  26.2.0**, **drf-spectacular** for OpenAPI. Dev-only: **pytest 9.1.1** +
  **pytest-django 4.14.0**, **ruff 0.17.1**.

## Commands

```sh
uv sync --group dev          # install everything (app + dev deps)
uv run python manage.py migrate
uv run python manage.py seed # idempotent: no-ops if customers already exist
uv run python manage.py runserver 0.0.0.0:8000

uv run python manage.py check  # Django system checks
uv run ruff check .            # lint
uv run pytest                  # unit + smoke tests (needs a reachable Postgres)
```

`DATABASE_URL` (see `.env.example`) defaults to the INFRA lane's compose stack
coordinates (`postgresql://monolith:monolith@localhost:5432/monolith`) but is
fully overridable -- pytest-django/CI point it at their own throwaway
database without this module ever hard-coding a dependency on the compose
stack being up.

## Structure

- `config/` -- the one Django project: settings, root urlconf, wsgi/asgi.
- `common/` -- shared-kernel `Customer` model, the uniform `ApiError`
  exception-mapping surface, and the `seed` management command.
- `order/`, `inventory/`, `payment/`, `shipping/`, `notification/`, `review/`
  -- the six bounded-context Django apps. Each follows the same shape:
  `models.py` (thin), `services.py` (the business logic, Java-`Service`-class
  equivalent but as plain functions), `serializers.py` (camelCase DRF
  serializers), `views.py` (thin DRF `APIView`s), `urls.py`.
- `tests/` -- pytest-django tests (`test_smoke.py` one assertion per
  `/api/*` surface, `test_checkout.py` the four deterministic
  failure-injection paths).

## Contract notes

- JSON is **camelCase** (`priceCents`, not `price_cents`) to match the Java
  sibling's contract -- every serializer maps explicitly via `source=`. Don't
  reach for a camelCase-rename middleware/renderer library; the explicit
  per-field mapping is the point (it's what a reader greps to find the wire
  contract).
- Routes have **no trailing slash** (`/api/inventory/{sku}`, not
  `/api/inventory/{sku}/`) to match that same contract. This trips Django's
  `urls.W002` system check; it's silenced in `config/settings.py` with a
  comment explaining why -- don't "fix" it by adding trailing slashes, that
  would 301-redirect `POST`s and break the contract.
- Uniform error body: `{"error": "<CODE>", "message": "...", "timestamp":
  "..."}`, wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` in
  `common/exceptions.py`.

## Testing

Tests need a reachable Postgres (pytest-django creates/drops a `test_<NAME>`
database against whatever `DATABASE_URL` resolves to). A quick local one:

```sh
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```
