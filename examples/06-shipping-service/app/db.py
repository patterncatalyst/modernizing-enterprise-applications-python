"""Async SQLAlchemy engine/session -- mirrors every other standalone
service's `app/db.py` in this project (`05-payment-service`'s byte-for-byte)
except for the schema name: this service's `shipments`/`outbox`/`sagas`/
`saga_log` tables live in their own `shipping` Postgres schema, created and
migrated by Alembic (`../migrations/`).

Every connection this engine opens sets `search_path=shipping,public` via
asyncpg's `server_settings` startup parameter, so e.g. an ad hoc `psql`
session against this database also defaults here. That is a convenience, not
the correctness guarantee: every model in `app/models.py` also declares
`schema="shipping"` explicitly in `__table_args__`, so generated SQL is
always fully schema-qualified regardless of the connection's search path.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Same default every other service in this project uses, so this service
# points at the same INFRA-lane compose stack out of the box.
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_SEARCH_PATH = "shipping,public"


def resolve_database_url(raw: str | None = None) -> str:
    """Normalize the monolith's psycopg-style `DATABASE_URL`
    (`postgresql://...`) onto the asyncpg driver SQLAlchemy's async engine
    needs (`postgresql+asyncpg://...`). Accepts either scheme as input,
    identical to every other standalone service's `resolve_database_url`.
    """
    value = raw if raw is not None else os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://") :]
    return value


def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        resolve_database_url(database_url),
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": _SEARCH_PATH}},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, from the session factory
    the app's lifespan built at startup (see `app/main.py`)."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
