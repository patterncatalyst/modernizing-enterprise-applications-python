"""`/api/shipments` contract tests -- the FastAPI sibling of the monolith's
`shipping/views.py` coverage (`ShipmentListView`/`ShipmentDetailView`).
Exercises this service's OWN, already-migrated `shipping` schema (see
`conftest.py`), proving the read contract matches the monolith's
`ShipmentSerializer` byte-for-byte: field names, the required-`orderId` 400,
and the 404-by-id uniform error body."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import create_engine, create_session_factory
from app.models import SHIPMENT_DISPATCHED, Shipment


def _random_id() -> int:
    # Random, not sequential/fixed -- these tests run against a real,
    # potentially-reused Postgres (not a fresh-per-test schema), so a fixed
    # id would risk colliding with another test run's row.
    return random.randint(10_000_000, 2_000_000_000)


async def _seed_shipment(
    *, order_id: int, address: str = "123 Main St", status: str = SHIPMENT_DISPATCHED
) -> int:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            shipment = Shipment(
                order_id=order_id,
                address=address,
                status=status,
                created_at=datetime.now(UTC),
            )
            session.add(shipment)
            await session.flush()
            await session.commit()
            return shipment.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_shipments_returns_camel_case_array(client: TestClient):
    order_id = _random_id()
    await _seed_shipment(order_id=order_id, address="42 Wallaby Way", status=SHIPMENT_DISPATCHED)

    response = client.get("/api/shipments", params={"orderId": order_id})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    shipment = body[0]
    assert set(shipment) == {"id", "orderId", "address", "status", "createdAt"}
    assert shipment["orderId"] == order_id
    assert shipment["address"] == "42 Wallaby Way"
    assert shipment["status"] == SHIPMENT_DISPATCHED


def test_list_shipments_returns_empty_array_for_unknown_order(client: TestClient):
    response = client.get("/api/shipments", params={"orderId": _random_id()})
    assert response.status_code == 200
    assert response.json() == []


def test_list_shipments_missing_order_id_returns_400_uniform_body(client: TestClient):
    # Matches the monolith's ShipmentListView-equivalent: no `orderId` query
    # param -> ValidationError -> DRF's generic 400. FastAPI's required
    # `Query(...)` (no default) raises `RequestValidationError`, remapped by
    # app/errors.py to the same `400 VALIDATION_FAILED`.
    response = client.get("/api/shipments")
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_get_shipment_by_id_returns_camel_case_body(client: TestClient):
    order_id = _random_id()
    shipment_id = await _seed_shipment(order_id=order_id, address="99 Elm St")

    response = client.get(f"/api/shipments/{shipment_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == shipment_id
    assert body["orderId"] == order_id
    assert body["address"] == "99 Elm St"


def test_get_shipment_by_id_unknown_returns_404_uniform_body(client: TestClient):
    response = client.get(f"/api/shipments/{_random_id()}")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "NOT_FOUND"


def test_no_trailing_slash_redirect(client: TestClient):
    # `redirect_slashes=False`, same contract posture as every other
    # standalone service: a trailing-slash request must not 307-redirect.
    response = client.get("/api/shipments/", follow_redirects=False)
    assert response.status_code != 307
