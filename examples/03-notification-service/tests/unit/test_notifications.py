"""`/api/notifications` contract tests -- the FastAPI sibling of the
monolith's `tests/test_smoke.py`-equivalent coverage for
`notification/views.py::NotificationListView`. Exercises this service's OWN,
already-migrated `notification` schema (see `conftest.py`), proving the read
contract matches byte-for-byte: field names and the required-`customerId`
400."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import repository
from app.db import create_engine, create_session_factory


def _random_id() -> int:
    # Random, not sequential/fixed -- these tests run against a real,
    # potentially-reused Postgres (not a fresh-per-test schema), so a fixed
    # id would risk colliding with another test run's row and tripping the
    # order_id partial unique index.
    return random.randint(10_000_000, 2_000_000_000)


async def _seed_notification(*, customer_id: int, order_id: int) -> None:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            await repository.create(
                session,
                customer_id=customer_id,
                order_id=order_id,
                channel="EMAIL",
                message=f"Order #{order_id} confirmed, total $49.99",
                sent_at=datetime.now(UTC),
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_notifications_returns_camel_case_array(client: TestClient):
    customer_id = _random_id()
    order_id = _random_id()
    await _seed_notification(customer_id=customer_id, order_id=order_id)

    response = client.get("/api/notifications", params={"customerId": customer_id})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    notification = body[0]
    assert set(notification) == {"id", "customerId", "orderId", "channel", "message", "sentAt"}
    assert notification["customerId"] == customer_id
    assert notification["orderId"] == order_id
    assert notification["channel"] == "EMAIL"


@pytest.mark.asyncio
async def test_list_notifications_filters_by_customer_id(client: TestClient):
    customer_a = _random_id()
    customer_b = _random_id()
    await _seed_notification(customer_id=customer_a, order_id=_random_id())
    await _seed_notification(customer_id=customer_b, order_id=_random_id())

    response = client.get("/api/notifications", params={"customerId": customer_a})
    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(notification["customerId"] == customer_a for notification in body)


def test_list_notifications_returns_empty_array_for_unknown_customer(client: TestClient):
    response = client.get("/api/notifications", params={"customerId": _random_id()})
    assert response.status_code == 200
    assert response.json() == []


def test_list_notifications_missing_customer_id_returns_400_uniform_body(client: TestClient):
    # Matches the monolith's `NotificationListView.get`: no `customerId`
    # query param -> `ValidationError` -> DRF's generic 400. FastAPI's
    # required `Query(...)` (no default) raises `RequestValidationError`,
    # remapped by app/errors.py to the same `400 VALIDATION_FAILED`.
    response = client.get("/api/notifications")
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "VALIDATION_FAILED"


def test_no_trailing_slash_redirect(client: TestClient):
    # `redirect_slashes=False`, same contract posture as review-service: a
    # trailing-slash request must not 307-redirect.
    response = client.get("/api/notifications/", follow_redirects=False)
    assert response.status_code != 307
