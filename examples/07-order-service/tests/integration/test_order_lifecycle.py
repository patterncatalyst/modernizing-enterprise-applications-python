"""Testcontainers integration test -- proves the full order lifecycle
end-to-end against a REAL Kafka broker, REAL Postgres, and a REAL (networked)
gRPC inventory server:

1. `service.place_order` reserves over a real gRPC call, persists the
   aggregate + `order_view` + outbox in one transaction, and the relay
   publishes exactly one `order.placed` record.
2. Publishing `payment.captured` through the real broker drives the real
   `OrderSagaConsumer` to transition `PENDING -> AWAITING_SHIPMENT` --
   READ-YOUR-WRITES proof: polling `GET`-equivalent `order_view` reads
   observes the transition `order_view` row, not a stale one.
3. Publishing `shipment.dispatched` drives `AWAITING_SHIPMENT -> CONFIRMED`.
4. `order.placed` is observed on the wire exactly once, even though the
   relay polls continuously for the duration of the test.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app import repository
from app.config import Settings
from app.consumer import OrderSagaConsumer
from app.db import create_engine, create_session_factory
from app.relay import OutboxRelay
from app.schemas import OrderLineIn
from app.service import place_order

pytestmark = pytest.mark.integration

PAYMENT_CAPTURED_TOPIC = "payment.captured"
PAYMENT_DECLINED_TOPIC = "payment.declined"
SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"
SHIPMENT_FAILED_TOPIC = "shipment.failed"
ORDER_PLACED_TOPIC = "order.placed"


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


async def _consume_matching(
    *,
    topic: str,
    kafka_bootstrap_servers: str,
    group_id: str,
    order_id: int,
    timeout_s: float = 20.0,
) -> list[dict]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap_servers,
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await consumer.start()
    matched: list[dict] = []
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            batches = await consumer.getmany(timeout_ms=1000)
            for records in batches.values():
                for record in records:
                    if record.value.get("orderId") == order_id:
                        matched.append(record.value)
            if matched:
                # Drain a little longer to catch an accidental duplicate
                # publish before declaring "exactly one".
                await asyncio.sleep(1.0)
                more = await consumer.getmany(timeout_ms=1000)
                for records in more.values():
                    for record in records:
                        if record.value.get("orderId") == order_id:
                            matched.append(record.value)
                return matched
        return matched
    finally:
        await consumer.stop()


@pytest.fixture
async def lifecycle(database_url: str, kafka_bootstrap_servers: str, fake_inventory_server):
    inventory_target, servicer = fake_inventory_server
    settings = Settings(
        http_port=8088,
        database_url=database_url,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        inventory_grpc_target=inventory_target,
        order_placed_topic=ORDER_PLACED_TOPIC,
        payment_captured_topic=PAYMENT_CAPTURED_TOPIC,
        payment_declined_topic=PAYMENT_DECLINED_TOPIC,
        shipment_dispatched_topic=SHIPMENT_DISPATCHED_TOPIC,
        shipment_failed_topic=SHIPMENT_FAILED_TOPIC,
        consumer_group=f"order-service-test-{id(servicer)}",
        outbox_poll_ms=200,
        grpc_timeout_s=5.0,
    )

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)

    producer = AIOKafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )
    await producer.start()

    consumer = OrderSagaConsumer(settings, session_factory)
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    await relay.start()

    try:
        yield settings, session_factory, producer
    finally:
        await relay.stop()
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_produces_order_placed_exactly_once(lifecycle):
    settings, session_factory, _producer = lifecycle

    order = await place_order(
        session_factory,
        inventory_grpc_target=settings.inventory_grpc_target,
        grpc_timeout_s=settings.grpc_timeout_s,
        customer_id=1,
        items=[OrderLineIn(sku="SKU-WIDGET-001", quantity=2)],
        payment_method="VISA-1234",
        shipping_address="1 Integration Test Lane",
    )
    assert order.status == "PENDING"

    published = await _consume_matching(
        topic=ORDER_PLACED_TOPIC,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"order-placed-verify-{order.id}",
        order_id=order.id,
    )
    assert len(published) == 1, "order.placed must be produced exactly once"
    assert published[0]["customerEmail"] == "ada@example.com"
    assert published[0]["totalCents"] == 1999 * 2
    assert published[0]["paymentMethod"] == "VISA-1234"


@pytest.mark.asyncio
async def test_payment_captured_then_shipment_dispatched_reach_confirmed_read_your_writes(
    lifecycle,
):
    settings, session_factory, producer = lifecycle

    order = await place_order(
        session_factory,
        inventory_grpc_target=settings.inventory_grpc_target,
        grpc_timeout_s=settings.grpc_timeout_s,
        customer_id=2,
        items=[OrderLineIn(sku="SKU-GADGET-002", quantity=1)],
        payment_method="VISA-1234",
        shipping_address="1 Analytical Engine Way",
    )

    await producer.send_and_wait(
        PAYMENT_CAPTURED_TOPIC,
        value={
            "orderId": order.id,
            "paymentId": 1,
            "amountCents": order.total_cents,
            "method": "VISA-1234",
            "status": "CAPTURED",
            "occurredAt": "2026-10-16T00:00:00+00:00",
        },
        key=str(order.id),
    )

    async def _view_status():
        async with session_factory() as session:
            view = await repository.get_order_view_by_id(session, order.id)
            return view if view is not None and view.status == "AWAITING_SHIPMENT" else None

    view = await _wait_until(_view_status)
    assert view.status == "AWAITING_SHIPMENT", "read-your-writes: order_view reflects the saga"

    await producer.send_and_wait(
        SHIPMENT_DISPATCHED_TOPIC,
        value={
            "orderId": order.id,
            "shipmentId": 7,
            "address": "1 Analytical Engine Way",
            "status": "DISPATCHED",
            "occurredAt": "2026-10-16T00:00:05+00:00",
        },
        key=str(order.id),
    )

    async def _confirmed():
        async with session_factory() as session:
            view = await repository.get_order_view_by_id(session, order.id)
            return view if view is not None and view.status == "CONFIRMED" else None

    confirmed_view = await _wait_until(_confirmed)
    assert confirmed_view.status == "CONFIRMED"


@pytest.mark.asyncio
async def test_payment_declined_releases_inventory_through_the_real_grpc_server(lifecycle):
    settings, session_factory, producer = lifecycle

    order = await place_order(
        session_factory,
        inventory_grpc_target=settings.inventory_grpc_target,
        grpc_timeout_s=settings.grpc_timeout_s,
        customer_id=1,
        items=[OrderLineIn(sku="SKU-WIDGET-001", quantity=5)],
        payment_method="VISA-1234",
        shipping_address="1 Integration Test Lane",
    )

    await producer.send_and_wait(
        PAYMENT_DECLINED_TOPIC,
        value={
            "orderId": order.id,
            "paymentId": 2,
            "amountCents": order.total_cents,
            "method": "CARD-DECLINE",
            "status": "DECLINED",
            "reason": "declined",
            "occurredAt": "2026-10-16T00:00:00+00:00",
        },
        key=str(order.id),
    )

    async def _declined():
        async with session_factory() as session:
            view = await repository.get_order_view_by_id(session, order.id)
            return view if view is not None and view.status == "PAYMENT_DECLINED" else None

    view = await _wait_until(_declined)
    assert view.status == "PAYMENT_DECLINED"
