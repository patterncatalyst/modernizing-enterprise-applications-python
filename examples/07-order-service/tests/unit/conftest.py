"""Shared fixtures for the unit test layer (`tests/unit/`).

These tests need a reachable Postgres with this service's OWN `order_svc`
schema already migrated and seeded (`uv run alembic upgrade head` against
`DATABASE_URL`) -- same convention as every other standalone service's
`tests/unit/conftest.py` in this project.

No Kafka broker and no live inventory-service gRPC server are required here:
- the `client` fixture builds a lightweight test app that reuses the
  production router/error handlers but swaps in a Kafka-free lifespan
  (engine + session factory only); the full `app.main.create_app()` wiring
  is exercised end-to-end instead by `tests/integration/`.
- `app.service.place_order`/the four reactions take `inventory_grpc_target`
  explicitly rather than reading it off a module-level `Settings` singleton,
  so unit tests can monkeypatch `app.inventory_client.AsyncInventoryClient`
  directly without needing a real gRPC server at all -- see
  `tests/unit/test_place_order.py`'s `fake_inventory_client` fixture.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.errors import install_exception_handlers
from app.routes import router


def _build_db_only_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from app.config import Settings

        engine = db.create_engine()
        app.state.engine = engine
        app.state.session_factory = db.create_session_factory(engine)
        app.state.settings = Settings.from_env()
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(redirect_slashes=False, lifespan=lifespan)
    install_exception_handlers(app)
    app.include_router(router)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A `TestClient` around a fresh Kafka-free app instance -- `TestClient`'s
    context manager drives the lifespan (engine open/dispose) for us."""
    app = _build_db_only_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def session_factory():
    """A bare session factory for tests that drive `app.service`/
    `app.repository` directly, without going through the HTTP layer."""
    engine = db.create_engine()
    factory = db.create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()
