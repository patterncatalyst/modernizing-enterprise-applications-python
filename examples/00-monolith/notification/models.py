from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """A record of a notification sent to a customer.

    SMELL[ch.18]: joins directly to both `customers` and `orders` in the
    shared schema."""

    customer = models.ForeignKey(
        "common.Customer",
        on_delete=models.PROTECT,
        related_name="notifications",
        db_column="customer_id",
    )
    order = models.ForeignKey(
        "order.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notifications",
        db_column="order_id",
    )
    channel = models.CharField(max_length=32)
    message = models.CharField(max_length=1024)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications"

    def __str__(self) -> str:
        return f"Notification#{self.pk} ({self.channel})"
