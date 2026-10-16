"""seed customers with Ada/Grace, matching the monolith's seed

This service's OWN seed, independent of `00-monolith`'s `common/management/
commands/seed.py` -- same names, emails, and created_at timestamps as the
monolith's seed data (`00-monolith/common/management/commands/seed.py`), so
`place_order()`'s customer validation accepts the SAME demo customer ids
(1=Ada, 2=Grace) regardless of which side currently serves checkout.
FORWARD-FILL, not CDC: this is a one-time migration-time copy, not a live
sync -- see `../../MIGRATION.md` for why order-service owns this master data
outright rather than reaching into the monolith's shared `common.Customer`
table over any protocol.

Idempotent: `ON CONFLICT (email) DO NOTHING`, so re-running `alembic upgrade
head` against an already-seeded database never duplicates rows.

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

SCHEMA = "order_svc"

_SEED_ROWS = [
    {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "created_at": datetime(2026, 1, 5, 9, 0, 0, tzinfo=UTC),
    },
    {
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "created_at": datetime(2026, 1, 6, 10, 30, 0, tzinfo=UTC),
    },
]

_customers = sa.table(
    "customers",
    sa.column("name", sa.String),
    sa.column("email", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
    schema=SCHEMA,
)


def upgrade() -> None:
    bind = op.get_bind()
    for row in _SEED_ROWS:
        stmt = pg_insert(_customers).values(**row).on_conflict_do_nothing(
            index_elements=["email"]
        )
        bind.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    emails = [row["email"] for row in _SEED_ROWS]
    bind.execute(_customers.delete().where(_customers.c.email.in_(emails)))
