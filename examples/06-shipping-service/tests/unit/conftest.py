"""Shared fixtures for the REST contract and orchestrator unit tests
(`tests/unit/`).

These tests need a reachable Postgres with this service's OWN `shipping`
schema already migrated (`uv run alembic upgrade head` against
`DATABASE_URL`) -- same convention as every other standalone service's
`tests/unit/conftest.py`.

No Kafka broker is required here: the `client` fixture builds a lightweight
test app that reuses the production router (`app/routes.py`) and error
handlers (`app/errors.py`) but swaps in a Kafka-free lifespan (engine +
session factory only). The full `app.main.create_app()` wiring -- which also
starts the `payment.captured` consumer AND the outbox relay -- is exercised
end-to-end instead by `tests/integration/`'s Testcontainers Kafka+Postgres
test.
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
    convention as every other standalone service's `client` fixture."""
    app = _build_db_only_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def session_factory():
    """A bare session factory (no FastAPI app) for the orchestrator/service
    tests, which drive `app.orchestrator`/`app.service` directly against the
    real, already-migrated `shipping` schema -- same shape as
    `05-payment-service/tests/unit/test_service.py`'s per-test
    `create_engine()`/`create_session_factory()` pattern, but shared here as
    a fixture since every orchestrator test needs one."""
    engine = db.create_engine()
    factory = db.create_session_factory(engine)
    yield factory
    await engine.dispose()
