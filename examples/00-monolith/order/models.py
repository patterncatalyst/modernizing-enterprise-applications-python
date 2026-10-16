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
        # r05/ch.23-25: the choreographed checkout's saga-listener reaction
        # (order.services.handle_payment_captured) to a ShippingFailed
        # sentinel raised AFTER payment already captured -- see that
        # function's docstring for the documented refund deferral. `status`
        # is a plain string column (no enum type in Postgres), so this new
        # value needs no migration.
        SHIPPING_FAILED = "SHIPPING_FAILED"

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

    def ship_fail(self) -> None:
        self.status = self.Status.SHIPPING_FAILED


class OrderItem(models.Model):
    """r04/ch.19: SMELL[ch.18]'s cross-context FK onto
    inventory.InventoryItem is CURED here -- `sku`/`item_name` are now a
    denormalized SNAPSHOT captured once at checkout time (from
    inventory.services.reserve()'s row in `local` mode, or the gRPC
    GetStock reply in `grpc` mode; see order.services.place_order() and
    order.inventory_client), a plain soft string reference with no database
    FK and no cross-app join. Because the price is captured at order time, a
    later price change in inventory never retroactively rewrites a
    historical order line -- the correct semantics for a read model
    regardless of which mode wrote it. See order/migrations/0002_*.py for the
    backfill-then-drop migration that cut the live FK."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", db_column="order_id"
    )
    sku = models.CharField(max_length=64)
    item_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()

    class Meta:
        db_table = "order_items"

    def __str__(self) -> str:
        return f"OrderItem#{self.pk} (order={self.order_id})"
