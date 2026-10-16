import pytest
from rest_framework.test import APIClient

from common.models import Customer
from inventory.models import InventoryItem
from order.services import place_order


@pytest.fixture
def api_client():
    return APIClient()


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
    orderId/customerId) have something to find."""
    return place_order(
        customer_id=customer.id,
        items=[{"sku": widget.sku, "quantity": 2}],
        payment_method="CARD-VISA",
        shipping_address="1 Analytical Engine Way, London",
    )
