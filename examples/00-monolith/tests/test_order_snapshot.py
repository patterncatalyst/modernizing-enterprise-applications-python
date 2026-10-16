"""r04/ch.19: OrderItem's denormalized sku/item_name/unit_price_cents
snapshot replaces the inventory_item cross-context FK (SMELL[ch.18],
partially cured). These tests pin that shape down directly -- the FK is
gone, the snapshot columns exist, and the wire contract is unchanged -- all
independent of which INVENTORY_MODE wrote the row."""

import pytest

from order.models import OrderItem

pytestmark = pytest.mark.django_db


def test_orderitem_has_no_inventory_item_fk():
    field_names = {f.name for f in OrderItem._meta.get_fields()}
    assert "inventory_item" not in field_names
    assert {"sku", "item_name", "unit_price_cents"} <= field_names


def test_local_mode_checkout_snapshots_sku_and_name_on_wire(api_client, customer, widget):
    response = api_client.post(
        "/api/orders",
        {
            "customerId": customer.id,
            "items": [{"sku": widget.sku, "quantity": 1}],
            "paymentMethod": "CARD-VISA",
            "shippingAddress": "1 Analytical Engine Way",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["items"][0]["sku"] == widget.sku
    assert body["items"][0]["unitPriceCents"] == widget.price_cents

    order_id = body["id"]
    detail = api_client.get(f"/api/orders/{order_id}")
    assert detail.status_code == 200
    # GET /api/orders/{id} is byte-for-byte unchanged on the wire even though
    # the sku now comes from OrderItem's own column, not a joined FK.
    assert detail.json()["items"][0]["sku"] == widget.sku
    assert detail.json()["items"][0]["unitPriceCents"] == widget.price_cents

    item = OrderItem.objects.get(order_id=order_id)
    assert item.sku == widget.sku
    assert item.item_name == widget.name
    assert item.unit_price_cents == widget.price_cents
