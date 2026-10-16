"""`/api/payments` contract tests -- the FastAPI sibling of the monolith's
`payment/views.py` coverage (`PaymentListView`/`PaymentDetailView`).
Exercises this service's OWN, already-migrated `payment` schema (see
`conftest.py`), proving the read contract matches byte-for-byte: field names,
the required-`orderId` 400, and the 404-by-id uniform error body."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import create_engine, create_session_factory
from app.models import Payment


def _random_id() -> int:
    # Random, not sequential/fixed -- these tests run against a real,
    # potentially-reused Postgres (not a fresh-per-test schema), so a fixed
    # id would risk colliding with another test run's row and tripping the
    # order_id unique index.
    return random.randint(10_000_000, 2_000_000_000)


async def _seed_payment(
    *, order_id: int, amount_cents: int = 4999, method: str = "CARD", status: str = "CAPTURED"
) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            payment = Payment(
                order_id=order_id,
                amount_cents=amount_cents,
                method=method,
                status=status,
                created_at=datetime.now(UTC),
            )
            session.add(payment)
            await session.flush()
            await session.commit()
            return payment.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_payments_returns_camel_case_array(client: TestClient):
    order_id = _random_id()
    await _seed_payment(order_id=order_id, amount_cents=4999, method="CARD", status="CAPTURED")

    response = client.get("/api/payments", params={"orderId": order_id})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    payment = body[0]
    assert set(payment) == {"id", "orderId", "amountCents", "method", "status", "createdAt"}
    assert payment["orderId"] == order_id
    assert payment["amountCents"] == 4999
    assert payment["method"] == "CARD"
    assert payment["status"] == "CAPTURED"


def test_list_payments_returns_empty_array_for_unknown_order(client: TestClient):
    response = client.get("/api/payments", params={"orderId": _random_id()})
    assert response.status_code == 200
    assert response.json() == []


def test_list_payments_missing_order_id_returns_400_uniform_body(client: TestClient):
    # Matches the monolith's `PaymentListView.get`: no `orderId` query param
    # -> `ValidationError` -> DRF's generic 400. FastAPI's required
    # `Query(...)` (no default) raises `RequestValidationError`, remapped by
    # app/errors.py to the same `400 VALIDATION_FAILED`.
    response = client.get("/api/payments")
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_get_payment_by_id_returns_camel_case_body(client: TestClient):
    order_id = _random_id()
    payment_id = await _seed_payment(order_id=order_id, amount_cents=1500, status="CAPTURED")

    response = client.get(f"/api/payments/{payment_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == payment_id
    assert body["orderId"] == order_id
    assert body["amountCents"] == 1500


def test_get_payment_by_id_unknown_returns_404_uniform_body(client: TestClient):
    response = client.get(f"/api/payments/{_random_id()}")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "NOT_FOUND"


def test_no_trailing_slash_redirect(client: TestClient):
    # `redirect_slashes=False`, same contract posture as notification-/
    # review-service: a trailing-slash request must not 307-redirect.
    response = client.get("/api/payments/", follow_redirects=False)
    assert response.status_code != 307
