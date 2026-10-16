"""The monolith's own consumer of its own `order.placed` event (ch.17 cure
for SMELL #5/#6 -- see SMELLS.md and `order.services.place_order`).

This is the "monolith becomes a consumer of its own event" half of r03: the
outbox relay (`common.management.commands.outbox_relay`) publishes
`order.placed` rows to Kafka; THIS command subscribes to that same topic and
repopulates the `Notification` read model via
`notification.services.record_order_placed`, so the flag-OFF
`GET /api/notifications` surface keeps working -- now event-driven instead of
written synchronously in-process by checkout.

`enable_auto_commit=True` + `auto_offset_reset="earliest"`: the simplest
correct starting point for a demo consumer. Combined with
`record_order_placed`'s idempotent check-then-create (backstopped by
`Notification`'s partial unique constraint on `order`), redelivery after a
crash before an offset commit is safe -- at-least-once end to end, not
exactly-once.
"""

import asyncio
import contextlib
import json
import logging
import signal

from aiokafka import AIOKafkaConsumer
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand

from notification.services import record_order_placed

logger = logging.getLogger(__name__)

CONSUMER_GROUP_ID = "monolith-notification"


class Command(BaseCommand):
    help = "Consume order.placed and repopulate the Notification read model."

    def handle(self, *args, **options):
        asyncio.run(_run())


_record_order_placed_async = sync_to_async(record_order_placed)


async def _run() -> None:
    topic = settings.ORDER_PLACED_TOPIC

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info(
        "order_placed_consumer.started bootstrap_servers=%s topic=%s group_id=%s",
        settings.KAFKA_BOOTSTRAP_SERVERS,
        topic,
        CONSUMER_GROUP_ID,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            # getmany() with a timeout (rather than `async for record in
            # consumer`, which blocks indefinitely on an idle topic) so the
            # stop_event set by the signal handler above actually gets a
            # chance to end the loop instead of waiting for the next message.
            batches = await consumer.getmany(timeout_ms=1000)
            for records in batches.values():
                for record in records:
                    event = json.loads(record.value.decode("utf-8"))
                    notification = await _record_order_placed_async(event)
                    logger.info(
                        "order_placed.consumed order_id=%s notification_id=%s",
                        event.get("orderId"),
                        getattr(notification, "id", None),
                    )
    finally:
        logger.info("order_placed_consumer.stopping")
        await consumer.stop()
