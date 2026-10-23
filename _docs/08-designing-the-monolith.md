---
title: "Designing the Monolith"
order: 8
part: "The Reference Monolith"
description: "The six bounded contexts as one Django deployable: domain model, layered apps, single shared schema, REST API (DRF), and seed data."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why the monolith's six bounded contexts (order, inventory, payment, shipping, notification, review) are split along Django app lines, and name the conceptual boundary each one models.
- Read the views-services-serializers-urls layering shared across all six contexts and explain why business logic lives in `services.py`, kept out of DRF's `views.py`, with no hexagonal ports drawn yet.
- Trace `order/services.py::place_order()` call by call and explain how the row-level lock in `inventory/services.py::find_with_lock_by_sku` (a Postgres `SELECT ... FOR UPDATE` via `select_for_update()`), used by `reserve()`, prevents two concurrent checkouts from overselling the same SKU.
- Identify where cents-as-integer currency (`total_cents`, `unit_price_cents`), Django's `TextChoices` enum (`Order.Status`), and a cascading `OrderItem.order` foreign key with `on_delete=models.CASCADE` are used, and state the bug each one avoids.
- Explain why this chapter chose mainstream Django 5.2 LTS and DRF over an exotic framework or hand-rolled ASGI app, so the book's modernization lesson comes from the shape of the deployment (one process, one schema) rather than from a framework choice.
- Recognize that DRF's camelCase serializers (`OrderCreateSerializer`, `OrderSerializer`) already do the translation job a hand-rolled FastAPI Pydantic schema will do later, once a context leaves the monolith, and that each app's `services.py` is what becomes that extracted service's own application layer.
- Read the shared-schema ER diagram and name the cross-context foreign keys (`orders.customer_id`, `payments.order_id`, `shipments.order_id`, `notifications.customer_id`/`order_id`, `reviews.customer_id`/`inventory_item_id`) that Chapter 9 tags as smells and later chapters (ch.18/19) cut.

## Why this matters

Every chapter before this one has been setup: toolchain, ledger, strategy,
the ADLC itself. This is the first chapter with a running system behind it.
`examples/00-monolith` is a Django 5.2 LTS project: one process, one
Postgres schema, six bounded contexts living inside it as Django apps. It
is the "before" picture for the entire book: the system every later part
incrementally takes apart, one seam at a time, without ever taking the
lights out.

Build it the way the business sold it, not the way a microservices
diagram would have drawn it from day one. A real team shipping this product
would reach for exactly this shape first: one deployable, one database,
one `uv run manage.py runserver`. The six contexts underneath are already
distinct; they just aren't independently deployable yet. That gap between
"the contexts are distinct" and "the contexts are deployable" is the whole
subject of Parts 5 through 7.

{% include excalidraw.html file="monolith-architecture" alt="The monolith as one Django deployable: a single ASGI/WSGI process fronting six Django apps, all backed by one shared Postgres schema" caption="Figure 8.1: One deployable, six contexts, one schema" %}

## The domain: six bounded contexts, one shipping business

The product is ordinary: a customer places an order, the order reserves
stock, charges a payment method, dispatches a shipment, and triggers a
confirmation. A customer can also leave a review of something they bought.
That single sentence already names six bounded contexts:

| Context | Owns | Django app |
|---|---|---|
| Order | The checkout aggregate and its line items | `order` |
| Inventory | Stock levels per SKU | `inventory` |
| Payment | Charge/decline records | `payment` |
| Shipping | Dispatch records | `shipping` |
| Notification | Order-confirmation messages | `notification` |
| Review | Product reviews, independent of the order lifecycle | `review` |

A seventh package, `common`, is not a bounded context; it is the shared
kernel: `Customer` (referenced by order, review, and notification) and
`OutboxEvent` (the transactional outbox that notification's extraction
later depends on, see ch.17). `config` is the Django project package:
settings, root URL configuration, WSGI/ASGI entry points.

{% include excalidraw.html file="monolith-six-contexts" alt="Six Django apps (order, inventory, payment, shipping, notification, review) plus the common shared kernel, all registered in one INSTALLED_APPS list" caption="Figure 8.2: Six contexts, one shared kernel, one Django project" %}

