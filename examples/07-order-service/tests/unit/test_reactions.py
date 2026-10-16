"""Fast, Kafka-free, gRPC-free proofs for the four saga reactions
(`app.service.handle_payment_captured`/`handle_payment_declined`/
`handle_shipment_dispatched`/`handle_shipment_failed`): status-transition
guards, idempotent redelivery (no-op, no double Release), the stable
per-(order, line) Release idempotency key, and net-zero stock restoration.

REFUND NOTE: a payment that captured and then hits `shipment.failed` is
refunded by `05-payment-service`'s OWN `shipment.failed` consumer
(`app/refund_consumer.py`, r06/DRQ-054) reacting to the SAME event this
service's `handle_shipment_failed` does -- order-service has no payment
collaborator of its own to call, so there is nothing to test for a refund
HERE; see `../06-shipping-service`/`../05-payment-service`'s own test suites
for that proof. This service's responsibility ends at releasing inventory
and transitioning the order to `SHIPPING_FAILED`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import repository
from app.schemas import (
    OrderLineIn,
    PaymentCapturedEvent,
    PaymentDeclinedEvent,
    ShipmentDispatchedEvent,
    ShipmentFailedEvent,
)
from app.service import (
    handle_payment_captured,
    handle_payment_declined,
    handle_shipment_dispatched,
    handle_shipment_failed,
    place_order,
)
from tests.unit.fakes import FakeInventoryClient, install_fake_inventory_client

UNUSED_TARGET = "unused:0"
TIMEOUT_S = 1.0


async def _new_pending_order(session_factory, fake, *, sku="SKU-WIDGET-001", quantity=1):
    order = await place_order(
        session_factory,
        inventory_grpc_target=UNUSED_TARGET,
        grpc_timeout_s=TIMEOUT_S,
        customer_id=1,
        items=[OrderLineIn(sku=sku, quantity=quantity)],
        payment_method="VISA-1234",
        shipping_address="1 Test Lane",
    )
    fake.reserve_calls.clear()
    fake.release_calls.clear()
    return order


def _payment_captured(order_id: int) -> PaymentCapturedEvent:
    return PaymentCapturedEvent(
        orderId=order_id,
        paymentId=1,
        amountCents=1999,
        method="VISA-1234",
        status="CAPTURED",
        occurredAt=datetime.now(UTC),
    )


def _payment_declined(order_id: int) -> PaymentDeclinedEvent:
    return PaymentDeclinedEvent(
        orderId=order_id,
        paymentId=1,
        amountCents=1999,
        method="VISA-1234",
        status="DECLINED",
        reason="declined",
        occurredAt=datetime.now(UTC),
    )


def _shipment_dispatched(order_id: int) -> ShipmentDispatchedEvent:
    return ShipmentDispatchedEvent(
        orderId=order_id,
        shipmentId=1,
        address="1 Test Lane",
        status="DISPATCHED",
        occurredAt=datetime.now(UTC),
    )


def _shipment_failed(order_id: int) -> ShipmentFailedEvent:
    return ShipmentFailedEvent(
        orderId=order_id,
        shipmentId=1,
        address="1 SHIP-FAIL Lane",
        status="FAILED",
        reason="carrier booking failed",
        occurredAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_handle_payment_captured_transitions_pending_to_awaiting_shipment(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)

    updated = await handle_payment_captured(session_factory, _payment_captured(order.id))

    assert updated is not None
    assert updated.status == "AWAITING_SHIPMENT"
    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
        assert view.status == "AWAITING_SHIPMENT", "view must update in the SAME transaction"
    assert fake.release_calls == [], "a captured payment never releases inventory"


@pytest.mark.asyncio
async def test_handle_payment_captured_is_idempotent_on_redelivery(session_factory, monkeypatch):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)
    event = _payment_captured(order.id)

    first = await handle_payment_captured(session_factory, event)
    second = await handle_payment_captured(session_factory, event)

    assert first is not None and first.status == "AWAITING_SHIPMENT"
    assert second is None, "a redelivered payment.captured for a non-PENDING order is a no-op"


@pytest.mark.asyncio
async def test_handle_payment_captured_unknown_order_is_a_safe_noop(session_factory, monkeypatch):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    result = await handle_payment_captured(session_factory, _payment_captured(999_999_999))
    assert result is None


@pytest.mark.asyncio
async def test_handle_payment_declined_releases_lines_with_stable_key_and_transitions(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake, sku="SKU-GADGET-002", quantity=2)
    stock_before = fake.stock["SKU-GADGET-002"]["on_hand"]

    updated = await handle_payment_declined(
        session_factory,
        _payment_declined(order.id),
        inventory_grpc_target=UNUSED_TARGET,
        grpc_timeout_s=TIMEOUT_S,
    )

    assert updated is not None
    assert updated.status == "PAYMENT_DECLINED"
    assert fake.release_calls == [("SKU-GADGET-002", 2, f"{order.id}:SKU-GADGET-002:release")]
    assert fake.stock["SKU-GADGET-002"]["on_hand"] == stock_before + 2, "net-zero"

    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
        assert view.status == "PAYMENT_DECLINED"


@pytest.mark.asyncio
async def test_handle_payment_declined_redelivery_releases_at_most_once(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)
    event = _payment_declined(order.id)

    first = await handle_payment_declined(
        session_factory, event, inventory_grpc_target=UNUSED_TARGET, grpc_timeout_s=TIMEOUT_S
    )
    second = await handle_payment_declined(
        session_factory, event, inventory_grpc_target=UNUSED_TARGET, grpc_timeout_s=TIMEOUT_S
    )

    assert first is not None and first.status == "PAYMENT_DECLINED"
    assert second is None, "a redelivered payment.declined for a non-PENDING order is a no-op"
    assert len(fake.release_calls) == 1, "Release must not be issued twice on redelivery"


@pytest.mark.asyncio
async def test_handle_shipment_dispatched_transitions_awaiting_shipment_to_confirmed(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)
    await handle_payment_captured(session_factory, _payment_captured(order.id))

    updated = await handle_shipment_dispatched(session_factory, _shipment_dispatched(order.id))

    assert updated is not None
    assert updated.status == "CONFIRMED"
    assert fake.release_calls == [], "a dispatched shipment never releases inventory"
    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
        assert view.status == "CONFIRMED"


@pytest.mark.asyncio
async def test_handle_shipment_dispatched_is_idempotent_on_redelivery(session_factory, monkeypatch):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)
    await handle_payment_captured(session_factory, _payment_captured(order.id))
    event = _shipment_dispatched(order.id)

    first = await handle_shipment_dispatched(session_factory, event)
    second = await handle_shipment_dispatched(session_factory, event)

    assert first is not None and first.status == "CONFIRMED"
    assert second is None


@pytest.mark.asyncio
async def test_handle_shipment_failed_releases_lines_with_stable_key_and_transitions(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake, sku="SKU-WIDGET-001", quantity=3)
    stock_before = fake.stock["SKU-WIDGET-001"]["on_hand"]
    await handle_payment_captured(session_factory, _payment_captured(order.id))

    updated = await handle_shipment_failed(
        session_factory,
        _shipment_failed(order.id),
        inventory_grpc_target=UNUSED_TARGET,
        grpc_timeout_s=TIMEOUT_S,
    )

    assert updated is not None
    assert updated.status == "SHIPPING_FAILED"
    assert fake.release_calls == [("SKU-WIDGET-001", 3, f"{order.id}:SKU-WIDGET-001:release")]
    assert fake.stock["SKU-WIDGET-001"]["on_hand"] == stock_before + 3, "net-zero"

    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
        assert view.status == "SHIPPING_FAILED"


@pytest.mark.asyncio
async def test_handle_shipment_failed_redelivery_releases_at_most_once(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)
    await handle_payment_captured(session_factory, _payment_captured(order.id))
    event = _shipment_failed(order.id)

    first = await handle_shipment_failed(
        session_factory, event, inventory_grpc_target=UNUSED_TARGET, grpc_timeout_s=TIMEOUT_S
    )
    second = await handle_shipment_failed(
        session_factory, event, inventory_grpc_target=UNUSED_TARGET, grpc_timeout_s=TIMEOUT_S
    )

    assert first is not None and first.status == "SHIPPING_FAILED"
    assert second is None
    assert len(fake.release_calls) == 1, "Release must not be issued twice on redelivery"


@pytest.mark.asyncio
async def test_handle_shipment_failed_requires_awaiting_shipment_not_pending(
    session_factory, monkeypatch
):
    """A `shipment.failed` arriving for an order still `PENDING` (it never
    reached `AWAITING_SHIPMENT`) must be a no-op, not a release against an
    order that never had a shipment saga started for it."""
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)
    order = await _new_pending_order(session_factory, fake)

    result = await handle_shipment_failed(
        session_factory,
        _shipment_failed(order.id),
        inventory_grpc_target=UNUSED_TARGET,
        grpc_timeout_s=TIMEOUT_S,
    )

    assert result is None
    assert fake.release_calls == []
