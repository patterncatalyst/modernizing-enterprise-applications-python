"""gRPC contract tests for `app/grpc_server.py::InventoryGrpcServiceServicer`
-- exercised by calling the servicer's coroutine methods directly against
real `CheckStockRequest`/`ReserveRequest`/`ReleaseRequest`/`GetStockRequest`
protobuf messages (no network listener needed; `context` is unused by every
RPC implementation, so `None` is passed). Same posture the Java sibling's
`InventoryGrpcServiceTest` uses via an in-JVM `@GrpcClient`, adapted to
Python's lighter-weight direct-call option explicitly allowed by the plan.

Against the real, already-migrated AND seeded `inventory` schema (see
`conftest.py`); `reset_inventory_quantities` (autouse) restores the seed
baseline after every test, so these tests are order-independent."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.grpc_gen import inventory_pb2
from app.grpc_server import InventoryGrpcServiceServicer


def _servicer(session_factory: async_sessionmaker[AsyncSession]) -> InventoryGrpcServiceServicer:
    return InventoryGrpcServiceServicer(session_factory)


@pytest.mark.asyncio
async def test_check_stock_sufficient_is_available(session_factory):
    servicer = _servicer(session_factory)
    request = inventory_pb2.CheckStockRequest(
        stock_keeping_unit="SKU-WIDGET-001", requested_qty=5
    )
    reply = await servicer.CheckStock(request, None)
    assert reply.stock_keeping_unit == "SKU-WIDGET-001"
    assert reply.display_name == "Standard Widget"
    assert reply.unit_price_cents == 1999
    assert reply.on_hand_qty == 100
    assert reply.available is True


@pytest.mark.asyncio
async def test_check_stock_insufficient_is_not_available(session_factory):
    servicer = _servicer(session_factory)
    request = inventory_pb2.CheckStockRequest(
        stock_keeping_unit="SKU-GIZMO-003", requested_qty=999
    )
    reply = await servicer.CheckStock(request, None)
    assert reply.on_hand_qty == 5
    assert reply.available is False


@pytest.mark.asyncio
async def test_check_stock_unknown_sku_is_not_available(session_factory):
    servicer = _servicer(session_factory)
    request = inventory_pb2.CheckStockRequest(stock_keeping_unit="NOPE", requested_qty=1)
    reply = await servicer.CheckStock(request, None)
    assert reply.stock_keeping_unit == "NOPE"
    assert reply.on_hand_qty == 0
    assert reply.available is False


@pytest.mark.asyncio
async def test_get_stock_known_sku(session_factory):
    servicer = _servicer(session_factory)
    request = inventory_pb2.GetStockRequest(stock_keeping_unit="SKU-GADGET-002")
    reply = await servicer.GetStock(request, None)
    assert reply.stock_keeping_unit == "SKU-GADGET-002"
    assert reply.display_name == "Deluxe Gadget"
    assert reply.unit_price_cents == 4999
    assert reply.on_hand_qty == 50
    assert reply.available is True


@pytest.mark.asyncio
async def test_get_stock_unknown_sku_is_unavailable(session_factory):
    servicer = _servicer(session_factory)
    request = inventory_pb2.GetStockRequest(stock_keeping_unit="NOPE")
    reply = await servicer.GetStock(request, None)
    assert reply.on_hand_qty == 0
    assert reply.available is False


@pytest.mark.asyncio
async def test_reserve_sufficient_decrements_exactly_by_requested_qty(session_factory):
    servicer = _servicer(session_factory)
    reply = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-WIDGET-001", requested_qty=5),
        None,
    )
    assert reply.reservation_ok is True
    assert reply.on_hand_qty == 95

    # Confirmed via a fresh read, not just the mutating call's own reply.
    check = await servicer.CheckStock(
        inventory_pb2.CheckStockRequest(stock_keeping_unit="SKU-WIDGET-001", requested_qty=0),
        None,
    )
    assert check.on_hand_qty == 95


@pytest.mark.asyncio
async def test_reserve_insufficient_leaves_stock_unchanged(session_factory):
    servicer = _servicer(session_factory)
    reply = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GIZMO-003", requested_qty=999),
        None,
    )
    assert reply.reservation_ok is False
    assert reply.on_hand_qty == 5  # unchanged -- no partial decrement


@pytest.mark.asyncio
async def test_reserve_sequential_over_reserve_second_call_fails_after_first_succeeds(
    session_factory,
):
    servicer = _servicer(session_factory)
    # SKU-GADGET-002 starts at 50. Reserve 50 (exactly all of it) succeeds...
    first = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GADGET-002", requested_qty=50),
        None,
    )
    assert first.reservation_ok is True
    assert first.on_hand_qty == 0

    # ...a second reservation against the now-exhausted sku must fail, not
    # oversell.
    second = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GADGET-002", requested_qty=1),
        None,
    )
    assert second.reservation_ok is False
    assert second.on_hand_qty == 0


@pytest.mark.asyncio
async def test_release_restores_stock(session_factory):
    servicer = _servicer(session_factory)
    reserved = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-WIDGET-001", requested_qty=5),
        None,
    )
    assert reserved.on_hand_qty == 95

    released = await servicer.Release(
        inventory_pb2.ReleaseRequest(stock_keeping_unit="SKU-WIDGET-001", requested_qty=5),
        None,
    )
    assert released.reservation_ok is True
    assert released.on_hand_qty == 100


@pytest.mark.asyncio
async def test_release_unknown_sku_reports_not_ok(session_factory):
    servicer = _servicer(session_factory)
    reply = await servicer.Release(
        inventory_pb2.ReleaseRequest(stock_keeping_unit="NOPE", requested_qty=1),
        None,
    )
    assert reply.reservation_ok is False
    assert reply.on_hand_qty == 0


@pytest.mark.asyncio
async def test_reserve_concurrent_requests_for_last_unit_exactly_one_succeeds(session_factory):
    """The proof that `app/repository.py::reserve`'s single conditional
    `UPDATE` is concurrency-safe WITHOUT an explicit application-level lock:
    two concurrent `Reserve(sku, 1)` calls racing a sku with exactly 1 unit
    on hand must yield exactly one `reservation_ok=true` and one
    `reservation_ok=false`, never both true (oversell) and never both false
    (under-sell/stuck stock)."""
    servicer = _servicer(session_factory)

    # SKU-GIZMO-003 starts at 5 -- bring it down to exactly 1 unit first
    # (sequential, not part of the race being measured).
    setup = await servicer.Reserve(
        inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GIZMO-003", requested_qty=4),
        None,
    )
    assert setup.reservation_ok is True
    assert setup.on_hand_qty == 1

    request_a = inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GIZMO-003", requested_qty=1)
    request_b = inventory_pb2.ReserveRequest(stock_keeping_unit="SKU-GIZMO-003", requested_qty=1)

    reply_a, reply_b = await asyncio.gather(
        servicer.Reserve(request_a, None),
        servicer.Reserve(request_b, None),
    )

    outcomes = [reply_a.reservation_ok, reply_b.reservation_ok]
    assert outcomes.count(True) == 1, (
        f"expected exactly one concurrent Reserve to succeed, got {outcomes}"
    )
    assert outcomes.count(False) == 1

    # Whichever won, the sku must now be fully exhausted -- not oversold
    # (negative) and not left at 1 (the loser's failure must truly be a
    # no-op, not a partial/duplicate decrement).
    final = await servicer.GetStock(
        inventory_pb2.GetStockRequest(stock_keeping_unit="SKU-GIZMO-003"), None
    )
    assert final.on_hand_qty == 0
