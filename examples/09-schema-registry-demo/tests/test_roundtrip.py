"""Field-for-field round trip: encode -> register/resolve against a live
Apicurio -> publish -> consume -> decode, proving the hand-rolled envelope
(`app/envelope.py`) and the fastavro + Apicurio v3 REST combination work
together end to end. The pure-Python analogue of the Java sibling's
`OrderAvroRoundTripTest` (which runs against Quarkus Dev Services); here,
Testcontainers (`tests/conftest.py`) plays that role. Requires a reachable
Docker daemon.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.consumer import OrderAvroConsumer
from app.producer import DemoOrderPlaced, OrderAvroProducer
from app.registry_client import RegistryClient

TOPIC = "order.events.avro.demo.roundtrip-test"


@pytest.mark.asyncio
async def test_emitted_event_is_consumed_field_for_field_equal(
    kafka_bootstrap_servers: str, registry_base_url: str
) -> None:
    async with (
        RegistryClient(registry_base_url) as producer_registry,
        RegistryClient(registry_base_url) as consumer_registry,
    ):
        producer = OrderAvroProducer(producer_registry, kafka_bootstrap_servers, topic=TOPIC)
        consumer = OrderAvroConsumer(
            consumer_registry,
            kafka_bootstrap_servers,
            topic=TOPIC,
            group_id="schema-registry-demo-roundtrip-test",
        )
        await producer.start()
        await consumer.start()
        try:
            sent = DemoOrderPlaced(
                order_id=555123,
                customer_id=1,
                customer_email="ada@example.com",
                total_cents=3998,
                confirmation_message="Order #555123 placed, total $39.98",
                placed_at=datetime.now(UTC),
                payment_method="VISA-1234",
            )
            await producer.send(sent)

            received = await consumer.poll_one(timeout=30.0)

            assert received["orderId"] == sent.order_id
            assert received["customerId"] == sent.customer_id
            assert received["customerEmail"] == sent.customer_email
            assert received["totalCents"] == sent.total_cents
            assert received["confirmationMessage"] == sent.confirmation_message
            assert received["paymentMethod"] == sent.payment_method
            # Avro's timestamp-millis logical type truncates to millisecond
            # precision on the wire; truncate both sides before comparing
            # so a sub-millisecond difference introduced before
            # serialization doesn't produce a false failure (same discipline
            # the Java sibling's OrderAvroRoundTripTest documents).
            expected_millis = sent.placed_at.replace(
                microsecond=(sent.placed_at.microsecond // 1000) * 1000
            )
            assert received["placedAt"] == expected_millis
        finally:
            await producer.stop()
            await consumer.stop()
