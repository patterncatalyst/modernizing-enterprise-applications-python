"""Async SQLAlchemy queries against this service's own `inventory` schema --
the sibling of `03-notification-service`'s `app/repository.py`, but against a
mutable aggregate rather than an append-only one.

`reserve`/`release` are the gRPC mutating hot path (r04/ch.19, DRQ-039/
DRQ-041/DRQ-042/DRQ-044) -- re-authored from the Java sibling's
`InventoryRepository#reserve/release` (Panache `update(query, params)`) onto
SQLAlchemy Core's `Update` construct, same single-statement shape.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryItem


async def list_all(session: AsyncSession) -> list[InventoryItem]:
    """`GET /api/inventory` -- the sibling of the monolith's
    `services.list_all()`, ordered by id for a deterministic response."""
    stmt = select(InventoryItem).order_by(InventoryItem.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_sku(session: AsyncSession, sku: str) -> InventoryItem | None:
    """`GET /api/inventory/{sku}` -- the sibling of the monolith's
    `services.get_by_sku()`. Also the read side of `CheckStock`/`GetStock`
    (see `app/grpc_server.py`)."""
    stmt = select(InventoryItem).where(InventoryItem.sku == sku)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def reserve(session: AsyncSession, sku: str, qty: int) -> int:
    """Server-side ATOMIC check-and-decrement against this service's OWN
    database (DRQ-041: correctness requires the gRPC caller to know
    synchronously, before confirming the order, whether stock was secured).

    A SINGLE conditional `UPDATE ... SET quantity_on_hand = quantity_on_hand
    - :qty WHERE sku = :sku AND quantity_on_hand >= :qty` -- NOT a
    read-then-write (`SELECT` then `UPDATE` in two round trips, which would
    race under concurrent callers). Returns the rows-affected count: exactly
    1 means the reservation succeeded (checked and decremented atomically);
    0 means insufficient stock or an unknown sku, and NO decrement happened.

    CONCURRENCY-SAFE without an explicit application-level lock (no
    `SELECT ... FOR UPDATE`, no optimistic-locking version column): Postgres
    takes a row-level write lock for the duration of the `UPDATE` statement
    itself, so two concurrent callers reserving the last unit serialize on
    that row -- whichever commits first leaves `quantity_on_hand` below the
    other's `>= :qty` predicate, so exactly one `UPDATE` affects a row
    (returns 1) and the other affects none (returns 0, re-evaluating the
    `WHERE` clause against the now-updated row). See
    `tests/test_inventory_grpc.py::test_reserve_concurrent_requests_for_last_unit_exactly_one_succeeds`.
    """
    stmt = (
        update(InventoryItem)
        .where(InventoryItem.sku == sku, InventoryItem.quantity_on_hand >= qty)
        .values(quantity_on_hand=InventoryItem.quantity_on_hand - qty)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def release(session: AsyncSession, sku: str, qty: int) -> int:
    """Compensating re-increment (DRQ-042 -- a deliberate first taste of
    saga, forward-ref ch.23). `UPDATE ... SET quantity_on_hand =
    quantity_on_hand + :qty WHERE sku = :sku`, UNCONDITIONAL (no upper-bound
    check). Returns the rows-affected count: 1 if the sku existed and was
    restored, 0 if the sku is unknown.

    Idempotency / at-least-once consideration (an honest limitation,
    documented rather than silently built around -- NOT speculative saga
    infrastructure, which is explicitly out of scope here): unlike
    `reserve`'s conditional `UPDATE`, this increment carries no dedupe/
    idempotency key. A retried `Release` call whose effect already landed
    server-side would over-restore stock. A full fix -- an idempotency key
    per reservation/compensation, or a saga ledger -- is deliberately
    deferred to a later choreographed-saga chapter; see
    `app/grpc_server.py::InventoryGrpcServiceServicer.Release`'s docstring
    for this deferral's record.
    """
    stmt = (
        update(InventoryItem)
        .where(InventoryItem.sku == sku)
        .values(quantity_on_hand=InventoryItem.quantity_on_hand + qty)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def get_stock(session: AsyncSession, sku: str) -> InventoryItem | None:
    """Alias of `get_by_sku`, named for the gRPC `GetStock` RPC it backs
    (`app/grpc_server.py`) -- full read of one sku's current stock record,
    the content-enricher fetch target for the order-side ACL."""
    return await get_by_sku(session, sku)