Review stands out early, because its shape previews a decision Part 5
makes explicit: review has no synchronous runtime dependency on order,
inventory, payment, shipping, or notification. `review/models.py` says this
directly in its own docstring: review is "the least-coupled context in
this monolith (REST-only, no synchronous collaborator)." That is exactly
why it gets pulled out first, in ch.15: the least-coupled context is the
cheapest place to prove the whole
extraction loop works before attempting it on something harder.

## The layering: one Django app per context, five files deep

Every one of the six apps follows the same internal shape:

- `models.py`: the Django ORM models, each one `Meta.db_table`-pinned to a
  plain, lowercase table name (`orders`, `inventory_items`, `payments`,
  `shipments`, `notifications`, `reviews`) rather than Django's
  app-prefixed default. That naming choice matters later: every extracted
  service in Part 5 keeps the same table name inside its own
  context-scoped schema, so a diff against the original monolith's schema
  stays legible context by context.
- `services.py`: the domain/application logic, kept *out* of the view by
  design. This is the layer that becomes the extracted service's own
  application layer once a context leaves the monolith: FastAPI endpoints
  in Part 5 call into logic shaped exactly like this.
- `serializers.py`: DRF serializers translating between the wire's
  camelCase JSON and the ORM's snake_case fields.
- `views.py`: thin DRF `APIView` subclasses: parse the request, call
  `services`, shape the `Response`. No business logic lives here.
- `urls.py`: the app's own `urlpatterns`, included once from the project's
  `config/urls.py`.

`order` additionally carries `inventory_client.py` (a gRPC anti-corruption
layer used once inventory is extracted, out of scope for this chapter) and
a handful of saga-listener management commands that only matter once
payment and shipping leave the process too. None of that machinery runs at
the state this chapter describes; the monolith's *original* design (the
one `reference/monolith-before` and the `v0-monolith` tag preserve) is
simpler: every checkout is synchronous, in-process, start to finish.

### The entities: one shared kernel, five contexts' worth of state

`common.models.Customer` is the shared kernel every other context's rows
point back to:

```python
class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "customers"
```

