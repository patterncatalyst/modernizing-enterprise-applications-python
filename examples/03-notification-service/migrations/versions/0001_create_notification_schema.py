"""create notification schema and notifications table

notification-service owns this schema from day one (ch.17 S5, DRQ-028/
DRQ-035) -- distinct from `00-monolith`'s `public.notifications` table: this
is a SEPARATE table in a SEPARATE Postgres schema, in the SAME Postgres
*instance* (`localhost:5432`, db `monolith`) every example in this project
shares by default.

Why own schema, not shared (contrast with `02-review-service`, DRQ-028):
Review only ever *reads* a synchronously-consistent REST contract, so it
could stay in the monolith's shared schema. Notification is event-driven
(consumes `order.placed` off Kafka asynchronously) -- sharing the upstream
aggregate's table would mean two writers racing on the same rows (the
monolith's decommissioned synchronous path and this service's consumer) with
no way to reconcile them. Owning the table from the start avoids that
split-brain entirely.

`customer_id` / `order_id` are plain `BIGINT` columns, not foreign keys into
the monolith's `customers`/`orders` tables -- this service's schema must not
reach across into tables it does not own (see `app/models.py`'s docstring).

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
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        schema="notification",
    )

    op.create_index(
        "idx_notifications_customer_id",
        "notifications",
        ["customer_id"],
        schema="notification",
    )

    # Partial unique index (ignores NULL order_id, since not every
    # notification need originate from an order) -- the database-level
    # backstop for app/service.py::record_order_placed's check-then-insert
    # idempotent dedupe, for the case of two at-least-once `order.placed`
    # redeliveries racing concurrently.
    op.create_index(
        "uq_notifications_order_id",
        "notifications",
        ["order_id"],
        unique=True,
        schema="notification",
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_order_id", table_name="notifications", schema="notification")
    op.drop_index(
        "idx_notifications_customer_id", table_name="notifications", schema="notification"
    )
    op.drop_table("notifications", schema="notification")
    op.execute("DROP SCHEMA IF EXISTS notification CASCADE")
