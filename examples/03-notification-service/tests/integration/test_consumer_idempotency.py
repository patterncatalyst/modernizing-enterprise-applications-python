"""Testcontainers integration test -- proves `OrderPlacedConsumer` +
`app.service.record_order_placed`'s idempotent dedupe end-to-end against a
REAL Kafka broker and REAL Postgres: publishing the IDENTICAL `order.placed`
event twice yields exactly ONE notification row, mirroring the at-least-once
redelivery a real outbox relay (`00-monolith`'s `outbox_relay` management
command) can actually produce on a crash-between-send-and-commit."""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime

import pytest
from aiokafka import AIOKafkaProducer

from app import repository
from app.config import Settings
from app.consumer import OrderPlacedConsumer
from app.db import create_engine, create_session_factory

pytestmark = pytest.mark.integration


async def _wait_until(predicate, *, timeout_s: float = 20.0, interval_s: float = 0.25) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        if await predicate():
            return
        if loop.time() >= deadline:
            raise AssertionError(f"condition not met within {timeout_s}s")
        await asyncio.sleep(interval_s)


@pytest.mark.asyncio
async def test_redelivered_order_placed_event_yields_one_notification(
    database_url: str, kafka_bootstrap_servers: str
):
    order_id = random.randint(10_000_000, 2_000_000_000)
    customer_id = random.randint(10_000_000, 2_000_000_000)
    topic = "order.placed"
    # A unique, test-scoped consumer group: this test's consumer must read
    # the topic from the beginning (`auto_offset_reset="earliest"`) rather
    # than share offsets with any other consumer of the same Testcontainers
    # broker.
    group_id = f"notification-service-test-{order_id}"

    event_payload = {
        "orderId": order_id,
        "customerId": customer_id,
        "customerEmail": "customer@example.com",
        "totalCents": 4999,
        "confirmationMessage": f"Order #{order_id} confirmed, total $49.99",
        "placedAt": datetime.now(UTC).isoformat(),
    }

    settings = Settings(
        port=8002,
        database_url=database_url,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        order_placed_topic=topic,
        consumer_group=group_id,
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

    try:
        # Publish the SAME event twice, keyed by orderId like the frozen
        # contract specifies -- the at-least-once redelivery scenario.
        await producer.send_and_wait(topic, value=event_payload, key=str(order_id))
        await producer.send_and_wait(topic, value=event_payload, key=str(order_id))

        async def _notification_recorded() -> bool:
            async with session_factory() as session:
                return await repository.get_by_order_id(session, order_id) is not None

        await _wait_until(_notification_recorded)

        # Give the background consume loop time to also work through the
        # (redundant) second delivery before asserting the final count, so
        # this isn't a race against the idempotency check itself.
        await asyncio.sleep(3.0)

        async with session_factory() as session:
            rows = await repository.list_by_customer_id(session, customer_id)

        assert len(rows) == 1, "redelivery of the same order.placed event must not duplicate"
        assert rows[0].order_id == order_id
        assert rows[0].customer_id == customer_id
        assert rows[0].channel == "EMAIL"
        assert rows[0].message == event_payload["confirmationMessage"]
    finally:
        await consumer.stop()
        await producer.stop()
        await engine.dispose()
