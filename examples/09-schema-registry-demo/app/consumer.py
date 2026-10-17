"""The Avro+Apicurio DEMONSTRATOR consumer -- the Python-native analogue of
the Java sibling's `OrderAvroConsumer`. Unwraps this module's hand-rolled
envelope (`app/envelope.py`) to recover the Apicurio global schema id the
producer stamped onto each record, fetches that EXACT writer schema from
the registry (never assuming its own locally-parsed copy of
`../schemas/order-placed-v1.avsc` is what actually produced the bytes --
the honest point of a schema registry), caches it by global id, and
fastavro-decodes the payload back into a plain `dict`.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any

import fastavro
from aiokafka import AIOKafkaConsumer

from app.envelope import decode_envelope
from app.producer import TOPIC
from app.registry_client import RegistryClient

logger = logging.getLogger("schema_registry_demo.consumer")

DEFAULT_GROUP_ID = "schema-registry-demo"


class OrderAvroConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer`, mirroring every other
    service's `app/consumer.py` idiom in this project (e.g.
    `../05-payment-service/app/consumer.py`'s start/stop shape), but exposed
    as a `poll_one()` request/response call rather than a background
    `asyncio.Task` -- `tests/test_roundtrip.py` and `app/demo_cli.py` both
    need exactly one proof event back, not an open-ended consume loop."""

    def __init__(
        self,
        registry: RegistryClient,
        bootstrap_servers: str,
        *,
        topic: str = TOPIC,
        group_id: str = DEFAULT_GROUP_ID,
    ) -> None:
        self._registry = registry
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._schema_cache: dict[int, Any] = {}

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        logger.info(
            "schema-registry-demo: consumer started (topic=%s, group=%s)",
            self._topic,
            self._group_id,
        )

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        logger.info("schema-registry-demo: consumer stopped")

    async def _schema_for(self, global_id: int) -> Any:
        schema = self._schema_cache.get(global_id)
        if schema is None:
            schema_json = await self._registry.get_schema_by_global_id(global_id)
            schema = fastavro.parse_schema(json.loads(schema_json))
            self._schema_cache[global_id] = schema
        return schema

    async def poll_one(self, timeout: float = 30.0) -> dict[str, Any]:
        """Waits up to `timeout` seconds for exactly one record, decodes
        it via the writer schema Apicurio reports for its envelope's
        global id, and returns the Avro record as a plain `dict`."""
        if self._consumer is None:
            raise RuntimeError("OrderAvroConsumer.start() must be awaited before poll_one()")
        record = await asyncio.wait_for(self._consumer.getone(), timeout=timeout)
        global_id, avro_bytes = decode_envelope(record.value)
        schema = await self._schema_for(global_id)
        decoded: dict[str, Any] = fastavro.schemaless_reader(io.BytesIO(avro_bytes), schema)
        logger.info(
            "schema-registry-demo: consumed orderId=%s (globalId=%s)",
            decoded.get("orderId"),
            global_id,
        )
        return decoded
