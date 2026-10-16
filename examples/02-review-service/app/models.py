"""SQLAlchemy 2.x declarative mappings onto the monolith's shared schema.

Column names and `db_table`s mirror `00-monolith`'s Django models exactly
(`review/models.py`, `common/models.py`, `inventory/models.py`, plus Django's
own built-in `auth_user` table from `django.contrib.auth`) -- this service
reads/writes the SAME tables, it just doesn't create or migrate them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuthUser(Base):
    """Django's `django.contrib.auth.models.User`, table `auth_user`.

    Read-only from this service's point of view: we only ever verify
    submitted HTTP Basic credentials against it (see `app/auth.py`), never
    write to it. Only the columns this service actually reads are mapped.
    """

    __tablename__ = "auth_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column()


class Customer(Base):
    """`common.Customer`, table `customers` -- shared-kernel entity this
    service only reads (to validate `customerId` on `POST /api/reviews`)."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))


class InventoryItem(Base):
    """`inventory.InventoryItem`, table `inventory_items` -- this service
    only reads it, to resolve `sku` <-> `id` for reviews."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))


class Review(Base):
    """`review.Review`, table `reviews` -- the one table this service owns
    writes to (via `POST /api/reviews`)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"))
    inventory_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory_items.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
