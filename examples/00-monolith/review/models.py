from django.db import models
from django.utils import timezone


class Review(models.Model):
    """SMELL[ch.18]: joins directly to `customers` and `inventory_items` in
    the shared schema.

    Note what review does NOT depend on: order, payment, shipping, or
    notification. It is genuinely the least-coupled context in this monolith
    (REST-only, no synchronous collaborator)."""

    customer = models.ForeignKey(
        "common.Customer",
        on_delete=models.PROTECT,
        related_name="reviews",
        db_column="customer_id",
    )
    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.PROTECT,
        related_name="reviews",
        db_column="inventory_item_id",
    )
    rating = models.IntegerField()
    comment = models.CharField(max_length=2048, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "reviews"

    def __str__(self) -> str:
        return f"Review#{self.pk} ({self.rating}/5)"
