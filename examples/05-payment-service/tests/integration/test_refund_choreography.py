"""Testcontainers integration test -- r06/DRQ-054, proves the full refund
choreography end-to-end against a REAL Kafka broker and REAL Postgres:

1. a `shipment.failed` for an order with a CAPTURED payment -> the Payment
   transitions to REFUNDED AND exactly one `payment.refunded` record is
   published;
2. redelivering the IDENTICAL `shipment.failed` event -> still exactly one
   REFUNDED payment and exactly one `payment.refunded` outbox row (the
   idempotent-dedupe guarantee, mirroring
   `test_payment_choreography.py::test_redelivered_order_placed_event_yields_exactly_one_payment_and_outbox_row`);
3. a `shipment.failed` for an order whose payment was DECLINED (never
   captured) -> no refund, no `payment.refunded` event -- this service never
   refunds money it never took.

Mirrors `test_payment_choreography.py`'s fixtures/helpers, but spins up BOTH
`OrderPlacedConsumer` and `ShipmentFailedConsumer` (plus the shared
`OutboxRelay`) -- the same pair of background tasks `app/main.py`'s lifespan
starts.
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
from app.refund_consumer import ShipmentFailedConsumer
from app.relay import OutboxRelay

pytestmark = pytest.mark.integration

ORDER_PLACED_TOPIC = "order.placed"
SHIPMENT_FAILED_TOPIC = "shipment.failed"
PAYMENT_CAPTURED_TOPIC = "payment.captured"
PAYMENT_DECLINED_TOPIC = "payment.declined"
PAYMENT_REFUNDED_TOPIC = "payment.refunded"


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


def _shipment_failed_payload(*, order_id: int) -> dict:
    return {
        "orderId": order_id,
        "shipmentId": random.randint(1, 1_000_000),
        "address": "123 Main St, Springfield",
        "status": "FAILED",
        "reason": "carrier booking failed",
        "occurredAt": datetime.now(UTC).isoformat(),
    }


async def _consume_one_matching(
    *,
    topic: str,
    kafka_bootstrap_servers: str,
    group_id: str,
    order_id: int,
    timeout_s: float = 20.0,
) -> dict:
    """Same filtering helper as `test_payment_choreography.py` -- the broker
    is shared across the whole Testcontainers session, so filtering by
    `orderId` makes each test's assertion independent of ordering/
    interleaving across tests."""
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
async def refund_choreography(database_url: str, kafka_bootstrap_servers: str):
    """Spins up a real `OrderPlacedConsumer` + `ShipmentFailedConsumer` +
    `OutboxRelay` trio -- the same three background tasks `app/main.py`'s
    lifespan starts -- plus a producer to publish `order.placed`/
    `shipment.failed` events, torn down after each test."""
    order_id = random.randint(10_000_000, 2_000_000_000)
    settings = Settings(
        http_port=8085,
        database_url=database_url,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        order_placed_topic=ORDER_PLACED_TOPIC,
        shipment_failed_topic=SHIPMENT_FAILED_TOPIC,
        payment_captured_topic=PAYMENT_CAPTURED_TOPIC,
        payment_declined_topic=PAYMENT_DECLINED_TOPIC,
        payment_refunded_topic=PAYMENT_REFUNDED_TOPIC,
        consumer_group=f"payment-service-refund-test-{order_id}",
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

    refund_consumer = ShipmentFailedConsumer(settings, session_factory)
    await refund_consumer.start()

    relay = OutboxRelay(settings, session_factory)
    await relay.start()

    try:
        yield order_id, settings, session_factory, producer
    finally:
        await relay.stop()
        await refund_consumer.stop()
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_shipment_failed_refunds_captured_payment_and_publishes_payment_refunded(
    refund_choreography,
):
    order_id, settings, session_factory, producer = refund_choreography

    await producer.send_and_wait(
        ORDER_PLACED_TOPIC,
        value=_order_placed_payload(order_id=order_id, payment_method="VISA-1234"),
        key=str(order_id),
    )

    async def _payment_captured():
        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            return payment if payment is not None and payment.status == "CAPTURED" else None

    captured_payment = await _wait_until(_payment_captured)

    await producer.send_and_wait(
        SHIPMENT_FAILED_TOPIC,
        value=_shipment_failed_payload(order_id=order_id),
        key=str(order_id),
    )

    async def _payment_refunded():
        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            return payment if payment is not None and payment.status == "REFUNDED" else None

    payment = await _wait_until(_payment_refunded)
    assert payment.id == captured_payment.id

    published = await _consume_one_matching(
        topic=PAYMENT_REFUNDED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"payment-refunded-verify-{order_id}",
        order_id=order_id,
    )
    assert published["status"] == "REFUNDED"
    assert published["paymentId"] == payment.id
    assert published["amountCents"] == 4999
    assert "method" not in published
    assert "reason" not in published
    assert "occurredAt" in published

    async with session_factory() as session:
        rows = await repository.list_by_order_id(session, order_id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_redelivered_shipment_failed_yields_exactly_one_refund(refund_choreography):
    order_id, settings, session_factory, producer = refund_choreography

    await producer.send_and_wait(
        ORDER_PLACED_TOPIC,
        value=_order_placed_payload(order_id=order_id, payment_method="VISA-1234"),
        key=str(order_id),
    )

    async def _payment_captured():
        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            return payment if payment is not None and payment.status == "CAPTURED" else None

    await _wait_until(_payment_captured)

    shipment_failed_payload = _shipment_failed_payload(order_id=order_id)
    # Publish the SAME shipment.failed event twice -- the at-least-once
    # redelivery scenario.
    await producer.send_and_wait(
        SHIPMENT_FAILED_TOPIC, value=shipment_failed_payload, key=str(order_id)
    )
    await producer.send_and_wait(
        SHIPMENT_FAILED_TOPIC, value=shipment_failed_payload, key=str(order_id)
    )

    async def _payment_refunded():
        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            return payment if payment is not None and payment.status == "REFUNDED" else None

    await _wait_until(_payment_refunded)

    # Give the background consume loop time to also work through the
    # (redundant) second delivery before asserting the final count, so this
    # isn't a race against the idempotency check itself.
    await asyncio.sleep(3.0)

    async with session_factory() as session:
        payments = await repository.list_by_order_id(session, order_id)
        refund_outbox_rows = (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == str(order_id))
                .where(OutboxEvent.event_type == "payment.refunded")
            )
        ).scalars().all()

    assert len(payments) == 1
    assert payments[0].status == "REFUNDED"
    assert len(refund_outbox_rows) == 1, (
        "redelivery of the same shipment.failed event must not emit a second payment.refunded"
    )


@pytest.mark.asyncio
async def test_shipment_failed_does_not_refund_a_declined_payment(refund_choreography):
    order_id, settings, session_factory, producer = refund_choreography

    await producer.send_and_wait(
        ORDER_PLACED_TOPIC,
        value=_order_placed_payload(order_id=order_id, payment_method="CARD-DECLINE"),
        key=str(order_id),
    )

    async def _payment_declined():
        async with session_factory() as session:
            payment = await repository.get_by_order_id(session, order_id)
            return payment if payment is not None and payment.status == "DECLINED" else None

    declined_payment = await _wait_until(_payment_declined)

    await producer.send_and_wait(
        SHIPMENT_FAILED_TOPIC,
        value=_shipment_failed_payload(order_id=order_id),
        key=str(order_id),
    )

    # There is no positive event to wait on here (a no-op produces nothing),
    # so give the consumer a bounded window to (incorrectly) act before
    # asserting it didn't.
    await asyncio.sleep(3.0)

    async with session_factory() as session:
        payment = await repository.get_by_order_id(session, order_id)
        outbox_rows = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
            )
        ).scalars().all()

    assert payment is not None
    assert payment.status == "DECLINED"
    assert payment.id == declined_payment.id
    assert len(outbox_rows) == 1
    assert outbox_rows[0].event_type == "payment.declined"
