from django.db import models
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
