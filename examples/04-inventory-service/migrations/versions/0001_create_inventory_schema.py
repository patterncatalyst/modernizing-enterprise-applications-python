"""create inventory schema and inventory_items table

inventory-service owns this schema from day one (ch.19, DRQ-044) -- distinct
from `00-monolith`'s `public.inventory_items` table: this is a SEPARATE table
in a SEPARATE Postgres schema, in the SAME Postgres *instance*
(`localhost:5432`, db `monolith`) every example in this project shares by
default.

Why own schema, not shared (same rationale as notification-service's
DRQ-035, contrast with review-service's DRQ-028): the gRPC `Reserve`/
`Release` mutating hot path (r04/ch.19 S6, DRQ-041/DRQ-042) needs this
service's own atomic, concurrency-safe `UPDATE` statements against rows it
alone owns -- sharing the monolith's table would mean two writers (the
monolith's own checkout path and this service's gRPC server) racing on the
same rows with no way to reconcile them.

`id` is a plain autoincrementing BIGINT primary key, owned by this service's
own Postgres sequence (see `app/models.py`'s docstring for the CDC-assigned-id
contrast with the Java sibling).

Revision ID: 0001
Revises:
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Defensive/idempotent -- `migrations/env.py::do_run_migrations` already
    # creates this schema before Alembic's own `alembic_version` bookkeeping
    # table is created inside it, so this statement is a no-op in the normal
    # `alembic upgrade head` path. Kept here so this migration is also
    # correct if ever run by different tooling that skips that env.py step.
    op.execute("CREATE SCHEMA IF NOT EXISTS inventory")

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="inventory",
    )

    # Unique index on sku -- `reserve`/`release`'s conditional UPDATEs
    # (app/repository.py) key on sku, and the monolith's own
    # `inventory_items.sku` column is `unique=True` -- matching it here keeps
    # the two schemas' invariants aligned even though they are otherwise
    # fully independent.
    op.create_index(
        "uq_inventory_items_sku",
        "inventory_items",
        ["sku"],
        unique=True,
        schema="inventory",
    )


def downgrade() -> None:
    op.drop_index("uq_inventory_items_sku", table_name="inventory_items", schema="inventory")
    op.drop_table("inventory_items", schema="inventory")
    op.execute("DROP SCHEMA IF EXISTS inventory CASCADE")
