"""SQLAlchemy 2.x declarative mapping onto this service's OWN `payment`
schema -- the sibling of `03-notification-service`'s `app/models.py`, but
this service owns BOTH halves of the outbox pattern: `payments` (the
aggregate this service writes) AND `outbox` (the events this service emits),
where notification-service only ever has the former half (it consumes, it
never publishes).

`order_id` is a plain `BIGINT` column, NOT a foreign key into the monolith's
`orders` table (contrast with the monolith's own `payment.Payment.order`,
which IS a hard FK/join into the shared schema -- see
`00-monolith/payment/models.py`'s docstring, SMELL[ch.18]). This service's
schema must not reach across into tables it does not own; only the foreign
*value* is kept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Payment(Base):
    """`payment.payments` -- one row per captured/declined payment attempt,
    written exclusively by this service's `order.placed` consumer (see
    `app/consumer.py` / `app/service.py`). The unique index on `order_id` is
    the idempotency backstop against the at-least-once `order.placed`
    delivery guarantee: one order places at most one payment attempt.
    """

    __tablename__ = "payments"
    __table_args__ = (
        # Unique (not partial -- every payment row has an order_id, unlike
        # notification's nullable-order_id case) index: the database-level
        # backstop for the consumer's application-level check-then-insert
        # dedupe (app/service.py::process_order_placed), for the case of two
        # redeliveries of the same at-least-once `order.placed` event racing
        # concurrently.
        Index("uq_payments_order_id", "order_id", unique=True),
        {"schema": "payment"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEvent(Base):
    """`payment.outbox` -- this service's OWN transactional outbox (ch.17
    pattern, same shape as the monolith's `common.OutboxEvent`:
    `aggregate_type`/`aggregate_id`/`event_type`/`payload`/`created_at`/
    `published_at`, same partial index on unpublished rows), publishing
    `payment.captured`/`payment.declined` -- see `app/relay.py`.

    Unlike the monolith's single shared outbox table feeding one topic
    (`order.placed`), this table's `event_type` selects the topic to publish
    to at relay time (`app/relay.py`'s `_TOPIC_BY_EVENT_TYPE`), since one
    payment attempt emits one of two distinct event types to two distinct
    topics.
    """

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "idx_payment_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": "payment"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
