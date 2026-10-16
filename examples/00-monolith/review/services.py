from common.exceptions import ResourceNotFound
from common.models import Customer
from inventory.models import InventoryItem

from .models import Review


def create_review(customer_id: int, sku: str, rating: int, comment: str | None) -> Review:
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist as exc:
        raise ResourceNotFound(f"No customer with id {customer_id}") from exc
    try:
        item = InventoryItem.objects.get(sku=sku)
    except InventoryItem.DoesNotExist as exc:
        raise ResourceNotFound(f"No inventory item with sku {sku}") from exc
    return Review.objects.create(
        customer=customer, inventory_item=item, rating=rating, comment=comment or ""
    )


def get_by_id(review_id: int) -> Review:
    try:
        return Review.objects.get(pk=review_id)
    except Review.DoesNotExist as exc:
        raise ResourceNotFound(f"No review with id {review_id}") from exc


def list_all():
    return Review.objects.all().order_by("id")


def list_by_sku(sku: str):
    return Review.objects.filter(inventory_item__sku=sku).order_by("id")
