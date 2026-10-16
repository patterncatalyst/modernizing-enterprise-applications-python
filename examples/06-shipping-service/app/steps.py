"""The bodies of the orchestrated saga's four forward steps
(`enrich -> dispatch -> book_carrier -> emit`) plus `dispatch`'s one semantic
inverse (`cancel_shipment`) -- `app/orchestrator.py`'s `STEPS` table wires
these in by name. Adapted from the Java sibling's `ShipmentSagaSteps`
(`~/Dev/modernizing-enterprise-applications/examples/06-shipping-service/src/main/java/dev/patterncatalyst/shipping/ShipmentSagaSteps.java`,
a Camel Saga EIP route's step bodies) onto this project's DB-backed
orchestrator engine -- same four-step shape and the same ordering
constraint (book_carrier's failure injection must run AFTER dispatch has
already committed a `Shipment` row, so compensation has something to act
on), re-expressed as plain async functions over a shared SQLAlchemy session
rather than Camel `Exchange` headers.

Every step function has the same signature -- `(session, settings, order_id,
context) -> dict` -- so `app/orchestrator.py` can dispatch to any of them
uniformly; the returned dict is folded into the saga's persisted `context`
under the step's own name (`app/orchestrator.py::_advance_one_step`), which
is how `dispatch`'s `shipment_id`/`address` become visible to `book_carrier`
and `emit` without a second database round trip or a direct call between
steps (see `_docs/17-appendix-d-sagas.md`'s "step B needs data only step A
produced" section).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import enrich_client, repository
from app.config import Settings
from app.models import SHIPMENT_CANCELLED, SHIPMENT_DISPATCHED

logger = logging.getLogger("shipping_service.steps")

# Deterministic demo failure-injection sentinel, lifted byte-for-byte from
# the monolith's own `shipping.services.SHIP_FAIL_SENTINEL` (the original
# in-process dispatch() this saga replaces) and the Java sibling's
# `ShipmentSagaSteps.SHIP_FAIL_SENTINEL`.
SHIP_FAIL_SENTINEL = "SHIP-FAIL"

SHIPMENT_DISPATCHED_EVENT_TYPE = "shipment.dispatched"
SHIPMENT_FAILED_EVENT_TYPE = "shipment.failed"


class BookCarrierFailed(Exception):
    """Raised by `book_carrier` when the enriched address carries the
    `SHIP-FAIL` sentinel. Runs AFTER `dispatch` (step 2) has already
    persisted and committed the `Shipment` row in a prior `advance()` call,
    so `app/orchestrator.py::compensate` always has a real row to cancel --
    the same ordering guarantee the Java sibling's docstring calls out."""


async def enrich(
    session: AsyncSession, *, settings: Settings, order_id: int, context: dict[str, Any]
) -> dict[str, Any]:
    """Saga step 1: fetch the order's `shippingAddress` from order-service's
    `GET /api/orders/{orderId}` (`app/enrich_client.py`, tenacity retry +
    bounded timeout) -- order-service's `order_view` CQRS read model serves
    the same `shippingAddress` field the monolith's `OrderSerializer` used to
    (r07 re-point; see `app/config.py`'s module docstring for the documented
    operator fallback). A failure here (order-service unreachable, retries
    exhausted, no address on the response) propagates straight out of this
    function -- `app/orchestrator.py::_advance_one_step` catches it like any
    other step failure and starts compensation. Since `dispatch` (step 2) has
    not run yet in that case, `compensate()` finds no `Shipment` row to
    cancel, and the saga's terminal `shipment.failed` event carries a null
    `shipmentId`/`address` (see `app/orchestrator.py::compensate`'s
    docstring).
    """
    address = await enrich_client.fetch_shipping_address(
        base_url=settings.order_base_url,
        order_id=order_id,
        timeout_s=settings.enrich_timeout_s,
    )
    return {"address": address}


