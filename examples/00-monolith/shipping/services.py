from common.exceptions import ResourceNotFound, ShippingFailed

from .models import Shipment

SHIP_FAIL_SENTINEL = "SHIP-FAIL"


def dispatch(order, address: str) -> Shipment:
    """Dispatch a shipment for a confirmed order.

    SMELL[ch.22]/[ch.26]: called directly and synchronously from
    order.services.place_order() inside the same ACID transaction.

    Deterministic failure injection: an address containing the sentinel
    "SHIP-FAIL" raises instead of writing a Shipment row, so the surrounding
    `transaction.atomic()` in place_order() rolls back the ENTIRE checkout --
    inventory reservation, order persistence, payment capture, all of it. Net
    effect: stock is left net-zero. SMELL[ch.22]'s whole point is that this
    rollback is free ONLY because Postgres gives it to us across all five
    contexts today; the moment any of them becomes its own service with its
    own database, this has to be rebuilt explicitly as a saga with
    compensating actions.
    """
    if SHIP_FAIL_SENTINEL in address.upper():
        raise ShippingFailed(f"Shipment dispatch failed for address '{address}'")
    return Shipment.objects.create(order=order, address=address, status=Shipment.Status.DISPATCHED)


def get_by_id(shipment_id: int) -> Shipment:
    try:
        return Shipment.objects.get(pk=shipment_id)
    except Shipment.DoesNotExist as exc:
        raise ResourceNotFound(f"No shipment with id {shipment_id}") from exc


def list_by_order_id(order_id):
    return Shipment.objects.filter(order_id=order_id).order_by("id")
