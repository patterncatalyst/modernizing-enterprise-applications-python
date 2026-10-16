"""Shared fixtures for `tests/`.

These tests need a reachable Postgres with this service's OWN `inventory`
schema already migrated AND seeded (`uv run alembic upgrade head` against
`DATABASE_URL`) -- NOT the monolith's shared schema. No Kafka broker is
required anywhere in this suite: the CDC consumer (`app/cdc_consumer.py`) is
transition-only and flag-gated OFF by default, and the gRPC tests exercise
`app/grpc_server.py::InventoryGrpcServiceServicer` directly rather than
through a real network listener, so no gRPC port needs to be bound either.

Same convention as `03-notification-service`'s `tests/unit/conftest.py`: the
`client` fixture builds a lightweight test app that reuses the production
router (`app/routes.py`) and error handlers (`app/errors.py`) but swaps in a
DB-only lifespan (engine + session factory only, no gRPC server, no CDC
consumer) -- the full `app.main.create_app()` wiring is exercised instead by
the live verification run documented in `../MIGRATION.md`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import db
from app.errors import install_exception_handlers
from app.models import Compensation, InventoryItem
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
    """A `TestClient` around a fresh gRPC/Kafka-free app instance --
    `TestClient`'s context manager drives the lifespan (engine open/dispose)
    for us, same convention as the other services' `client` fixture."""
    app = _build_db_only_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A standalone async session factory for tests that talk to the
    repository/gRPC servicer directly, independent of the HTTP `client`
    fixture's own engine."""
    engine = db.create_engine()
    factory = db.create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


# The canonical seed baseline (`migrations/versions/0002_seed_inventory.py`)
# -- the fixed, documented skus this whole suite exercises. Unlike
# notification-service's tests (random ids, safe to leave behind forever),
# inventory's `Reserve`/`Release` RPCs mutate these SAME three rows by
# design, so every test that reserves/releases stock must leave the table
# back at this baseline for the next test, regardless of run order.
SEED_QUANTITIES = {
    "SKU-WIDGET-001": 100,
    "SKU-GADGET-002": 50,
    "SKU-GIZMO-003": 5,
}


@pytest.fixture(autouse=True)
async def reset_inventory_quantities(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Autouse teardown: restores the three seed skus' `quantity_on_hand` to
    `SEED_QUANTITIES`, and empties `inventory.compensations` (DRQ-043's
    idempotency ledger), after every test -- so `Reserve`/`Release`
    mutations AND recorded idempotency keys in one test (or one `pytest`
    invocation) never leak into the next, regardless of test execution order
    or how many times the suite is re-run against the same Postgres. Without
    the ledger wipe, a fixed idempotency-key literal reused across test runs
    would collide with its own prior run's row and make a genuinely-first
    `Release` call look like a replay."""
    yield
    async with session_factory() as session:
        for sku, quantity in SEED_QUANTITIES.items():
            await session.execute(
                update(InventoryItem)
                .where(InventoryItem.sku == sku)
                .values(quantity_on_hand=quantity)
            )
        await session.execute(delete(Compensation))
        await session.commit()
