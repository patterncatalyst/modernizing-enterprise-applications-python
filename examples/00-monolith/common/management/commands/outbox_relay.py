"""The transactional outbox relay (ch.17 cure for SMELL #5/#6 -- see
SMELLS.md and `order.services.place_order`).

A SIMPLE POLLING RELAY, not Debezium/CDC -- the pattern this teaches, same as
the Java sibling's `V3__outbox.sql` commentary describes for its own
(scheduled-job) relay. Every `OUTBOX_RELAY_POLL_MS` (default 1000), this
command:

1. reads unpublished `OutboxEvent` rows oldest-first (the partial index on
   `common_outbox(created_at) WHERE published_at IS NULL` keeps that cheap),
2. publishes each to Kafka via `AIOKafkaProducer.send_and_wait()`, keyed by
   `aggregate_id` (the frozen `order.placed` contract: key = orderId as a
   string),
3. stamps `published_at` in a short transaction.

AT-LEAST-ONCE, not exactly-once: publish happens before the stamp, so a crash
between steps 2 and 3 re-publishes the same row on the next poll. Consumers
(e.g. `notification.management.commands.order_placed_consumer`) are
responsible for their own idempotency on redelivery -- see
`notification.services.record_order_placed`.

CDC (reading the WAL instead of polling this table) is deferred, same as the
Java sibling -- this command teaches the simpler relay first.
"""

import asyncio
import contextlib
import json
import logging
import signal

from aiokafka import AIOKafkaProducer
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from common.models import OutboxEvent

logger = logging.getLogger(__name__)

DEFAULT_POLL_MS = 1000
BATCH_SIZE = 100


class Command(BaseCommand):
    help = "Poll the outbox table and publish unpublished rows to Kafka at-least-once."

    def handle(self, *args, **options):
        asyncio.run(_run())


@sync_to_async
def _fetch_unpublished_batch() -> list[OutboxEvent]:
    return list(
        OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at", "id")[
            :BATCH_SIZE
        ]
    )


@sync_to_async
def _mark_published(event_id: int) -> None:
    with transaction.atomic():
        OutboxEvent.objects.filter(pk=event_id, published_at__isnull=True).update(
            published_at=timezone.now()
        )


async def _publish_one(producer: AIOKafkaProducer, topic: str, event: OutboxEvent) -> None:
    key = str(event.aggregate_id).encode("utf-8")
    value = json.dumps(event.payload).encode("utf-8")
    await producer.send_and_wait(topic, key=key, value=value)
    # A crash here -- after the publish, before the stamp -- re-sends this
    # row on the relay's next poll. That's the documented at-least-once
    # tradeoff; see the module docstring and SMELLS.md.
    await _mark_published(event.id)
    logger.info(
        "outbox.published id=%s aggregate_type=%s aggregate_id=%s event_type=%s",
        event.id,
        event.aggregate_type,
        event.aggregate_id,
        event.event_type,
    )


async def _run() -> None:
    poll_ms = int(getattr(settings, "OUTBOX_RELAY_POLL_MS", DEFAULT_POLL_MS))
    topic = settings.ORDER_PLACED_TOPIC

    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()
    logger.info(
        "outbox_relay.started bootstrap_servers=%s topic=%s poll_ms=%s",
        settings.KAFKA_BOOTSTRAP_SERVERS,
        topic,
        poll_ms,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        # NotImplementedError on platforms without signal handler support in
        # the event loop (e.g. some Windows configurations) -- fall back to
        # Ctrl-C raising KeyboardInterrupt instead.
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            batch = await _fetch_unpublished_batch()
            for event in batch:
                if stop_event.is_set():
                    break
                await _publish_one(producer, topic, event)

            if not batch:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_ms / 1000)
                except TimeoutError:
                    pass
    finally:
        logger.info("outbox_relay.stopping")
        await producer.stop()
