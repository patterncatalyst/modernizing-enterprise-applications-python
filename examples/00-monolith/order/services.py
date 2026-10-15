"""Checkout orchestration.

SMELL[ch.26]: place_order() is the "god service" -- the single orchestration
point for checkout. It reaches directly into inventory's, payment's,
shipping's, and notification's services/models instead of those contexts
being independently deployable collaborators reached over a stable contract.
Order is deliberately the HARDEST and LAST context to extract in a
decomposition roadmap, precisely because every other context's extraction has
to first remove one of this function's direct dependencies.
"""

import logging

from django.db import transaction

import inventory.services as inventory_services
import notification.services as notification_services
import payment.services as payment_services
import shipping.services as shipping_services
from common.exceptions import ResourceNotFound
from common.models import Customer

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


@transaction.atomic
def place_order(
    customer_id: int, items: list[dict], payment_method: str, shipping_address: str
) -> Order:
    """
    SMELL[ch.22]: everything below runs inside ONE in-process ACID
    transaction (the `@transaction.atomic` decorator above) spanning FIVE
    bounded contexts -- order, inventory, payment, shipping, notification. It
    "works" today because Postgres gives us atomic rollback for free across
    all five. The moment any one of these becomes its own service with its
    own database, this rollback-everything behavior disappears and has to be
    rebuilt explicitly as a saga with compensating actions -- the ACID -> ACD
    story.

    Flow: validate customer -> reserve stock per line (inventory, SMELL[ch.26]
    -- no anti-corruption layer at this seam) -> persist the order -> charge
    payment (a decline raises and rolls back everything written so far) ->
    dispatch shipment (a SHIP-FAIL address raises too, same rollback) -> send
    the confirmation notification SYNCHRONOUSLY inside this same transaction
    (notification, SMELL[ch.17]).
    """
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist as exc:
        raise ResourceNotFound(f"No customer with id {customer_id}") from exc

    order = Order.objects.create(
        customer=customer,
        shipping_address=shipping_address,
        status=Order.Status.PENDING,
    )

    total_cents = 0
    # SMELL[ch.26]: reaching directly into inventory's services/model layer
    # from the order context, with no anti-corruption layer at the seam --
    # the Python equivalent of the Java monolith's `OrderService` calling
    # straight into `InventoryService`/`InventoryItem`.
    for line in items:
        inventory_item = inventory_services.get_by_sku(line["sku"])
        # raises InsufficientStock -- no writes yet at this point.
        inventory_services.reserve(line["sku"], line["quantity"])
        OrderItem.objects.create(
            order=order,
            inventory_item=inventory_item,
            quantity=line["quantity"],
            unit_price_cents=inventory_item.price_cents,
        )
        total_cents += inventory_item.price_cents * line["quantity"]

    order.total_cents = total_cents
    order.save(update_fields=["total_cents"])

    # SMELL[ch.22]/[ch.26]: payment captured synchronously, in-process, inside
    # the same transaction as the inventory decrement above. A decline here
    # rolls back the inventory reservation too (see PaymentDeclined).
    payment_services.charge(order, order.total_cents, payment_method)
    order.confirm()
    order.save(update_fields=["status"])

    # SMELL[ch.26]: shipping dispatched synchronously from the order god
    # service rather than being triggered by an event the order context
    # emits. A SHIP-FAIL address raises here and unwinds this entire
    # `transaction.atomic()` -- the inventory reservation, the order row, and
    # the payment capture above, all of it (net-zero stock, SMELL[ch.22]).
    shipping_services.dispatch(order, order.shipping_address)

    # SMELL[ch.17]: notification sent synchronously inside the checkout
    # transaction instead of via a transactional outbox + async consumer. See
    # notification.services.send_order_confirmation() for the dual-write
    # hazard this also plants on purpose (SMELL[ch.17], smell #6).
    notification_services.send_order_confirmation(customer, order)

    return order


def get_by_id(order_id: int) -> Order:
    try:
        return Order.objects.prefetch_related("items__inventory_item").get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise ResourceNotFound(f"No order with id {order_id}") from exc


def list_all():
    return Order.objects.prefetch_related("items__inventory_item").all().order_by("id")
