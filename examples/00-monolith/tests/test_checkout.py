"""Deterministic failure injection in the checkout flow (`POST /api/orders`).
Each of these exercises a different one of the six smells in
`order.services.place_order()`: the over-order and decline cases prove the
single `transaction.atomic()` (SMELL[ch.22]) rolls back cleanly; SHIP-FAIL
proves it rolls back the ENTIRE checkout, including the inventory
reservation, leaving stock net-zero."""

import pytest

pytestmark = pytest.mark.django_db


def _checkout(api_client, customer, sku, quantity, payment_method, shipping_address):
    return api_client.post(
        "/api/orders",
        {
            "customerId": customer.id,
            "items": [{"sku": sku, "quantity": quantity}],
            "paymentMethod": payment_method,
            "shippingAddress": shipping_address,
        },
        format="json",
    )


def test_happy_path_confirms_order(api_client, customer, widget):
    address = "1 Analytical Engine Way"
    response = _checkout(api_client, customer, widget.sku, 1, "CARD-VISA", address)
    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"
    assert response["Location"] == f"/api/orders/{response.json()['id']}"


def test_over_order_returns_409_out_of_stock(api_client, customer, low_stock_item):
    address = "1 Analytical Engine Way"
    response = _checkout(api_client, customer, low_stock_item.sku, 999, "CARD-VISA", address)
    assert response.status_code == 409
    assert response.json()["error"] == "OUT_OF_STOCK"


def test_decline_sentinel_returns_402_and_rolls_back_stock(api_client, customer, widget):
    before = widget.quantity_on_hand
    address = "1 Analytical Engine Way"
    response = _checkout(api_client, customer, widget.sku, 1, "CARD-DECLINE", address)
    assert response.status_code == 402
    assert response.json()["error"] == "PAYMENT_DECLINED"
    widget.refresh_from_db()
    # net-zero: the atomic() rolled back the inventory reservation too.
    assert widget.quantity_on_hand == before


def test_ship_fail_sentinel_rolls_back_entire_checkout(api_client, customer, widget):
    before = widget.quantity_on_hand
    response = _checkout(api_client, customer, widget.sku, 1, "CARD-VISA", "SHIP-FAIL Lane")
    assert response.status_code == 422
    assert response.json()["error"] == "SHIPPING_FAILED"
    widget.refresh_from_db()
    assert widget.quantity_on_hand == before  # net-zero stock, SMELL[ch.22]
