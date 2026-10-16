"""SQLAlchemy 2.x declarative mapping onto this service's OWN `order_svc`
schema (see `app/db.py`'s docstring for why not literally `order`) -- CQRS
from day one, two families:

- **Command side** (the write aggregate): `customers` (lifted, OWNED master
  data -- r04/ch.19's "own your validation data" posture extended one step
  further than inventory/payment/shipping did: this service does not reach
  into the monolith's shared `common.Customer` table AT ALL, not even via
  gRPC, it owns a forward-filled copy -- see `../MIGRATION.md`), `orders`
  (the aggregate root: status, totals, a `customer_email` SNAPSHOT captured
  at checkout time so a later customer-record change never retroactively
  rewrites a historical order, the same snapshot discipline `OrderItem`'s
  `sku`/`unit_price_cents` already follow), `order_items` (sku/quantity/
  unit_price_cents snapshots, no FK to inventory -- same SMELL[ch.18] cure
  r04/ch.19 already established for the monolith's own `OrderItem`), and
  `outbox` (this service's own transactional outbox, producing
  `order.placed`).
- **Read side**: `order_view`, the ONE table `app/routes.py`'s `GET
  /api/orders[/{id}]` reads from -- NEVER the `orders`/`order_items` write
  tables directly. Projected in the SAME local transaction as every write to
  the aggregate (`app/service.py`/`app/repository.py`), so a reader never
  observes a write that hasn't also updated its own read-side row. `items`
  is a denormalized JSON array (not a child table) because the read side has
  no independent query shape of its own beyond "the whole order, as the
  monolith's `OrderSerializer` would have rendered it" -- see
  `app/schemas.py::OrderOut`.

`customer_id` on `orders` IS a real foreign key into this service's OWN
`customers` table -- an ordinary intra-schema relationship (not the
cross-service-FK smell `05-payment-service`/`06-shipping-service`'s
`order_id: BigInteger` (no FK) columns document), because `customers` is
owned and migrated by THIS service, not borrowed from `00-monolith`'s shared
schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "order_svc"


class Base(DeclarativeBase):
    pass


# -- Order aggregate states (mirrors 00-monolith/order/models.py::Order.Status
# byte-for-byte, including the two sagas-only values added in r05/r06) --
STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_PAYMENT_DECLINED = "PAYMENT_DECLINED"
STATUS_SHIPPING_FAILED = "SHIPPING_FAILED"
STATUS_AWAITING_SHIPMENT = "AWAITING_SHIPMENT"


class Customer(Base):
    """`order_svc.customers` -- OWNED master data, forward-filled at
    migration time from the monolith's seed (`0002_seed_customers.py`), not
    read live from `00-monolith`'s shared `common.Customer` table over any
    protocol. `place_order()`'s customer validation
    (`app/service.py::place_order`) queries THIS table, never the monolith's.
    See `../MIGRATION.md` for the "customer FK -> snapshot" story this
    completes: `Order.customer_id` below is a real FK into this table, and
    `Order.customer_email` is additionally captured as its own point-in-time
    SNAPSHOT so a later email change on this table never rewrites history.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_email", "email", unique=True),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Order(Base):
    """`order_svc.orders` -- the write aggregate root, the sibling of
    `00-monolith/order/models.py::Order` minus the cross-schema FK
    (SMELL[ch.18]): `customer_id` here is a real FK, but into THIS service's
    OWNED `customers` table, not the monolith's shared one.

    `customer_email` is a point-in-time snapshot captured at checkout
    (`app/service.py::place_order`) -- the produced `order.placed` event's
    frozen `customerEmail` field needs it, and a snapshot (not a live join)
    means a later change to `customers.email` never rewrites a historical
    order's outbox payload if it were ever replayed.
    """

    __tablename__ = "orders"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.customers.id"), nullable=False
    )
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_PENDING)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    shipping_address: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderItem(Base):
    """`order_svc.order_items` -- denormalized line-item SNAPSHOTS (sku,
    quantity, unit_price_cents) captured once at checkout from
    inventory-service's gRPC `GetStock`/`Reserve` replies -- no FK onto any
    inventory table, same cure r04/ch.19 already established for the
    monolith's own `OrderItem` (see that model's docstring). `order_id` IS a
    real FK into `orders.id` -- both tables are owned by this service, an
    ordinary intra-schema relationship, not the cross-service smell."""

    __tablename__ = "order_items"
    __table_args__ = (
        Index("idx_order_items_order_id", "order_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.orders.id"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OrderView(Base):
    """`order_svc.order_view` -- the CQRS READ MODEL. `app/routes.py`'s `GET
    /api/orders[/{id}]` queries ONLY this table, never `orders`/
    `order_items` directly (see `app/repository.py`'s read functions). Keyed
    1:1 by `order_id` (the aggregate's own id -- there is exactly one
    current view row per order, replaced wholesale on every status
    transition, not appended to).

    `items` is a denormalized JSON array (`[{"sku": ..., "quantity": ...,
    "unitPriceCents": ...}, ...]`, already camelCase on the wire -- see
    `app/repository.py::_item_view_payload`) rather than a join against
    `order_items`: the read side's only query shape is "the whole order,
    exactly as `app/schemas.py::OrderOut` serializes it," so there is no
    normalized-query benefit to a child table here, only an extra join on
    every read.

    REBUILDABLE: `app/service.py::rebuild_order_view` recomputes this row
    from the current `orders`/`order_items` aggregate state at any time --
    this table is a cache of the aggregate's shape for reads, never a second
    source of truth. `app/service.py`'s own write paths keep it current by
    upserting it in the SAME transaction as every aggregate mutation (the
    projection-disabled negative test,
    `tests/unit/test_place_order.py::test_read_model_goes_stale_if_projection_is_skipped`,
    proves this by skipping the upsert and showing the read goes stale).
    """

    __tablename__ = "order_view"
    __table_args__ = ({"schema": SCHEMA},)

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shipping_address: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class OutboxEvent(Base):
    """`order_svc.outbox` -- this service's OWN transactional outbox (ch.17
    pattern, same shape as every other standalone service's), producing
    `order.placed` -- see `app/relay.py`. Written in the SAME local
    transaction as the aggregate's PENDING insert AND the `order_view`
    PENDING row (`app/repository.py::create_order_with_outbox_and_view`) --
    the three-way atomicity guarantee this CQRS lane's acceptance criteria
    calls out directly."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "idx_order_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
