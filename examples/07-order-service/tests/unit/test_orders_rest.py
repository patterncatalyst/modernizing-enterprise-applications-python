"""REST contract tests for `/api/orders` -- matches
`00-monolith/order/views.py`/`serializers.py`'s contract (camelCase, uniform
error body, no trailing slash) with ONE deliberate difference this lane's
acceptance criteria calls out: `POST /api/orders` returns **202 Accepted**
with a `Location` header and status `PENDING`, never `201`."""

from __future__ import annotations

import app.service as service_module
from tests.unit.fakes import FakeInventoryClient


def _install_fake(monkeypatch) -> FakeInventoryClient:
    fake = FakeInventoryClient()
    monkeypatch.setattr(service_module, "AsyncInventoryClient", lambda *a, **kw: fake)
    return fake


def test_create_order_returns_202_with_location_and_pending_status(client, monkeypatch):
    _install_fake(monkeypatch)

    response = client.post(
        "/api/orders",
        json={
            "customerId": 1,
            "items": [{"sku": "SKU-WIDGET-001", "quantity": 2}],
            "paymentMethod": "VISA-1234",
            "shippingAddress": "221B Baker Street",
        },
    )

    assert response.status_code == 202
    assert "Location" in response.headers
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["customerId"] == 1
    assert body["totalCents"] == 1999 * 2
    assert body["shippingAddress"] == "221B Baker Street"
    assert body["items"] == [{"sku": "SKU-WIDGET-001", "quantity": 2, "unitPriceCents": 1999}]
    assert response.headers["Location"] == f"/api/orders/{body['id']}"


def test_get_order_serves_camelcase_contract_from_order_view(client, monkeypatch):
    _install_fake(monkeypatch)
    created = client.post(
        "/api/orders",
        json={
            "customerId": 2,
            "items": [{"sku": "SKU-GADGET-002", "quantity": 1}],
            "paymentMethod": "VISA-1234",
            "shippingAddress": "1 Analytical Engine Way",
        },
    ).json()

    response = client.get(f"/api/orders/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "customerId",
        "status",
        "totalCents",
        "createdAt",
        "shippingAddress",
        "items",
    }
    assert body["items"][0].keys() == {"sku", "quantity", "unitPriceCents"}


def test_get_unknown_order_returns_404(client):
    response = client.get("/api/orders/999999999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "NOT_FOUND"
    assert "timestamp" in body


def test_list_orders_returns_an_array(client, monkeypatch):
    _install_fake(monkeypatch)
    client.post(
        "/api/orders",
        json={
            "customerId": 1,
            "items": [{"sku": "SKU-WIDGET-001", "quantity": 1}],
            "paymentMethod": "VISA-1234",
            "shippingAddress": "1 Test Lane",
        },
    )

    response = client.get("/api/orders")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 1


def test_create_order_unknown_customer_returns_404(client, monkeypatch):
    _install_fake(monkeypatch)
    response = client.post(
        "/api/orders",
        json={
            "customerId": 999999,
            "items": [{"sku": "SKU-WIDGET-001", "quantity": 1}],
            "paymentMethod": "VISA-1234",
            "shippingAddress": "1 Test Lane",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"


def test_create_order_insufficient_stock_returns_409(client, monkeypatch):
    _install_fake(monkeypatch)
    response = client.post(
        "/api/orders",
        json={
            "customerId": 1,
            "items": [{"sku": "SKU-GIZMO-003", "quantity": 9999}],
            "paymentMethod": "VISA-1234",
            "shippingAddress": "1 Test Lane",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == "OUT_OF_STOCK"


def test_create_order_missing_field_returns_400_validation_failed(client):
    response = client.post(
        "/api/orders",
        json={
            "customerId": 1,
            "items": [{"sku": "SKU-WIDGET-001", "quantity": 1}],
            "shippingAddress": "1 Test Lane",
            # paymentMethod omitted
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "VALIDATION_FAILED"


def test_trailing_slash_is_not_redirected(client):
    response = client.get("/api/orders/", follow_redirects=False)
    assert response.status_code == 404
