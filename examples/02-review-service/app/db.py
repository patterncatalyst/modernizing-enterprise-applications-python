"""Async SQLAlchemy engine/session.

This service owns no schema of its own: `reviews`, `customers`,
`inventory_items`, and `auth_user` all live in the monolith's shared Postgres
database, created by `00-monolith`'s `manage.py migrate` (+ `seed`). This
module only ever opens sessions against tables that already exist -- there is
no Alembic setup here, intentionally, matching the Java sibling's
"no migrations of its own" note (see ../README.md).
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

# Same default the monolith's config/settings.py uses, so this service points
# at the same INFRA-lane compose stack out of the box.
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"


def resolve_database_url(raw: str | None = None) -> str:
    """Normalize the monolith's psycopg-style `DATABASE_URL`
    (`postgresql://...`) onto the asyncpg driver SQLAlchemy's async engine
    needs (`postgresql+asyncpg://...`). Accepts either scheme as input so
    the same `DATABASE_URL` env var works unmodified for both services.
    """
    value = raw if raw is not None else os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://") :]
    return value


def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(resolve_database_url(database_url), pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, from the session factory
    the app's lifespan built at startup (see `app/main.py`)."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
