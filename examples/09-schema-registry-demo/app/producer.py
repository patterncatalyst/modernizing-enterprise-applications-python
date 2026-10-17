"""The Avro+Apicurio DEMONSTRATOR producer -- the Python-native analogue of
the Java sibling's `OrderAvroProducer`. fastavro-encodes a synthesized
`OrderPlaced` record (field-for-field mirror of the real
`examples/07-order-service` `order.placed` JSON event -- see
`../schemas/order-placed-v1.avsc`'s docstring), registers/resolves its Avro
schema against Apicurio (idempotent: the first call creates the artifact's
version 1, every later call with the same schema resolves the existing
registration), and publishes the encoded bytes -- wrapped in this module's
hand-rolled envelope (`app/envelope.py`) carrying Apicurio's global schema
id -- to this demo's OWN `order.events.avro.demo` topic.

Deliberately standalone: no outbox, no database, no correlation to the real
order aggregate (`examples/07-order-service`) -- this is a teaching surface
for the Avro/registry mechanics, not a second production event source.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import fastavro
from aiokafka import AIOKafkaProducer

from app.envelope import encode_envelope
from app.registry_client import RegistryClient

logger = logging.getLogger("schema_registry_demo.producer")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "order-placed-v1.avsc"
ARTIFACT_ID = "order-placed-value"
TOPIC = "order.events.avro.demo"


def load_schema_json() -> str:
    """Reads `../schemas/order-placed-v1.avsc` verbatim -- the SAME text
    both registered with Apicurio and parsed for fastavro encoding, so the
    two never drift."""
    return SCHEMA_PATH.read_text()


def parsed_schema() -> dict[str, Any]:
    return fastavro.parse_schema(json.loads(load_schema_json()))


@dataclass(frozen=True)
class DemoOrderPlaced:
    """This demo's own synthesized event -- field names match
    `order-placed-v1.avsc` exactly (camelCase, matching the real JSON
    event's wire shape too)."""

    order_id: int
    customer_id: int
    customer_email: str
    total_cents: int
    confirmation_message: str
    placed_at: datetime
    payment_method: str | None = "CARD-VISA"

    def to_avro_record(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "customerId": self.customer_id,
            "customerEmail": self.customer_email,
            "totalCents": self.total_cents,
            "confirmationMessage": self.confirmation_message,
            "placedAt": self.placed_at,
            "paymentMethod": self.payment_method,
        }


def encode_order_placed(event: DemoOrderPlaced, schema: dict[str, Any]) -> bytes:
    """fastavro's `schemaless_writer` -- no embedded schema, no Confluent
    wire-format header; just the raw Avro binary. The schema id travels
    separately, in this demo's own envelope (`app/envelope.py`)."""
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, schema, event.to_avro_record())
    return buf.getvalue()


class OrderAvroProducer:
    """Lifecycle wrapper around an `AIOKafkaProducer`, mirroring every other
    service's `app/relay.py`/outbox-producer idiom in this project (e.g.
    `../05-payment-service/app/relay.py`), minus the outbox: this demo
    publishes directly, with no persistence step of its own."""

    def __init__(
        self,
        registry: RegistryClient,
        bootstrap_servers: str,
        *,
        topic: str = TOPIC,
        artifact_id: str = ARTIFACT_ID,
    ) -> None:
        self._registry = registry
        self._topic = topic
        self._artifact_id = artifact_id
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        self._schema = parsed_schema()
        self._global_id: int | None = None

    async def start(self) -> None:
        await self._producer.start()
        registered = await self._registry.register_or_resolve(
            self._artifact_id, load_schema_json()
        )
        self._global_id = registered.global_id
        logger.info(
            "schema-registry-demo: %s registered/resolved (globalId=%s, version=%s)",
            self._artifact_id,
            registered.global_id,
            registered.version,
        )

    async def stop(self) -> None:
        await self._producer.stop()

    async def send(self, event: DemoOrderPlaced) -> int:
        """Encodes, wraps, and publishes `event`; returns the Apicurio
        global schema id the envelope was stamped with (callers use this
        purely for logging/assertions -- the id is already inside the
        published bytes)."""
        if self._global_id is None:
            raise RuntimeError("OrderAvroProducer.start() must be awaited before send()")
        avro_bytes = encode_order_placed(event, self._schema)
        envelope = encode_envelope(self._global_id, avro_bytes)
        key = str(event.order_id).encode("utf-8")
        await self._producer.send_and_wait(self._topic, key=key, value=envelope)
        logger.info(
            "schema-registry-demo: published Avro order.placed orderId=%d to %s (globalId=%s)",
            event.order_id,
            self._topic,
            self._global_id,
        )
        return self._global_id
