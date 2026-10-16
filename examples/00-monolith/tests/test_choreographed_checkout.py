"""Unit coverage for `settings.PAYMENT_MODE = "choreographed"` (r05/ch.23-25,
the MONOLITH-SAGA + ASYNC-CHECKOUT lane): `order.services.place_order()`'s
new `_place_order_choreographed` branch, and the saga-listener reaction
functions it hands off to (`handle_payment_captured`/`handle_payment_declined`)
-- called DIRECTLY here, exactly like `tests/test_grpc_checkout.py` calls
`place_order()` directly, so none of this needs a live Kafka broker or a
running `examples/05-payment-service`. `order.management.commands
.order_saga_listener` is deliberately thin (aiokafka wiring only) so these
functions are testable without it."""

import pytest

from common.exceptions import InsufficientStock
from common.models import OutboxEvent
from order import inventory_client, services
from order.models import Order, OrderItem
from payment.models import Payment
from shipping.models import Shipment

pytestmark = pytest.mark.django_db


class FakeRemoteInventoryClient:
    """In-memory stand-in for order.inventory_client.RemoteInventoryClient,
    same shape as test_grpc_checkout.py's fake, extended to record each
    Release's `idempotency_key` alongside (sku, quantity) -- the compensation
    contract this lane adds for the saga listener's redelivery-safe Release
    calls."""

    def __init__(self, stock: dict):
        self._stock = stock
        self.reserve_calls: list[tuple[str, int]] = []
        self.release_calls: list[tuple[str, int, str]] = []
        self.closed = False

    def reserve(self, sku: str, quantity: int) -> inventory_client.ReserveResult:
        self.reserve_calls.append((sku, quantity))
        item = self._stock.get(sku)
        on_hand = item["on_hand"] if item else 0
        if item is None or on_hand < quantity:
            raise InsufficientStock(f"Requested {quantity} of {sku} but only {on_hand} on hand")
        item["on_hand"] -= quantity
        return inventory_client.ReserveResult(
            sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"]
        )

    def get_stock(self, sku: str) -> inventory_client.StockSnapshot:
        item = self._stock[sku]
        return inventory_client.StockSnapshot(
            sku=sku,
            name=item["name"],
            unit_price_cents=item["price_cents"],
            on_hand_qty=item["on_hand"],
            available=item["on_hand"] > 0,
        )

    def release(
        self, sku: str, quantity: int, idempotency_key: str = ""
    ) -> inventory_client.ReserveResult:
        self.release_calls.append((sku, quantity, idempotency_key))
        item = self._stock.setdefault(sku, {"name": sku, "price_cents": 0, "on_hand": 0})
        item["on_hand"] += quantity
        return inventory_client.ReserveResult(
            sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"]
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def choreographed_mode(settings):
    settings.PAYMENT_MODE = "choreographed"
    return settings


def _patch_client(monkeypatch, fake_client):
    monkeypatch.setattr(inventory_client, "RemoteInventoryClient", lambda: fake_client)


def _make_pending_order(
    customer,
    sku: str = "SKU-A",
    quantity: int = 2,
    price_cents: int = 1500,
    address: str = "1 Analytical Engine Way",
) -> Order:
    """Build a PENDING order + its OrderItem snapshot row directly -- the
    saga-listener reaction functions are tested against a persisted order,
    independent of whichever checkout flow produced it."""
    order = Order.objects.create(
        customer=customer,
        shipping_address=address,
        status=Order.Status.PENDING,
        total_cents=price_cents * quantity,
    )
    OrderItem.objects.create(
        order=order,
        sku=sku,
        item_name="Widget A",
        quantity=quantity,
        unit_price_cents=price_cents,
    )
    return order


def _payment_event(order: Order, status_: str, **extra) -> dict:
    event = {
        "orderId": order.id,
        "paymentId": 42,
        "amountCents": order.total_cents,
        "method": "CARD-VISA",
        "status": status_,
        "occurredAt": "2026-10-16T05:26:45.400000+00:00",
    }
    event.update(extra)
    return event


# --- place_order() in choreographed mode -----------------------------------


def test_choreographed_checkout_returns_pending_without_charging_or_shipping(
    choreographed_mode, monkeypatch, customer
):
    stock = {"SKU-A": {"name": "Widget A", "price_cents": 1500, "on_hand": 10}}
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    order = services.place_order(
        customer_id=customer.id,
        items=[{"sku": "SKU-A", "quantity": 2}],
        payment_method="CARD-VISA",
        shipping_address="1 Analytical Engine Way",
    )

    assert order.status == Order.Status.PENDING
    assert order.total_cents == 3000
    assert fake_client.reserve_calls == [("SKU-A", 2)]
    assert not fake_client.release_calls
    assert fake_client.closed

    # No payment charged, no shipment dispatched at checkout time.
    assert not Payment.objects.filter(order=order).exists()
    assert not Shipment.objects.filter(order=order).exists()

    event = OutboxEvent.objects.get(aggregate_type="order", aggregate_id=str(order.id))
    assert event.event_type == "order.placed"
    assert event.payload["paymentMethod"] == "CARD-VISA"
    assert event.payload["orderId"] == order.id


def test_choreographed_checkout_insufficient_stock_releases_prior_lines(
    choreographed_mode, monkeypatch, customer
):
    stock = {
        "SKU-A": {"name": "Widget A", "price_cents": 1000, "on_hand": 10},
        "SKU-B": {"name": "Widget B", "price_cents": 2000, "on_hand": 1},
    }
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(InsufficientStock):
        services.place_order(
            customer_id=customer.id,
            items=[{"sku": "SKU-A", "quantity": 1}, {"sku": "SKU-B", "quantity": 5}],
            payment_method="CARD-VISA",
            shipping_address="1 Analytical Engine Way",
        )

    assert fake_client.reserve_calls == [("SKU-A", 1), ("SKU-B", 5)]
    # Pre-commit compensation (same helper _place_order_remote uses) does not
    # pass an idempotency_key -- it runs once, synchronously, in this same
    # call, with nothing to redeliver.
    assert fake_client.release_calls == [("SKU-A", 1, "")]
    assert not Order.objects.filter(customer=customer).exists()


def test_synchronous_mode_is_unaffected_by_payment_mode_setting(customer, widget):
    """Sanity check: with the default settings (PAYMENT_MODE=synchronous),
    place_order() takes the old, byte-for-byte-unchanged path -- this is the
    zero-regression baseline the whole lane must not disturb."""
    order = services.place_order(
        customer_id=customer.id,
        items=[{"sku": widget.sku, "quantity": 1}],
        payment_method="CARD-VISA",
        shipping_address="1 Analytical Engine Way",
    )
    assert order.status == Order.Status.CONFIRMED
    assert Payment.objects.filter(order=order).exists()
    assert Shipment.objects.filter(order=order).exists()
    event = OutboxEvent.objects.get(aggregate_type="order", aggregate_id=str(order.id))
    assert "paymentMethod" not in event.payload


def test_post_api_orders_returns_202_pending_location_in_choreographed_mode(
    choreographed_mode, monkeypatch, api_client, customer
):
    """Acceptance criterion, exercised through the real view/serializer
    stack (not just place_order() directly): `POST /api/orders` under
    `PAYMENT_MODE=choreographed` answers `202 Accepted` with a `Location`
    header and a PENDING body -- the synchronous flow's `201 Created`
    CONFIRMED contract (test_checkout.py::test_happy_path_confirms_order)
    is untouched."""
    stock = {"SKU-A": {"name": "Widget A", "price_cents": 1500, "on_hand": 10}}
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    response = api_client.post(
        "/api/orders",
        {
            "customerId": customer.id,
            "items": [{"sku": "SKU-A", "quantity": 1}],
            "paymentMethod": "CARD-VISA",
            "shippingAddress": "1 Analytical Engine Way",
        },
        format="json",
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "PENDING"
    assert response["Location"] == f"/api/orders/{body['id']}"


# --- handle_payment_captured() ----------------------------------------------


def test_payment_captured_dispatches_shipping_and_confirms(monkeypatch, customer):
    order = _make_pending_order(customer)
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    result = services.handle_payment_captured(_payment_event(order, "CAPTURED"))

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert result.id == order.id
    assert Shipment.objects.filter(order=order).exists()
    assert not fake_client.release_calls


def test_payment_captured_with_shipfail_releases_every_line_and_marks_shipping_failed(
    monkeypatch, customer
):
    order = _make_pending_order(customer, sku="SKU-A", quantity=2, address="SHIP-FAIL Lane")
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    services.handle_payment_captured(_payment_event(order, "CAPTURED"))

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert fake_client.release_calls == [("SKU-A", 2, f"{order.id}:SKU-A:release")]
    assert not Shipment.objects.filter(order=order).exists()
    # Known deferral: no Payment row/refund attempted here -- payment-service
    # owns that, and there is no Refund RPC/event yet (r06's job).
    assert not Payment.objects.filter(order=order).exists()


def test_payment_captured_releases_every_reserved_line_multi_sku(monkeypatch, customer):
    order = Order.objects.create(
        customer=customer,
        shipping_address="SHIP-FAIL Lane",
        status=Order.Status.PENDING,
        total_cents=5000,
    )
    OrderItem.objects.create(
        order=order, sku="SKU-A", item_name="Widget A", quantity=1, unit_price_cents=1000
    )
    OrderItem.objects.create(
        order=order, sku="SKU-B", item_name="Widget B", quantity=2, unit_price_cents=2000
    )
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    services.handle_payment_captured(_payment_event(order, "CAPTURED"))

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert sorted(fake_client.release_calls) == sorted(
        [
            ("SKU-A", 1, f"{order.id}:SKU-A:release"),
            ("SKU-B", 2, f"{order.id}:SKU-B:release"),
        ]
    )


def test_redelivered_captured_event_after_confirm_is_a_noop(monkeypatch, customer):
    order = _make_pending_order(customer)
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)
    event = _payment_event(order, "CAPTURED")

    services.handle_payment_captured(event)
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert Shipment.objects.filter(order=order).count() == 1

    # Redelivery of the SAME event.
    result = services.handle_payment_captured(event)
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert result.id == order.id
    assert Shipment.objects.filter(order=order).count() == 1  # not re-dispatched
    assert not fake_client.release_calls


# --- handle_payment_declined() ----------------------------------------------


def test_payment_declined_releases_every_line_and_marks_payment_declined(monkeypatch, customer):
    order = _make_pending_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    result = services.handle_payment_declined(
        _payment_event(order, "DECLINED", method="CARD-DECLINE", reason="declined")
    )

    order.refresh_from_db()
    assert order.status == Order.Status.PAYMENT_DECLINED
    assert result.id == order.id
    assert fake_client.release_calls == [("SKU-A", 2, f"{order.id}:SKU-A:release")]
    assert not Payment.objects.filter(order=order).exists()
    assert not Shipment.objects.filter(order=order).exists()


def test_redelivered_declined_event_is_a_noop_release_not_called_again(monkeypatch, customer):
    order = _make_pending_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)
    event = _payment_event(order, "DECLINED", method="CARD-DECLINE", reason="declined")

    services.handle_payment_declined(event)
    order.refresh_from_db()
    assert order.status == Order.Status.PAYMENT_DECLINED
    assert len(fake_client.release_calls) == 1

    # Redelivery of the SAME event -- the status guard must no-op this,
    # and in particular must NOT issue a second Release.
    result = services.handle_payment_declined(event)
    order.refresh_from_db()
    assert order.status == Order.Status.PAYMENT_DECLINED
    assert result.id == order.id
    assert len(fake_client.release_calls) == 1  # unchanged


