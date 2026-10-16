"""`payment.captured` consumer -- the saga's TRIGGER. Same lifecycle-wrapper
shape as every other standalone service's consumer in this project
(`05-payment-service/app/consumer.py::OrderPlacedConsumer`), binding to the
`shipping-service` consumer group (see `app/config.py`) so across a replica
set exactly one replica starts any given order's saga --
`auto_offset_reset="earliest"` so a fresh deployment (empty consumer-group
offset) backfills from the topic's start rather than only seeing events
published after it joined.

Runs as a background `asyncio.Task` launched from `app/main.py`'s lifespan,
alongside the outbox relay (`app/relay.py`) -- the read path (`app/routes.py`)
and both write/publish paths are fully decoupled from the request/response
cycle, same posture as every other service in this project.
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import service
from app.config import Settings
from app.schemas import PaymentCapturedEvent

logger = logging.getLogger("shipping_service.consumer")


class PaymentCapturedConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer` subscribed to the
    frozen `payment.captured` topic, delegating each record's idempotent
    saga-start to `app.service.handle_payment_captured`."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def partitions_assigned(self) -> bool:
        """Used by `GET /health` (see `app/main.py`) as a CI readiness
        signal: a consumer with no partition assignment yet hasn't completed
        its group-join/rebalance, so a reader polling this service right
        after startup would see no saga started even once a matching
        `payment.captured` event has already been published."""
        return self._consumer is not None and len(self._consumer.assignment()) > 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.payment_captured_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop(), name="payment-captured-consumer")
        logger.info(
            "payment.captured consumer started (topic=%s, group=%s, bootstrap=%s)",
            self._settings.payment_captured_topic,
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
        logger.info("payment.captured consumer stopped")

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                event = PaymentCapturedEvent.model_validate(record.value)
                await service.handle_payment_captured(self._session_factory, self._settings, event)
                logger.info(
                    "consumed payment.captured for order %s (payment %s)",
                    event.order_id,
                    event.payment_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # A single malformed/unprocessable record, or a saga step
                # that raised past what `app/orchestrator.py` already
                # converts into a COMPENSATING transition (e.g. a DB outage
                # mid-advance), must not kill the background task -- log and
                # keep consuming subsequent records rather than silently
                # stopping saga starts for every order placed afterward.
                logger.exception(
                    "failed to process payment.captured record at offset %s", record.offset
                )
