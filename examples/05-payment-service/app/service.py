"""`process_order_placed` -- the single owner of the choreographed saga's
capture-then-emit core (mirrors the Java sibling's
`PaymentService#processOrderPlaced`,
`~/Dev/modernizing-enterprise-applications/examples/05-payment-service/src/main/java/dev/patterncatalyst/payment/PaymentService.java`).
`app/consumer.py` delegates here rather than writing to the repository
directly, so there is exactly one place that decides "have I already charged
this order" and "what do I write to the outbox."

NET-NEW for this service, same posture as `03-notification-service`'s
`record_order_placed`: the monolith's checkout path still charges in-process,
synchronously, inside the SAME `transaction.atomic()` as the inventory
reservation (see `00-monolith/payment/services.py::charge`'s docstring) --
there is no Django original for a choreographed, async payment consumer to
lift. The demo DECLINE rule below is lifted byte-for-byte from that
synchronous original (`DECLINE_SENTINEL = "DECLINE"`), but the control flow
around it -- idempotent dedupe, never raising, writing an outbox event instead
of returning an HTTP 402 -- is authored fresh for the choreography.

Also owns `process_shipment_failed` (r06/DRQ-054) -- the refund reaction to a
`shipment.failed` event, closing the stranded-payment gap: a `CAPTURED`
payment whose shipment later fails must be refunded, idempotently, via this
service's same outbox. See that function's own docstring for the full
contract.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repository
from app.models import Payment
from app.schemas import OrderPlacedEvent, ShipmentFailedEvent

logger = logging.getLogger("payment_service.service")

AGGREGATE_TYPE = "payment"

STATUS_CAPTURED = "CAPTURED"
STATUS_DECLINED = "DECLINED"
STATUS_REFUNDED = "REFUNDED"

PAYMENT_CAPTURED_EVENT_TYPE = "payment.captured"
PAYMENT_DECLINED_EVENT_TYPE = "payment.declined"
PAYMENT_REFUNDED_EVENT_TYPE = "payment.refunded"

DECLINE_SENTINEL = "DECLINE"

# Forward-compatibility fallback (see `app/schemas.py::OrderPlacedEvent`'s
# docstring): today's `order.placed` payload may not carry a payment method
# at all (it is net-new, optional, in r05). This literal substitutes for a
# missing/`null` method -- deliberately NOT containing "DECLINE" -- so a
# method-less event always captures rather than crashing the consumer or
# silently declining. Matches the Java sibling's `UNSPECIFIED_METHOD`
# (`"CARD-UNSPECIFIED"`).
UNSPECIFIED_METHOD = "CARD-UNSPECIFIED"


def _effective_method(method: str | None) -> str:
    return method if method is not None else UNSPECIFIED_METHOD


def charge(method: str | None) -> str:
    """Deterministic demo decline rule, lifted byte-for-byte from the
    monolith's `payment.services.charge`: any `method` value containing
    "DECLINE" (case-insensitive) is declined. Unlike the monolith's version,
    this NEVER raises -- it always returns a status (`CAPTURED` or
    `DECLINED`), since the choreography needs a `Payment` row (and an emitted
    event) either way, not an exception that aborts a local transaction.

    `method=None` (today's forward-compatible, method-less `order.placed`
    payload) is substituted with `UNSPECIFIED_METHOD` and always captures.
    """
    effective_method = _effective_method(method)
    if DECLINE_SENTINEL in effective_method.upper():
        return STATUS_DECLINED
    return STATUS_CAPTURED


def _event_type_for(status: str) -> str:
    return PAYMENT_CAPTURED_EVENT_TYPE if status == STATUS_CAPTURED else PAYMENT_DECLINED_EVENT_TYPE


def _build_event_payload(payment: Payment, *, occurred_at: datetime) -> dict[str, object]:
    """Builds the `payment.captured`/`payment.declined` wire payload (see
    `../EVENTS.md`) matching this `Payment` row -- the sibling of the Java
    service's `PaymentService#buildOutboxEvent`."""
    base = {
        "orderId": payment.order_id,
        "paymentId": payment.id,
        "amountCents": payment.amount_cents,
        "method": payment.method,
        "status": payment.status,
        "occurredAt": occurred_at.isoformat(),
    }
    if payment.status == STATUS_DECLINED:
        base["reason"] = f"Payment method '{payment.method}' was declined"
    return base


