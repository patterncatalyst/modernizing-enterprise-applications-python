"""create inventory.compensations idempotency ledger

r05, DRQ-043 (IDEMPOTENT-COMPENSATION lane): backs `Release`'s at-least-once
safety -- the payment saga can retry a `Release` call and this ledger is what
lets `app/repository.py::release` tell "never applied" from "already applied
under this key" apart in ONE atomic statement (`INSERT ... ON CONFLICT
(idempotency_key) DO NOTHING RETURNING id`), the same "let the unique index
do the concurrency-safety work" posture `0001_create_inventory_schema.py`
already uses for `inventory_items.sku` (and `0002_seed_inventory.py`'s own
`on_conflict_do_nothing(index_elements=["sku"])` upsert).

Lives in this service's OWN `inventory` schema (DRQ-044 posture, same as
`inventory_items`) -- no foreign key back into the monolith.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compensations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        # Not populated by this lane -- see `app/models.py::Compensation`'s
        # docstring for why (`ReleaseRequest` carries no separate order_id
        # field today). Reserved for a later lane to backfill without a
        # migration.
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        schema="inventory",
    )

    # Unique index on idempotency_key -- the arbiter `app/repository.py
    # ::release`'s `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING`
    # targets. This is the race-safety mechanism: Postgres serializes
    # concurrent inserts targeting the same key on this index, so two
    # identical-key `Release` calls racing each other can never both insert
    # (and therefore never both re-increment).
    op.create_index(
        "uq_compensations_idempotency_key",
        "compensations",
        ["idempotency_key"],
        unique=True,
        schema="inventory",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_compensations_idempotency_key", table_name="compensations", schema="inventory"
    )
    op.drop_table("compensations", schema="inventory")
