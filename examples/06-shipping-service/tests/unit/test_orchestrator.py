"""Fast, Kafka-free proofs for the orchestrated saga against this service's
real `shipping` schema (same reachable, already-migrated Postgres
`conftest.py`'s `client`/`session_factory` fixtures use): the happy path
(dispatch + emit -> COMPLETED), the deterministic SHIP-FAIL abort
(compensate -> CANCELLED + `shipment.failed`, no `shipment.dispatched`), and
the idempotent-redelivery guarantee (one saga per order, however many times
`payment.captured` is redelivered). Complements
`tests/integration/test_crash_resume.py`, which proves the startup
crash-resume scan end-to-end.

order-service's `GET /api/orders/{id}` is NOT live in this test layer --
`fake_addresses` monkeypatches `app.enrich_client.fetch_shipping_address`
(the saga's `enrich` step's only collaborator) to return a controllable
address per order id, same posture as `05-payment-service`'s Kafka-free
`app.service` unit tests standing in for the real broker.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import enrich_client, repository, service
from app.config import Settings
from app.models import (
    SAGA_COMPENSATED,
    SAGA_COMPLETED,
    SHIPMENT_CANCELLED,
    SHIPMENT_DISPATCHED,
    OutboxEvent,
    Saga,
    Shipment,
)
from app.schemas import PaymentCapturedEvent


def _settings() -> Settings:
    return Settings(
        http_port=8087,
        database_url="unused-by-the-orchestrator-directly",
        kafka_bootstrap_servers="unused-in-this-test-layer",
        order_base_url="http://order.invalid",
        monolith_base_url="http://monolith.invalid",
        payment_captured_topic="payment.captured",
        shipment_dispatched_topic="shipment.dispatched",
        shipment_failed_topic="shipment.failed",
        consumer_group="shipping-service-test",
        outbox_poll_ms=1000,
        enrich_timeout_s=1.0,
    )


def _random_order_id() -> int:
    return random.randint(10_000_000, 2_000_000_000)


def _event(order_id: int) -> PaymentCapturedEvent:
    return PaymentCapturedEvent(
        orderId=order_id,
        paymentId=random.randint(1, 1_000_000),
        amountCents=4999,
        method="CARD",
        status="CAPTURED",
        occurredAt=datetime.now(UTC),
    )


@pytest.fixture
def fake_addresses(monkeypatch) -> dict[int, str]:
    """Maps `order_id -> shippingAddress`, standing in for the monolith's
    `GET /api/orders/{id}` enrichment call. Raises `KeyError` (surfaced to
    the caller as the saga's `enrich` step failing, same as a real
    unreachable monolith) for any order_id a test did not seed."""
    addresses: dict[int, str] = {}

    async def _fake_fetch(*, base_url: str, order_id: int, timeout_s: float) -> str:
        return addresses[order_id]

    monkeypatch.setattr(enrich_client, "fetch_shipping_address", _fake_fetch)
    return addresses


async def _get_saga(session_factory, order_id: int) -> Saga:
    async with session_factory() as session:
        saga = await repository.get_saga_by_order_id(session, order_id)
        assert saga is not None, f"no saga found for order {order_id}"
        return saga


async def _list_shipments(session_factory, order_id: int) -> list[Shipment]:
    async with session_factory() as session:
        stmt = select(Shipment).where(Shipment.order_id == order_id)
        return list((await session.execute(stmt)).scalars().all())


async def _list_outbox(session_factory, order_id: int) -> list[OutboxEvent]:
    async with session_factory() as session:
        stmt = select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
        return list((await session.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_saga_happy_path_dispatches_shipment_and_completes(
    session_factory: AsyncIterator, fake_addresses: dict[int, str]
):
    order_id = _random_order_id()
    fake_addresses[order_id] = "42 Wallaby Way, Sydney"
    settings = _settings()

    await service.handle_payment_captured(session_factory, settings, _event(order_id))

    saga = await _get_saga(session_factory, order_id)
    assert saga.status == SAGA_COMPLETED
    assert saga.step_index == 4  # enrich, dispatch, book_carrier, emit

    shipments = await _list_shipments(session_factory, order_id)
    assert len(shipments) == 1
    assert shipments[0].status == SHIPMENT_DISPATCHED
    assert shipments[0].address == "42 Wallaby Way, Sydney"

    outbox_rows = await _list_outbox(session_factory, order_id)
    assert len(outbox_rows) == 1
    event = outbox_rows[0]
    assert event.event_type == "shipment.dispatched"
    assert event.payload["orderId"] == order_id
    assert event.payload["shipmentId"] == shipments[0].id
    assert event.payload["status"] == "DISPATCHED"
    assert event.published_at is None


@pytest.mark.asyncio
async def test_saga_ship_fail_sentinel_compensates_and_never_dispatches(
    session_factory: AsyncIterator, fake_addresses: dict[int, str]
):
    order_id = _random_order_id()
    fake_addresses[order_id] = "1 SHIP-FAIL Lane"
    settings = _settings()

    await service.handle_payment_captured(session_factory, settings, _event(order_id))

    saga = await _get_saga(session_factory, order_id)
    assert saga.status == SAGA_COMPENSATED
    # Only enrich + dispatch completed before book_carrier raised.
    assert saga.step_index == 2

    shipments = await _list_shipments(session_factory, order_id)
    assert len(shipments) == 1, "dispatch still persists a row before book_carrier can fail"
    assert shipments[0].status == SHIPMENT_CANCELLED

    outbox_rows = await _list_outbox(session_factory, order_id)
    assert len(outbox_rows) == 1, "exactly one terminal event, never a dispatched one too"
    event = outbox_rows[0]
    assert event.event_type == "shipment.failed"
    assert event.payload["orderId"] == order_id
    assert event.payload["shipmentId"] == shipments[0].id
    assert event.payload["status"] == "FAILED"
    assert "SHIP-FAIL" in event.payload["reason"]


@pytest.mark.asyncio
async def test_handle_payment_captured_is_idempotent_on_redelivery(
    session_factory: AsyncIterator, fake_addresses: dict[int, str]
):
    order_id = _random_order_id()
    fake_addresses[order_id] = "7 Redelivery Road"
    settings = _settings()
    event = _event(order_id)

    await service.handle_payment_captured(session_factory, settings, event)
    # Redelivery of the IDENTICAL event -- the at-least-once
    # payment.captured publisher scenario this dedupe check exists for.
    await service.handle_payment_captured(session_factory, settings, event)

    async with session_factory() as session:
        stmt = select(Saga).where(Saga.order_id == order_id)
        sagas = list((await session.execute(stmt)).scalars().all())
    assert len(sagas) == 1, "redelivery of payment.captured must not start a second saga"
    assert sagas[0].status == SAGA_COMPLETED

    shipments = await _list_shipments(session_factory, order_id)
    assert len(shipments) == 1, "redelivery must not duplicate the dispatched shipment"

    outbox_rows = await _list_outbox(session_factory, order_id)
    assert len(outbox_rows) == 1, "redelivery must not emit a second outbox event"
