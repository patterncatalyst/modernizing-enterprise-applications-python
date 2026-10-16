"""Shared fixtures for the REST contract tests (`tests/unit/`).

These tests need a reachable Postgres with this service's OWN `notification`
schema already migrated (`uv run alembic upgrade head` against
`DATABASE_URL`) -- NOT the monolith's shared schema (contrast with
`02-review-service`'s `tests/conftest.py`, which needs `manage.py migrate &&
manage.py seed` from `00-monolith` instead).

No Kafka broker is required here: the `client` fixture builds a lightweight
test app that reuses the production router (`app/routes.py`) and error
handlers (`app/errors.py`) but swaps in a Kafka-free lifespan (engine +
session factory only). The full `app.main.create_app()` wiring -- which also
starts the `order.placed` consumer -- is exercised end-to-end instead by
`tests/integration/`'s Testcontainers Kafka+Postgres test.
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
        engine = db.create_engine()
        app.state.engine = engine
        app.state.session_factory = db.create_session_factory(engine)
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
    context manager drives the lifespan (engine open/dispose) for us, same
    convention as `02-review-service`'s `client` fixture."""
    app = _build_db_only_app()
    with TestClient(app) as test_client:
        yield test_client
