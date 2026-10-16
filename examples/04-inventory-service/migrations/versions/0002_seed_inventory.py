"""seed inventory_items with the three demo skus

This service's OWN seed, independent of `00-monolith`'s `common/management/
commands/seed.py` -- same names, prices, and quantities as the monolith's
seed data (Python sibling of the Java monolith's `V2__seed_data.sql`), so the
read contract (`GET /api/inventory`) returns the identical demo dataset
whichever side currently serves the route (strangler-proxy equivalence).

Idempotent: a plain `INSERT` guarded by a `sku`-existence check via
`ON CONFLICT (sku) DO NOTHING`, so re-running `alembic upgrade head` against
an already-seeded database (or one whose rows were later modified by
`Reserve`/`Release`) never resets quantities back to the seed baseline.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_ROWS = [
    {
        "sku": "SKU-WIDGET-001",
        "name": "Standard Widget",
        "price_cents": 1999,
        "quantity_on_hand": 100,
    },
    {
        "sku": "SKU-GADGET-002",
        "name": "Deluxe Gadget",
        "price_cents": 4999,
        "quantity_on_hand": 50,
    },
    # Deliberately low stock -- exercises the insufficient-stock /
    # reservation_ok=false gRPC path (see tests/test_inventory_grpc.py)
    # without any extra setup, same teaching point as the monolith's own
    # seed comment on this row.
    {
        "sku": "SKU-GIZMO-003",
        "name": "Pocket Gizmo",
        "price_cents": 999,
        "quantity_on_hand": 5,
    },
]

_inventory_items = sa.table(
    "inventory_items",
    sa.column("sku", sa.String),
    sa.column("name", sa.String),
    sa.column("price_cents", sa.BigInteger),
    sa.column("quantity_on_hand", sa.Integer),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    schema="inventory",
)


def upgrade() -> None:
    seeded_at = datetime(2026, 1, 5, 8, 0, 0, tzinfo=UTC)
    bind = op.get_bind()
    for row in _SEED_ROWS:
        stmt = (
            pg_insert(_inventory_items)
            .values(**row, updated_at=seeded_at)
            .on_conflict_do_nothing(index_elements=["sku"])
        )
        bind.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    skus = [row["sku"] for row in _SEED_ROWS]
    bind.execute(_inventory_items.delete().where(_inventory_items.c.sku.in_(skus)))