`order.models.Order` is the aggregate root of the whole business flow: a
`status` field (`PENDING`, `CONFIRMED`, `PAYMENT_DECLINED`, and a couple of
states that only exist once Part 6's sagas are running), a `total_cents`
computed at checkout time, and a `customer` foreign key straight into the
shared `customers` table. `order.models.OrderItem` carries a *denormalized*
snapshot of what was ordered (`sku`, `item_name`, `quantity`,
`unit_price_cents`) captured once at checkout rather than joined live
against `inventory_items` on every read. That snapshot shape is deliberate:
a later price change in inventory should never retroactively rewrite a
historical order line, which is the correct read-model semantics
regardless of whether inventory lives in this schema or its own.

`inventory.models.InventoryItem` is almost embarrassingly simple (`sku`,
`name`, `price_cents`, `quantity_on_hand`), which is exactly the point.
Simple state, directly reachable, is what makes it so easy for `order` to
reach straight into it instead of going through a contract (more on that in
ch.9). `payment.models.Payment` and `shipping.models.Shipment` are equally
plain: one row per order, an `order` foreign key, a `status` field, nothing
else. `notification.models.Notification` joins to *both* `customers` and
`orders`, which makes it the most tightly coupled read model in the schema,
and the first one extraction has to prove it can still populate
correctly once checkout stops writing it synchronously (ch.17).

`review.models.Review` is the odd one out, by design: it joins to
`customers` and `inventory_items`, and nothing else. No order, no payment,
no shipping, no notification. That absence of a foreign key is review's own
seam, visible straight out of the model definitions, long before any
diagram is drawn.

## Persistence: one shared Postgres schema

`config/settings.py` wires all six apps plus `common` into one
`INSTALLED_APPS` list and one `DATABASES["default"]` entry: one Postgres
database, env-overridable via `DATABASE_URL`, defaulting to
`postgresql://monolith:monolith@localhost:5432/monolith`. There is exactly
one migration history across all six apps; a schema change to `inventory`
and a schema change to `payment` land in the same `manage.py migrate` run,
whether or not either context asked for the other's change to ship at the
same time. That is the literal mechanism behind "shared data, shared
deploy," which ch.18 names and starts to undo.

{% include excalidraw.html file="monolith-shared-schema-er" alt="Entity-relationship diagram of the monolith's one Postgres schema: customers, inventory_items, orders, order_items, payments, shipments, notifications, reviews, and outbox, with foreign keys crossing context boundaries" caption="Figure 8.3: One schema, eight tables, foreign keys crossing every bounded-context line" %}

Every arrow in that diagram that crosses from one context's table into
another's is a cross-context foreign key: `orders.customer_id` into
`customers`, `payments.order_id` and `shipments.order_id` into `orders`,
`notifications.customer_id`/`order_id` into both, `reviews.customer_id`/
`inventory_item_id` into two more. None of them are accidental; they are
the ordinary, idiomatic way to model this domain in one relational schema.
The point this book makes starting in ch.9 is not that this was done
wrong; it's that every one of those joins becomes a decision the moment the
tables it crosses stop living in the same database.

## The REST API surface

`config/urls.py` is one router for all six contexts: a flat list of
`include()`s, one per app, under `/api/orders`, `/api/inventory`,
`/api/payments`, `/api/shipments`, `/api/notifications`, and `/api/reviews`,
plus a `drf-spectacular` OpenAPI schema endpoint. Every view follows the
same request/response contract: camelCase JSON in and out, a `Location`
header on every `201 Created`, and a uniform error body
(`{"error": ..., "message": ..., "timestamp": ...}`) produced by
`common/exceptions.py`'s `api_exception_handler`, wired in as DRF's global
`EXCEPTION_HANDLER`. A handful of typed `ApiError` subclasses
(`ResourceNotFound` → 404, `InsufficientStock` → 409, `PaymentDeclined` →
402, `ShippingFailed` → 422, `InventoryServiceUnavailable` → 503) map
domain failures onto that one body shape, so every client (a human
hitting Swagger, a test, or later the strangler proxy) sees exactly one
error contract no matter which context raised it.

`review/views.py` is the one view in the whole monolith that looks
different: `POST /api/reviews` is gated by DRF's `BasicAuthentication` and
`IsAuthenticated`, while `GET /api/reviews` and `GET /api/reviews/{id}`
stay open to anyone, no credentials required. The gate is wired per-view
(`authentication_classes`, an overridden `get_permissions()`), specifically
not through DRF's global `DEFAULT_PERMISSION_CLASSES`, because turning
that on would require every other context's reads to authenticate too.
Chapter 9 explains exactly why this one view borrowing shared auth
machinery is itself a planted smell, not a stylistic quirk.

Every DTO on the wire is camelCase, even though the ORM underneath is
ordinary snake_case Python: `OrderCreateSerializer` maps `customerId` to
`customer_id`, `paymentMethod` to `payment_method`, and so on; `OrderSerializer`
does the same in reverse for reads. That translation layer does two jobs
at once: it matches the contract the Java sibling project established
(so the two books describe the same wire shape even though neither runtime
shares a line of code with the other), and it means every DRF serializer in
this project is already doing the one job a hand-rolled FastAPI Pydantic
schema will do later, once a context leaves the monolith: translate
between "what Python calls this" and "what the contract calls this," in one
place, at the edge.

## The wiring: config, logging, and forward-looking flags

`config/settings.py` is this project's one configuration module, and it
carries more than `INSTALLED_APPS` and `DATABASES`. It wires `drf-spectacular`
for a generated OpenAPI schema (`GET /api/schema`, plus a Swagger UI at
`/api/schema/swagger-ui`) so every one of the six contexts' endpoints is
browsable without hand-written API docs drifting out of sync with the code.
It configures a rotating file handler under `logs/` alongside the console
logger, a convention this book keeps across every Python service it
builds, because a scrollback buffer is not a substitute for a log file that
survives a crashed test run. And it carries three feature flags
(`INVENTORY_MODE`, `PAYMENT_MODE`, `SHIPPING_MODE`) that do nothing yet at
the state this chapter describes; every one of them defaults to the
original, synchronous, in-process behavior this chapter walks through.
They exist in the file already because later chapters (ch.19, ch.23–25)
cut their respective contexts over by flipping one flag at a time, not by
rewriting `place_order()` from scratch. Seeing them here, inert, is a small
preview of how this book prefers to make a change: add the new path beside
the old one, default to the old one, and only flip the default once the new
path is proven equivalent.

## The checkout transaction

`order/services.py::place_order()` is the center of gravity for the entire
monolith: the one function that touches every other context in a single
request. Its original, pre-extraction shape (preserved byte-for-byte as
`_place_order_local()`, still the default code path today) reads like this:

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

One `transaction.atomic()` block spans five contexts' worth of writes:
order persistence, an inventory decrement, a payment capture, a shipment
dispatch, and an outbox row for notification to pick up later. Every one of
those calls reaches directly into another app's `services` module
(`inventory_services.reserve()`, `payment_services.charge()`,
`shipping_services.dispatch()`) in-process, synchronously, with no network
boundary and no contract between them. That works, today, because Postgres
gives atomic rollback across all of it automatically: an over-ordered line
raises before any writes happen; a declined payment or a failed shipment
address unwinds everything written so far in the same request.

{% include excalidraw.html file="place-order-transaction-sequence" alt="Sequence diagram of place_order(): order creation, inventory reservation, payment capture, shipment dispatch, and an outbox write, all inside one transaction.atomic() block" caption="Figure 8.4: place_order()'s single transaction, five contexts deep" %}

Two deterministic failure sentinels make that rollback provable, not just
asserted: a `paymentMethod` containing `DECLINE` raises `PaymentDeclined`
(`402`) after the inventory reservation already happened, and a
`shippingAddress` containing `SHIP-FAIL` raises `ShippingFailed` (`422`)
after payment already captured. Both roll the *entire* transaction back,
inventory reservation included, leaving stock at exactly the level it
started at. `tests/test_checkout.py` exercises both paths directly; ch.9
returns to this same function as the clearest example of why "it works
today" and "it will keep working once this becomes six services" are two
different claims.

## Seed data, and running it

`common/management/commands/seed.py` populates two customers, three
inventory items (one kept low-stock, to exercise the
over-order path with no extra setup), one fully confirmed order with its
payment/shipment/notification already attached, two reviews, and one fixed
Basic-auth demo user (`reviewer`) for the review write endpoint. The whole
command is idempotent: re-running it against a database that already has
customers is a no-op except for backfilling the auth user. Bringing the
monolith up end to end is three commands:

```sh
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000
```

That is the whole "before" system: one process, one schema, six contexts,
a deterministic seed, and a REST surface any client can drive without
knowing six services exist underneath it, because at this point in the
book, they don't. A checkout against the seeded data looks like this:

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

One request, five contexts' worth of work, one `201 Created` with a
`Location: /api/orders/2` header: the same `place_order()` sequence
walked through above, confirmed end to end against a running server.

## Why mainstream Django

Nothing about this monolith's stack is exotic, by design. Django
5.2 LTS plus Django REST Framework is one of the most ordinary ways to ship
a REST API in Python: an ORM with migrations built in, a batteries-included
admin and auth system (borrowed, in this project's case, for exactly one
thing: review's Basic-auth gate), and a request/response cycle every Python
developer has already seen somewhere. A more exotic framework, or a
hand-rolled ASGI app, would have made the "before" picture look unusual, and
an unusual "before" invites the wrong lesson, that the
coupling problems in Part 5 come from a framework choice rather than from
sharing one process and one schema across six contexts. They don't. A team
that reached for Flask, or FastAPI, or straight `psycopg` and raw SQL for
this same monolith would have planted the exact same seven smells, because
every one of them follows from the *shape* of the deployment (one process,
one database), not from which web framework answers the HTTP request. Using
the most ordinary possible tool for the "before" picture is what makes the
"after" picture's lesson about modernization, not about a
framework migration.

## A healthy "before," with seams already visible

Nothing about this design is a mistake. A single Django project with a
shared Postgres schema is a defensible, even *good*, way to ship this
product's first version: fast to build, trivial to test end to end, one
thing to deploy, one transaction model to reason about. What makes it the
right teaching artifact for this book is that the six contexts are already
visible in the code, long before any of them become their own service:
six Django apps, six `services.py` modules, six URL prefixes, a domain
model that already names its own joins. Ch.9 does not invent the seams;
it points at them, in code that already exists.

As of the book's current state, every one of those six contexts has since
been pulled out into its own service, and this monolith's checkout path is
frozen: no live traffic reaches `_place_order_local()` anymore. The code
in `examples/00-monolith` still runs as a break-glass reference (the same
`uv run` commands above work against a fresh Postgres), and the pristine,
pre-extraction state this chapter describes is preserved exactly on the
`reference/monolith-before` branch and the `v0-monolith` tag: the version
every extraction in Parts 5 through 7 was proven equivalent to, one context
at a time.

Next: ch.9 reads this same codebase again, this time hunting on the record:
naming all seven smells by their `# SMELL[ch.NN]:` tags and the exact
chapter each one gets cured in.
