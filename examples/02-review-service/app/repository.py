"""Async SQLAlchemy queries against the shared schema -- the FastAPI sibling
of `review/services.py`. No ORM-relationship traversal; every join is
written out explicitly (`InventoryItem` for `sku`, `Customer` for
`customerId` validation), matching the monolith's direct cross-context FKs
(SMELL[ch.18], see `app/models.py`)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthUser, Customer, InventoryItem, Review

_REVIEW_COLUMNS = (
    Review.id,
    Review.customer_id,
    InventoryItem.sku,
    Review.rating,
    Review.comment,
    Review.created_at,
)


def _review_query():
    return select(*_REVIEW_COLUMNS).join(
        InventoryItem, InventoryItem.id == Review.inventory_item_id
    )


async def list_reviews(session: AsyncSession, *, sku: str | None) -> list[Row[Any]]:
    """`GET /api/reviews` (optional `?sku=`) -- the sibling of
    `services.list_all()` / `services.list_by_sku()`, ordered by id like the
    monolith's `.order_by("id")`."""
    stmt = _review_query().order_by(Review.id)
    if sku is not None:
        stmt = stmt.where(InventoryItem.sku == sku)
    result = await session.execute(stmt)
    return list(result.all())


async def get_review_by_id(session: AsyncSession, review_id: int) -> Row[Any] | None:
    """`GET /api/reviews/{id}` -- the sibling of `services.get_by_id()`."""
    stmt = _review_query().where(Review.id == review_id)
    result = await session.execute(stmt)
    return result.first()


async def get_customer_by_id(session: AsyncSession, customer_id: int) -> Customer | None:
    """Existence check for `POST /api/reviews`'s `customerId`."""
    return await session.get(Customer, customer_id)


async def get_inventory_item_by_sku(session: AsyncSession, sku: str) -> InventoryItem | None:
    """Existence check (and id lookup) for `POST /api/reviews`'s `sku`."""
    stmt = select(InventoryItem).where(InventoryItem.sku == sku)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_review(
    session: AsyncSession,
    *,
    customer_id: int,
    inventory_item_id: int,
    rating: int,
    comment: str,
) -> Review:
    """`POST /api/reviews` -- insert, returning the generated id (the
    sibling of `services.create_review()`). `created_at` is set here in
    Python rather than left to a DB default, matching the monolith's own
    `default=timezone.now` (a Django-side default, not a DB server-side
    one)."""
    review = Review(
        customer_id=customer_id,
        inventory_item_id=inventory_item_id,
        rating=rating,
        comment=comment,
        created_at=datetime.now(UTC),
    )
    session.add(review)
    await session.flush()  # populates review.id via INSERT ... RETURNING
    await session.commit()
    return review


async def get_auth_user_by_username(session: AsyncSession, username: str) -> AuthUser | None:
    """Looks up the shared `auth_user` row for HTTP Basic verification
    (see `app/auth.py`) -- never creates or modifies this table."""
    stmt = select(AuthUser).where(AuthUser.username == username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
