"""Checkout orchestration.

SMELL[ch.26]: place_order() is the "god service" -- the single orchestration
point for checkout. It reaches directly into inventory's, payment's,
shipping's, and notification's services/models instead of those contexts
being independently deployable collaborators reached over a stable contract.
Order is deliberately the HARDEST and LAST context to extract in a
decomposition roadmap, precisely because every other context's extraction has
to first remove one of this function's direct dependencies.

r04/ch.19: `settings.INVENTORY_MODE` now dispatches place_order() between two
checkout strategies. `local` (the default, r01-r03 behavior, UNCHANGED) keeps
inventory reservation in-process, inside the SAME `transaction.atomic()` as
order persistence/payment/shipping/outbox -- SMELL[ch.22]'s "free rollback"
still applies. `grpc` is the cutover path: reservation happens OVER THE
NETWORK via order.inventory_client.RemoteInventoryClient, BEFORE and OUTSIDE
any local transaction.atomic(), because once a remote Reserve commits in the
inventory service's own database there is no longer one write-ahead log
spanning both writes for Postgres to unwind. That free rollback has to be
rebuilt explicitly: place_order() tracks every sku it reserves remotely this
checkout and issues a compensating remote Release for all of them the moment
anything later fails -- a later line's insufficient stock, or a
PaymentDeclined/ShippingFailed raised inside the (still-local) atomic block
that persists the order/payment/shipment/outbox rows.

r05/ch.23-25: `settings.PAYMENT_MODE` is now a SECOND, ORTHOGONAL axis on top
of `INVENTORY_MODE`. `synchronous` (the default) is every byte of the above,
UNCHANGED -- the zero-regression baseline this lane must not disturb.
`choreographed` cuts payment over to the standalone payment-service
(`examples/05-payment-service`): place_order() reserves inventory over gRPC
(the SAME `_reserve_lines_remote`/`_release_reserved` helpers `grpc`-mode
INVENTORY_MODE already uses) and persists the order as PENDING plus its
`order.placed` outbox event -- and stops there. No in-process charge, no
in-process shipping dispatch, no confirm. Payment-service reacts to that
`order.placed` event asynchronously and emits its own
`payment.captured`/`payment.declined` outcome event; this monolith reacts to
THAT, in turn, via `order.management.commands.order_saga_listener` driving
`handle_payment_captured`/`handle_payment_declined` below. See SMELLS.md
SMELL[ch.22] ("ACID -> ACD realized for payment").
"""

import logging
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction

import inventory.services as inventory_services
import payment.services as payment_services
import shipping.services as shipping_services
from common.exceptions import ResourceNotFound, ShippingFailed
from common.models import Customer, OutboxEvent

from . import inventory_client
from .models import Order, OrderItem

logger = logging.getLogger(__name__)


