"""Shared fixtures for the review-service test suite.

These tests need a reachable Postgres with the monolith's shared schema
already migrated AND seeded -- same convention as `00-monolith`'s own
pytest-django suite (a "shared test DB", not a per-service throwaway
schema): this service owns no migrations of its own, so there is nothing for
it to create. See `../README.md` / `../AGENTS.md` for the one-time setup
commands (`manage.py migrate && manage.py seed` from `00-monolith`, against
`DATABASE_URL`).
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

REVIEWER_USERNAME = "reviewer"
REVIEWER_PASSWORD = "review-pw-r02"
SEEDED_SKU = "SKU-WIDGET-001"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A `TestClient` around a fresh app instance (fresh engine/session
    factory per test, built from `DATABASE_URL`) -- `TestClient`'s context
    manager drives the FastAPI `lifespan` (startup/shutdown) for us."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def reviewer_auth_header() -> dict[str, str]:
    """Basic-auth header for the monolith's seeded `reviewer` demo user."""
    token = base64.b64encode(f"{REVIEWER_USERNAME}:{REVIEWER_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}
