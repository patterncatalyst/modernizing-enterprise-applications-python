"""The transactional outbox relay (ch.17 cure for the dual-write hazard,
same pattern notification-service's producer-side sibling -- the monolith's
`00-monolith/common/management/commands/outbox_relay.py` -- teaches). This
is THIS SERVICE's own half of the pattern: `app/service.py::process_order_placed`
writes `payment.outbox` rows atomically with each `Payment`; this module
polls those unpublished rows and publishes them to Kafka.

A SIMPLE POLLING RELAY, not Debezium/CDC -- same posture as the monolith's
relay. Every `Settings.outbox_poll_ms` (default 1000), this:

1. reads unpublished `OutboxEvent` rows oldest-first (the partial index
   `idx_payment_outbox_unpublished` keeps that cheap),
2. publishes each to the Kafka topic matching its `event_type`
   (`payment.captured` or `payment.declined`) via
   `AIOKafkaProducer.send_and_wait()`, keyed by `aggregate_id` (= `orderId`
   as a string, the frozen contract -- see `../EVENTS.md`),
3. stamps `published_at` in a short transaction.

AT-LEAST-ONCE, not exactly-once: publish happens before the stamp, so a crash
between steps 2 and 3 re-publishes the same row on the next poll. Downstream
consumers of `payment.captured`/`payment.declined` are responsible for their
own idempotency on redelivery, same discipline this service's own
`order.placed` consumer (`app/consumer.py`) already follows.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repository
from app.config import Settings
from app.models import OutboxEvent

logger = logging.getLogger("payment_service.relay")


class OutboxRelay:
    """Lifecycle wrapper around an `AIOKafkaProducer`, polling this
    service's own `payment.outbox` table on a background `asyncio.Task` --
    the publish-side sibling of `app/consumer.py::OrderPlacedConsumer`."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._producer: AIOKafkaProducer | None = None
        self._task: asyncio.Task[None] | None = None

    def _topic_for(self, event_type: str) -> str | None:
        return {
            "payment.captured": self._settings.payment_captured_topic,
            "payment.declined": self._settings.payment_declined_topic,
        }.get(event_type)

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
        )
        await self._producer.start()
        self._task = asyncio.create_task(self._relay_loop(), name="payment-outbox-relay")
        logger.info(
            "outbox relay started (bootstrap=%s, captured_topic=%s, declined_topic=%s, "
            "poll_ms=%s)",
            self._settings.kafka_bootstrap_servers,
            self._settings.payment_captured_topic,
            self._settings.payment_declined_topic,
            self._settings.outbox_poll_ms,
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        logger.info("outbox relay stopped")

    async def _relay_loop(self) -> None:
        poll_s = self._settings.outbox_poll_ms / 1000
        while True:
            try:
                published_any = await self._publish_one_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient DB/broker hiccup must not kill the background
                # task -- log and retry on the next poll tick, same
                # never-die-on-a-single-failure discipline as
                # `app/consumer.py`'s record loop.
                logger.exception("outbox relay: batch failed, will retry on next poll")
                published_any = False

            if not published_any:
                await asyncio.sleep(poll_s)

    async def _publish_one_batch(self) -> bool:
        assert self._producer is not None
        async with self._session_factory() as session:
            batch = await repository.list_unpublished_outbox_events(session)
            for event in batch:
                await self._publish_one(session, event)
            return len(batch) > 0

    async def _publish_one(self, session: AsyncSession, event: OutboxEvent) -> None:
        assert self._producer is not None
        topic = self._topic_for(event.event_type)
        if topic is None:
            logger.warning(
                "outbox relay: unknown event_type=%s for outbox id=%s; leaving unpublished",
                event.event_type,
                event.id,
            )
            return

        key = event.aggregate_id.encode("utf-8")
        value = json.dumps(event.payload).encode("utf-8")
        await self._producer.send_and_wait(topic, key=key, value=value)
        # A crash here -- after the publish, before the stamp -- re-sends
        # this row on the relay's next poll. That's the documented
        # at-least-once tradeoff; see the module docstring.
        await repository.mark_outbox_event_published(
            session, event.id, published_at=datetime.now(UTC)
        )
        logger.info(
            "outbox.published id=%s aggregate_type=%s aggregate_id=%s event_type=%s topic=%s",
            event.id,
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            topic,
        )
