"""Async SQLAlchemy queries against this service's own `shipping` schema --
split, like every other standalone service's `app/repository.py`, into the
read paths `app/routes.py` calls and the write paths the saga machinery
(`app/orchestrator.py`, `app/steps.py`, `app/service.py`, `app/relay.py`)
calls.

Unlike `05-payment-service/app/repository.py`'s write helpers (which open and
commit their own short transaction per call), every WRITE function here takes
an already-open `AsyncSession` and does NOT commit -- the saga engine
(`app/orchestrator.py::advance()`/`compensate()`) owns the transaction
boundary explicitly (`async with session.begin():`), because a single saga
step's side effects (e.g. the `emit` step's `Shipment` status flip AND its
matching `OutboxEvent` row) must commit atomically WITH the saga's own
`step_index`/`status` update -- see `app/models.py::OutboxEvent`'s docstring
and `../EVENTS.md`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, Saga, SagaLog, Shipment

_RELAY_BATCH_SIZE = 100

# -- Read paths (app/routes.py) --------------------------------------------


async def get_shipment_by_id(session: AsyncSession, shipment_id: int) -> Shipment | None:
    return await session.get(Shipment, shipment_id)


async def list_shipments_by_order_id(session: AsyncSession, order_id: int) -> list[Shipment]:
    """`GET /api/shipments?orderId=` -- ordered by id like the monolith's own
    `shipping.services.list_by_order_id().order_by("id")`."""
    stmt = select(Shipment).where(Shipment.order_id == order_id).order_by(Shipment.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# -- Saga persistence (app/service.py, app/orchestrator.py) ----------------


async def get_saga_by_order_id(session: AsyncSession, order_id: int) -> Saga | None:
    """Existence check for `app/service.py::handle_payment_captured`'s
    idempotent dedupe -- one saga per order."""
    stmt = select(Saga).where(Saga.order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_saga(session: AsyncSession, *, order_id: int, now: datetime) -> Saga:
    saga = Saga(
        order_id=order_id,
        status="RUNNING",
        step_index=0,
        context={},
        created_at=now,
        updated_at=now,
    )
    session.add(saga)
    await session.flush()  # populates saga.id via INSERT ... RETURNING
    return saga


async def get_saga_for_update(session: AsyncSession, saga_id: int) -> Saga | None:
    """`SELECT ... FOR UPDATE` row lock -- the Python/asyncpg re-homing of
    the CNDP orchestrator's raw `SELECT id, status, step_index, context FROM
    sagas WHERE id=$1 FOR UPDATE`. MUST be called inside an open transaction
    (`async with session.begin():`) -- the lock is released at commit."""
    stmt = select(Saga).where(Saga.id == saga_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_resumable_saga_ids(session: AsyncSession) -> Sequence[tuple[int, str]]:
    """Startup crash-resume scan (`app/orchestrator.py::resume_running_sagas`):
    every saga still `RUNNING` or `COMPENSATING` when the process last
    stopped (a crash, a redeploy) needs its engine kicked again."""
    stmt = select(Saga.id, Saga.status).where(Saga.status.in_(["RUNNING", "COMPENSATING"]))
    result = await session.execute(stmt)
    return [(row.id, row.status) for row in result.all()]


async def add_saga_log(
    session: AsyncSession,
    *,
    saga_id: int,
    step: str,
    status: str,
    detail: dict[str, Any] | None,
    now: datetime,
) -> None:
    session.add(SagaLog(saga_id=saga_id, step=step, status=status, detail=detail, at=now))


# -- Shipment writes (app/steps.py) -----------------------------------------


async def create_shipment(
    session: AsyncSession, *, order_id: int, address: str, status: str, now: datetime
) -> Shipment:
    shipment = Shipment(order_id=order_id, address=address, status=status, created_at=now)
    session.add(shipment)
    await session.flush()  # populates shipment.id via INSERT ... RETURNING
    return shipment


async def set_shipment_status(session: AsyncSession, shipment_id: int, status: str) -> None:
    stmt = update(Shipment).where(Shipment.id == shipment_id).values(status=status)
    await session.execute(stmt)


# -- Outbox (app/steps.py writes, app/relay.py reads) -----------------------


async def create_outbox_event(
    session: AsyncSession,
    *,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
) -> OutboxEvent:
    outbox_event = OutboxEvent(
        aggregate_type="shipment",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        created_at=now,
        published_at=None,
    )
    session.add(outbox_event)
    await session.flush()
    return outbox_event


async def list_unpublished_outbox_events(
    session: AsyncSession, *, limit: int = _RELAY_BATCH_SIZE
) -> list[OutboxEvent]:
    """`app/relay.py`'s poll query -- oldest-first, same convention as every
    other standalone service's relay. The partial index
    `idx_shipping_outbox_unpublished` keeps this cheap."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_outbox_event_published(
    session: AsyncSession, event_id: int, *, published_at: datetime
) -> None:
    """Stamps `published_at` in its own short transaction, AFTER the relay's
    Kafka send has already succeeded -- see `app/relay.py`'s module docstring
    for why this is an at-least-once, not exactly-once, guarantee."""
    stmt = (
        update(OutboxEvent)
        .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
        .values(published_at=published_at)
    )
    await session.execute(stmt)
    await session.commit()
