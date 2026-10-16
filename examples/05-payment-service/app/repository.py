"""Async SQLAlchemy queries against this service's own `payment` schema --
the sibling of `03-notification-service`'s `app/repository.py`, plus the
outbox write this service's consumer needs that notification-service never
does (notification only ever consumes; it has no outbox of its own).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, Payment

_RELAY_BATCH_SIZE = 100


async def get_by_id(session: AsyncSession, payment_id: int) -> Payment | None:
    return await session.get(Payment, payment_id)


async def get_by_order_id(session: AsyncSession, order_id: int) -> Payment | None:
    """Existence check for the consumer's idempotent dedupe
    (`app/service.py::process_order_placed`)."""
    stmt = select(Payment).where(Payment.order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_order_id(session: AsyncSession, order_id: int) -> list[Payment]:
    """`GET /api/payments?orderId=` -- ordered by id like the monolith's own
    `payment.services.list_by_order_id().order_by("id")`. In practice this
    is at most one row (the unique index on `order_id` enforces it), but the
    endpoint stays list-shaped to match the monolith's contract byte-for-byte."""
    stmt = select(Payment).where(Payment.order_id == order_id).order_by(Payment.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_payment_with_outbox_event(
    session: AsyncSession,
    *,
    order_id: int,
    amount_cents: int,
    method: str,
    status: str,
    created_at: datetime,
    event_type: str,
    build_payload: Callable[[Payment], dict[str, Any]],
) -> Payment:
    """Writes the `Payment` row AND its matching outbox event in ONE
    transaction -- the transactional-outbox guarantee (ch.17): either both
    land, or neither does, so a crash between "captured the payment" and
    "queued the event to tell the world" can never happen.

    `build_payload` is a callback rather than a precomputed dict because the
    wire payload needs `payment.id` (`paymentId`, see `../EVENTS.md`), which
    does not exist until AFTER the `Payment` row's own INSERT -- `flush()`
    below populates it via `INSERT ... RETURNING` while still inside this
    same transaction, so the callback can build the final payload before the
    commit that makes both rows durable together.

    `aggregate_id` is the `orderId` as a string, matching the frozen Kafka
    key contract so `app/relay.py` can key the published record identically
    without a second lookup.
    """
    payment = Payment(
        order_id=order_id,
        amount_cents=amount_cents,
        method=method,
        status=status,
        created_at=created_at,
    )
    session.add(payment)
    await session.flush()  # populates payment.id via INSERT ... RETURNING

    outbox_event = OutboxEvent(
        aggregate_type="payment",
        aggregate_id=str(order_id),
        event_type=event_type,
        payload=build_payload(payment),
        created_at=created_at,
        published_at=None,
    )
    session.add(outbox_event)

    await session.flush()
    await session.commit()
    return payment


async def transition_payment_status_with_outbox_event(
    session: AsyncSession,
    *,
    order_id: int,
    expected_status: str,
    new_status: str,
    created_at: datetime,
    event_type: str,
    build_payload: Callable[[Payment], dict[str, Any]],
) -> Payment | None:
    """Conditionally transitions a `Payment` row's `status` (e.g.
    `CAPTURED` -> `REFUNDED`, `app/service.py::process_shipment_failed`,
    r06/DRQ-054) and writes the matching outbox event, in ONE transaction --
    the same transactional-outbox atomicity guarantee
    `create_payment_with_outbox_event` makes for the initial insert.

    Returns the updated `Payment`, or `None` if no row matched BOTH
    `order_id` AND `expected_status` -- the idempotent no-op path: either
    there is no payment for that order at all, it was never `CAPTURED`
    (e.g. `DECLINED`), or a prior call already moved it past
    `expected_status` (e.g. a redelivered `shipment.failed` finding the
    payment already `REFUNDED`).

    The `WHERE status = expected_status` guard on the `UPDATE` is this
    transition's version of `create_payment_with_outbox_event`'s
    insert-side unique index: it makes the read-then-decide-then-write shape
    safe against two `shipment.failed` deliveries for the same order racing
    concurrently -- only one `UPDATE` can match the row while it is still in
    `expected_status`, so only one caller ever sees a non-`None` result and
    writes the outbox event; the loser's `UPDATE` matches zero rows and this
    returns `None`, same safe no-op as any other idempotent redelivery.
    """
    stmt = (
        update(Payment)
        .where(Payment.order_id == order_id, Payment.status == expected_status)
        .values(status=new_status)
        .returning(Payment)
    )
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    if payment is None:
        await session.rollback()
        return None

    outbox_event = OutboxEvent(
        aggregate_type="payment",
        aggregate_id=str(order_id),
        event_type=event_type,
        payload=build_payload(payment),
        created_at=created_at,
        published_at=None,
    )
    session.add(outbox_event)

    await session.flush()
    await session.commit()
    return payment


async def list_unpublished_outbox_events(
    session: AsyncSession, *, limit: int = _RELAY_BATCH_SIZE
) -> list[OutboxEvent]:
    """`app/relay.py`'s poll query -- oldest-first, same convention as the
    monolith's `outbox_relay`'s `_fetch_unpublished_batch`. The partial index
    `idx_payment_outbox_unpublished` keeps this cheap."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_outbox_event_published(
    session: AsyncSession, event_id: int, *, published_at: datetime
) -> None:
    """Stamps `published_at` in its own short transaction, AFTER the relay's
    Kafka send has already succeeded -- see `app/relay.py`'s module docstring
    for why this is an at-least-once, not exactly-once, guarantee."""
    stmt = (
        update(OutboxEvent)
        .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
        .values(published_at=published_at)
    )
    await session.execute(stmt)
    await session.commit()