def place_order(
    customer_id: int, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """Validate the customer, then dispatch on `settings.PAYMENT_MODE` first
    (`synchronous`, the default, UNCHANGED baseline -- further dispatches on
    `settings.INVENTORY_MODE` exactly as r04 did; `choreographed`, r05's new
    async-checkout lane, ALWAYS reserves inventory over gRPC regardless of
    `INVENTORY_MODE`, since the whole point of choreography is that nothing
    downstream of the reservation runs in this request anymore). See
    `_place_order_local`/`_place_order_remote`/`_place_order_choreographed`
    for the three flows.
    """
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist as exc:
        raise ResourceNotFound(f"No customer with id {customer_id}") from exc

    if settings.PAYMENT_MODE == "choreographed":
        return _place_order_choreographed(customer, items, payment_method, shipping_address)
    if settings.INVENTORY_MODE == "grpc":
        return _place_order_remote(customer, items, payment_method, shipping_address)
    return _place_order_local(customer, items, payment_method, shipping_address)


def _place_order_local(
    customer: Customer, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """r01-r03, UNCHANGED: everything below runs inside ONE in-process ACID
    transaction (`transaction.atomic()`) spanning FIVE bounded contexts --
    order, inventory, payment, shipping, notification (the outbox write only
    -- see r03). It "works" today because Postgres gives us atomic rollback
    for free across all five. The moment any one of these becomes its own
    service with its own database, this rollback-everything behavior
    disappears and has to be rebuilt explicitly as a saga with compensating
    actions -- see `_place_order_remote` for that cure, inventory-first.
    """
    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            shipping_address=shipping_address,
            status=Order.Status.PENDING,
        )

        total_cents = 0
        # SMELL[ch.26]: reaching directly into inventory's services/model
        # layer from the order context, with no anti-corruption layer at the
        # seam -- the Python equivalent of the Java monolith's
        # `OrderService` calling straight into `InventoryService`.
        for line in items:
            inventory_item = inventory_services.get_by_sku(line["sku"])
            # raises InsufficientStock -- no writes yet at this point.
            inventory_services.reserve(line["sku"], line["quantity"])
            OrderItem.objects.create(
                order=order,
                sku=inventory_item.sku,
                item_name=inventory_item.name,
                quantity=line["quantity"],
                unit_price_cents=inventory_item.price_cents,
            )
            total_cents += inventory_item.price_cents * line["quantity"]

        order.total_cents = total_cents
        order.save(update_fields=["total_cents"])

        # SMELL[ch.22]/[ch.26]: payment captured synchronously, in-process,
        # inside the same transaction as the inventory decrement above. A
        # decline here rolls back the inventory reservation too.
        payment_services.charge(order, order.total_cents, payment_method)
        order.confirm()
        order.save(update_fields=["status"])

        # SMELL[ch.26]: shipping dispatched synchronously from the order god
        # service. A SHIP-FAIL address raises here and unwinds this entire
        # transaction -- the inventory reservation, the order row, and the
        # payment capture above, all of it (net-zero stock, SMELL[ch.22]).
        shipping_services.dispatch(order, order.shipping_address)

        _write_order_placed_outbox_event(customer, order)

    return order


def _place_order_remote(
    customer: Customer, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """r04/ch.19 cutover path: reserve every line over gRPC FIRST, outside
    any local `transaction.atomic()` (a remote Reserve is not part of this
    process's Postgres transaction and cannot be rolled back by it). Only
    once every line is reserved does the order/payment/shipping/outbox
    sequence run inside its own `transaction.atomic()`, exactly as `local`
    mode does for those four contexts. Any failure from that point on --
    PaymentDeclined, ShippingFailed, or anything else -- is caught OUTSIDE
    the atomic block (which has already rolled itself back by the time this
    function's `except` sees it) and triggers a compensating remote Release
    for every sku reserved this checkout, restoring the net-zero stock
    behavior the single shared transaction used to give for free.
    """
    client = inventory_client.RemoteInventoryClient()
    try:
        line_snapshots, reserved = _reserve_lines_remote(client, items)

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=shipping_address,
                    status=Order.Status.PENDING,
                )

                total_cents = 0
                for snapshot in line_snapshots:
                    OrderItem.objects.create(
                        order=order,
                        sku=snapshot["sku"],
                        item_name=snapshot["item_name"],
                        quantity=snapshot["quantity"],
                        unit_price_cents=snapshot["unit_price_cents"],
                    )
                    total_cents += snapshot["unit_price_cents"] * snapshot["quantity"]

                order.total_cents = total_cents
                order.save(update_fields=["total_cents"])

                payment_services.charge(order, order.total_cents, payment_method)
                order.confirm()
                order.save(update_fields=["status"])

                shipping_services.dispatch(order, order.shipping_address)

                _write_order_placed_outbox_event(customer, order)
        except Exception:
            # Net-zero: every sku reserved remotely this checkout gets a
            # compensating Release, same as _reserve_lines_remote's own
            # mid-loop compensation below -- just triggered by a failure
            # further downstream (payment/shipping/outbox) instead of a
            # later line's insufficient stock.
            _release_reserved(client, reserved)
            raise

        return order
    finally:
        client.close()


def _place_order_choreographed(
    customer: Customer, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """r05/ch.23-25 -- the async-checkout cutover. Reserves every line over
    gRPC exactly like `_place_order_remote` (same `_reserve_lines_remote`/
    `_release_reserved` helpers, same net-zero-on-failure compensation story
    for a reservation/persistence failure BEFORE the `order.placed` event is
    committed), then persists the order/items/outbox event as ONE local
    `transaction.atomic()` -- but stops there. Deliberately NOT charging
    payment and NOT dispatching shipping: the order comes back PENDING, and
    `order.views.OrderListCreateView.post` answers `202 Accepted` for it
    instead of `201 Created`. The outbox event now carries `paymentMethod`
    (optional on the wire -- see `examples/05-payment-service/EVENTS.md`) so
    payment-service's own `order.placed` consumer knows what to charge.
    Everything from here on (capture/decline, then confirm/ship or
    decline/release) happens OUTSIDE this function and this request, reacted
    to by `handle_payment_captured`/`handle_payment_declined` below once
    payment-service's outcome event arrives.
    """
    client = inventory_client.RemoteInventoryClient()
    try:
        line_snapshots, reserved = _reserve_lines_remote(client, items)

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=shipping_address,
                    status=Order.Status.PENDING,
                )

                total_cents = 0
                for snapshot in line_snapshots:
                    OrderItem.objects.create(
                        order=order,
                        sku=snapshot["sku"],
                        item_name=snapshot["item_name"],
                        quantity=snapshot["quantity"],
                        unit_price_cents=snapshot["unit_price_cents"],
                    )
                    total_cents += snapshot["unit_price_cents"] * snapshot["quantity"]

                order.total_cents = total_cents
                order.save(update_fields=["total_cents"])

                _write_order_placed_outbox_event(customer, order, payment_method=payment_method)
        except Exception:
            # Same net-zero compensation as _place_order_remote's: nothing
            # downstream of the reservation has run yet (no payment, no
            # shipping to unwind), so a reserve/persist failure before the
            # order.placed event commits only ever has inventory to release.
            _release_reserved(client, reserved)
            raise

        return order
    finally:
        client.close()


def handle_payment_captured(event: dict) -> Order | None:
    """Saga-listener reaction (r05/ch.23-25) to a `payment.captured` event
    published by payment-service's own outbox relay (see
    `examples/05-payment-service/EVENTS.md`) -- driven by
    `order.management.commands.order_saga_listener`, never called directly
    from the checkout request. Dispatches shipping IN-PROCESS (shipping
    extraction is r06's job, not this lane's) and confirms the order on
    success. On a `ShippingFailed` sentinel, issues a compensating gRPC
    Release for every line this order reserved at checkout and marks the
    order `SHIPPING_FAILED` instead.

    Idempotent via a STATUS-TRANSITION GUARD: an order that has already left
    `PENDING` (because an earlier delivery of this exact event, or of
    `payment.declined` for the same order, already resolved it) is a no-op --
    no second shipping dispatch, no second Release, no re-confirm. Kafka's
    at-least-once delivery (same discipline as `outbox_relay.py`/
    `order_placed_consumer.py`) makes this guard load-bearing, not
    decorative.

    KNOWN DEFERRAL (documented, not a bug): a payment that captured and then
    hits `ShippingFailed` here is NOT refunded -- payment-service exposes no
    Refund RPC/event yet. That is r06's orchestrated saga's job, once
    shipping itself is extracted; for now `SHIPPING_FAILED` leaves a captured
    payment on the books.
    """
    order = _get_order_for_saga_event(event, event_type="payment.captured")
    if order is None or not _is_pending(order, event_type="payment.captured"):
        return order

    try:
        shipping_services.dispatch(order, order.shipping_address)
    except ShippingFailed:
        _release_order_lines(order)
        order.ship_fail()
        order.save(update_fields=["status"])
        logger.info(
            "payment.captured order_id=%s shipping dispatch failed -> SHIPPING_FAILED",
            order.id,
        )
        return order

    order.confirm()
    order.save(update_fields=["status"])
    logger.info("payment.captured order_id=%s -> CONFIRMED", order.id)
    return order


def handle_payment_declined(event: dict) -> Order | None:
    """Saga-listener reaction (r05/ch.23-25) to a `payment.declined` event
    published by payment-service's own outbox relay. Recovers the lines this
    order reserved at checkout from the persisted `OrderItem` snapshot rows
    (sku, quantity -- there is no in-memory reservation list to reuse here,
    unlike the synchronous checkout request that did the original Reserve),
    issues a compensating gRPC Release for every one of them, and marks the
    order `PAYMENT_DECLINED`.

    Same status-transition-guard idempotency as `handle_payment_captured`:
    an order that already left `PENDING` is a no-op, so a redelivered
    `payment.declined` never double-releases inventory.
    """
    order = _get_order_for_saga_event(event, event_type="payment.declined")
    if order is None or not _is_pending(order, event_type="payment.declined"):
        return order

    _release_order_lines(order)
    order.decline_payment()
    order.save(update_fields=["status"])
    logger.info("payment.declined order_id=%s -> PAYMENT_DECLINED", order.id)
    return order


def _get_order_for_saga_event(event: dict, event_type: str) -> Order | None:
    order_id = event.get("orderId")
    try:
        return Order.objects.prefetch_related("items").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("%s for unknown orderId=%s -- ignoring", event_type, order_id)
        return None


def _is_pending(order: Order, event_type: str) -> bool:
    """The saga-listener idempotency guard: an order that has already left
    PENDING resolved on an earlier delivery of this (or the other outcome's)
    event -- redelivery is a no-op, by design, not an error."""
    if order.status != Order.Status.PENDING:
        logger.info(
            "%s redelivered for order_id=%s status=%s -- no-op (status guard)",
            event_type,
            order.id,
            order.status,
        )
        return False
    return True


def _release_order_lines(order: Order) -> None:
    """Compensating gRPC Release for every line THIS order reserved at
    checkout, recovered from the persisted `OrderItem` snapshot rows (sku,
    quantity) -- the saga listener runs later, off a Kafka event, in a
    different call stack than the checkout request that did the original
    Reserve, so there is no in-memory `reserved` list like
    `_place_order_remote`'s to reuse.

    `idempotency_key` is a STABLE per-(order, line) key --
    `f"{order_id}:{sku}:release"` -- so that even if the status guard above
    were ever bypassed (or inventory-service's Release is retried for any
    other reason), a repeated Release for the same line is a no-op against
    inventory-service's own idempotent handling of this field, never a
    double credit."""
    client = inventory_client.RemoteInventoryClient()
    try:
        for item in order.items.all():
            idempotency_key = f"{order.id}:{item.sku}:release"
            try:
                client.release(item.sku, item.quantity, idempotency_key=idempotency_key)
            except Exception:
                logger.exception(
                    "compensation FAILED for order_id=%s sku=%s qty=%d -- stock NOT restored",
                    order.id,
                    item.sku,
                    item.quantity,
                )
    finally:
        client.close()


def _reserve_lines_remote(
    client: inventory_client.RemoteInventoryClient, items: list[dict]
) -> tuple[list[dict], list[tuple[str, int]]]:
    """Reserve every checkout line over gRPC, in order. The moment any line
    fails -- insufficient/unknown sku (`InsufficientStock`) or the inventory
    service being unreachable (`InventoryServiceUnavailable`) -- every sku
    ALREADY reserved earlier in THIS call is compensated with a remote
    Release before the exception propagates. Returns the denormalized line
    snapshots `OrderItem` needs plus the full (sku, quantity) reservation
    list, so the CALLER can compensate again if a later step (payment,
    shipping, the outbox write) fails after every line reserved cleanly.
    """
    line_snapshots: list[dict] = []
    reserved: list[tuple[str, int]] = []
    for line in items:
        sku, quantity = line["sku"], line["quantity"]
        try:
            client.reserve(sku, quantity)
            # Only recorded once the remote decrement has actually
            # committed -- an InsufficientStock/InventoryServiceUnavailable
            # raised by reserve() itself means nothing to compensate for
            # THIS line.
            reserved.append((sku, quantity))
            stock = client.get_stock(sku)
        except Exception:
            _release_reserved(client, reserved)
            raise
        line_snapshots.append(
            {
                "sku": stock.sku,
                "item_name": stock.name,
                "unit_price_cents": stock.unit_price_cents,
                "quantity": quantity,
            }
        )
    return line_snapshots, reserved


def _release_reserved(
    client: inventory_client.RemoteInventoryClient, reserved: list[tuple[str, int]]
) -> None:
    """Best-effort compensating Release for every sku reserved so far this
    checkout -- logged loudly on failure rather than silently swallowed; a
    Release failure does NOT replace the original checkout failure being
    propagated to the caller (no saga ledger/retry at this stage -- see
    ch.19/23/25)."""
    for sku, quantity in reserved:
        try:
            client.release(sku, quantity)
        except Exception:
            logger.exception(
                "compensation FAILED for sku=%s qty=%d -- stock NOT restored", sku, quantity
            )


def _write_order_placed_outbox_event(
    customer: Customer, order: Order, payment_method: str | None = None
) -> None:
    """SMELL[ch.17] CURED (r03, smells #5/#6): the outbox write below is the
    ONLY notification-related side effect of checkout -- no synchronous send,
    no dual write to a second system. The frozen `order.placed` contract
    (camelCase, see docs/events.md or the r03 plan) carries everything
    notification's consumer needs to repopulate its read model without this
    context reaching into notification's services/models directly. A
    separate process (`common.management.commands.outbox_relay`) publishes
    unpublished rows to Kafka at-least-once; `notification`'s own consumer
    (`notification.management.commands.order_placed_consumer`) repopulates
    the `Notification` read model from that event.

    r05/ch.23-25: `payment_method` is a net-new, OPTIONAL field on this same
    event -- `_place_order_local`/`_place_order_remote` (synchronous mode)
    never pass it, so their outbox payload is BYTE-FOR-BYTE unchanged from
    r04 (zero-regression baseline). `_place_order_choreographed` DOES pass
    it, so payment-service's own `order.placed` consumer
    (`examples/05-payment-service/app/schemas.py::OrderPlacedEvent`) knows
    what to charge. `confirmation_message` likewise reflects the order's
    ACTUAL status at write time -- CONFIRMED for the synchronous flows (this
    outbox row is written only after `order.confirm()`), PENDING for the
    choreographed flow (this row is written before any payment decision
    exists) -- rather than always claiming "confirmed"."""
    confirmed = order.status == Order.Status.CONFIRMED
    verb = "confirmed" if confirmed else "placed"
    confirmation_message = f"Order #{order.id} {verb}, total ${order.total_cents / 100:.2f}"
    payload = {
        "orderId": order.id,
        "customerId": customer.id,
        "customerEmail": customer.email,
        "totalCents": order.total_cents,
        "confirmationMessage": confirmation_message,
        "placedAt": datetime.now(tz=UTC).isoformat(),
    }
    if payment_method is not None:
        payload["paymentMethod"] = payment_method
    OutboxEvent.objects.create(
        aggregate_type="order",
        aggregate_id=str(order.id),
        event_type="order.placed",
        payload=payload,
    )


def get_by_id(order_id: int) -> Order:
    try:
        return Order.objects.prefetch_related("items").get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise ResourceNotFound(f"No order with id {order_id}") from exc


def list_all():
    return Order.objects.prefetch_related("items").all().order_by("id")