def test_declined_then_captured_redelivery_cross_event_is_also_a_noop(monkeypatch, customer):
    """The status guard is keyed on the order's CURRENT status, not on which
    topic the event came from -- a late/duplicate payment.captured for an
    order ALREADY resolved PAYMENT_DECLINED (e.g. reordered redelivery) must
    also no-op, not re-confirm or re-release."""
    order = _make_pending_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    services.handle_payment_declined(
        _payment_event(order, "DECLINED", method="CARD-DECLINE", reason="declined")
    )
    order.refresh_from_db()
    assert order.status == Order.Status.PAYMENT_DECLINED
    assert len(fake_client.release_calls) == 1

    result = services.handle_payment_captured(_payment_event(order, "CAPTURED"))
    order.refresh_from_db()
    assert order.status == Order.Status.PAYMENT_DECLINED  # unchanged
    assert result.id == order.id
    assert len(fake_client.release_calls) == 1  # unchanged
    assert not Shipment.objects.filter(order=order).exists()


def test_event_for_unknown_order_id_is_ignored(monkeypatch):
    fake_client = FakeRemoteInventoryClient({})
    _patch_client(monkeypatch, fake_client)

    result = services.handle_payment_captured(
        {
            "orderId": 999999999,
            "paymentId": 1,
            "amountCents": 100,
            "method": "CARD-VISA",
            "status": "CAPTURED",
            "occurredAt": "2026-10-16T05:26:45.400000+00:00",
        }
    )

    assert result is None
    assert not fake_client.release_calls
