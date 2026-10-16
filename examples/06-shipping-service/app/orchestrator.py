"""The DB-backed saga engine -- the whole point of r06's ORCHESTRATED
contrast with r05's choreography. Adapted from
`~/Dev/cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/main.py`
(`advance()`/`compensate()`, the `SELECT ... FOR UPDATE` + "not RUNNING ->
no-op" idempotent guard, reverse-order compensation over only-completed
steps, the startup crash-resume scan) and
`_docs/17-appendix-d-sagas.md`'s DB-backed-state-machine design doc -- but
re-homed onto this project's async SQLAlchemy stack (`select(Saga)
.with_for_update()` instead of raw asyncpg `FOR UPDATE`, real ORM models
instead of hand-encoded JSON text columns) rather than lifted verbatim.

## The saga

```
STEPS = enrich -> dispatch -> book_carrier -> emit
```

Each `advance()` call executes EXACTLY ONE step, in its own transaction, then
recurses (or hands off to `compensate()`) based on the saga's status after
that step committed -- same one-step-per-call shape the CNDP original and its
design doc's Figure D.1 both use, so a crash between any two steps leaves the
saga in a well-defined, resumable state (`resume_running_sagas()` below).

Only `dispatch` has a named compensation (`cancel_shipment`) -- `enrich` and
`book_carrier` persist nothing of their own, so they have nothing to undo
(see `app/steps.py`'s docstrings). `emit` has no compensation either: it only
runs once `book_carrier` has already succeeded, so a saga can never reach
`emit` and later need to unwind it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repository, steps
from app.config import Settings
from app.models import SAGA_COMPENSATED, SAGA_COMPENSATING, SAGA_COMPLETED, SAGA_RUNNING
from app.steps import SHIP_FAIL_SENTINEL, SHIPMENT_FAILED_EVENT_TYPE

logger = logging.getLogger("shipping_service.orchestrator")

# The forward steps, in order, each naming its one semantic inverse (or
# `None` if it has nothing to undo) -- the Python re-expression of the CNDP
# orchestrator's `STEPS = [{"name": ..., "compensate": ...}, ...]` table.
STEPS: list[dict[str, str | None]] = [
    {"name": "enrich", "compensate": None},
    {"name": "dispatch", "compensate": "cancel_shipment"},
    {"name": "book_carrier", "compensate": None},
    {"name": "emit", "compensate": None},
]

_STEP_FUNCS = {
    "enrich": steps.enrich,
    "dispatch": steps.dispatch,
    "book_carrier": steps.book_carrier,
    "emit": steps.emit,
}

_COMPENSATION_FUNCS = {
    "cancel_shipment": steps.cancel_shipment,
}


async def advance(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, saga_id: int
) -> None:
    """Drives a saga forward until it either completes, starts compensating
    (handed off to `compensate()`), or this call turns out to be a no-op
    (the saga is unknown, or already in a terminal/compensating state --
    the idempotent guard a redelivered `payment.captured` event, or a
    resumed-and-still-in-flight saga being kicked twice, relies on)."""
    status = await _advance_one_step(session_factory, settings, saga_id)
    if status == SAGA_RUNNING:
        await advance(session_factory, settings, saga_id)
    elif status == SAGA_COMPENSATING:
        await compensate(session_factory, settings, saga_id)
    # COMPLETED, or None (no-op), or COMPENSATED/COMPENSATING already handled
    # by a concurrent caller -- nothing more for this call to do.


async def _advance_one_step(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, saga_id: int
) -> str | None:
    """Executes exactly one step inside one transaction -- the re-homing of
    the CNDP original's `async with db_pool.acquire() as conn: async with
    conn.transaction(): row = await conn.fetchrow(... FOR UPDATE)`. Returns
    the saga's status AFTER this attempt (or `None` if the saga does not
    exist), so `advance()` knows whether to loop, hand off to `compensate()`,
    or stop.
    """
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        saga = await repository.get_saga_for_update(session, saga_id)
        if saga is None:
            return None
        if saga.status != SAGA_RUNNING:
            # Idempotent guard (`_docs/17-appendix-d-sagas.md`'s "if
            # s.status != RUNNING: return"): already COMPLETED/COMPENSATED,
            # or another concurrent caller already flipped it to
            # COMPENSATING -- a no-op, not an error.
            return saga.status

        if saga.step_index >= len(STEPS):
            # Defensive: every `_advance_one_step` call that completes the
            # final step already flips to COMPLETED below in the SAME
            # transaction (the "emit folds into the terminal transition"
            # design), so this branch is normally unreachable -- kept for
            # the same reason the CNDP original keeps the matching check.
            saga.status = SAGA_COMPLETED
            saga.updated_at = now
            return SAGA_COMPLETED

        step = STEPS[saga.step_index]
        step_name = step["name"]
        func = _STEP_FUNCS[step_name]
        try:
            result = await func(
                session, settings=settings, order_id=saga.order_id, context=saga.context
            )
            # Reassign (not mutate in place) so SQLAlchemy's change-tracking
            # on the JSONB column sees a new value to flush -- the saga's
            # context accumulates one step's output at a time, exactly the
            # "thread A's output to B through the persisted context"
            # mechanism the design doc describes.
            saga.context = {**saga.context, step_name: result}
            saga.step_index += 1
            await repository.add_saga_log(
                session, saga_id=saga.id, step=step_name, status="EXECUTED", detail=result, now=now
            )
            if saga.step_index >= len(STEPS):
                saga.status = SAGA_COMPLETED
            saga.updated_at = now
            return saga.status
        except Exception as exc:
            logger.warning(
                "saga %s: step %s failed: %s -- starting compensation", saga.id, step_name, exc
            )
            await repository.add_saga_log(
                session,
                saga_id=saga.id,
                step=step_name,
                status="FAILED",
                detail={"error": str(exc)},
                now=now,
            )
            saga.status = SAGA_COMPENSATING
            saga.updated_at = now
            return SAGA_COMPENSATING


async def compensate(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, saga_id: int
) -> None:
    """Unwinds a `COMPENSATING` saga: runs each COMPLETED step's semantic
    inverse in REVERSE order (`_docs/17-appendix-d-sagas.md`'s "undo only the
    steps that actually completed, newest first"), then writes the saga's
    terminal `shipment.failed` outbox row and flips it to `COMPENSATED` --
    all in ONE transaction, so the outcome event and the saga's own terminal
    state commit atomically, same discipline `_advance_one_step` applies to
    the happy path's `emit`/`COMPLETED` pair.

    Idempotent by the same `SELECT ... FOR UPDATE` + status guard as
    `_advance_one_step`: a saga already `COMPENSATED` (or not `COMPENSATING`
    at all) is a no-op, so `resume_running_sagas()` re-driving a saga that
    finished compensating just before a crash never double-compensates or
    double-emits `shipment.failed`.
    """
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        saga = await repository.get_saga_for_update(session, saga_id)
        if saga is None or saga.status != SAGA_COMPENSATING:
            return

        completed_steps = STEPS[: saga.step_index]
        for step in reversed(completed_steps):
            compensation_name = step["compensate"]
            if compensation_name is None:
                continue
            func = _COMPENSATION_FUNCS[compensation_name]
            try:
                result = await func(
                    session, settings=settings, order_id=saga.order_id, context=saga.context
                )
                await repository.add_saga_log(
                    session,
                    saga_id=saga.id,
                    step=compensation_name,
                    status="COMPENSATED",
                    detail=result,
                    now=now,
                )
            except Exception as exc:
                # Compensations themselves can fail; a saga stuck
                # compensating is an alert, not a silent loss
                # (`_docs/17-appendix-d-sagas.md`) -- log it and keep
                # unwinding the remaining (independent) compensations rather
                # than aborting the whole transaction.
                logger.error(
                    "saga %s: compensation %s failed: %s", saga.id, compensation_name, exc
                )
                await repository.add_saga_log(
                    session,
                    saga_id=saga.id,
                    step=compensation_name,
                    status="COMPENSATION_FAILED",
                    detail={"error": str(exc)},
                    now=now,
                )

        await _emit_shipment_failed(
            session, saga_id=saga.id, order_id=saga.order_id, context=saga.context, now=now
        )
        saga.status = SAGA_COMPENSATED
        saga.updated_at = now
        logger.info("saga %s: fully compensated for order %s", saga.id, saga.order_id)


async def _emit_shipment_failed(
    session: AsyncSession, *, saga_id: int, order_id: int, context: dict[str, Any], now: datetime
) -> None:
    """Builds and persists the saga's terminal `shipment.failed` outbox row.
    `shipmentId`/`address` are present only if `dispatch` ran before the
    saga aborted (the Java sibling's `ShipmentFailed` javadoc documents the
    identical null-if-earlier-step-failed contract) -- `reason` distinguishes
    the deterministic `SHIP-FAIL` sentinel from any other abort.
    """
    dispatch_result = context.get("dispatch")
    shipment_id = dispatch_result["shipment_id"] if dispatch_result else None
    address = dispatch_result["address"] if dispatch_result else None

    if address is not None and SHIP_FAIL_SENTINEL in address.upper():
        reason = f"carrier booking failed for order {order_id}: SHIP-FAIL sentinel detected"
    else:
        reason = f"shipping saga aborted for order {order_id}"

    payload = {
        "orderId": order_id,
        "shipmentId": shipment_id,
        "address": address,
        "status": "FAILED",
        "reason": reason,
        "occurredAt": now.isoformat(),
    }
    await repository.create_outbox_event(
        session,
        aggregate_id=str(order_id),
        event_type=SHIPMENT_FAILED_EVENT_TYPE,
        payload=payload,
        now=now,
    )


async def resume_running_sagas(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> int:
    """The startup crash-resume scan (`app/main.py`'s lifespan calls this
    before serving traffic): every saga still `RUNNING` or `COMPENSATING`
    when the process last stopped -- a crash, a redeploy, a `kill -9` mid-step
    -- gets its engine kicked again. Because `advance()`/`compensate()` are
    idempotent and the row is locked per step, resuming is exactly the CNDP
    design doc's "trivial" case: it picks up at the persisted `step_index`
    and `context`, not from scratch. Returns the count resumed, for
    `/health`'s resume-complete signal and the crash-resume test's assertion.
    """
    async with session_factory() as session:
        resumable = await repository.list_resumable_saga_ids(session)

    for saga_id, status in resumable:
        logger.info("resuming saga %s (status=%s)", saga_id, status)
        if status == SAGA_RUNNING:
            await advance(session_factory, settings, saga_id)
        else:
            await compensate(session_factory, settings, saga_id)

    return len(resumable)