async def dispatch(
    session: AsyncSession, *, settings: Settings, order_id: int, context: dict[str, Any]
) -> dict[str, Any]:
    """Saga step 2: persists a NEW `Shipment` row as `DISPATCHED` directly
    (this saga has no separate "reserved" phase -- see `app/models.py`'s
    `Shipment` docstring for why `PENDING` stays declared but unused here).
    This step's own transaction commits before `book_carrier` (step 3) runs
    in the NEXT `advance()` call, which is what makes `cancel_shipment`
    meaningful if step 3 fails: there is always a durable row to flip to
    `CANCELLED`. The address comes from step 1's output, threaded through
    the saga's persisted `context` -- never re-fetched.
    """
    address = context["enrich"]["address"]
    now = datetime.now(UTC)
    shipment = await repository.create_shipment(
        session, order_id=order_id, address=address, status=SHIPMENT_DISPATCHED, now=now
    )
    logger.info(
        "dispatch: persisted shipment id=%s (DISPATCHED) for order %s", shipment.id, order_id
    )
    return {"shipment_id": shipment.id, "address": address}


async def book_carrier(
    session: AsyncSession, *, settings: Settings, order_id: int, context: dict[str, Any]
) -> dict[str, Any]:
    """Saga step 3, and the deterministic failure-injection point: raises
    `BookCarrierFailed` if the enriched shipping address contains the
    `SHIP-FAIL` sentinel (case-insensitive, matching the monolith's original
    `shipping.services.dispatch`'s `SHIP_FAIL_SENTINEL in address.upper()`
    rule). Deliberately has no persistence of its own -- step 2 already
    committed the `Shipment` row this failure needs compensated.
    """
    address = context["dispatch"]["address"]
    if SHIP_FAIL_SENTINEL in address.upper():
        raise BookCarrierFailed(
            f"carrier booking failed for order {order_id}: SHIP-FAIL sentinel detected"
        )
    return {"booked": True}


async def emit(
    session: AsyncSession, *, settings: Settings, order_id: int, context: dict[str, Any]
) -> dict[str, Any]:
    """Saga step 4 -- folded into the saga's terminal transition:
    `app/orchestrator.py::_advance_one_step` marks the saga `COMPLETED` in
    the SAME transaction this function runs in, immediately after it
    returns, so the `shipment.dispatched` outbox row this step writes and
    the saga's own `COMPLETED` status land atomically (never a saga marked
    done with no outcome event queued, or vice versa). `app/relay.py`
    publishes the row later, independently.
    """
    shipment_id = context["dispatch"]["shipment_id"]
    address = context["dispatch"]["address"]
    now = datetime.now(UTC)
    payload = {
        "orderId": order_id,
        "shipmentId": shipment_id,
        "address": address,
        "status": SHIPMENT_DISPATCHED,
        "occurredAt": now.isoformat(),
    }
    await repository.create_outbox_event(
        session,
        aggregate_id=str(order_id),
        event_type=SHIPMENT_DISPATCHED_EVENT_TYPE,
        payload=payload,
        now=now,
    )
    logger.info(
        "emit: shipment.dispatched queued for order %s (shipment %s)", order_id, shipment_id
    )
    return {"event": SHIPMENT_DISPATCHED_EVENT_TYPE}


async def cancel_shipment(
    session: AsyncSession, *, settings: Settings, order_id: int, context: dict[str, Any]
) -> dict[str, Any]:
    """`dispatch`'s semantic inverse: flips the `Shipment` row persisted by
    step 2 to `CANCELLED` -- never deleted, preserving an auditable record of
    the aborted attempt (same posture as the Java sibling's `ShipmentStatus`
    enum). Called by `app/orchestrator.py::compensate` for the one forward
    step in this saga that has anything to undo; `enrich` and `book_carrier`
    have no `compensate` entry in `app/orchestrator.py::STEPS` because
    neither persists anything of its own.
    """
    shipment_id = context["dispatch"]["shipment_id"]
    await repository.set_shipment_status(session, shipment_id, SHIPMENT_CANCELLED)
    logger.info(
        "cancel_shipment: shipment id=%s for order %s now CANCELLED", shipment_id, order_id
    )
    return {"cancelled": True}
