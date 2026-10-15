"""Six-context smoke test: one assertion per `/api/*` surface, proving every
bounded context still lives in this monolith (the Python sibling of the Java
monolith's `SixContextsSmokeTest`, but at r01 none of the six contexts have
been extracted yet -- every one of these should serve 200/201, not 404)."""

import pytest

pytestmark = pytest.mark.django_db


def test_inventory_serves(api_client, widget):
    response = api_client.get("/api/inventory")
    assert response.status_code == 200
    assert any(item["sku"] == widget.sku for item in response.json())


def test_orders_serves(api_client, confirmed_order):
    response = api_client.get("/api/orders")
    assert response.status_code == 200
    assert any(order["id"] == confirmed_order.id for order in response.json())


def test_payments_serves(api_client, confirmed_order):
    response = api_client.get(f"/api/payments?orderId={confirmed_order.id}")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_shipments_serves(api_client, confirmed_order):
    response = api_client.get(f"/api/shipments?orderId={confirmed_order.id}")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_notifications_serves(api_client, confirmed_order):
    response = api_client.get(f"/api/notifications?customerId={confirmed_order.customer_id}")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_reviews_serves(api_client, customer, widget):
    response = api_client.post(
        "/api/reviews",
        {"customerId": customer.id, "sku": widget.sku, "rating": 5, "comment": "Great"},
        format="json",
    )
    assert response.status_code == 201
