"""`shipment.failed` consumer -- r06/DRQ-054, the stranded-payment-refund
reaction. Same `aiokafka` lifecycle-wrapper idiom as
`app/consumer.py::OrderPlacedConsumer` (same `payment-service` consumer
group, same `auto_offset_reset="earliest"`, same never-die-on-a-single-bad-
record posture), kept in its OWN module/class rather than folded into
`OrderPlacedConsumer` because it subscribes to a DIFFERENT topic
(`shipment.failed`, not `order.placed`) and delegates to a DIFFERENT
`app/service.py` entry point (`process_shipment_failed`, not
`process_order_placed`) -- one `AIOKafkaConsumer` per topic, same as a
Kafka consumer group can have multiple members independently polling
different topics.

Runs as a second background `asyncio.Task` launched from `app/main.py`'s
lifespan, alongside `OrderPlacedConsumer` and the outbox relay
(`app/relay.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import service
from app.config import Settings
from app.schemas import ShipmentFailedEvent

logger = logging.getLogger("payment_service.refund_consumer")


class ShipmentFailedConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer` subscribed to the
    frozen `shipment.failed` topic, delegating each record's idempotent
    refund-if-captured decision to `app.service.process_shipment_failed`."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def partitions_assigned(self) -> bool:
        """Mirrors `OrderPlacedConsumer.partitions_assigned` -- used by
        `GET /health` (see `app/main.py`) as a second CI readiness signal
        for this consumer's own group-join/rebalance."""
        return self._consumer is not None and len(self._consumer.assignment()) > 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.shipment_failed_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop(), name="shipment-failed-consumer")
        logger.info(
            "shipment.failed consumer started (topic=%s, group=%s, bootstrap=%s)",
            self._settings.shipment_failed_topic,
            self._settings.consumer_group,
            self._settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        logger.info("shipment.failed consumer stopped")

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                event = ShipmentFailedEvent.model_validate(record.value)
                await service.process_shipment_failed(self._session_factory, event)
                logger.info(
                    "consumed shipment.failed for order %s (shipment %s)",
                    event.order_id,
                    event.shipment_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # A single malformed/unprocessable record must not kill the
                # background task -- log and keep consuming subsequent
                # records, same discipline as `app/consumer.py`'s record loop.
                logger.exception(
                    "failed to process shipment.failed record at offset %s", record.offset
                )
