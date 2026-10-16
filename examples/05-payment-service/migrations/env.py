"""Alembic online-migration environment for payment-service's OWNED `payment`
schema -- byte-for-byte the same shape as `03-notification-service`'s
`migrations/env.py`, just pointed at this service's own schema name and
`app/models.py::Base`.

Runs fully async via SQLAlchemy's async engine + `Connection.run_sync` (the
officially documented Alembic-with-asyncio pattern) -- there is no separate
synchronous driver dependency (e.g. `psycopg2`) pulled in just for
migrations; the same `asyncpg` driver `app/db.py` uses at runtime is reused
here.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import Settings
from app.db import resolve_database_url
from app.models import Base

# Alembic Config object, providing access to values within alembic.ini.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `app/models.py::Base.metadata` is the single source of truth autogenerate
# diffs against.
target_metadata = Base.metadata

# The schema Alembic's own `alembic_version` bookkeeping table lives in --
# keeps migration history scoped to this service's owned schema rather than
# the shared database's `public` schema (which this service never touches).
_VERSION_TABLE_SCHEMA = "payment"


def _database_url() -> str:
    """Resolves `DATABASE_URL` the same way `app/db.py` does, read at
    migration-run time (not import time) so `DATABASE_URL` env overrides
    (e.g. the Testcontainers integration test, or CI) are picked up."""
    return resolve_database_url(Settings.from_env().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade
    head --sql`) -- not used by this service's own tooling, but kept for
    parity with Alembic's standard environment template."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_VERSION_TABLE_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # The `payment` schema must exist before Alembic can create/read its own
    # `alembic_version` table inside it (`version_table_schema` below) --
    # Alembic does not create schemas itself. Idempotent, and re-asserted
    # defensively inside the first migration's own `upgrade()` too (see
    # `versions/0001_create_payment_schema.py`). Committed in its OWN
    # transaction, separate from the one `context.begin_transaction()`
    # manages below for the migration itself -- SQLAlchemy 2.x Core
    # connections autobegin but do not auto-commit, so leaving this
    # uncommitted would roll the `CREATE SCHEMA` back along with everything
    # else if `run_migrations_online`'s `connect()` context exits without an
    # explicit commit.
    connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS payment"))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=_VERSION_TABLE_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _database_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
