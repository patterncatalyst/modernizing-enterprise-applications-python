from django.db import models
from django.utils import timezone


class InventoryItem(models.Model):
    """Stock levels for a product. order, review, and (indirectly)
    payment/shipping all reach across context boundaries to this table --
    see SMELL[ch.18] on order.OrderItem and review.Review."""

    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    price_cents = models.BigIntegerField()
    quantity_on_hand = models.IntegerField()
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "inventory_items"

    def __str__(self) -> str:
        return self.sku