async def process_order_placed(
    session_factory: async_sessionmaker[AsyncSession], event: OrderPlacedEvent
) -> None:
    """IDEMPOTENT by design: the monolith's (future) outbox relay publishing
    `order.placed` is an AT-LEAST-ONCE publisher -- a crash between the Kafka
    send and marking that outbox row published republishes the identical
    event. Check-then-insert, dedup'd by `order_id`, means a redelivered
    event is a safe no-op: this consumer neither double-charges nor emits a
    second outcome event. The database-level unique index on `order_id`
    (`../migrations/versions/0001_create_payment_schema.py`) is the backstop
    for two deliveries racing concurrently -- caught here as an
    `IntegrityError` and swallowed, since by definition a payment for that
    order already exists.

    Charging (`charge()`) and persisting the `Payment` row AND its matching
    outbox event happen in ONE transaction
    (`repository.create_payment_with_outbox_event`) -- the transactional-
    outbox atomicity guarantee: either both writes land, or neither does.
    """
    async with session_factory() as session:
        existing = await repository.get_by_order_id(session, event.order_id)
        if existing is not None:
            logger.info(
                "order.placed for order %s already has a payment recorded, skipping "
                "(idempotent no-op)",
                event.order_id,
            )
            return

        method = _effective_method(event.payment_method)
        status = charge(event.payment_method)
        now = datetime.now(UTC)

        try:
            payment = await repository.create_payment_with_outbox_event(
                session,
                order_id=event.order_id,
                amount_cents=event.total_cents,
                method=method,
                status=status,
                created_at=now,
                event_type=_event_type_for(status),
                build_payload=lambda p: _build_event_payload(p, occurred_at=now),
            )
            logger.info(
                "processed order.placed for order %s -> payment %s (payment id=%s)",
                event.order_id,
                status,
                payment.id,
            )
        except IntegrityError:
            # Lost the race against a concurrent redelivery that inserted
            # first -- the unique index on order_id rejected this one. The
            # other insert already recorded the payment (and its outbox
            # event), so this is still a safe no-op, not an error.
            await session.rollback()
            logger.info(
                "order.placed for order %s raced a concurrent insert, discarding duplicate",
                event.order_id,
            )


def _build_refund_event_payload(payment: Payment, *, occurred_at: datetime) -> dict[str, object]:
    """Builds the `payment.refunded` wire payload (see `../EVENTS.md`) --
    the refund sibling of `_build_event_payload` above. Deliberately a
    SMALLER shape than `payment.captured`/`payment.declined` (no `method`,
    no `reason`): the FROZEN r06/DRQ-054 contract is
    `{orderId, paymentId, amountCents, status, occurredAt}`, and `status` is
    always the literal `REFUNDED` here."""
    return {
        "orderId": payment.order_id,
        "paymentId": payment.id,
        "amountCents": payment.amount_cents,
        "status": payment.status,
        "occurredAt": occurred_at.isoformat(),
    }


async def process_shipment_failed(
    session_factory: async_sessionmaker[AsyncSession], event: ShipmentFailedEvent
) -> None:
    """r06/DRQ-054 -- closes the stranded-payment gap: a shipping failure
    AFTER payment has already been captured must refund that payment, or the
    customer is charged for an order that never ships. The mirror of
    `process_order_placed`'s idempotent, single-owner shape, but a STATUS
    TRANSITION rather than an insert: find the `Payment` for this
    `shipment.failed`'s `orderId`, and if (and only if) it is currently
    `CAPTURED`, move it to `REFUNDED` and write a matching `payment.refunded`
    outbox row, atomically (`repository.transition_payment_status_with_outbox_event`).

    IDEMPOTENT by design, same at-least-once posture as every other consumer
    in this service: a redelivered `shipment.failed` for an order already
    `REFUNDED` finds no row in the expected `CAPTURED` state and is a safe
    no-op -- it does NOT re-refund, and does NOT emit a second
    `payment.refunded` event. An order with no payment recorded at all, or
    whose payment is `DECLINED` (never captured in the first place), is ALSO
    a no-op for the same reason: there is nothing to refund, and this must
    NEVER "refund" money that was never taken.
    """
    async with session_factory() as session:
        now = datetime.now(UTC)
        payment = await repository.transition_payment_status_with_outbox_event(
            session,
            order_id=event.order_id,
            expected_status=STATUS_CAPTURED,
            new_status=STATUS_REFUNDED,
            created_at=now,
            event_type=PAYMENT_REFUNDED_EVENT_TYPE,
            build_payload=lambda p: _build_refund_event_payload(p, occurred_at=now),
        )
        if payment is None:
            logger.info(
                "shipment.failed for order %s: no CAPTURED payment to refund (already "
                "REFUNDED, DECLINED, or no payment recorded) -- idempotent no-op",
                event.order_id,
            )
            return

        logger.info(
            "processed shipment.failed for order %s -> payment %s (payment id=%s)",
            event.order_id,
            payment.status,
            payment.id,
        )
