import base64

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from common.management.commands.seed import REVIEWER_PASSWORD, REVIEWER_USERNAME
from common.models import Customer, OutboxEvent
from inventory.models import InventoryItem
from notification.services import record_order_placed
from order.services import place_order


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def reviewer_user(db):
    """The fixed Basic-auth demo user seeded by `manage.py seed`
    (SMELL[ch.15] -- review's write endpoint auth gate)."""
    return get_user_model().objects.create_user(
        username=REVIEWER_USERNAME, password=REVIEWER_PASSWORD
    )


@pytest.fixture
def reviewer_auth_header(reviewer_user):
    """kwargs for `api_client.post(..., **reviewer_auth_header)`: a valid
    HTTP Basic `Authorization` header for the seeded `reviewer` user."""
    token = base64.b64encode(f"{REVIEWER_USERNAME}:{REVIEWER_PASSWORD}".encode()).decode()
    return {"HTTP_AUTHORIZATION": f"Basic {token}"}


@pytest.fixture
def customer(db):
    return Customer.objects.create(name="Ada Lovelace", email="ada@example.com")


@pytest.fixture
def other_customer(db):
    return Customer.objects.create(name="Grace Hopper", email="grace@example.com")


@pytest.fixture
def widget(db):
    return InventoryItem.objects.create(
        sku="SKU-WIDGET-001", name="Standard Widget", price_cents=1999, quantity_on_hand=100
    )


@pytest.fixture
def low_stock_item(db):
    return InventoryItem.objects.create(
        sku="SKU-GIZMO-003", name="Pocket Gizmo", price_cents=999, quantity_on_hand=5
    )


@pytest.fixture
def confirmed_order(db, customer, widget):
    """A confirmed order with a payment, shipment, and notification already
    attached -- exercises place_order()'s full six-context checkout flow once
    so the read-side smoke tests (payments/shipments/notifications by
    orderId/customerId) have something to find.

    r03: `place_order()` itself only writes an `order.placed` OutboxEvent
    row now (see SMELLS.md #5/#6, cured) -- there's no live Kafka broker in
    the test environment to carry it to the consumer. This fixture plays the
    part of `common.management.commands.outbox_relay` +
    `notification.management.commands.order_placed_consumer` end to end,
    synchronously, by handing the outbox row's own payload straight to
    `notification.services.record_order_placed()` -- the same function the
    real consumer calls. That keeps the read-side smoke tests exercising the
    real `Notification`-creation code path without requiring a broker."""
    order = place_order(
        customer_id=customer.id,
        items=[{"sku": widget.sku, "quantity": 2}],
        payment_method="CARD-VISA",
        shipping_address="1 Analytical Engine Way, London",
    )
    outbox_event = OutboxEvent.objects.get(aggregate_type="order", aggregate_id=str(order.id))
    record_order_placed(outbox_event.payload)
    return order
