"""The crash-resume proof -- `_docs/17-appendix-d-sagas.md`'s "kill the
orchestrator pod mid-flow and restart it: the RUNNING saga should resume from
its persisted step_index and context, not start over," reproduced against a
REAL, isolated Testcontainers Postgres (not the throwaway dev Postgres
`tests/unit/` shares).

A crash is simulated the only way that's actually representative: by
inserting a `Saga` row DIRECTLY, bypassing `app/service.py::handle_payment_captured`
entirely, with `status="RUNNING"`, a non-zero `step_index`, and a `context`
already carrying the earlier step's output -- exactly the row a real process
would leave behind if it died right after committing step 1 (`enrich`) but
before attempting step 2 (`dispatch`). `app/orchestrator.py::resume_running_sagas`
is then called directly (the same call `app/main.py`'s lifespan makes on
startup), and the test asserts two things that only hold if resume actually
honors the persisted state rather than restarting from scratch:

1. `app/enrich_client.py::fetch_shipping_address` is NEVER called again --
   proving step 1 is not re-run, because `step_index=1` says it already
   completed and its output is already in `context`.
2. The saga still reaches `COMPLETED`, with a `DISPATCHED` `Shipment` row and
   exactly one `shipment.dispatched` outbox row -- proving steps 2-4 DO run,
   picking up exactly where the "crashed" process left off.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import enrich_client, orchestrator
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.models import (
    SAGA_COMPLETED,
    SAGA_RUNNING,
    SHIPMENT_DISPATCHED,
    OutboxEvent,
    Saga,
    Shipment,
)

pytestmark = pytest.mark.integration


def _settings() -> Settings:
    return Settings(
        http_port=8087,
        database_url="unused-by-the-orchestrator-directly",
        kafka_bootstrap_servers="unused-in-this-test",
        order_base_url="http://order.invalid",
        monolith_base_url="http://monolith.invalid",
        payment_captured_topic="payment.captured",
        shipment_dispatched_topic="shipment.dispatched",
        shipment_failed_topic="shipment.failed",
        consumer_group="shipping-service-crash-resume-test",
        outbox_poll_ms=1000,
        enrich_timeout_s=1.0,
    )


async def _seed_crashed_saga(
    session_factory: async_sessionmaker, *, order_id: int, address: str
) -> int:
    """Writes a `Saga` row as if `enrich` (step 0) already ran and committed,
    then the process died before `dispatch` (step 1) could execute --
    `step_index=1`, `context={"enrich": {"address": ...}}`, `status=RUNNING`."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        saga = Saga(
            order_id=order_id,
            status=SAGA_RUNNING,
            step_index=1,
            context={"enrich": {"address": address}},
            created_at=now,
            updated_at=now,
        )
        session.add(saga)
        await session.flush()
        await session.commit()
        return saga.id


@pytest.mark.asyncio
async def test_resume_running_sagas_continues_from_persisted_step_index(
    database_url: str, monkeypatch
):
    enrich_calls: list[int] = []

    async def _enrich_must_not_be_called(*, base_url: str, order_id: int, timeout_s: float) -> str:
        # If resume_running_sagas() re-ran step 0 instead of picking up at
        # the persisted step_index=1, this would be called -- failing loudly
        # is the point, not returning a plausible-looking address.
        enrich_calls.append(order_id)
        raise AssertionError(
            f"enrich was re-invoked for order {order_id}; resume should have started at "
            "step_index=1 (dispatch), not re-run step 0"
        )

    monkeypatch.setattr(enrich_client, "fetch_shipping_address", _enrich_must_not_be_called)

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    settings = _settings()
    order_id = random.randint(10_000_000, 2_000_000_000)

    try:
        saga_id = await _seed_crashed_saga(
            session_factory, order_id=order_id, address="200 Resume Street"
        )

        resumed_count = await orchestrator.resume_running_sagas(session_factory, settings)
        assert resumed_count == 1

        assert enrich_calls == [], "resume must not re-run the already-completed enrich step"

        async with session_factory() as session:
            saga = await session.get(Saga, saga_id)
            assert saga.status == SAGA_COMPLETED
            assert saga.step_index == 4
            assert saga.context["enrich"]["address"] == "200 Resume Street"
            assert "dispatch" in saga.context
            assert "book_carrier" in saga.context
            assert "emit" in saga.context

            shipments = list(
                (
                    await session.execute(select(Shipment).where(Shipment.order_id == order_id))
                ).scalars()
            )
            assert len(shipments) == 1
            assert shipments[0].status == SHIPMENT_DISPATCHED
            assert shipments[0].address == "200 Resume Street"

            outbox_rows = list(
                (
                    await session.execute(
                        select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
                    )
                ).scalars()
            )
            assert len(outbox_rows) == 1
            assert outbox_rows[0].event_type == "shipment.dispatched"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resume_running_sagas_is_a_noop_with_nothing_in_flight(database_url: str):
    """No RUNNING/COMPENSATING sagas at startup -> resume scans and finds
    nothing to do, same as a clean start with no prior crash."""
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    settings = _settings()
    try:
        resumed_count = await orchestrator.resume_running_sagas(session_factory, settings)
        assert resumed_count == 0
    finally:
        await engine.dispose()
