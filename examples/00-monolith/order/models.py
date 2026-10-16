from django.db import models
from django.utils import timezone


class Order(models.Model):
    """The core aggregate; it would be extracted last in a decomposition
    roadmap because order.services.place_order() reaches directly into every
    other context (SMELL[ch.26])."""

    class Status(models.TextChoices):
        PENDING = "PENDING"
        CONFIRMED = "CONFIRMED"
        PAYMENT_DECLINED = "PAYMENT_DECLINED"

    # SMELL[ch.18]: customer_id is a direct FK/join into the shared
    # `customers` table rather than an owned/replicated copy.
    customer = models.ForeignKey(
        "common.Customer",
        on_delete=models.PROTECT,
        related_name="orders",
        db_column="customer_id",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    total_cents = models.BigIntegerField(default=0)
    shipping_address = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "orders"

    def __str__(self) -> str:
        return f"Order#{self.pk}"

    def confirm(self) -> None:
        self.status = self.Status.CONFIRMED

    def decline_payment(self) -> None:
        self.status = self.Status.PAYMENT_DECLINED


class OrderItem(models.Model):
    """SMELL[ch.18]: OrderItem holds a direct FK/join onto
    inventory.InventoryItem -- an order-context table referencing an
    inventory-context table in the one shared schema. Once inventory owns its
    own database, this join would be replaced by a denormalized copy of the
    fields the order context actually needs (sku, name, price-at-time-of-order),
    kept current via CDC."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", db_column="order_id"
    )
    # SMELL[ch.18]: cross-context FK, see class docstring above.
    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.PROTECT,
        related_name="order_items",
        db_column="inventory_item_id",
    )
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()

    class Meta:
        db_table = "order_items"

    def __str__(self) -> str:
        return f"OrderItem#{self.pk} (order={self.order_id})"
