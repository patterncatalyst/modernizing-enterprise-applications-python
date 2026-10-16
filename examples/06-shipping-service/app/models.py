"""SQLAlchemy 2.x declarative mapping onto this service's OWN `shipping`
schema. Four tables, two families:

- `shipments` + `outbox` -- the sibling of `05-payment-service`'s
  `payments`/`outbox` pair: the aggregate this service writes, plus this
  service's own transactional-outbox half (publishing
  `shipment.dispatched`/`shipment.failed`).
- `sagas` + `saga_log` -- NET-NEW for this service, and the whole point of
  r06's ORCHESTRATED contrast with r05's choreography: the DB-backed saga
  state machine `app/orchestrator.py` drives, adapted from
  `~/Dev/cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/main.py`'s
  `sagas`/`saga_log` tables (there raw-asyncpg/`TEXT`-encoded JSON; here
  SQLAlchemy models with a real `JSONB` column). One row per in-flight saga
  instance, surviving a process restart -- see `app/orchestrator.py`'s
  `resume_running_sagas()` and `../MIGRATION.md` for why this is a durability
  upgrade over the Java sibling's in-memory Camel Saga EIP coordinator.

`order_id` is a plain `BIGINT` column, NOT a foreign key into the monolith's
`orders` table (same posture as every other standalone service's owned
aggregate in this project -- see `05-payment-service/app/models.py`'s
docstring, SMELL[ch.18]): this service's schema must not reach across into
tables it does not own; only the foreign *value* is kept. `saga_log.saga_id`
IS a real foreign key, because `sagas` is a table THIS SERVICE owns too --
that's an ordinary intra-schema relationship, not the cross-service smell.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# -- Saga states (app/orchestrator.py is the only writer of `sagas.status`) --
SAGA_RUNNING = "RUNNING"
SAGA_COMPENSATING = "COMPENSATING"
SAGA_COMPLETED = "COMPLETED"
SAGA_COMPENSATED = "COMPENSATED"

# -- Shipment states --
SHIPMENT_PENDING = "PENDING"
SHIPMENT_DISPATCHED = "DISPATCHED"
SHIPMENT_CANCELLED = "CANCELLED"


class Shipment(Base):
    """`shipping.shipments` -- one row per shipment the saga has dispatched
    (or attempted to dispatch), written exclusively by `app/steps.py`'s
    `dispatch`/`cancel_shipment` step bodies via `app/repository.py`.

    Not a unique index on `order_id`: an order's saga runs `dispatch` at most
    once (the saga's own `RUNNING`-only idempotent guard prevents a
    redelivered `payment.captured` from re-triggering it -- see
    `app/service.py::handle_payment_captured`), so in practice this is a
    one-row-per-order table too, but the column stays list-shaped (a plain
    index, not unique) to match the monolith's own
    `shipping.services.list_by_order_id` contract byte-for-byte (`GET
    /api/shipments?orderId=` returns an array).

    `PENDING` is declared for completeness (a future saga variant that
    separates "shipment reserved" from "shipment emitted" could use it) but
    this saga's `dispatch` step persists `DISPATCHED` directly -- see
    `app/steps.py::dispatch`'s docstring.
    """

    __tablename__ = "shipments"
    __table_args__ = (
        Index("idx_shipments_order_id", "order_id"),
        {"schema": "shipping"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEvent(Base):
    """`shipping.outbox` -- this service's OWN transactional outbox (ch.17
    pattern, same shape as `05-payment-service/app/models.py::OutboxEvent`),
    publishing `shipment.dispatched`/`shipment.failed` -- see `app/relay.py`.

    Written by `app/steps.py`'s `emit`/`cancel_shipment` step bodies, in the
    SAME transaction as the saga's terminal `COMPLETED`/`COMPENSATED` status
    update (`app/orchestrator.py`'s `advance()`/`compensate()`) -- never a
    dual write between "the saga finished" and "the outcome event is queued."
    """

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "idx_shipping_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": "shipping"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Saga(Base):
    """`shipping.sagas` -- one row per orchestrated shipping saga instance,
    the DB-backed state machine `app/orchestrator.py::advance()`/
    `compensate()`/`resume_running_sagas()` drives. Adapted from
    `~/Dev/cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/main.py`'s
    `sagas` table and `_docs/17-appendix-d-sagas.md`'s DB-backed-state-machine
    pattern (Figure D.1): `status` + `step_index` + a `context` JSONB blob
    that accumulates each completed step's output, so a later step (or a
    resumed saga after a crash) can read an earlier step's result without
    re-calling it.

    `order_id` is UNIQUE -- the idempotency backstop for the at-least-once
    `payment.captured` delivery guarantee: one order runs at most one saga
    (see `app/service.py::handle_payment_captured`'s check-then-insert
    dedupe, mirroring `05-payment-service`'s `uq_payments_order_id`
    precedent).
    """

    __tablename__ = "sagas"
    __table_args__ = (
        Index("uq_sagas_order_id", "order_id", unique=True),
        {"schema": "shipping"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=SAGA_RUNNING)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SagaLog(Base):
    """`shipping.saga_log` -- append-only audit trail of every step
    execution/compensation attempt a saga instance has gone through, the
    sibling of the CNDP orchestrator's `saga_log` table. `saga_id` is a real
    foreign key (both tables are owned by this service, in the same schema --
    not the cross-service-FK smell `app/models.py`'s module docstring
    documents for `order_id`).
    """

    __tablename__ = "saga_log"
    __table_args__ = (
        Index("idx_saga_log_saga_id", "saga_id"),
        {"schema": "shipping"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    saga_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shipping.sagas.id"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
