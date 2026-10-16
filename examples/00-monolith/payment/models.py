from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """SMELL[ch.18]: order_id is a direct FK/join into the order context's
    table in the same shared schema, not an owned copy or an event-carried
    reference."""

    class Status(models.TextChoices):
        CAPTURED = "CAPTURED"
        DECLINED = "DECLINED"

    order = models.ForeignKey(
        "order.Order",
        on_delete=models.PROTECT,
        related_name="payments",
        db_column="order_id",
    )
    amount_cents = models.BigIntegerField()
    method = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=Status.choices)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "payments"

    def __str__(self) -> str:
        return f"Payment#{self.pk} ({self.status})"
