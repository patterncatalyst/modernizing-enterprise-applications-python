"""SQLAlchemy 2.x declarative mapping onto this service's OWN `inventory`
schema (DRQ-044, own-schema from day one -- same posture as notification-
service's DRQ-035, contrast with review-service's shared-schema posture,
DRQ-028). Net-new storage this service creates, seeds, and owns via Alembic
(`../migrations/`): there is no foreign key back into the monolith's
`public.inventory_items` table -- this service's schema must not reach across
into a table it does not own.

`id` is a plain autoincrementing `BIGINT` primary key, owned by this
service's own Postgres sequence -- NOT CDC-assigned (contrast with the Java
sibling's `InventoryItem`, whose `id` IS CDC-assigned because its Phase A
backfilled the table from the monolith's Debezium change stream before
Alembic-equivalent ownership existed). This Python service seeds its own
three rows directly (`migrations/versions/0002_seed_inventory.py`); the
transition-only `app/cdc_consumer.py` is flag-gated OFF by default and is
retired after cutover (see `../CUTOVER.md`) -- if ever enabled, its upsert-
by-source-id story is documented there as a known caveat against this
column's own sequence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InventoryItem(Base):
    """`inventory.inventory_items` -- stock levels for a product. Matches the
    monolith's `inventory.models.InventoryItem` field-for-field
    (`sku, name, price_cents, quantity_on_hand, updated_at`), but as an
    independently-owned table rather than a shared one."""

    __tablename__ = "inventory_items"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Compensation(Base):
    """`inventory.compensations` -- the idempotency ledger backing `Release`'s
    at-least-once-safe compensating re-increment (r05, DRQ-043,
    IDEMPOTENT-COMPENSATION lane). One row per successfully-applied
    compensation, keyed on the caller-supplied `idempotency_key`: a retried
    `Release` carrying a key already present here is a no-op (see
    `app/repository.py::release`'s docstring for the race-safety argument
    behind the unique index on `idempotency_key`, below).

    `order_id` is nullable and NOT currently populated by this lane -- the
    gRPC `ReleaseRequest` only carries `idempotency_key`/`stock_keeping_unit`/
    `requested_qty`, no separate `order_id` field (deliberately out of scope
    for DRQ-043; a caller that wants `order_id` on the ledger can encode it
    into the key itself, e.g. `f"{order_id}:RELEASE:{sku}"`). The column
    exists so a later lane can backfill it from an explicit field without a
    schema change. `kind` is always `"RELEASE"` today -- carried as a column
    rather than hard-coded so a future compensating-action type (e.g. a
    payment refund ledger entry) can share this table without a migration."""

    __tablename__ = "compensations"
    __table_args__ = {"schema": "inventory"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
