"""create order_svc schema and the full CQRS table set

order-service owns this schema from day one, idiomatic-from-the-start (no
CDC, no shared-schema phase -- see `../../MIGRATION.md`): a SEPARATE
`order_svc` Postgres schema (NOT the reserved word `order` -- see
`app/db.py`'s docstring), in the SAME Postgres *instance* (`localhost:5432`,
db `monolith`) every example in this project shares by default.

Five tables, two families:

- Command side: `customers` (OWNED master data, forward-filled from the
  monolith's seed by `0002_seed_customers.py` -- see `app/models.py::Customer`'s
  docstring), `orders` (the aggregate root), `order_items` (sku/quantity/
  unit_price_cents snapshots, no FK to inventory), `outbox` (this service's
  own transactional outbox, producing `order.placed`).
- Read side: `order_view` -- the ONE table `app/routes.py`'s GET handlers
  query. Projected in the SAME transaction as every aggregate write
  (`app/repository.py`).

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

SCHEMA = "order_svc"


def upgrade() -> None:
    # Defensive/idempotent -- `migrations/env.py::do_run_migrations` already
    # creates this schema before Alembic's own `alembic_version` bookkeeping
    # table is created inside it, so this statement is a no-op in the normal
    # `alembic upgrade head` path.
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_customers_email", "customers", ["email"], unique=True, schema=SCHEMA
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.customers.id"),
            nullable=False,
        ),
        sa.Column("customer_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("shipping_address", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.orders.id"), nullable=False
        ),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_order_items_order_id", "order_items", ["order_id"], schema=SCHEMA
    )

    # The CQRS read model -- keyed 1:1 by order_id (the aggregate's own id),
    # one current row per order, upserted (never appended to) on every
    # status transition. See app/models.py::OrderView's docstring.
    op.create_table(
        "order_view",
        sa.Column("order_id", sa.BigInteger(), primary_key=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("shipping_address", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_order_outbox_unpublished",
        "outbox",
        ["created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_order_outbox_unpublished", table_name="outbox", schema=SCHEMA)
    op.drop_table("outbox", schema=SCHEMA)
    op.drop_table("order_view", schema=SCHEMA)
    op.drop_index("idx_order_items_order_id", table_name="order_items", schema=SCHEMA)
    op.drop_table("order_items", schema=SCHEMA)
    op.drop_table("orders", schema=SCHEMA)
    op.drop_index("uq_customers_email", table_name="customers", schema=SCHEMA)
    op.drop_table("customers", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
