"""Deterministic demo seed data.

Python sibling of the Java monolith's `V2__seed_data.sql`. Relies on
auto-incrementing PK assignment in insertion order against a fresh schema
(customers 1-2, inventory_items 1-3, orders 1, etc.) so every context has at
least one row to serve, matching the Java seed exactly (same names, emails,
prices, quantities, timestamps, confirmed order, and reviews).

Also seeds ONE fixed, documented Django auth `User` (`REVIEWER_USERNAME` /
`REVIEWER_PASSWORD` below) so the review write endpoint's Basic-auth gate
(SMELL[ch.15], see `review/views.py`) has known-good demo credentials to
authenticate with -- e.g. the equivalence suite's 201 case. Fixed demo
credentials only; never reuse these for anything real.

Run with: `uv run manage.py seed`
"""

from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from common.models import Customer
from inventory.models import InventoryItem
from notification.models import Notification
from order.models import Order, OrderItem
from payment.models import Payment
from review.models import Review
from shipping.models import Shipment

# Fixed, documented demo credentials for the review write endpoint's Basic
# auth gate (SMELL[ch.15]) -- NOT a production secret.
REVIEWER_USERNAME = "reviewer"
REVIEWER_PASSWORD = "review-pw-r02"


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


class Command(BaseCommand):
    help = "Seed deterministic demo data (customers, inventory, one confirmed order, two reviews)."

    @transaction.atomic
    def handle(self, *args, **options):
        reviewer_created = self._seed_reviewer_user()

        if Customer.objects.exists():
            if reviewer_created:
                self.stdout.write(
                    self.style.SUCCESS(f"Seeded auth user '{REVIEWER_USERNAME}'.")
                )
            self.stdout.write(self.style.WARNING("Seed data already present -- skipping."))
            return

        ada = Customer.objects.create(
            name="Ada Lovelace", email="ada@example.com", created_at=_utc(2026, 1, 5, 9, 0, 0)
        )
        grace = Customer.objects.create(
            name="Grace Hopper", email="grace@example.com", created_at=_utc(2026, 1, 6, 10, 30, 0)
        )

        widget = InventoryItem.objects.create(
            sku="SKU-WIDGET-001",
            name="Standard Widget",
            price_cents=1999,
            quantity_on_hand=100,
            updated_at=_utc(2026, 1, 5, 8, 0, 0),
        )
        gadget = InventoryItem.objects.create(
            sku="SKU-GADGET-002",
            name="Deluxe Gadget",
            price_cents=4999,
            quantity_on_hand=50,
            updated_at=_utc(2026, 1, 5, 8, 0, 0),
        )
        # Deliberately low stock -- exercises the over-order -> 409 OUT_OF_STOCK
        # path (SMELL[ch.22]'s InsufficientStock) without any extra setup.
        InventoryItem.objects.create(
            sku="SKU-GIZMO-003",
            name="Pocket Gizmo",
            price_cents=999,
            quantity_on_hand=5,
            updated_at=_utc(2026, 1, 5, 8, 0, 0),
        )

        # Order #1: Ada buys two Standard Widgets, fully confirmed and shipped.
        order = Order.objects.create(
            customer=ada,
            status=Order.Status.CONFIRMED,
            total_cents=3998,
            shipping_address="1 Analytical Engine Way, London",
            created_at=_utc(2026, 1, 7, 12, 0, 0),
        )
        OrderItem.objects.create(
            order=order, inventory_item=widget, quantity=2, unit_price_cents=1999
        )

        Payment.objects.create(
            order=order,
            amount_cents=3998,
            method="CARD-VISA",
            status=Payment.Status.CAPTURED,
            created_at=_utc(2026, 1, 7, 12, 0, 5),
        )
        Shipment.objects.create(
            order=order,
            address="1 Analytical Engine Way, London",
            status=Shipment.Status.DISPATCHED,
            created_at=_utc(2026, 1, 7, 12, 0, 10),
        )
        Notification.objects.create(
            customer=ada,
            order=order,
            channel="EMAIL",
            message="Order #1 confirmed, total $39.98",
            sent_at=_utc(2026, 1, 7, 12, 0, 15),
        )

        # Reviews: independent of orders entirely (review has no synchronous
        # collaborator -- see review/models.py).
        Review.objects.create(
            customer=grace,
            inventory_item=widget,
            rating=5,
            comment="Works great, exactly as advertised!",
            created_at=_utc(2026, 1, 8, 15, 0, 0),
        )
        Review.objects.create(
            customer=ada,
            inventory_item=gadget,
            rating=4,
            comment="Solid build, a little pricey.",
            created_at=_utc(2026, 1, 9, 11, 0, 0),
        )

        summary = (
            "Seeded 2 customers, 3 inventory items, 1 confirmed order, 2 reviews, "
            f"1 auth user ('{REVIEWER_USERNAME}')."
        )
        self.stdout.write(self.style.SUCCESS(summary))

    def _seed_reviewer_user(self) -> bool:
        """Idempotently create the fixed `reviewer` auth user. Returns True
        if it was created just now, False if it already existed. Kept
        independent of the Customer-existence guard above so re-running
        `seed` against an older database (seeded before SMELL[ch.15] existed)
        still backfills the auth user."""
        user_model = get_user_model()
        if user_model.objects.filter(username=REVIEWER_USERNAME).exists():
            return False
        user_model.objects.create_user(username=REVIEWER_USERNAME, password=REVIEWER_PASSWORD)
        return True
