"""The saga-reaction consumer -- the FastAPI/`aiokafka` sibling of
`00-monolith/order/management/commands/order_saga_listener.py`: ONE consumer
group (`order-service`), FOUR topics (`payment.captured`/`payment.declined`/
`shipment.dispatched`/`shipment.failed`), a dispatch table keyed by topic
name, delegating each record to the matching `app.service.handle_*` reaction.

`enable_auto_commit=True` + `auto_offset_reset="earliest"` -- the same
simplest-correct-starting-point choice every consumer in this project makes.
At-least-once redelivery is safe only because every one of the four handlers
is idempotent via its own status-transition guard (see `app/service.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import service
from app.config import Settings
from app.schemas import (
    PaymentCapturedEvent,
    PaymentDeclinedEvent,
    ShipmentDispatchedEvent,
    ShipmentFailedEvent,
)

logger = logging.getLogger("order_service.consumer")


class OrderSagaConsumer:
    """Lifecycle wrapper around an `AIOKafkaConsumer` subscribed to all FOUR
    saga-outcome topics at once, dispatching each record to the matching
    reaction in `app/service.py`."""

    def __init__(
        self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def partitions_assigned(self) -> bool:
        """Used by `GET /health` as a CI readiness signal -- a consumer with
        no partition assignment yet hasn't completed its group-join/
        rebalance."""
        return self._consumer is not None and len(self._consumer.assignment()) > 0

    async def start(self) -> None:
        s = self._settings
        self._consumer = AIOKafkaConsumer(
            s.payment_captured_topic,
            s.payment_declined_topic,
            s.shipment_dispatched_topic,
            s.shipment_failed_topic,
            bootstrap_servers=s.kafka_bootstrap_servers,
            group_id=s.consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop(), name="order-saga-consumer")
        logger.info(
            "order-saga-consumer started (topics=%s,%s,%s,%s group=%s bootstrap=%s)",
            s.payment_captured_topic,
            s.payment_declined_topic,
            s.shipment_dispatched_topic,
            s.shipment_failed_topic,
            s.consumer_group,
            s.kafka_bootstrap_servers,
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
        logger.info("order-saga-consumer stopped")

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                await self._dispatch(record.topic, record.value)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A single malformed/unprocessable record must not kill the
                # background task -- log and keep consuming.
                logger.exception(
                    "failed to process %s record at offset %s", record.topic, record.offset
                )

    async def _dispatch(self, topic: str, raw_value: dict) -> None:
        s = self._settings
        if topic == s.payment_captured_topic:
            event = PaymentCapturedEvent.model_validate(raw_value)
            await service.handle_payment_captured(self._session_factory, event)
        elif topic == s.payment_declined_topic:
            event = PaymentDeclinedEvent.model_validate(raw_value)
            await service.handle_payment_declined(
                self._session_factory,
                event,
                inventory_grpc_target=s.inventory_grpc_target,
                grpc_timeout_s=s.grpc_timeout_s,
            )
        elif topic == s.shipment_dispatched_topic:
            event = ShipmentDispatchedEvent.model_validate(raw_value)
            await service.handle_shipment_dispatched(self._session_factory, event)
        elif topic == s.shipment_failed_topic:
            event = ShipmentFailedEvent.model_validate(raw_value)
            await service.handle_shipment_failed(
                self._session_factory,
                event,
                inventory_grpc_target=s.inventory_grpc_target,
                grpc_timeout_s=s.grpc_timeout_s,
            )
        else:
            logger.warning("order-saga-consumer: unexpected topic=%s, ignoring", topic)
