"""Async SQLAlchemy engine/session -- mirrors every other standalone
service's `app/db.py` in this project (`05-payment-service`'s/
`06-shipping-service`'s, byte-for-byte in shape) except for the schema name.

SCHEMA NAME CHOICE: `order` is a reserved word in the SQL standard (and in
Postgres specifically it collides with nothing reserved at the identifier
level, but IS one of the ~70 "reserved, cannot be function or type" keywords
-- `CREATE SCHEMA order;` still parses, but every unqualified reference to it
anywhere near a `FROM`/`JOIN`/DDL clause becomes a quoting minefield, e.g.
`SET search_path = order, public` is a syntax error without quoting it as
`"order"` every single time). Alembic's `version_table_schema`, this file's
`search_path` server setting, and every `__table_args__ = {"schema": ...}` in
`app/models.py` would ALL need defensive quoting forever. The service owns
its tables and schema name choice end to end, so this project picks the
unambiguous, zero-quoting-tax name **`order_svc`** instead of fighting the
reserved word on every line -- documented here once rather than re-litigated
at each call site.
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
_SEARCH_PATH = "order_svc,public"


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
