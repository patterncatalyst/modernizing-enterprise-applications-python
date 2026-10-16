"""Fast, Kafka-free proofs for `app.service` against this service's real
`payment` schema (same reachable, already-migrated Postgres `conftest.py`'s
`client` fixture uses): the deterministic DECLINE rule, the null-method
forward-compatibility fallback, atomic outbox-event creation, and the
idempotent-redelivery guarantee. Complements
`tests/integration/test_payment_choreography.py`, which proves the same
guarantees end-to-end through a real Kafka broker and the real
`OrderPlacedConsumer`/`OutboxRelay`."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import repository, service
from app.db import create_engine, create_session_factory
from app.models import OutboxEvent
from app.schemas import OrderPlacedEvent, ShipmentFailedEvent


def _event(*, order_id: int, payment_method: str | None) -> OrderPlacedEvent:
    return OrderPlacedEvent(
        orderId=order_id,
        customerId=random.randint(10_000_000, 2_000_000_000),
        customerEmail="customer@example.com",
        totalCents=4999,
        confirmationMessage=f"Order #{order_id} confirmed, total $49.99",
        placedAt=datetime.now(UTC),
        paymentMethod=payment_method,
    )


def _shipment_failed_event(*, order_id: int, shipment_id: int | None = 1) -> ShipmentFailedEvent:
    return ShipmentFailedEvent(
        orderId=order_id,
        shipmentId=shipment_id,
        address="123 Main St, Springfield",
        status="FAILED",
        reason="carrier booking failed",
        occurredAt=datetime.now(UTC),
    )


def _random_order_id() -> int:
    return random.randint(10_000_000, 2_000_000_000)


def test_charge_captures_a_normal_method():
    assert service.charge("VISA-1234") == service.STATUS_CAPTURED


def test_charge_declines_a_method_containing_decline_case_insensitive():
    assert service.charge("visa-DECLINE-1234") == service.STATUS_DECLINED
    assert service.charge("decline") == service.STATUS_DECLINED


def test_charge_captures_when_method_is_none():
    # Forward-compatibility fallback: a missing/null paymentMethod on
    # order.placed must never crash the consumer, and must never be treated
    # as a decline.
    assert service.charge(None) == service.STATUS_CAPTURED


@pytest.mark.asyncio
async def test_process_order_placed_captures_and_writes_matching_outbox_event():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    event = _event(order_id=order_id, payment_method="VISA-1234")

    try:
        await service.process_order_placed(session_factory, event)

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "CAPTURED"
            assert payment.amount_cents == 4999
            assert payment.method == "VISA-1234"

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                )
            ).scalars().all()
            assert len(outbox_rows) == 1
            outbox_event = outbox_rows[0]
            assert outbox_event.event_type == "payment.captured"
            assert outbox_event.published_at is None
            assert outbox_event.payload["orderId"] == order_id
            assert outbox_event.payload["paymentId"] == payment.id
            assert outbox_event.payload["status"] == "CAPTURED"
            assert "reason" not in outbox_event.payload
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_order_placed_declines_and_writes_matching_outbox_event():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    event = _event(order_id=order_id, payment_method="CARD-DECLINE")

    try:
        await service.process_order_placed(session_factory, event)

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "DECLINED"

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                )
            ).scalars().all()
            assert len(outbox_rows) == 1
            outbox_event = outbox_rows[0]
            assert outbox_event.event_type == "payment.declined"
            assert outbox_event.payload["status"] == "DECLINED"
            assert "reason" in outbox_event.payload
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_order_placed_null_method_captures_never_crashes():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    event = _event(order_id=order_id, payment_method=None)

    try:
        await service.process_order_placed(session_factory, event)

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "CAPTURED"
            assert payment.method == service.UNSPECIFIED_METHOD
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_order_placed_is_idempotent_on_redelivery():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    event = _event(order_id=order_id, payment_method="VISA-1234")

    try:
        await service.process_order_placed(session_factory, event)
        # Redelivery of the IDENTICAL event -- the at-least-once order.placed
        # publisher scenario this dedupe check exists for.
        await service.process_order_placed(session_factory, event)

        async with session_factory() as session:
            payments = await repository.list_by_order_id(session, order_id)
            assert len(payments) == 1

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                )
            ).scalars().all()
            assert len(outbox_rows) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_shipment_failed_refunds_a_captured_payment_and_writes_outbox_event():
    """r06/DRQ-054 happy path: a `shipment.failed` for an order with a
    `CAPTURED` payment transitions it to `REFUNDED` and writes exactly one
    matching `payment.refunded` outbox row."""
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    order_placed = _event(order_id=order_id, payment_method="VISA-1234")

    try:
        await service.process_order_placed(session_factory, order_placed)

        async with session_factory() as session:
            captured_payment = await repository.get_by_order_id(session, order_id)
        assert captured_payment is not None
        assert captured_payment.status == "CAPTURED"

        await service.process_shipment_failed(
            session_factory, _shipment_failed_event(order_id=order_id)
        )

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "REFUNDED"
            assert payment.id == captured_payment.id

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == str(order_id))
                    .where(OutboxEvent.event_type == "payment.refunded")
                )
            ).scalars().all()
            assert len(outbox_rows) == 1
            refund_event = outbox_rows[0]
            assert refund_event.published_at is None
            assert refund_event.payload["orderId"] == order_id
            assert refund_event.payload["paymentId"] == payment.id
            assert refund_event.payload["amountCents"] == 4999
            assert refund_event.payload["status"] == "REFUNDED"
            assert "method" not in refund_event.payload
            assert "reason" not in refund_event.payload
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_shipment_failed_is_idempotent_on_redelivery():
    """A redelivered `shipment.failed` for an order already `REFUNDED` must
    not re-refund or emit a second `payment.refunded` event."""
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    order_placed = _event(order_id=order_id, payment_method="VISA-1234")
    shipment_failed = _shipment_failed_event(order_id=order_id)

    try:
        await service.process_order_placed(session_factory, order_placed)
        await service.process_shipment_failed(session_factory, shipment_failed)
        # Redelivery of the IDENTICAL shipment.failed event.
        await service.process_shipment_failed(session_factory, shipment_failed)

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "REFUNDED"

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == str(order_id))
                    .where(OutboxEvent.event_type == "payment.refunded")
                )
            ).scalars().all()
            assert len(outbox_rows) == 1, "redelivery must not emit a second payment.refunded"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_shipment_failed_does_not_refund_a_declined_payment():
    """A `shipment.failed` for an order whose payment was `DECLINED` (never
    captured) must be a no-op: never "refund" money that was never taken."""
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()
    order_placed = _event(order_id=order_id, payment_method="CARD-DECLINE")

    try:
        await service.process_order_placed(session_factory, order_placed)

        async with session_factory() as session:
            declined_payment = await repository.get_by_order_id(session, order_id)
        assert declined_payment is not None
        assert declined_payment.status == "DECLINED"

        await service.process_shipment_failed(
            session_factory, _shipment_failed_event(order_id=order_id)
        )

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is not None
            assert payment.status == "DECLINED", "a DECLINED payment must never become REFUNDED"

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                )
            ).scalars().all()
            # Only the original payment.declined row -- no payment.refunded.
            assert len(outbox_rows) == 1
            assert outbox_rows[0].event_type == "payment.declined"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_process_shipment_failed_is_a_noop_when_no_payment_exists():
    """A `shipment.failed` for an order this service never saw an
    `order.placed` for must be a safe no-op, not a crash."""
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = _random_order_id()

    try:
        await service.process_shipment_failed(
            session_factory, _shipment_failed_event(order_id=order_id)
        )

        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            assert payment is None

            outbox_rows = (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                )
            ).scalars().all()
            assert len(outbox_rows) == 0
    finally:
        await engine.dispose()
