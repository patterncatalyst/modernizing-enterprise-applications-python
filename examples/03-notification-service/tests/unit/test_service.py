"""Fast, Kafka-free idempotency proof for `app.service.record_order_placed`
against this service's real `notification` schema (same reachable, already-
migrated Postgres `conftest.py`'s `client` fixture uses). Complements
`tests/integration/test_consumer_idempotency.py`, which proves the SAME
guarantee end-to-end through a real Kafka broker and the real
`OrderPlacedConsumer`."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from app import repository, service
from app.db import create_engine, create_session_factory
from app.schemas import OrderPlacedEvent


def _event(*, order_id: int, customer_id: int) -> OrderPlacedEvent:
    return OrderPlacedEvent(
        orderId=order_id,
        customerId=customer_id,
        customerEmail="customer@example.com",
        totalCents=4999,
        confirmationMessage=f"Order #{order_id} confirmed, total $49.99",
        placedAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_record_order_placed_is_idempotent_on_redelivery():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = random.randint(10_000_000, 2_000_000_000)
    customer_id = random.randint(10_000_000, 2_000_000_000)
    event = _event(order_id=order_id, customer_id=customer_id)

    try:
        await service.record_order_placed(session_factory, event)
        # Redelivery of the IDENTICAL event -- the at-least-once outbox relay
        # scenario this dedupe check exists for.
        await service.record_order_placed(session_factory, event)

        async with session_factory() as session:
            rows = await repository.list_by_customer_id(session, customer_id)

        assert len(rows) == 1
        assert rows[0].order_id == order_id
        assert rows[0].channel == "EMAIL"
        assert rows[0].message == event.confirmation_message
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_order_placed_persists_a_new_order():
    engine = create_engine()
    session_factory = create_session_factory(engine)
    order_id = random.randint(10_000_000, 2_000_000_000)
    customer_id = random.randint(10_000_000, 2_000_000_000)
    event = _event(order_id=order_id, customer_id=customer_id)

    try:
        await service.record_order_placed(session_factory, event)

        async with session_factory() as session:
            notification = await repository.get_by_order_id(session, order_id)

        assert notification is not None
        assert notification.customer_id == customer_id
        assert notification.channel == "EMAIL"
    finally:
        await engine.dispose()
