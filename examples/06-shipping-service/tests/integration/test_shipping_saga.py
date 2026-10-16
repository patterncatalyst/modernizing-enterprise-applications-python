"""Testcontainers integration test -- proves the full ORCHESTRATED saga round
trip end-to-end against a REAL Kafka broker and REAL Postgres: a
`payment.captured` event triggers `app/consumer.py`, which starts a saga that
`app/orchestrator.py` drives through all four steps, and `app/relay.py`
publishes the terminal outcome onto a real topic -- the sibling of
`05-payment-service/tests/integration/test_payment_choreography.py`, proving
the ORCHESTRATED wiring the same way that proves the CHOREOGRAPHED one.

`app/enrich_client.py::fetch_shipping_address` is monkeypatched here too
(same as `tests/unit/test_orchestrator.py`) -- this test is about proving the
Kafka/outbox/saga wiring, not standing up a live monolith.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app import enrich_client, repository
from app.config import Settings
from app.consumer import PaymentCapturedConsumer
from app.db import create_engine, create_session_factory
from app.models import SHIPMENT_CANCELLED, SHIPMENT_DISPATCHED
from app.relay import OutboxRelay

pytestmark = pytest.mark.integration

PAYMENT_CAPTURED_TOPIC = "payment.captured"
SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"
SHIPMENT_FAILED_TOPIC = "shipment.failed"


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


def _payment_captured_payload(*, order_id: int) -> dict:
    return {
        "orderId": order_id,
        "paymentId": random.randint(1, 1_000_000),
        "amountCents": 4999,
        "method": "CARD",
        "status": "CAPTURED",
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
async def orchestrated_saga(database_url: str, kafka_bootstrap_servers: str, monkeypatch):
    """Spins up a real `PaymentCapturedConsumer` + `OutboxRelay` pair (the
    same two background tasks `app/main.py`'s lifespan starts), plus a
    producer to publish `payment.captured` events -- torn down after each
    test. `addresses` lets each test control what the (monkeypatched)
    `enrich` step sees for its own order_id."""
    addresses: dict[int, str] = {}

    async def _fake_fetch(*, base_url: str, order_id: int, timeout_s: float) -> str:
        return addresses[order_id]

    monkeypatch.setattr(enrich_client, "fetch_shipping_address", _fake_fetch)

    order_id = random.randint(10_000_000, 2_000_000_000)
    settings = Settings(
        http_port=8087,
        database_url=database_url,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        monolith_base_url="http://monolith.invalid",
        payment_captured_topic=PAYMENT_CAPTURED_TOPIC,
        shipment_dispatched_topic=SHIPMENT_DISPATCHED_TOPIC,
        shipment_failed_topic=SHIPMENT_FAILED_TOPIC,
        consumer_group=f"shipping-service-test-{order_id}",
        outbox_poll_ms=200,
        enrich_timeout_s=1.0,
    )

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)

    producer = AIOKafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )
    await producer.start()

    consumer = PaymentCapturedConsumer(settings, session_factory)
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    await relay.start()

    try:
        yield order_id, settings, session_factory, producer, addresses
    finally:
        await relay.stop()
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_payment_captured_triggers_saga_and_publishes_shipment_dispatched(
    orchestrated_saga,
):
    order_id, settings, session_factory, producer, addresses = orchestrated_saga
    addresses[order_id] = "500 Kafka Court"

    await producer.send_and_wait(
        PAYMENT_CAPTURED_TOPIC,
        value=_payment_captured_payload(order_id=order_id),
        key=str(order_id),
    )

    async def _shipment_dispatched():
        async with session_factory() as session:
            rows = await repository.list_shipments_by_order_id(session, order_id)
            return rows[0] if rows else None

    shipment = await _wait_until(_shipment_dispatched)
    assert shipment.status == SHIPMENT_DISPATCHED

    published = await _consume_one_matching(
        topic=SHIPMENT_DISPATCHED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"shipment-dispatched-verify-{order_id}",
        order_id=order_id,
    )
    assert published["status"] == "DISPATCHED"
    assert published["shipmentId"] == shipment.id
    assert published["address"] == "500 Kafka Court"
    assert "occurredAt" in published


@pytest.mark.asyncio
async def test_ship_fail_sentinel_publishes_shipment_failed(orchestrated_saga):
    order_id, settings, session_factory, producer, addresses = orchestrated_saga
    addresses[order_id] = "1 SHIP-FAIL Plaza"

    await producer.send_and_wait(
        PAYMENT_CAPTURED_TOPIC,
        value=_payment_captured_payload(order_id=order_id),
        key=str(order_id),
    )

    async def _shipment_cancelled():
        async with session_factory() as session:
            rows = await repository.list_shipments_by_order_id(session, order_id)
            if rows and rows[0].status == SHIPMENT_CANCELLED:
                return rows[0]
            return None

    shipment = await _wait_until(_shipment_cancelled)

    published = await _consume_one_matching(
        topic=SHIPMENT_FAILED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"shipment-failed-verify-{order_id}",
        order_id=order_id,
    )
    assert published["status"] == "FAILED"
    assert published["shipmentId"] == shipment.id
    assert "SHIP-FAIL" in published["reason"]
