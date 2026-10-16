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
from app.schemas import OrderPlacedEvent


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
