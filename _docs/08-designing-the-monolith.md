---
title: "Designing the Monolith"
order: 8
part: "The Reference Monolith"
description: "Six bounded contexts as one Django deployable: layered apps, one shared schema, a DRF API, a single checkout transaction and seed data."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Name the six bounded contexts (order, inventory, payment, shipping, notification, review) and the Django app that models each.
- Read the views, services, serializers, urls layering and say why business logic lives in `services.py`, out of DRF's `views.py`.
- Trace `order/services.py::place_order()` call by call and explain how `select_for_update()` in `inventory/services.py::find_with_lock_by_sku` stops two concurrent checkouts overselling a SKU.
- Say which bug each of these avoids: cents-as-integer currency (`total_cents`, `unit_price_cents`), `Order.Status` as `TextChoices`, and `OrderItem.order` with `on_delete=models.CASCADE`.
- List the cross-context foreign keys in the shared schema: `orders.customer_id`, `payments.order_id`, `shipments.order_id`, `notifications.customer_id` and `order_id`, and `reviews.customer_id` and `inventory_item_id`.
- Explain why DRF's camelCase serializers already do the translation job a FastAPI Pydantic schema does once a context is extracted.

## Why this matters

`examples/00-monolith` is the system every later extraction takes apart: a Django project with one process, one Postgres schema and six bounded contexts living inside it as Django apps. It is built the way the business would have shipped it, as one deployable and one database started with one `uv run manage.py runserver`. The contexts are already distinct. They just aren't independently deployable, and that gap is what the extractions close.

{% include excalidraw.html file="monolith-architecture" alt="The monolith as one Django deployable: a single ASGI/WSGI process fronting six Django apps, all backed by one shared Postgres schema" caption="Figure 8.1: One deployable, six contexts, one schema" %}

## The domain: six bounded contexts

A customer places an order, the order reserves stock, charges a payment method, dispatches a shipment and triggers a confirmation. A customer can also review something they bought. That sentence names six contexts:

| Context | Owns | Django app |
|---|---|---|
| Order | The checkout aggregate and its line items | `order` |
| Inventory | Stock levels per SKU | `inventory` |
| Payment | Charge and decline records | `payment` |
| Shipping | Dispatch records | `shipping` |
| Notification | Order-confirmation messages | `notification` |
| Review | Product reviews, independent of the order lifecycle | `review` |

Two more packages are not contexts. `common` is the shared kernel: `Customer` (referenced by order, review and notification) and `OutboxEvent`, the transactional outbox the notification extraction later depends on. `config` is the Django project package: settings, root URL configuration and the WSGI/ASGI entry points.

{% include excalidraw.html file="monolith-six-contexts" alt="Six Django apps (order, inventory, payment, shipping, notification, review) plus the common shared kernel, all registered in one INSTALLED_APPS list" caption="Figure 8.2: Six contexts, one shared kernel, one Django project" %}

Review stands out. It has no synchronous runtime dependency on order, inventory, payment, shipping or notification, and `review/models.py` says so in its docstring: review is "the least-coupled context in this monolith (REST-only, no synchronous collaborator)." That makes it the cheapest place to prove the extraction loop, so it goes first.

## The layering: one app per context, five files deep

Every app has the same shape:

- `models.py`: the ORM models, each with `Meta.db_table` set to a plain lowercase name (`orders`, `inventory_items`, `payments`, `shipments`, `notifications`, `reviews`) instead of Django's app-prefixed default. Extracted services keep the same table names inside their own schemas, so a diff against the monolith's schema stays readable context by context.
- `services.py`: the domain and application logic, kept out of the view. It becomes the extracted service's application layer; FastAPI endpoints later call logic shaped exactly like this.
- `serializers.py`: DRF serializers translating between camelCase wire JSON and snake_case ORM fields.
- `views.py`: thin `APIView` subclasses that parse the request, call `services` and shape the `Response`.
- `urls.py`: the app's `urlpatterns`, included once from `config/urls.py`.

`order` also carries `inventory_client.py` (a gRPC anti-corruption layer used once inventory is extracted) and some saga-listener management commands that only matter once payment and shipping leave the process. At the state described here they don't run. The original design, preserved at the `reference/monolith-before` branch and the `v0-monolith` tag, is simpler: every checkout is synchronous and in-process.

### The entities

`common.models.Customer` is the shared kernel every other context points back to:

```python
class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "customers"
```

`order.models.Order` is the aggregate root: a `status` (`PENDING`, `CONFIRMED`, `PAYMENT_DECLINED`, plus a few states that exist only once the sagas run), a `total_cents` computed at checkout, and a `customer` foreign key into `customers`. `OrderItem` holds a denormalized snapshot of what was ordered (`sku`, `item_name`, `quantity`, `unit_price_cents`) taken at checkout, not joined live against `inventory_items`. A later price change in inventory must never rewrite a historical order line, and that holds whether or not inventory shares the schema.

