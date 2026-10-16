"""Testcontainers integration test -- proves the full choreographed round
trip end-to-end against a REAL Kafka broker and REAL Postgres:

1. a normal `order.placed` event -> exactly one CAPTURED `Payment` row AND
   one published `payment.captured` record;
2. a DECLINE-method `order.placed` event -> exactly one DECLINED `Payment`
   row AND one published `payment.declined` record (with a `reason`);
3. redelivering the IDENTICAL `order.placed` event -> exactly one `Payment`
   row and exactly one outbox row (the idempotent-dedupe guarantee,
   mirroring `03-notification-service`'s own Testcontainers proof and this
   service's `tests/unit/test_service.py::test_process_order_placed_is_idempotent_on_redelivery`).
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select

from app import repository
from app.config import Settings
from app.consumer import OrderPlacedConsumer
from app.db import create_engine, create_session_factory
from app.models import OutboxEvent
from app.relay import OutboxRelay

pytestmark = pytest.mark.integration

ORDER_PLACED_TOPIC = "order.placed"
PAYMENT_CAPTURED_TOPIC = "payment.captured"
PAYMENT_DECLINED_TOPIC = "payment.declined"


async def _wait_until(predicate, *, timeout_s: float = 20.0, interval_s: float = 0.25):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        result = await predicate()
        if result:
            return result
        if loop.time() >= deadline:
            raise AssertionError(f"condition not met within {timeout_s}s")
        await asyncio.sleep(interval_s)


def _order_placed_payload(*, order_id: int, payment_method: str | None) -> dict:
    return {
        "orderId": order_id,
        "customerId": random.randint(10_000_000, 2_000_000_000),
        "customerEmail": "customer@example.com",
        "totalCents": 4999,
        "confirmationMessage": f"Order #{order_id} confirmed, total $49.99",
        "placedAt": datetime.now(UTC).isoformat(),
        "paymentMethod": payment_method,
    }


async def _consume_one_matching(
    *,
    topic: str,
    kafka_bootstrap_servers: str,
    group_id: str,
    order_id: int,
    timeout_s: float = 20.0,
) -> dict:
    """Reads `topic` from the beginning in a dedicated consumer group until a
    record whose payload `orderId` matches is found -- the broker is shared
    across the whole Testcontainers session, so other tests' records may also
    be present; filtering by `orderId` makes each test's assertion
    independent of ordering/interleaving."""
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap_servers,
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await consumer.start()
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AssertionError(
                    f"no record with orderId={order_id} on topic {topic} within {timeout_s}s"
                )
            batches = await consumer.getmany(timeout_ms=int(remaining * 1000))
            for records in batches.values():
                for record in records:
                    if record.value.get("orderId") == order_id:
                        return record.value
    finally:
        await consumer.stop()


@pytest.fixture
async def choreography(database_url: str, kafka_bootstrap_servers: str):
    """Spins up a real `OrderPlacedConsumer` + `OutboxRelay` pair (the same
    two background tasks `app/main.py`'s lifespan starts), plus a producer to
    publish `order.placed` events -- torn down after each test."""
    order_id = random.randint(10_000_000, 2_000_000_000)
    settings = Settings(
        http_port=8085,
        database_url=database_url,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        order_placed_topic=ORDER_PLACED_TOPIC,
        shipment_failed_topic="shipment.failed",
        payment_captured_topic=PAYMENT_CAPTURED_TOPIC,
        payment_declined_topic=PAYMENT_DECLINED_TOPIC,
        payment_refunded_topic="payment.refunded",
        consumer_group=f"payment-service-test-{order_id}",
        outbox_poll_ms=200,
    )

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)

    producer = AIOKafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )
    await producer.start()

    consumer = OrderPlacedConsumer(settings, session_factory)
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    await relay.start()

    try:
        yield order_id, settings, session_factory, producer
    finally:
        await relay.stop()
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_order_placed_captures_payment_and_publishes_payment_captured(choreography):
    order_id, settings, session_factory, producer = choreography

    await producer.send_and_wait(
        ORDER_PLACED_TOPIC,
        value=_order_placed_payload(order_id=order_id, payment_method="VISA-1234"),
        key=str(order_id),
    )

    async def _payment_recorded():
        async with session_factory() as session:
            return await repository.get_by_order_id(session, order_id)

    payment = await _wait_until(_payment_recorded)
    assert payment.status == "CAPTURED"

    published = await _consume_one_matching(
        topic=PAYMENT_CAPTURED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"payment-captured-verify-{order_id}",
        order_id=order_id,
    )
    assert published["status"] == "CAPTURED"
    assert published["paymentId"] == payment.id
    assert published["amountCents"] == 4999
    assert published["method"] == "VISA-1234"
    assert "reason" not in published
    assert "occurredAt" in published

    async with session_factory() as session:
        rows = await repository.list_by_order_id(session, order_id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_decline_method_declines_payment_and_publishes_payment_declined(choreography):
    order_id, settings, session_factory, producer = choreography

    await producer.send_and_wait(
        ORDER_PLACED_TOPIC,
        value=_order_placed_payload(order_id=order_id, payment_method="CARD-DECLINE"),
        key=str(order_id),
    )

    async def _payment_recorded():
        async with session_factory() as session:
            return await repository.get_by_order_id(session, order_id)

    payment = await _wait_until(_payment_recorded)
    assert payment.status == "DECLINED"

    published = await _consume_one_matching(
        topic=PAYMENT_DECLINED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"payment-declined-verify-{order_id}",
        order_id=order_id,
    )
    assert published["status"] == "DECLINED"
    assert published["paymentId"] == payment.id
    assert "reason" in published
    assert "DECLINE" in published["reason"].upper()


@pytest.mark.asyncio
async def test_redelivered_order_placed_event_yields_exactly_one_payment_and_outbox_row(
    choreography,
):
    order_id, settings, session_factory, producer = choreography
    payload = _order_placed_payload(order_id=order_id, payment_method="VISA-1234")

    # Publish the SAME event twice, keyed by orderId like the frozen
    # contract specifies -- the at-least-once redelivery scenario.
    await producer.send_and_wait(ORDER_PLACED_TOPIC, value=payload, key=str(order_id))
    await producer.send_and_wait(ORDER_PLACED_TOPIC, value=payload, key=str(order_id))

    async def _payment_recorded():
        async with session_factory() as session:
            return await repository.get_by_order_id(session, order_id)

    await _wait_until(_payment_recorded)

    # Give the background consume loop time to also work through the
    # (redundant) second delivery before asserting the final count, so this
    # isn't a race against the idempotency check itself.
    await asyncio.sleep(3.0)

    async with session_factory() as session:
        payments = await repository.list_by_order_id(session, order_id)
        outbox_rows = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
            )
        ).scalars().all()

    assert len(payments) == 1, "redelivery of the same order.placed event must not duplicate"
    assert len(outbox_rows) == 1, "redelivery must not emit a second outbox event"
