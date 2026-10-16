from django.utils import timezone

from common.exceptions import InsufficientStock, ResourceNotFound

from .models import InventoryItem


def list_all():
    return InventoryItem.objects.all().order_by("sku")


def get_by_sku(sku: str) -> InventoryItem:
    try:
        return InventoryItem.objects.get(sku=sku)
    except InventoryItem.DoesNotExist as exc:
        raise ResourceNotFound(f"No inventory item with sku {sku}") from exc


def find_with_lock_by_sku(sku: str) -> InventoryItem:
    """Row-level lock, the Python/Postgres equivalent of the Java monolith's
    `InventoryRepository#findWithLockBySku` (a `SELECT ... FOR UPDATE`). Must
    be called inside an open `transaction.atomic()` block -- see
    order.services.place_order(), SMELL[ch.22]."""
    try:
        return InventoryItem.objects.select_for_update().get(sku=sku)
    except InventoryItem.DoesNotExist as exc:
        raise ResourceNotFound(f"No inventory item with sku {sku}") from exc


def reserve(sku: str, quantity: int) -> InventoryItem:
    """Reserves (decrements) stock for one checkout line.

    SMELL[ch.26]: called directly from order.services.place_order() against
    this app's own model/queryset, with no translation layer (anti-corruption
    layer) and no network boundary in between -- a cross-context in-process
    call, not a call to an independently deployable service over a stable
    contract.
    """
    item = find_with_lock_by_sku(sku)
    if item.quantity_on_hand < quantity:
        raise InsufficientStock(
            f"Requested {quantity} of {sku} but only {item.quantity_on_hand} on hand"
        )
    item.quantity_on_hand -= quantity
    item.updated_at = timezone.now()
    item.save(update_fields=["quantity_on_hand", "updated_at"])
    return item
