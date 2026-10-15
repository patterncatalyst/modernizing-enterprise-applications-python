from django.db import models
from django.utils import timezone


class Shipment(models.Model):
    """SMELL[ch.18]: order_id is a direct FK/join into the order context's
    table."""

    class Status(models.TextChoices):
        DISPATCHED = "DISPATCHED"

    order = models.ForeignKey(
        "order.Order",
        on_delete=models.PROTECT,
        related_name="shipments",
        db_column="order_id",
    )
    address = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DISPATCHED)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "shipments"

    def __str__(self) -> str:
        return f"Shipment#{self.pk}"
