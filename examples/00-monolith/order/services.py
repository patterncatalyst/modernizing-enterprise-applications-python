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
"""

import logging
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction

import inventory.services as inventory_services
import payment.services as payment_services
import shipping.services as shipping_services
from common.exceptions import ResourceNotFound
from common.models import Customer, OutboxEvent

from . import inventory_client
from .models import Order, OrderItem

logger = logging.getLogger(__name__)


def place_order(
    customer_id: int, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """Validate the customer, then dispatch to the `local` or `grpc`
    inventory-reservation strategy selected by `settings.INVENTORY_MODE`. See
    `_place_order_local`/`_place_order_remote` for the two flows; both
    produce the SAME external contract (201 CONFIRMED, 409 OUT_OF_STOCK, 402
    PAYMENT_DECLINED, 422 SHIPPING_FAILED) and the SAME `order.placed` outbox
    event, written by `_write_order_placed_outbox_event` either way.
    """
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist as exc:
        raise ResourceNotFound(f"No customer with id {customer_id}") from exc

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


def _write_order_placed_outbox_event(customer: Customer, order: Order) -> None:
    """SMELL[ch.17] CURED (r03, smells #5/#6): the outbox write below is the
    ONLY notification-related side effect of checkout -- no synchronous send,
    no dual write to a second system. The frozen `order.placed` contract
    (camelCase, see docs/events.md or the r03 plan) carries everything
    notification's consumer needs to repopulate its read model without this
    context reaching into notification's services/models directly. A
    separate process (`common.management.commands.outbox_relay`) publishes
    unpublished rows to Kafka at-least-once; `notification`'s own consumer
    (`notification.management.commands.order_placed_consumer`) repopulates
    the `Notification` read model from that event."""
    confirmation_message = f"Order #{order.id} confirmed, total ${order.total_cents / 100:.2f}"
    OutboxEvent.objects.create(
        aggregate_type="order",
        aggregate_id=str(order.id),
        event_type="order.placed",
        payload={
            "orderId": order.id,
            "customerId": customer.id,
            "customerEmail": customer.email,
            "totalCents": order.total_cents,
            "confirmationMessage": confirmation_message,
            "placedAt": datetime.now(tz=UTC).isoformat(),
        },
    )


def get_by_id(order_id: int) -> Order:
    try:
        return Order.objects.prefetch_related("items").get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise ResourceNotFound(f"No order with id {order_id}") from exc


def list_all():
    return Order.objects.prefetch_related("items").all().order_by("id")
