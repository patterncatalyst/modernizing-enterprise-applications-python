# 00-monolith

The r01 "before" system: a Django 5.2 LTS + Django REST Framework monolith with
all six bounded contexts -- **order, inventory, payment, shipping,
notification, review** -- living in one Django project, sharing one Postgres
schema, checkout orchestrated by one synchronous god function. This is the
walking skeleton the book incrementally decomposes.

Python sibling of
[`modernizing-enterprise-applications/examples/00-monolith`](https://github.com/patterncatalyst/modernizing-enterprise-applications)
(Java/Spring Boot), built to that project's *original* schema/seed/smell
intent.

## Six deliberate smells

Every smell below is intentional -- see [`SMELLS.md`](./SMELLS.md) for the full
table and which chapter cures each one.

1. God checkout service (`order/services.py::place_order`)
2. One ACID transaction spanning all six contexts (`@transaction.atomic`)
3. Shared single Postgres schema for all six Django apps
4. Cross-context foreign keys (e.g. `OrderItem.inventory_item`, `Payment.order`)
5. Synchronous in-process notification send inside the checkout transaction
6. Dual-write hazard (a DB write and an external-provider call, not atomic together)

```sh
grep -rn 'SMELL\[ch\.' .
```

## Quickstart

```sh
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed   # 2 customers, 3 inventory items, 1 confirmed order, 2 reviews
uv run python manage.py runserver 0.0.0.0:8000
```

Defaults to `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`
(the INFRA lane's compose stack). Override via `.env`/environment -- see
[`.env.example`](./.env.example). A quick standalone Postgres for local use:

```sh
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
```

## API surface

All JSON is **camelCase** to match the Java sibling's contract. No trailing
slashes.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/inventory` | list |
| GET | `/api/inventory/{sku}` | |
| GET | `/api/orders` | list |
| POST | `/api/orders` | checkout -- 201 + `Location` + `status: CONFIRMED` on success |
| GET | `/api/orders/{id}` | |
| GET | `/api/payments?orderId=` | |
| GET | `/api/payments/{id}` | |
| GET | `/api/shipments?orderId=` | |
| GET | `/api/shipments/{id}` | |
| GET | `/api/notifications?customerId=` | |
| GET\|POST | `/api/reviews` | GET takes an optional `?sku=` filter |
| GET | `/api/reviews/{id}` | |
| GET | `/api/schema`, `/api/schema/swagger-ui` | OpenAPI (drf-spectacular) |

### Deterministic failure injection (checkout)

| Scenario | Trigger | Result |
|---|---|---|
| Happy path | any valid checkout | `201 Created`, `status: CONFIRMED` |
| Out of stock | a line quantity exceeding `quantityOnHand` | `409 Conflict`, `error: OUT_OF_STOCK` |
| Payment declined | `paymentMethod` contains `DECLINE` | `402 Payment Required`, `error: PAYMENT_DECLINED`, stock reservation rolled back |
| Shipping failure | `shippingAddress` contains `SHIP-FAIL` | `422 Unprocessable Entity`, `error: SHIPPING_FAILED`, ENTIRE checkout rolled back (net-zero stock) |

## Testing

```sh
uv run python manage.py check   # Django system checks
uv run ruff check .             # lint
uv run pytest                   # six-context smoke + checkout failure-injection tests
```

Tests need a reachable Postgres (pytest-django creates/drops its own
`test_<NAME>` database against `DATABASE_URL`).

## Container

```sh
docker build -f Dockerfile -t mea-monolith:r01 .
docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql://monolith:monolith@<host>:5432/monolith mea-monolith:r01
```

UBI 10 (`ubi10/python-314-minimal`), multi-stage `uv sync`, runs as non-root
(UID 1001, GID 0 -- OpenShift/arbitrary-UID compatible) under gunicorn on
`:8000`.

## Structured logging

Rotating file logs land in `logs/monolith.log` (JSON-free, human-readable;
see `config/settings.py`'s `LOGGING` dict) alongside console output, so an
agent or a developer can grep the log after a crash or a failed test run even
once the console output has scrolled away.
