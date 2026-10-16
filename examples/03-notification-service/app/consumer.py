"""`order.placed` consumer -- NET-NEW for this service (DRQ-035): the
monolith never consumed its own `order.placed` event (it only ever sent the
confirmation synchronously, in-process), so there is no Django/Spring
original to lift here, unlike `02-review-service`'s HTTP routes. Authored
directly on `aiokafka` idioms (DRQ-019: aiokafka is this project's Kafka
client on both the producer and consumer sides).

Binds to the `notification-service` consumer group (see `app/config.py`), so
across a replica set exactly one replica persists any given event --
`auto_offset_reset="earliest"` so a fresh deployment (empty consumer-group
offset) backfills from the topic's start rather than only seeing events
published after it joined.

Runs as a background `asyncio.Task` launched from `app/main.py`'s lifespan,
not inside the request/response cycle -- the read path (`app/routes.py`) and
the write path (this module, via `app/service.py`) are fully decoupled.
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import service
from app.config import Settings
from app.schemas import OrderPlacedEvent

logger = logging.getLogger("notification_service.consumer")


class OrderPlacedConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer` subscribed to the
    frozen `order.placed` topic, delegating each record's idempotent
    persistence to `app.service.record_order_placed`."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def partitions_assigned(self) -> bool:
        """Used by `GET /health` (see `app/main.py`) as a CI readiness
        signal: a consumer with no partition assignment yet hasn't
        completed its group-join/rebalance, so a reader polling this
        service right after startup would see an empty result even once a
        matching `order.placed` event has already been published."""
        return self._consumer is not None and len(self._consumer.assignment()) > 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.order_placed_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop(), name="order-placed-consumer")
        logger.info(
            "order.placed consumer started (topic=%s, group=%s, bootstrap=%s)",
            self._settings.order_placed_topic,
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
        logger.info("order.placed consumer stopped")

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                event = OrderPlacedEvent.model_validate(record.value)
                await service.record_order_placed(self._session_factory, event)
                logger.info(
                    "consumed order.placed for order %s (customer %s)",
                    event.order_id,
                    event.customer_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # A single malformed/unprocessable record must not kill the
                # background task -- log and keep consuming subsequent
                # records rather than silently stopping delivery for every
                # order placed afterward.
                logger.exception(
                    "failed to process order.placed record at offset %s", record.offset
                )
