"""The transactional outbox relay (ch.17 cure for the dual-write hazard) --
THIS service's own half of the pattern: `app/repository.py::
create_order_with_outbox_and_view` writes one `order_svc.outbox` row per
checkout atomically with the aggregate + `order_view`; this module polls
those unpublished rows and publishes them to Kafka, mirroring
`05-payment-service/app/relay.py`/`06-shipping-service/app/relay.py`'s
`OutboxRelay`.

A SIMPLE POLLING RELAY, not Debezium/CDC -- same posture as every other
outbox in this project. Only ONE event type is ever written to this
service's outbox (`order.placed`), unlike payment-service's three -- but the
`_topic_for` lookup stays table-driven rather than hard-coded, so a future
event type is a one-line addition, not a structural change.

AT-LEAST-ONCE, not exactly-once: publish happens before the `published_at`
stamp, so a crash between the two re-publishes the identical row on the next
poll. `05-payment-service`'s own `order.placed` consumer is responsible for
its own idempotency on redelivery (it already is, by design -- see
`../05-payment-service/app/service.py::process_order_placed`).
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

logger = logging.getLogger("order_service.relay")


class OutboxRelay:
    """Lifecycle wrapper around an `AIOKafkaProducer`, polling this
    service's own `order_svc.outbox` table on a background `asyncio.Task`."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._producer: AIOKafkaProducer | None = None
        self._task: asyncio.Task[None] | None = None

    def _topic_for(self, event_type: str) -> str | None:
        return {
            repository.ORDER_PLACED_EVENT_TYPE: self._settings.order_placed_topic,
        }.get(event_type)

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
        )
        await self._producer.start()
        self._task = asyncio.create_task(self._relay_loop(), name="order-outbox-relay")
        logger.info(
            "outbox relay started (bootstrap=%s, order_placed_topic=%s, poll_ms=%s)",
            self._settings.kafka_bootstrap_servers,
            self._settings.order_placed_topic,
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
        # this row on the relay's next poll. Documented at-least-once
        # tradeoff; see the module docstring.
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
