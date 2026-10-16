"""create shipping schema, shipments/outbox/sagas/saga_log tables

shipping-service owns this schema from day one, idiomatic-from-the-start (no
CDC, no shared-schema phase -- see `../../MIGRATION.md`): a SEPARATE
`shipping` Postgres schema, in the SAME Postgres *instance* (`localhost:5432`,
db `monolith`) every example in this project shares by default.

Why own schema (contrast with the monolith's `shipping.Shipment`, which FKs
directly into `order.Order` in the shared schema, SMELL[ch.18]): this
service's saga is triggered by `payment.captured` off Kafka, not called
synchronously in-process -- sharing the upstream aggregate's table would mean
two writers (the monolith's in-process dispatch path and this service's
saga) racing on related rows with no way to reconcile them. Owning the table
from the start avoids that split-brain entirely, same reasoning every other
standalone service's own-schema migration in this project documents.

`order_id` is a plain `BIGINT` column on both `shipments` and `sagas`, not a
foreign key into the monolith's `orders` table -- this service's schema must
not reach across into tables it does not own (see `app/models.py`'s
docstring). `saga_log.saga_id` IS a real foreign key into this SAME schema's
`sagas` table -- an ordinary intra-schema relationship, not the cross-service
smell.

This migration also creates `shipping.sagas` and `shipping.saga_log` --
r06's net-new tables, the DB-backed saga state machine
`app/orchestrator.py` drives (`_docs/17-appendix-d-sagas.md`'s Figure D.1
pattern), and `shipping.outbox`, this service's OWN transactional outbox
(the pattern `05-payment-service`'s own-schema migration already established
for this project).

Revision ID: 0001
Revises:
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

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
    op.execute("CREATE SCHEMA IF NOT EXISTS shipping")

    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="shipping",
    )
    # Plain (not unique) index: a saga dispatches at most once per order in
    # practice (the saga's own RUNNING-only idempotent guard prevents a
    # redelivered payment.captured from re-triggering dispatch), but the
    # column stays list-shaped to match the monolith's own
    # `shipping.services.list_by_order_id` contract byte-for-byte.
    op.create_index(
        "idx_shipments_order_id",
        "shipments",
        ["order_id"],
        schema="shipping",
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
        schema="shipping",
    )
    # Partial index on unpublished rows -- keeps app/relay.py's poll query
    # cheap regardless of how large the table grows, same convention as
    # every other service's outbox table in this project.
    op.create_index(
        "idx_shipping_outbox_unpublished",
        "outbox",
        ["created_at"],
        schema="shipping",
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "sagas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="shipping",
    )
    # UNIQUE: one saga per order -- the idempotency backstop for the
    # at-least-once `payment.captured` delivery guarantee
    # (`app/service.py::handle_payment_captured`'s check-then-insert dedupe).
    op.create_index(
        "uq_sagas_order_id",
        "sagas",
        ["order_id"],
        unique=True,
        schema="shipping",
    )

    op.create_table(
        "saga_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("saga_id", sa.BigInteger(), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["saga_id"], ["shipping.sagas.id"], name="fk_saga_log_saga_id_sagas"
        ),
        schema="shipping",
    )
    op.create_index(
        "idx_saga_log_saga_id",
        "saga_log",
        ["saga_id"],
        schema="shipping",
    )


def downgrade() -> None:
    op.drop_index("idx_saga_log_saga_id", table_name="saga_log", schema="shipping")
    op.drop_table("saga_log", schema="shipping")
    op.drop_index("uq_sagas_order_id", table_name="sagas", schema="shipping")
    op.drop_table("sagas", schema="shipping")
    op.drop_index("idx_shipping_outbox_unpublished", table_name="outbox", schema="shipping")
    op.drop_table("outbox", schema="shipping")
    op.drop_index("idx_shipments_order_id", table_name="shipments", schema="shipping")
    op.drop_table("shipments", schema="shipping")
    op.execute("DROP SCHEMA IF EXISTS shipping CASCADE")
