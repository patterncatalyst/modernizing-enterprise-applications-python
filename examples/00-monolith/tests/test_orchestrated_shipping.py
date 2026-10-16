"""Unit coverage for `settings.SHIPPING_MODE = "orchestrated"` (r06, the
MONOLITH-LIFECYCLE lane): `order.services.handle_payment_captured`'s new
`orchestrated` branch (PENDING -> AWAITING_SHIPMENT, no in-process shipping
dispatch/confirm), plus the two new saga-listener reactions it hands off to
-- `handle_shipment_dispatched` (AWAITING_SHIPMENT -> CONFIRMED) and
`handle_shipment_failed` (AWAITING_SHIPMENT -> SHIPPING_FAILED + a
compensating gRPC Release per reserved line) -- called DIRECTLY here,
exactly like `tests/test_choreographed_checkout.py` calls
`handle_payment_captured`/`handle_payment_declined` directly, so none of this
needs a live Kafka broker or a running shipping-service.
`order.management.commands.order_saga_listener` is deliberately thin
(aiokafka wiring only) so these functions are testable without it.

`tests/test_choreographed_checkout.py` already pins down that
`SHIPPING_MODE=inprocess` (the default) is r05's behavior, byte-for-byte
unchanged -- this file only adds `orchestrated`-mode coverage, it does not
re-test the inprocess path.
"""

import pytest

from order import inventory_client, services
from order.models import Order, OrderItem
from payment.models import Payment
from shipping.models import Shipment

pytestmark = pytest.mark.django_db


class FakeRemoteInventoryClient:
    """In-memory stand-in for order.inventory_client.RemoteInventoryClient --
    same shape as test_choreographed_checkout.py's fake, only the Release
    side is exercised here (handle_shipment_failed is the only path in this
    file that calls it)."""

    def __init__(self):
        self.release_calls: list[tuple[str, int, str]] = []
        self.closed = False

    def release(
        self, sku: str, quantity: int, idempotency_key: str = ""
    ) -> inventory_client.ReserveResult:
        self.release_calls.append((sku, quantity, idempotency_key))
        return inventory_client.ReserveResult(sku=sku, reservation_ok=True, on_hand_qty=0)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def orchestrated_mode(settings):
    settings.SHIPPING_MODE = "orchestrated"
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


def _make_awaiting_shipment_order(customer, **kwargs) -> Order:
    order = _make_pending_order(customer, **kwargs)
    order.await_shipment()
    order.save(update_fields=["status"])
    return order


def _payment_event(order: Order, **extra) -> dict:
    event = {
        "orderId": order.id,
        "paymentId": 42,
        "amountCents": order.total_cents,
        "method": "CARD-VISA",
        "status": "CAPTURED",
        "occurredAt": "2026-10-16T05:26:45.400000+00:00",
    }
    event.update(extra)
    return event


def _shipment_event(order: Order, **extra) -> dict:
    event = {
        "orderId": order.id,
        "shipmentId": 7,
        "address": order.shipping_address,
        "status": "DISPATCHED",
        "occurredAt": "2026-10-16T05:26:45.400000+00:00",
    }
    event.update(extra)
    return event


# --- handle_payment_captured(), orchestrated mode ---------------------------


def test_payment_captured_orchestrated_transitions_to_awaiting_shipment(
    orchestrated_mode, customer
):
    order = _make_pending_order(customer)

    result = services.handle_payment_captured(_payment_event(order))

    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_SHIPMENT
    assert result.id == order.id
    assert not Shipment.objects.filter(order=order).exists()
    assert not Payment.objects.filter(order=order).exists()


def test_payment_captured_orchestrated_redelivery_is_a_noop(orchestrated_mode, customer):
    order = _make_pending_order(customer)
    event = _payment_event(order)

    services.handle_payment_captured(event)
    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_SHIPMENT

    result = services.handle_payment_captured(event)
    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_SHIPMENT
    assert result.id == order.id


def test_payment_captured_inprocess_default_unaffected_by_shipping_mode_setting(customer):
    """Sanity check: with the default SHIPPING_MODE=inprocess, the old
    behavior (dispatch shipping synchronously, confirm) is unchanged by this
    lane's addition."""
    order = _make_pending_order(customer)

    result = services.handle_payment_captured(_payment_event(order))

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert result.id == order.id
    assert Shipment.objects.filter(order=order).exists()


# --- handle_shipment_dispatched() -------------------------------------------


def test_shipment_dispatched_confirms_order(customer):
    order = _make_awaiting_shipment_order(customer)

    result = services.handle_shipment_dispatched(_shipment_event(order))

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert result.id == order.id