`InventoryItem` is just `sku`, `name`, `price_cents` and `quantity_on_hand`. Because the state is simple and directly reachable, `order` reaches straight into it instead of going through a contract. `Payment` and `Shipment` are equally plain: one row per order, an `order` foreign key and a `status`. `Notification` joins to both `customers` and `orders`, the most tightly coupled read model in the schema. `Review` joins to `customers` and `inventory_items` and nothing else, so its seam is visible in the model definitions before any diagram is drawn.

## Persistence: one shared Postgres schema

`config/settings.py` registers all six apps plus `common` in one `INSTALLED_APPS` and one `DATABASES["default"]`: one Postgres database, overridable with `DATABASE_URL`, defaulting to `postgresql://monolith:monolith@localhost:5432/monolith`. There is one migration history. A schema change to `inventory` and one to `payment` land in the same `manage.py migrate` run whether or not either context wanted the other's change to ship. That is the mechanism behind "shared data, shared deploy."

{% include excalidraw.html file="monolith-shared-schema-er" alt="Entity-relationship diagram of the monolith's one Postgres schema: customers, inventory_items, orders, order_items, payments, shipments, notifications, reviews, and outbox, with foreign keys crossing context boundaries" caption="Figure 8.3: One schema, eight tables, foreign keys crossing every bounded-context line" %}

Every arrow that leaves one context's table for another's is a cross-context foreign key: `orders.customer_id` into `customers`, `payments.order_id` and `shipments.order_id` into `orders`, `notifications.customer_id` and `order_id` into both, `reviews.customer_id` and `inventory_item_id` into two more. They are the ordinary way to model this domain in one relational schema, not mistakes. Each becomes a decision the moment the tables on either end stop sharing a database.

## The REST API surface

`config/urls.py` is one router with an `include()` per app under `/api/orders`, `/api/inventory`, `/api/payments`, `/api/shipments`, `/api/notifications` and `/api/reviews`, plus a `drf-spectacular` OpenAPI endpoint. Every view uses camelCase JSON in and out, a `Location` header on every `201 Created`, and one error body, `{"error": ..., "message": ..., "timestamp": ...}`, produced by `api_exception_handler` in `common/exceptions.py` and wired in as DRF's global `EXCEPTION_HANDLER`. Typed `ApiError` subclasses map domain failures onto it:

| Exception | Status |
|---|---|
| `ResourceNotFound` | 404 |
| `InsufficientStock` | 409 |
| `PaymentDeclined` | 402 |
| `ShippingFailed` | 422 |
| `InventoryServiceUnavailable` | 503 |

A browser, a test or the strangler proxy sees one error contract whichever context raised it.

`review/views.py` is the one view that differs. `POST /api/reviews` uses `BasicAuthentication` and `IsAuthenticated`, while `GET /api/reviews` and `GET /api/reviews/{id}` stay open. Auth is wired per view (`authentication_classes` and an overridden `get_permissions()`) rather than through DRF's global `DEFAULT_PERMISSION_CLASSES`, because the global setting would make every other context's reads authenticate too. That one view borrowing shared auth is itself a planted smell.

The wire is camelCase while the ORM is snake_case. `OrderCreateSerializer` maps `customerId` to `customer_id` and `paymentMethod` to `payment_method`, and `OrderSerializer` does the reverse on reads. This fixes the contract independent of internal names, and it is the job a hand-rolled FastAPI Pydantic schema does once a context leaves the monolith: translate between what Python calls a field and what the contract calls it, once, at the edge.

## The wiring: config, logging and flags

`config/settings.py` is the one configuration module. It wires `drf-spectacular` for a generated schema (`GET /api/schema`, Swagger UI at `/api/schema/swagger-ui`), so endpoint docs can't drift from the code. It adds a rotating file handler under `logs/` beside the console logger, because a scrollback buffer doesn't survive a crashed test run. And it carries three feature flags, `INVENTORY_MODE`, `PAYMENT_MODE` and `SHIPPING_MODE`, that default to the original synchronous, in-process behavior. Later extractions flip one flag at a time instead of rewriting `place_order()`. The habit is to add the new path beside the old one, default to the old one, and flip the default once the new path is proven equivalent.

## The checkout transaction

`order/services.py::place_order()` is the one function that touches every other context in a single request. Its original shape, preserved byte for byte as `_place_order_local()` and still the default path, reads:

```python
with transaction.atomic():
    order = Order.objects.create(customer=customer, ...)
    for line in items:
        inventory_item = inventory_services.get_by_sku(line["sku"])
        inventory_services.reserve(line["sku"], line["quantity"])
        OrderItem.objects.create(order=order, sku=inventory_item.sku, ...)
    order.total_cents = total_cents
    order.save(update_fields=["total_cents"])

    payment_services.charge(order, order.total_cents, payment_method)
    order.confirm()
    order.save(update_fields=["status"])

    shipping_services.dispatch(order, order.shipping_address)
    _write_order_placed_outbox_event(customer, order)
```

