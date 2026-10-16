"""`handle_payment_captured` -- the single owner of "should a saga start for
this order," mirroring `05-payment-service/app/service.py::process_order_placed`'s
role as the one place that decides whether an at-least-once event has already
been handled. `app/consumer.py` delegates here rather than creating a `Saga`
row directly, so there is exactly one place that implements the
one-saga-per-order idempotency guarantee `../EVENTS.md` documents.

Unlike payment-service's `process_order_placed` (which does the ENTIRE unit
of work -- charge, persist, emit -- inline), this function's job ends at
"does a saga exist for this order; if not, create one and kick the engine
once." Everything else (the four-step saga body, compensation, the
terminal outbox write) lives in `app/orchestrator.py`/`app/steps.py` --
necessary because a saga's steps span MULTIPLE separate transactions
(`app/orchestrator.py::advance`'s one-step-per-call design), not the single
atomic unit payment-service's choreography gets away with.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import orchestrator, repository
from app.config import Settings
from app.schemas import PaymentCapturedEvent

logger = logging.getLogger("shipping_service.service")


async def handle_payment_captured(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    event: PaymentCapturedEvent,
) -> None:
    """IDEMPOTENT by design: `payment.captured` is published by
    payment-service's own at-least-once outbox relay -- a crash between the
    Kafka send and marking that outbox row published republishes the
    identical event. Check-then-insert, dedup'd by `order_id` (plus the
    database-level `uq_sagas_order_id` unique index as the backstop for two
    deliveries racing concurrently, caught here as an `IntegrityError`),
    means a redelivered event starts at most one saga per order -- exactly
    `05-payment-service`'s `uq_payments_order_id` idempotency shape, re-aimed
    at sagas instead of payments.
    """
    async with session_factory() as session:
        existing = await repository.get_saga_by_order_id(session, event.order_id)
        if existing is not None:
            logger.info(
                "payment.captured for order %s already has a saga (id=%s, status=%s), "
                "skipping (idempotent no-op)",
                event.order_id,
                existing.id,
                existing.status,
            )
            return

        now = datetime.now(UTC)
        try:
            saga = await repository.create_saga(session, order_id=event.order_id, now=now)
            await session.commit()
        except IntegrityError:
            # Lost the race against a concurrent redelivery that inserted
            # first -- the unique index on order_id rejected this one. The
            # other insert already owns this order's saga, so this is still
            # a safe no-op, not an error (same race-loser handling as
            # payment-service's `process_order_placed`).
            await session.rollback()
            logger.info(
                "payment.captured for order %s raced a concurrent insert, discarding duplicate",
                event.order_id,
            )
            return

        logger.info(
            "started saga %s for order %s (payment %s)", saga.id, event.order_id, event.payment_id
        )
        saga_id = saga.id

    await orchestrator.advance(session_factory, settings, saga_id)
