from django.db import models
from django.db.models import Q
from django.utils import timezone


class Notification(models.Model):
    """A record of a notification sent to a customer.

    SMELL[ch.18]: joins directly to both `customers` and `orders` in the
    shared schema.

    r03: repopulated by `notification.services.record_order_placed()`, the
    `order.placed` consumer's handler, rather than written synchronously
    in-process by checkout (see SMELLS.md #5/#6, cured). The partial unique
    constraint on `order` is the idempotency backstop for that at-least-once
    consumer: a redelivered `order.placed` event (e.g. a relay crash between
    publish and stamping `published_at`, or a consumer re-read after a crash
    before its offset commit) must not create a second Notification for the
    same order."""

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
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                name="uniq_notification_per_order",
                condition=Q(order__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"Notification#{self.pk} ({self.channel})"
