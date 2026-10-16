"""Async SQLAlchemy queries against this service's own `inventory` schema --
the sibling of `03-notification-service`'s `app/repository.py`, but against a
mutable aggregate rather than an append-only one.

`reserve`/`release` are the gRPC mutating hot path (r04/ch.19, DRQ-039/
DRQ-041/DRQ-042/DRQ-044) -- re-authored from the Java sibling's
`InventoryRepository#reserve/release` (Panache `update(query, params)`) onto
SQLAlchemy Core's `Update` construct, same single-statement shape.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Compensation, InventoryItem


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


async def release(session: AsyncSession, sku: str, qty: int, idempotency_key: str = "") -> bool:
    """Compensating re-increment (DRQ-042, now made idempotent by DRQ-043 --
    the IDEMPOTENT-COMPENSATION lane -- so the payment saga can safely retry
    this call).

    When `idempotency_key` is NON-EMPTY, the re-increment is applied AT MOST
    ONCE per key, in ONE transaction:

      1. `INSERT INTO inventory.compensations (...) ON CONFLICT
         (idempotency_key) DO NOTHING RETURNING id` -- a SINGLE statement,
         NOT a `SELECT` followed by an `INSERT` (which would race under
         concurrent identical-key callers, the exact bug class `reserve`'s
         conditional `UPDATE` already avoids for the decrement side). The
         unique index on `idempotency_key`
         (`migrations/versions/0003_create_compensations_table.py`) is the
         arbiter: Postgres serializes concurrent inserts targeting the same
         key, so of two racing identical-key `Release` calls, exactly one
         gets a row back from this `INSERT` and goes on to step 2; the other
         sees no row (conflict) and short-circuits as a no-op.
      2. ONLY if step 1 actually inserted a new row: the same unconditional
         `UPDATE ... SET quantity_on_hand = quantity_on_hand + :qty WHERE
         sku = :sku` as the backward-compat path below.

    Both statements commit together as one unit of work, so a crash between
    them can never leave a ledger entry with no matching stock mutation (or
    vice versa) -- see `app/grpc_server.py::InventoryGrpcServiceServicer
    .Release` for the one-session-per-call wiring this relies on.

    Returns True if stock was restored THIS call, or a prior `Release` under
    the SAME key already restored it (an idempotent no-op is a logical
    success, not a failure); False if the sku is unknown and this is the
    first time this key is seen (nothing to compensate, and in that case
    nothing is recorded either).

    Honest, documented edge case (not engineered around -- see
    `feedback_scope_discipline`): an unknown sku's FIRST call under a given
    key still inserts a ledger row, because the dedupe check can't know the
    `sku` lookup will fail without a second round trip that would reopen the
    exact race this design avoids. A retried identical-key call against that
    SAME unknown sku would then report a no-op `True` instead of repeating
    `False`. `Release` against an unknown sku is already a degenerate path
    outside the saga's happy path -- the monolith only calls `Release` for a
    sku a prior `Reserve` already proved exists.

    Backward compatibility: an EMPTY/absent `idempotency_key` (the proto3
    default for a caller that predates this field) falls back to the
    ORIGINAL unconditional, non-deduped re-increment below -- no ledger row
    at all. New callers (the payment saga) should always pass a key.
    """
    if not idempotency_key:
        stmt = (
            update(InventoryItem)
            .where(InventoryItem.sku == sku)
            .values(quantity_on_hand=InventoryItem.quantity_on_hand + qty)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount == 1

    insert_ledger_stmt = (
        pg_insert(Compensation)
        .values(
            idempotency_key=idempotency_key,
            order_id=None,
            sku=sku,
            kind="RELEASE",
            applied_at=func.now(),
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Compensation.id)
    )
    newly_recorded = (
        await session.execute(insert_ledger_stmt)
    ).scalar_one_or_none() is not None

    if not newly_recorded:
        # Same key already compensated -- NO-OP, do not re-increment again.
        await session.commit()
        return True

    update_stmt = (
        update(InventoryItem)
        .where(InventoryItem.sku == sku)
        .values(quantity_on_hand=InventoryItem.quantity_on_hand + qty)
    )
    result = await session.execute(update_stmt)
    await session.commit()
    return result.rowcount == 1


async def get_stock(session: AsyncSession, sku: str) -> InventoryItem | None:
    """Alias of `get_by_sku`, named for the gRPC `GetStock` RPC it backs
    (`app/grpc_server.py`) -- full read of one sku's current stock record,
    the content-enricher fetch target for the order-side ACL."""
    return await get_by_sku(session, sku)
