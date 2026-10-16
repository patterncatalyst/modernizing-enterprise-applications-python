from django.db import models
from django.db.models import Q
from django.utils import timezone


class Customer(models.Model):
    """Shared-kernel entity. Not one of the six bounded contexts itself, but
    referenced by order, review, and notification via direct cross-app
    foreign keys.

    SMELL[ch.18]: Customer lives in the one shared Postgres schema and is
    joined directly (FK) from order/review/notification tables. In a
    decomposed system each context would own (or replicate via CDC/ACL) only
    the customer fields it needs -- see ch.18 (shared data -> owned data) and
    ch.19 (CDC backfill).
    """

    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "customers"

    def __str__(self) -> str:
        return self.name


class OutboxEvent(models.Model):
    """The transactional outbox (ch.17 cure for SMELL #5/#6, see SMELLS.md):
    the ONLY notification-related side effect written inside
    `order.services.place_order()`'s `@transaction.atomic()`. A separate
    process (`common.management.commands.outbox_relay`) polls the
    unpublished rows oldest-first and publishes them to Kafka
    at-least-once, stamping `published_at` on success -- decoupling both
    checkout latency and failure domain from the notification path, and
    curing the dual-write hazard by making this row the only thing inside
    the local transaction.

    Python sibling of the Java monolith's `V3__outbox.sql` (same shape:
    `aggregate_type`/`aggregate_id`/`event_type`/`payload`/`created_at`/
    `published_at`, same partial index on unpublished rows)."""

    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "outbox"
        indexes = [
            models.Index(
                fields=["created_at"],
                name="idx_outbox_unpublished",
                condition=Q(published_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"OutboxEvent#{self.pk} ({self.event_type})"
