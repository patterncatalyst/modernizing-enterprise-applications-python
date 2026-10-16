"""create payment schema, payments table, and outbox table

payment-service owns this schema from day one, idiomatic-from-the-start (no
CDC, no shared-schema phase -- see `../../MIGRATION.md`): a SEPARATE `payment`
Postgres schema, in the SAME Postgres *instance* (`localhost:5432`, db
`monolith`) every example in this project shares by default.

Why own schema (contrast with the monolith's `payment.Payment`, which FKs
directly into `order.Order` in the shared schema, SMELL[ch.18]): this service
is choreographed off `order.placed`, not called synchronously in-process --
sharing the upstream aggregate's table would mean two writers (the monolith's
synchronous checkout path and this service's consumer) racing on related rows
with no way to reconcile them. Owning the table from the start avoids that
split-brain entirely, same reasoning `03-notification-service`'s own-schema
migration documents.

`order_id` is a plain `BIGINT` column, not a foreign key into the monolith's
`orders` table -- this service's schema must not reach across into tables it
does not own (see `app/models.py`'s docstring).

This migration also creates `payment.outbox`, this service's OWN
transactional outbox -- the half of the pattern notification-service's schema
never needed (it only ever consumes `order.placed`; it never publishes).

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
    op.execute("CREATE SCHEMA IF NOT EXISTS payment")

    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="payment",
    )

    # Unique (not partial -- every payment row has an order_id) index: the
    # database-level backstop for app/service.py::process_order_placed's
    # check-then-insert idempotent dedupe, for the case of two at-least-once
    # `order.placed` redeliveries racing concurrently. Also the idempotency
    # backstop the acceptance criteria calls out directly: one order places
    # at most one payment attempt.
    op.create_index(
        "uq_payments_order_id",
        "payments",
        ["order_id"],
        unique=True,
        schema="payment",
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
        schema="payment",
    )

    # Partial index on unpublished rows -- keeps app/relay.py's poll query
    # cheap regardless of how large the table grows, same convention as the
    # monolith's `common_outbox` index and notification-service's
    # `uq_notifications_order_id` partial-index precedent (though this one is
    # a plain index, not unique: many outbox rows can be simultaneously
    # unpublished).
    op.create_index(
        "idx_payment_outbox_unpublished",
        "outbox",
        ["created_at"],
        schema="payment",
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_payment_outbox_unpublished", table_name="outbox", schema="payment")
    op.drop_table("outbox", schema="payment")
    op.drop_index("uq_payments_order_id", table_name="payments", schema="payment")
    op.drop_table("payments", schema="payment")
    op.execute("DROP SCHEMA IF EXISTS payment CASCADE")
