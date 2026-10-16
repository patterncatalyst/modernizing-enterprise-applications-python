# The Seven Deliberate Smells

This monolith is the "before" picture for the whole book, mirroring the intent of
the Java sibling's `examples/00-monolith/SMELLS.md` at its *original*, pre-extraction
state: all six bounded contexts live, nothing extracted. r01 planted six smells; r02
adds a seventh (#7 below), realizing the Java contract's review/auth coupling that r01
had left unenforced. r03 CURES #5 and #6 (see the "Status" column) -- not by extracting
notification into its own service yet, but by giving the still-in-process monolith a
transactional outbox (`common.models.OutboxEvent` + `common.management.commands
.outbox_relay`) and making it "become a consumer of its own event"
(`notification.management.commands.order_placed_consumer`, driving
`notification.services.record_order_placed`). Each smell is tagged in-code with a
`# SMELL[ch.NN]:` comment (grep for `SMELL\[ch\.` to find every occurrence) and mapped
below to the chapter(s) that later cures it.

| # | Smell | Where it's planted | Curing chapter(s) | Status |
|---|---|---|---|---|
| 1 | **God checkout service** -- `order/services.py::place_order()` is the single orchestration point for checkout. It reaches directly into `inventory`, `payment`, `shipping`, and `notification`'s services/models instead of those contexts being independently deployable collaborators reached over a stable contract. | `order/services.py` | ch.26 (order extraction -- deliberately the hardest/last, because every other context's extraction removes one of this function's direct dependencies first) | open |
| 2 | **One in-process ACID transaction spanning six contexts** -- the entire `place_order()` body runs inside a single `@transaction.atomic()`, so a failure anywhere (over-order, a declined payment, a failed shipment dispatch) rolls back everything written so far, everywhere. That rollback is free today only because Postgres gives it to us across all six contexts in one shared schema; once any one of them becomes its own service with its own database, it has to be rebuilt explicitly as a saga with compensating actions (ACID -> ACD). | `order/services.py::place_order` | ch.22 (ACID -> ACD), ch.23/24 (choreographed/orchestrated sagas) | open for `PAYMENT_MODE=synchronous` (default, unchanged). **ACID -> ACD realized for payment (r05)** under `PAYMENT_MODE=choreographed`: `_place_order_choreographed`'s `transaction.atomic()` spans only order persistence + the `order.placed` outbox row -- payment capture/decline now happens in payment-service's own transaction (`examples/05-payment-service`), reacted to asynchronously by `order.management.commands.order_saga_listener` (`order/services.py::handle_payment_captured`/`handle_payment_declined`) with an explicit compensating gRPC Release (stable per-line idempotency key) instead of a free rollback. Shipping is still dispatched IN-PROCESS from that saga listener (shipping extraction is r06) -- the cure does not yet reach shipping, and a captured-then-`ShippingFailed` order is deliberately NOT refunded yet (documented deferral in `handle_payment_captured`'s docstring; r06's orchestrated saga's job). |
| 3 | **Shared single schema/DB for all six apps** -- one Postgres schema, one set of Django migrations, all six bounded contexts migrate and deploy together. | `config/settings.py` (INSTALLED_APPS/DATABASES commentary); every model's `db_table` | ch.18 (shared data -> owned data) | open |
| 4 | **Cross-context foreign keys** -- `order.Order.customer`, `order.OrderItem.inventory_item`, `payment.Payment.order`, `shipping.Shipment.order`, `notification.Notification.customer`/`.order`, `review.Review.customer`/`.inventory_item` are all direct FKs crossing bounded-context boundaries in the one shared schema. | every cross-app `ForeignKey` field (see each app's `models.py`) | ch.18 (shared data -> owned data), ch.19 (CDC backfill + decommission) | open |
| 5 | **Synchronous in-process notification send inside the checkout transaction** -- `notification/services.py::send_order_confirmation()` was called synchronously from `place_order()`, inside the same `transaction.atomic()` as the rest of checkout. Checkout latency was coupled to however long "sending" a notification took, and a failure there would have rolled back the whole order. | `order/services.py::place_order` (now writes an `OutboxEvent` instead) | ch.17 (notification extraction: transactional outbox + async event-driven consumer) | **CURED (r03)** -- `place_order()` writes an `order.placed` `OutboxEvent` row in the same `@transaction.atomic()` and returns; nothing notification-shaped runs synchronously in the checkout path anymore. |
| 6 | **Dual-write hazard** -- inside the old `send_order_confirmation()`, the `Notification` DB row (atomic with checkout) and the call to `_dispatch_via_external_provider()` (a stand-in for a real email/SMS provider call) were two independent writes to two independent systems with no shared transaction. A crash between the DB commit and the provider call would have lost the notification silently; a naive retry could have duplicated it. This was the textbook "dual write" problem. | `notification/services.py::record_order_placed` (replaces `send_order_confirmation`/`_dispatch_via_external_provider`) | ch.17 (the transactional outbox cures it: the outbox write becomes the only thing inside the local transaction, and a relay publishes to the real provider at-least-once, independently) | **CURED (r03)** -- `common.management.commands.outbox_relay` is the only thing that reads the outbox and publishes to Kafka (`order.placed`), at-least-once, stamping `published_at` after a successful `send_and_wait()`; `notification.management.commands.order_placed_consumer` consumes that same topic and calls `notification.services.record_order_placed()`, which is idempotent (check-then-create, backstopped by `Notification`'s partial unique constraint on `order`). |
| 7 | **Review tangled into shared security despite being genuinely independent** -- *(added r02, Option B)* `review/models.py` is explicit that review has no runtime dependency on order/inventory/payment/shipping/notification (REST-only, no synchronous collaborator) -- yet `POST /api/reviews` is gated by Basic auth against THIS monolith's shared `django.contrib.auth` `auth_user` table (`common/management/commands/seed.py` seeds the fixed `reviewer` demo user), the same shared-security surface every other context would reach for if it needed auth. `GET /api/reviews`/`GET /api/reviews/{id}` stay open; only the write is gated, per-view. This realizes the Java sibling's original contract (401 unauthenticated / 201 authenticated writes), left unenforced at r01. | `review/views.py::ReviewListCreateView` | ch.15 (review extraction -- the walking skeleton; review gets its OWN, independent auth configuration in `examples/02-review-service`, no longer borrowing this module's `auth_user` table) | open |

## Finding them

```sh
grep -rn 'SMELL\[ch\.' examples/00-monolith
```

## Deterministic failure injection

Four behaviors prove smells #1/#2 are real, not theoretical, and are exercised by
`tests/test_checkout.py` and the Newman collection:

- Happy path checkout -> `201 Created`, `Location: /api/orders/{id}`, `status: CONFIRMED`.
- A checkout line that exceeds `quantityOnHand` -> `409 Conflict`, `error: OUT_OF_STOCK` (raised
  *before* any writes -- see `inventory/services.py::reserve`).
- A `paymentMethod` containing the sentinel `DECLINE` (case-insensitive) -> `402 Payment Required`,
  `error: PAYMENT_DECLINED`, and the inventory reservation made earlier in the same transaction is
  rolled back (net-zero stock).
- A `shippingAddress` containing the sentinel `SHIP-FAIL` (case-insensitive) -> `422 Unprocessable
  Entity`, `error: SHIPPING_FAILED`, and the ENTIRE checkout rolls back -- inventory reservation,
  order row, and payment capture, all of it (net-zero stock). This is smell #2's whole point: today
  this rollback is free.

Since r03, the `OutboxEvent` write is part of that same free rollback: the happy path leaves
exactly one `order.placed` outbox row; a `DECLINE`/`SHIP-FAIL` checkout leaves zero (see
`tests/test_checkout.py`).
