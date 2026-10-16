"""SQLAlchemy 2.x declarative mapping onto this service's OWN `notification`
schema (DRQ-028/DRQ-035) -- unlike `02-review-service`'s `app/models.py`
(which maps onto the monolith's shared tables and never migrates them), this
is net-new storage this service creates and owns via Alembic
(`../migrations/`).

`customer_id` / `order_id` are plain `BIGINT` columns, NOT foreign keys into
the monolith's `customers`/`orders` tables -- this service's schema must not
reach across into tables it does not own (contrast with the monolith's own
`notification.Notification`, which FKs both, and review-service's
`app/models.py`, which reads the monolith's tables directly because it stays
in the shared schema). Only the foreign *values* are kept.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Notification(Base):
    """`notification.notifications` -- a record of a notification sent to a
    customer, written exclusively by this service's `order.placed` consumer
    (see `app/consumer.py` / `app/service.py`). `order_id` is nullable (not
    every notification need originate from an order, matching the monolith's
    own `Notification.order` being `null=True`) with a partial unique index
    (`../migrations/versions/0001_...py`) backstopping the consumer's
    application-level idempotent dedupe-by-`order_id` check against the
    at-least-once `order.placed` delivery guarantee.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_customer_id", "customer_id"),
        # Partial unique index (ignores NULL order_id) -- the database-level
        # backstop for the consumer's application-level check-then-insert
        # dedupe (app/service.py::record_order_placed), for the case of two
        # redeliveries of the same at-least-once `order.placed` event racing
        # concurrently.
        Index(
            "uq_notifications_order_id",
            "order_id",
            unique=True,
            postgresql_where=text("order_id IS NOT NULL"),
        ),
        {"schema": "notification"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