def test_shipment_dispatched_redelivery_after_confirm_is_a_noop(customer):
    order = _make_awaiting_shipment_order(customer)
    event = _shipment_event(order)

    services.handle_shipment_dispatched(event)
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED

    result = services.handle_shipment_dispatched(event)
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert result.id == order.id


def test_shipment_dispatched_for_pending_order_is_a_noop(customer):
    """Status guard: an order that never reached AWAITING_SHIPMENT (still
    PENDING) must not be confirmed by a stray/out-of-order
    shipment.dispatched event."""
    order = _make_pending_order(customer)

    result = services.handle_shipment_dispatched(_shipment_event(order))

    order.refresh_from_db()
    assert order.status == Order.Status.PENDING
    assert result.id == order.id


def test_shipment_dispatched_for_unknown_order_id_is_ignored():
    result = services.handle_shipment_dispatched(
        {
            "orderId": 999999999,
            "shipmentId": 1,
            "address": "nowhere",
            "status": "DISPATCHED",
            "occurredAt": "2026-10-16T05:26:45.400000+00:00",
        }
    )
    assert result is None


# --- handle_shipment_failed() -----------------------------------------------


def test_shipment_failed_releases_every_line_and_marks_shipping_failed(monkeypatch, customer):
    order = _make_awaiting_shipment_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)

    result = services.handle_shipment_failed(_shipment_event(order, status="FAILED", reason="x"))

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert result.id == order.id
    assert fake_client.release_calls == [("SKU-A", 2, f"{order.id}:SKU-A:release")]
    assert fake_client.closed
    # Known deferral: no refund attempted here either -- same gap as the
    # inprocess flow's handle_payment_captured.
    assert not Payment.objects.filter(order=order).exists()


def test_shipment_failed_releases_every_reserved_line_multi_sku(monkeypatch, customer):
    order = Order.objects.create(
        customer=customer,
        shipping_address="1 Analytical Engine Way",
        status=Order.Status.AWAITING_SHIPMENT,
        total_cents=5000,
    )
    OrderItem.objects.create(
        order=order, sku="SKU-A", item_name="Widget A", quantity=1, unit_price_cents=1000
    )
    OrderItem.objects.create(
        order=order, sku="SKU-B", item_name="Widget B", quantity=2, unit_price_cents=2000
    )
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)

    services.handle_shipment_failed(_shipment_event(order, status="FAILED", reason="x"))

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert sorted(fake_client.release_calls) == sorted(
        [
            ("SKU-A", 1, f"{order.id}:SKU-A:release"),
            ("SKU-B", 2, f"{order.id}:SKU-B:release"),
        ]
    )


def test_shipment_failed_redelivery_does_not_release_again(monkeypatch, customer):
    order = _make_awaiting_shipment_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)
    event = _shipment_event(order, status="FAILED", reason="x")

    services.handle_shipment_failed(event)
    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert len(fake_client.release_calls) == 1

    # Redelivery of the SAME event -- the status guard must no-op this, and
    # in particular must NOT issue a second Release (stable idempotency key
    # notwithstanding -- this call must not even be attempted again).
    result = services.handle_shipment_failed(event)
    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPING_FAILED
    assert result.id == order.id
    assert len(fake_client.release_calls) == 1  # unchanged


def test_shipment_failed_for_pending_order_is_a_noop(monkeypatch, customer):
    order = _make_pending_order(customer)
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)

    result = services.handle_shipment_failed(_shipment_event(order, status="FAILED", reason="x"))

    order.refresh_from_db()
    assert order.status == Order.Status.PENDING
    assert result.id == order.id
    assert not fake_client.release_calls


def test_dispatched_then_failed_redelivery_cross_event_is_also_a_noop(monkeypatch, customer):
    """The status guard is keyed on the order's CURRENT status, not on which
    topic the event came from -- a late/duplicate shipment.failed for an
    order ALREADY resolved CONFIRMED (e.g. reordered redelivery) must also
    no-op, not re-release or flip the order back to SHIPPING_FAILED."""
    order = _make_awaiting_shipment_order(customer, sku="SKU-A", quantity=2)
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)

    services.handle_shipment_dispatched(_shipment_event(order))
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED

    result = services.handle_shipment_failed(_shipment_event(order, status="FAILED", reason="x"))
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED  # unchanged
    assert result.id == order.id
    assert not fake_client.release_calls


def test_shipment_failed_for_unknown_order_id_is_ignored(monkeypatch):
    fake_client = FakeRemoteInventoryClient()
    _patch_client(monkeypatch, fake_client)

    result = services.handle_shipment_failed(
        {
            "orderId": 999999999,
            "shipmentId": 1,
            "address": "nowhere",
            "status": "FAILED",
            "reason": "x",
            "occurredAt": "2026-10-16T05:26:45.400000+00:00",
        }
    )

    assert result is None
    assert not fake_client.release_calls
