"""Async SQLAlchemy queries against this service's own `notification` schema
-- the sibling of `02-review-service`'s `app/repository.py`, but against
owned storage rather than the monolith's shared tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


async def list_by_customer_id(session: AsyncSession, customer_id: int) -> list[Notification]:
    """`GET /api/notifications?customerId=` -- the sibling of the monolith's
    `services.list_by_customer_id()`, ordered by id like its `.order_by("id")`."""
    stmt = (
        select(Notification)
        .where(Notification.customer_id == customer_id)
        .order_by(Notification.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_order_id(session: AsyncSession, order_id: int) -> Notification | None:
    """Existence check for the consumer's idempotent dedupe
    (`app/service.py::record_order_placed`)."""
    stmt = select(Notification).where(Notification.order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    customer_id: int,
    order_id: int | None,
    channel: str,
    message: str,
    sent_at: datetime,
) -> Notification:
    notification = Notification(
        customer_id=customer_id,
        order_id=order_id,
        channel=channel,
        message=message,
        sent_at=sent_at,
    )
    session.add(notification)
    await session.flush()  # populates notification.id via INSERT ... RETURNING
    await session.commit()
    return notification
