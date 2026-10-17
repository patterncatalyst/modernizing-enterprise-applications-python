"""Standalone CLI entry point for `../../../demos/demo-schema-registry.sh`.

Runs the SAME progression `tests/test_roundtrip.py` + `tests/test_compatibility.py`
prove under Testcontainers, but against a LIVE registry/broker pair --
`REGISTRY_URL`/`KAFKA_BOOTSTRAP_SERVERS` env vars, pointed by the demo
script at its own throwaway Kafka + Apicurio containers (or, just as well,
at this project's shared `compose.yaml` services):

1. register/resolve `order-placed-v1.avsc` against Apicurio,
2. publish one demo `order.placed` Avro event and consume it back,
   asserting field-for-field equality (the round trip),
3. attach a BACKWARD compatibility rule to that same artifact,
4. register v2 (adds `giftMessage` WITH a default) -- must be ACCEPTED,
5. register v3 (retypes `totalCents` long -> string) -- must be REJECTED.

Exits non-zero (and the demo script's `set -euo pipefail` catches it) if any
step doesn't come out the way this module docstring says it must.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.consumer import OrderAvroConsumer
from app.producer import ARTIFACT_ID, DemoOrderPlaced, OrderAvroProducer
from app.registry_client import RegistryClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("schema_registry_demo.cli")

_RESOURCES = Path(__file__).resolve().parents[1] / "tests" / "resources"
_V2_SCHEMA = (_RESOURCES / "order-placed-v2-backward-compatible.avsc").read_text()
_V3_SCHEMA = (_RESOURCES / "order-placed-v3-incompatible.avsc").read_text()


async def _run_round_trip(registry: RegistryClient, bootstrap_servers: str, topic: str) -> None:
    producer = OrderAvroProducer(registry, bootstrap_servers, topic=topic)
    consumer = OrderAvroConsumer(
        registry,
        bootstrap_servers,
        topic=topic,
        group_id=f"schema-registry-demo-cli-{uuid.uuid4().hex[:8]}",
    )
    await producer.start()
    await consumer.start()
    try:
        sent = DemoOrderPlaced(
            order_id=555123,
            customer_id=1,
            customer_email="ada@example.com",
            total_cents=3998,
            confirmation_message="Order #555123 placed, total $39.98 (Avro demo)",
            placed_at=datetime.now(UTC),
            payment_method="VISA-1234",
        )
        global_id = await producer.send(sent)
        logger.info("step 1-2: registered/resolved schema globalId=%d", global_id)

        received = await consumer.poll_one(timeout=30.0)
        assert received["orderId"] == sent.order_id, "orderId mismatch on round trip"
        assert received["customerId"] == sent.customer_id, "customerId mismatch on round trip"
        assert received["customerEmail"] == sent.customer_email, "customerEmail mismatch"
        assert received["totalCents"] == sent.total_cents, "totalCents mismatch"
        assert received["confirmationMessage"] == sent.confirmation_message, (
            "confirmationMessage mismatch"
        )
        assert received["paymentMethod"] == sent.payment_method, "paymentMethod mismatch"
        logger.info(
            "step 2: round trip OK -- consumed orderId=%s field-for-field equal to what was sent",
            received["orderId"],
        )
    finally:
        await producer.stop()
        await consumer.stop()


async def _run_compatibility_checks(registry: RegistryClient) -> None:
    await registry.set_compatibility_rule(ARTIFACT_ID, config="BACKWARD")
    logger.info("step 3: attached BACKWARD compatibility rule to %r", ARTIFACT_ID)

    v2_response = await registry.register_version(ARTIFACT_ID, _V2_SCHEMA, version="2")
    if v2_response.status_code != 200:
        raise AssertionError(
            f"expected v2 (optional giftMessage) to be ACCEPTED (200), got "
            f"{v2_response.status_code}: {v2_response.text}"
        )
    logger.info("step 4: v2 (optional giftMessage, WITH a default) ACCEPTED as expected (200)")

    v3_response = await registry.register_version(ARTIFACT_ID, _V3_SCHEMA, version="3")
    v3_body = v3_response.json() if v3_response.content else {}
    if v3_response.status_code != 400 or v3_body.get("name") != "RuleViolationException":
        raise AssertionError(
            f"expected v3 (totalCents long -> string) to be REJECTED "
            f"(400, RuleViolationException), got {v3_response.status_code}: {v3_response.text}"
        )
    logger.info(
        "step 5: v3 (totalCents long -> string) REJECTED as expected (%d %s)",
        v3_response.status_code,
        v3_body["name"],
    )


async def main() -> int:
    registry_url = os.environ.get("REGISTRY_URL", "http://localhost:8095/apis/registry/v3")
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.environ.get("DEMO_TOPIC", "order.events.avro.demo")

    logger.info(
        "schema-registry-demo CLI starting (registry=%s, kafka=%s, topic=%s)",
        registry_url,
        bootstrap_servers,
        topic,
    )

    async with RegistryClient(registry_url) as registry:
        try:
            await _run_round_trip(registry, bootstrap_servers, topic)
            await _run_compatibility_checks(registry)
        except AssertionError as exc:
            logger.error("schema-registry-demo CLI FAILED: %s", exc)
            return 1

    logger.info("schema-registry-demo CLI: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
