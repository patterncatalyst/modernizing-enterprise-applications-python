"""`record_order_placed` -- the single owner of the write path's idempotency
guarantee (DRQ-034/DRQ-037 equivalent, mirroring the Java sibling's
`NotificationService#recordOrderPlaced`). `app/consumer.py` delegates here
rather than writing to the repository directly, so there is exactly one place
that decides "have I already recorded this order."

NET-NEW for this service: the monolith never consumed its own `order.placed`
event (it only ever sent the confirmation synchronously, in-process, from
`order.services.place_order()`), so there is no Django original to lift --
this is authored idiomatic-from-the-start, same posture as the Java
sibling's `OrderPlacedConsumer`/`NotificationService` pair.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repository
from app.schemas import OrderPlacedEvent

logger = logging.getLogger("notification_service.service")


async def record_order_placed(
    session_factory: async_sessionmaker[AsyncSession], event: OrderPlacedEvent
) -> None:
    """IDEMPOTENT by design: the monolith's outbox relay is an
    AT-LEAST-ONCE publisher -- a crash between the Kafka send and marking the
    outbox row published republishes the identical event. Check-then-insert,
    dedup'd by `order_id`, means a redelivered event is a safe no-op. The
    database-level partial unique index on `order_id`
    (`../migrations/versions/0001_...py`) is the backstop for two deliveries
    racing concurrently -- caught here as an `IntegrityError` and swallowed,
    since by definition a notification for that order already exists.
    """
    async with session_factory() as session:
        existing = await repository.get_by_order_id(session, event.order_id)
        if existing is not None:
            logger.info(
                "order.placed for order %s already recorded, skipping (idempotent no-op)",
                event.order_id,
            )
            return

        message = event.confirmation_message
        try:
            await repository.create(
                session,
                customer_id=event.customer_id,
                order_id=event.order_id,
                channel="EMAIL",
                message=message,
                sent_at=datetime.now(UTC),
            )
        except IntegrityError:
            # Lost the race against a concurrent redelivery that inserted
            # first -- the partial unique index on order_id rejected this
            # one. The other insert already recorded the notification, so
            # this is still a safe no-op, not an error.
            await session.rollback()
            logger.info(
                "order.placed for order %s raced a concurrent insert, discarding duplicate",
                event.order_id,
            )
