"""The monolith's first SAGA consumer (r05/ch.23-25): reacts to
payment-service's own outbox-published `payment.captured`/`payment.declined`
events (see `examples/05-payment-service/EVENTS.md`) to finish a
CHOREOGRAPHED checkout (`settings.PAYMENT_MODE = "choreographed"`) that
`order.services.place_order()` (via `_place_order_choreographed`) left
PENDING. All the actual reaction logic -- the status-transition idempotency
guard, the in-process shipping dispatch, the compensating gRPC Release on a
decline/ship-fail -- lives in `order.services.handle_payment_captured`/
`handle_payment_declined`, where it's unit-testable without Kafka; this
command is just the aiokafka wiring, cloned from
`notification.management.commands.order_placed_consumer`'s getmany/
signal-stop/sync_to_async idiom, subscribed to BOTH outcome topics at once
(one consumer group, two topics -- aiokafka's `AIOKafkaConsumer` accepts
multiple topic names).

`enable_auto_commit=True` + `auto_offset_reset="earliest"`: the same
simplest-correct-starting-point choice `order_placed_consumer` makes.
At-least-once redelivery (a crash after processing, before the next
auto-commit) is safe ONLY because `handle_payment_captured`/
`handle_payment_declined` are idempotent via their own status-transition
guard -- see those functions' docstrings in `order/services.py`.
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

from order.services import handle_payment_captured, handle_payment_declined

logger = logging.getLogger(__name__)

_handle_payment_captured_async = sync_to_async(handle_payment_captured)
_handle_payment_declined_async = sync_to_async(handle_payment_declined)


class Command(BaseCommand):
    help = "Consume payment.captured/payment.declined and finish a choreographed checkout."

    def handle(self, *args, **options):
        asyncio.run(_run())


async def _run() -> None:
    captured_topic = settings.PAYMENT_CAPTURED_TOPIC
    declined_topic = settings.PAYMENT_DECLINED_TOPIC
    group_id = settings.ORDER_SAGA_CONSUMER_GROUP

    consumer = AIOKafkaConsumer(
        captured_topic,
        declined_topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info(
        "order_saga_listener.started bootstrap_servers=%s topics=%s,%s group_id=%s",
        settings.KAFKA_BOOTSTRAP_SERVERS,
        captured_topic,
        declined_topic,
        group_id,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        # NotImplementedError on platforms without signal handler support in
        # the event loop -- fall back to Ctrl-C raising KeyboardInterrupt
        # instead (same guard as order_placed_consumer/outbox_relay).
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            # getmany() with a timeout (rather than `async for record in
            # consumer`, which blocks indefinitely on an idle topic) so the
            # stop_event set by the signal handler above actually gets a
            # chance to end the loop instead of waiting for the next message.
            batches = await consumer.getmany(timeout_ms=1000)
            for topic_partition, records in batches.items():
                for record in records:
                    event = json.loads(record.value.decode("utf-8"))
                    if topic_partition.topic == captured_topic:
                        order = await _handle_payment_captured_async(event)
                    else:
                        order = await _handle_payment_declined_async(event)
                    logger.info(
                        "order_saga.consumed topic=%s order_id=%s status=%s",
                        topic_partition.topic,
                        event.get("orderId"),
                        getattr(order, "status", None),
                    )
    finally:
        logger.info("order_saga_listener.stopping")
        await consumer.stop()
