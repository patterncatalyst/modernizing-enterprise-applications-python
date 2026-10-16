# order-service -- Migration Notes

This file follows `examples/05-payment-service/MIGRATION.md`/
`examples/06-shipping-service/MIGRATION.md`'s template, adapted for the one
structural difference this lane introduces: **no two-phase lift.** Every
prior lane in this series built a documented-but-not-shipped Phase A (a thin
FastAPI shim over the monolith's Django ORM, read-only) before its Phase B
rewrite. This lane skips Phase A outright and goes straight to idiomatic --
see "Why no Phase A" below for the CQRS-specific reason that isn't just "no
code to lift" (every prior lane's Phase A write path had that same gap; this
lane's Phase A READ path has an additional, structural one).

## What's lifted byte-for-byte

- `00-monolith/order/services.py::_reserve_lines_remote`/`_release_reserved`'s
  reserve-outside-any-local-transaction discipline and net-zero compensation
  shape -- re-authored `async`, otherwise unchanged in intent.
- `00-monolith/order/services.py::_release_order_lines`'s stable
  per-(order, line) Release idempotency key, `f"{order_id}:{sku}:release"`.
- `00-monolith/order/services.py::handle_payment_captured`/
  `handle_payment_declined`/`handle_shipment_dispatched`/
  `handle_shipment_failed`'s status-transition idempotency GUARDS -- the
  monolith enforces these as a Python `if order.status != EXPECTED` check
  inside Django's implicit per-request transaction; this service enforces
  the SAME guard as a database-level atomic conditional `UPDATE ... WHERE
  status = expected` (`app/repository.py::transition_order_status_with_view`),
  since there is no implicit request-scoped transaction here to hang a
  Python-level check off of, and the stronger guarantee is free to build
  once you're already writing the UPDATE by hand.
- `00-monolith/order/inventory_client.py::RemoteInventoryClient`'s wire
  vocabulary translation (`stock_keeping_unit`/`display_name`/
  `unit_price_cents`/`on_hand_qty`/`reservation_ok` -> plain dataclasses) --
  re-authored on `grpc.aio` instead of a blocking `grpc.insecure_channel`
  (FastAPI's request path runs on an asyncio event loop; the monolith's
  Django/WSGI request path does not).
- `00-monolith/order/serializers.py::OrderSerializer`'s GET contract field
  list, byte-for-byte (including the r06-additive `shippingAddress`).

## What's re-shaped for CQRS (net-new, idiomatic-from-day-one)

There is no monolith original for ANY of this -- the monolith's `Order`/
`OrderItem` ARE both the write model and the read model, queried directly by
`OrderSerializer`. This lane splits that in two:

- `app/models.py::OrderView` -- the read projection, net-new.
- `app/repository.py::create_order_with_outbox_and_view`/
  `transition_order_status_with_view` -- every write path upserts
  `order_view` in the SAME local transaction as the aggregate mutation it is
  paired with. The monolith has no equivalent concern: its `OrderSerializer`
  reads `Order`/`OrderItem` directly, so there is nothing to keep in sync.
- `app/service.py::rebuild_order_view` -- proves the projection is
  rebuildable from the aggregate at any time, never a second source of
  truth.
- `app/models.py::Customer` -- OWNED, forward-filled master data (see
  "Customer FK -> snapshot" below). The monolith's `Order.customer` is a
  live FK/join; this service has no live join to a shared table AT ALL.

## Customer FK -> snapshot

`00-monolith/order/models.py::Order.customer` is a hard FK into the shared
`common.Customer` table (SMELL[ch.18]) -- every `place_order()` call joins
live against it. This service owns a forward-filled COPY
(`order_svc.customers`, `migrations/versions/0002_seed_customers.py`, same
Ada/Grace rows as the monolith's own seed) and validates against THAT table,
never the monolith's, over any protocol (not even gRPC -- there is no
customer-service in this project to call). `orders.customer_id` is a real
FK, but into this OWNED table -- an ordinary intra-schema relationship, not
the cross-service smell. `orders.customer_email` is ADDITIONALLY captured as
its own point-in-time snapshot at checkout time, separate from the live
`customers.email` column, because the `order.placed` event's
`customerEmail` field must never retroactively change if a customer's email
is later updated.

This is the SAME snapshot discipline `OrderItem.sku`/`unit_price_cents`
already follow (r04/ch.19's cure for the inventory-side version of
SMELL[ch.18]) -- extended here to the customer relationship, the ONE
cross-context FK every prior lane left untouched because none of them owned
`order`.

## Why no Phase A

Every prior lane's Phase A sketch (`05-payment-service/MIGRATION.md`,
`06-shipping-service/MIGRATION.md`) demonstrated the SAME two problems for
its write path: Django's ORM is synchronous (`sync_to_async` everywhere),
and the dependency direction is backwards (a build-time dependency on the
monolith's whole codebase just to reach one model). This lane's write path
has that identical gap -- `place_order()`'s choreographed/gRPC-reserving
shape has no synchronous Django original to lift, same as every choreographed
lane before it.

What's DIFFERENT here, and why Phase A was skipped rather than merely
sketched: every prior lane's Phase A read surface was a legitimate,
non-trivial illustration (`GET /api/payments` querying `payment.Payment`
through `sync_to_async`, genuinely showing what a lift-without-reshape looks
like). This lane's read surface is `order_view` -- a denormalized CQRS
projection with inline JSON items that has NO SHAPE IN THE MONOLITH'S TABLES
to even approximate with a thin shim. A Phase A "lift" of `GET /api/orders`
against the monolith's `Order`/`OrderItem` tables through `sync_to_async`
would just be an ordinary two-table join -- it would teach nothing about the
CQRS split this lane exists to build, and would not resemble `app/repository.py`'s
actual read functions (`order_view`-only) at all. Given the acceptance bar
is "Phase B is the final, live code, Phase A is documented, not shipped,"
and this lane's Phase A has nothing non-trivial to document on EITHER axis
(write: no sync original, same as every choreographed lane; read: no
equivalent shape to shim against, unique to this lane), the team did not
spend implementation/CI surface on a Phase A module at all.

## Per-component refactor (A -> B), as designed (not built)

| Component | Phase A (illustrative, not built) | Phase B (idiomatic, shipped) |
|---|---|---|
| HTTP layer | FastAPI route calling into Django ORM via `sync_to_async` | `app/routes.py` -- native async, reads from `order_view` only |
| Data access | `order.models.Order`/`OrderItem` (Django ORM, hard FK to `common.Customer`) | `app/models.py` -- independent SQLAlchemy 2.x mapping, split into write (`orders`/`order_items`/`customers`/`outbox`) and read (`order_view`) |
| Schema ownership | Shared (`public.orders`, FK-joined to `customers`) | **Owned** -- `order_svc` schema (5 tables), Alembic |
| Serialization | DRF `OrderSerializer`, reused directly | `app/schemas.py` -- independent Pydantic v2 `OrderOut`, camelCase |
| Checkout orchestration | `order.services.place_order` -- synchronous, in-process, every collaborator called directly | `app/service.py::place_order` -- gRPC reserve outside tx, THREE writes (aggregate+view+outbox) in one local transaction |
| Customer validation | Live FK/join into `common.Customer` | **Net-new** -- owned, forward-filled `order_svc.customers`, no live join to anything |
| Read model | None -- `OrderSerializer` reads the write tables directly | **Net-new** -- `order_view`, projected same-transaction as every write |
| Saga reactions | `order.services.handle_*` -- Python `if` status guard inside Django's implicit transaction | `app/service.py::handle_*` -- atomic conditional `UPDATE` guard, same-transaction `order_view` upsert |
| Inventory collaborator | `order.inventory_client.RemoteInventoryClient` -- blocking `grpc.insecure_channel` | `app/inventory_client.py::AsyncInventoryClient` -- `grpc.aio`, non-blocking on FastAPI's event loop |
| Outcome notification | `common.OutboxEvent`, shared table | **Net-new** -- this service's OWN `order_svc.outbox` + `app/relay.py` |
| Exception mapping | Hand-adapt DRF's `api_exception_handler` output shape | `app/errors.py` -- native FastAPI exception handlers |
| Process model | `django.setup()` in `lifespan`, loading all 6 monolith apps' registries | No Django import anywhere |
| Build dependency | `uv` path dependency on `../00-monolith` | None -- `pyproject.toml` depends only on FastAPI/SQLAlchemy/asyncpg/Pydantic/aiokafka/Alembic/grpcio/protobuf |
| Concurrency | Every DB call threaded via `sync_to_async` | Native `async`/`await` all the way to `asyncpg`, `aiokafka`, and `grpc.aio` |

## Verification

- `uv run alembic upgrade head` against a throwaway `postgres:18.6-alpine`:
  creates the `order_svc` schema, all 5 tables (`customers`, `orders`,
  `order_items`, `order_view`, `outbox`), every index (`uq_customers_email`
  unique, `idx_order_items_order_id`, `idx_order_outbox_unpublished`
  partial), and seeds customers Ada (id=1) / Grace (id=2) -- confirmed via
  `psql`'s `\dn`/`\dt`/`\di` and a direct `SELECT`. Re-running is a correct
  no-op.
- `uv run pytest`: **27 passed** -- 24 unit tests (`tests/unit/
  test_orders_rest.py`: 8 REST contract tests incl. 202+Location, camelCase
  GET contract, 404/409/400 mappings, no-trailing-slash; `tests/unit/
  test_place_order.py`: 6 tests incl. the three-way one-transaction proof,
  reserve-outside-DB-tx + net-zero compensation on a mid-reservation
  failure, net-zero compensation on a post-reservation persistence failure,
  and the CQRS projection-disabled negative; `tests/unit/test_reactions.py`:
  10 tests covering all four reactions' status guards, idempotent
  redelivery, and Release-at-most-once-with-a-stable-key) + 3 Testcontainers
  integration tests (`tests/integration/test_order_lifecycle.py`: checkout
  produces `order.placed` exactly once through a real Kafka broker and a
  REAL networked `grpc.aio` inventory server; `payment.captured` then
  `shipment.dispatched` drive `order_view` through `AWAITING_SHIPMENT` to
  `CONFIRMED`, read-your-writes against the live projection; `payment.declined`
  releases inventory through the real gRPC server and reaches
  `PAYMENT_DECLINED`).
- `uv run ruff check .`: **All checks passed.**
- `grpcio==1.84.0`/`grpcio-tools==1.84.0`/`protobuf==7.36.2` all resolve
  prebuilt cp314 wheels under `uv sync` -- no C compiler needed.
