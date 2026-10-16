"""The transactional outbox (ch.17 cure for SMELL #5/#6 -- see SMELLS.md).

Proves three things without a live Kafka broker (the end-to-end Kafka path
-- outbox_relay publishing, order_placed_consumer subscribing -- is the
Newman/CI lanes' job, per the r03 plan):

1. checkout is still a synchronous `201 CONFIRMED` and writes exactly one
   `order.placed` outbox row, in the SAME transaction as the rest of
   checkout.
2. a DECLINE and a SHIP-FAIL checkout roll that outbox row back along with
   everything else `transaction.atomic()` already covers (net-zero stock,
   SMELL[ch.22]) -- zero new outbox rows survive.
3. `notification.services.record_order_placed()`, the consumer's handler, is
   idempotent: delivering the same `order.placed` event twice creates
   exactly one `Notification`.
"""

import pytest

from common.models import OutboxEvent
from notification.models import Notification
from notification.services import record_order_placed

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


def test_checkout_writes_exactly_one_order_placed_outbox_row(api_client, customer, widget):
    before = OutboxEvent.objects.count()

    response = _checkout(
        api_client, customer, widget.sku, 1, "CARD-VISA", "1 Analytical Engine Way"
    )

    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"

    assert OutboxEvent.objects.count() == before + 1
    order_id = response.json()["id"]
    event = OutboxEvent.objects.get(aggregate_type="order", aggregate_id=str(order_id))
    assert event.event_type == "order.placed"
    assert event.published_at is None

    payload = event.payload
    assert payload["orderId"] == order_id
    assert payload["customerId"] == customer.id
    assert payload["customerEmail"] == customer.email
    assert payload["totalCents"] == response.json()["totalCents"]
    assert payload["confirmationMessage"] == (
        f"Order #{order_id} confirmed, total ${payload['totalCents'] / 100:.2f}"
    )
    assert "placedAt" in payload


def test_decline_checkout_leaves_no_new_outbox_row(api_client, customer, widget):
    before = OutboxEvent.objects.count()

    response = _checkout(
        api_client, customer, widget.sku, 1, "CARD-DECLINE", "1 Analytical Engine Way"
    )

    assert response.status_code == 402
    assert OutboxEvent.objects.count() == before


def test_ship_fail_checkout_leaves_no_new_outbox_row(api_client, customer, widget):
    before = OutboxEvent.objects.count()

    response = _checkout(api_client, customer, widget.sku, 1, "CARD-VISA", "SHIP-FAIL Lane")

    assert response.status_code == 422
    assert OutboxEvent.objects.count() == before


def test_record_order_placed_is_idempotent(customer, confirmed_order):
    # confirmed_order already drove record_order_placed() once (see the
    # fixture) -- exactly one Notification should exist for it.
    assert Notification.objects.filter(order_id=confirmed_order.id).count() == 1

    event = OutboxEvent.objects.get(
        aggregate_type="order", aggregate_id=str(confirmed_order.id)
    ).payload

    # Deliver the same event a second (and third) time, as an at-least-once
    # redelivery would -- still exactly one Notification for this order.
    record_order_placed(event)
    record_order_placed(event)

    assert Notification.objects.filter(order_id=confirmed_order.id).count() == 1