One `transaction.atomic()` block spans five contexts' writes: order persistence, an inventory decrement, a payment capture, a shipment dispatch and an outbox row for notification. Each call goes straight into another app's `services` module, in-process and synchronous, with no network boundary and no contract. That works because Postgres rolls back all of it atomically. An over-ordered line raises before any write happens, and a declined payment or failed shipment unwinds everything written so far.

{% include excalidraw.html file="place-order-transaction-sequence" alt="Sequence diagram of place_order(): order creation, inventory reservation, payment capture, shipment dispatch, and an outbox write, all inside one transaction.atomic() block" caption="Figure 8.4: place_order()'s single transaction, five contexts deep" %}

Two deterministic failure sentinels make the rollback observable. A `paymentMethod` containing `DECLINE` raises `PaymentDeclined` (`402`) after the inventory reservation already happened. A `shippingAddress` containing `SHIP-FAIL` raises `ShippingFailed` (`422`) after payment already captured. Both roll the whole transaction back, reservation included, leaving stock where it started.

## Seed data

`common/management/commands/seed.py` creates two customers, three inventory items (one low on stock, so the over-order path needs no setup), one fully confirmed order with its payment, shipment and notification, two reviews, and a fixed Basic-auth demo user, `reviewer`, for the review write endpoint. It is idempotent: against a database that already has customers, it only backfills the auth user.

## Why mainstream Django

Django and DRF are among the most ordinary ways to ship a REST API in Python: an ORM with migrations, an admin and auth system (borrowed here for one thing, review's Basic-auth gate), and a request cycle every Python developer has seen. An exotic framework or a hand-rolled ASGI app would make the "before" look unusual and invite the wrong lesson, that the coupling comes from a framework choice. It comes from sharing one process and one schema across six contexts. A team on Flask, FastAPI or raw `psycopg` would plant the same seven smells.

## A healthy "before"

A single Django project with a shared Postgres schema is a defensible way to ship a first version: fast to build, easy to test end to end, one thing to deploy, one transaction model to reason about. The six contexts are already visible in the code: six Django apps, six `services.py` modules, six URL prefixes and a domain model that names its own joins. The smells are in code that already exists.

All six contexts have since been extracted, and the monolith's checkout path is frozen: no live traffic reaches `_place_order_local()`. `examples/00-monolith` still runs as a break-glass reference with the same `uv run` commands below against a fresh Postgres. The pristine pre-extraction state is preserved on the `reference/monolith-before` branch and the `v0-monolith` tag, the version every extraction was proven equivalent to.

> **Decision**
>
> Keep a context in the shared Django project until you can name the cross-context foreign keys and calls it depends on. Draw the extraction line along the app boundary that has the fewest, and start with the context that makes no synchronous call in or out.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith`, list every cross-app `ForeignKey` and every cross-app import of a `services` module. Group them by context and rank the six contexts from least to most coupled. Say which one is the cheapest to extract first and why."
>
> Check: the reply puts `review` first (foreign keys only to `customers` and `inventory_items`, and no import of another context's `services`) and `order` last, matching `SMELLS.md`.

## Build, run, observe

Start the monolith against a local Postgres:

```sh
cd examples/00-monolith
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000
```

Check out against the seeded data:

```sh
curl -s -X POST localhost:8000/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId": 1, "items": [{"sku": "SKU-WIDGET-001", "quantity": 1}],
       "paymentMethod": "CARD-VISA", "shippingAddress": "1 Analytical Engine Way"}'
```

```json
{
  "id": 2,
  "customerId": 1,
  "status": "CONFIRMED",
  "totalCents": 1999,
  "createdAt": "2026-01-10T09:00:00Z",
  "shippingAddress": "1 Analytical Engine Way",
  "items": [{"sku": "SKU-WIDGET-001", "quantity": 1, "unitPriceCents": 1999}]
}
```

The response is `201 Created` with `Location: /api/orders/2`. `uv run pytest` runs the monolith's tests, smoke and checkout failure injection included, against the same Postgres. Experiments:

- Send `"paymentMethod": "CARD-DECLINE"`: the response is `402 PAYMENT_DECLINED` and stock for the SKU is unchanged.
- Send `"shippingAddress": "SHIP-FAIL"`: the response is `422 SHIPPING_FAILED`, with the reservation, order row and payment capture all rolled back.
- Order more than `quantityOnHand`: the response is `409 OUT_OF_STOCK`, raised before any write.

## For deeper coverage

`examples/00-monolith/README.md` has the frozen-status notes and `examples/00-monolith/SMELLS.md` the full smell table. The Django REST Framework documentation covers serializers and per-view permissions.
