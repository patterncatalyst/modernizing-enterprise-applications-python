"""Checkout orchestration (command) + the four saga reactions -- the CQRS
re-shaping of `00-monolith/order/services.py`'s god `place_order()` (its
`_place_order_remote`/`_place_order_choreographed` gRPC-reservation flavor)
plus `handle_payment_captured`/`handle_payment_declined`/
`handle_shipment_dispatched`/`handle_shipment_failed`.

**What's lifted byte-for-byte:** the reserve-outside-any-local-transaction
discipline (a remote `Reserve` commits in inventory-service's own database
and cannot be rolled back by this service's Postgres transaction), the
net-zero compensation on failure (`_reserve_lines_remote`/
`_release_reserved`), the stable per-(order, line) Release idempotency key
(`f"{order_id}:{sku}:release"`), and the status-transition idempotency guards
(`_is_pending`/`_is_awaiting_shipment` in spirit -- here enforced
DATABASE-SIDE by `app/repository.py::transition_order_status_with_view`'s
conditional `UPDATE` rather than a Python-level `if` check, since this
service, unlike the monolith's Django ORM, has no implicit per-request
transaction to hang that check off of).

**What's re-shaped for CQRS:** every write below persists the aggregate
change AND upserts `order_view` in the SAME local transaction
(`app/repository.py`'s write functions each own that transaction boundary) --
there is no monolith original for this projection; `order_view` is net-new,
idiomatic-from-day-one.

**What's re-shaped for the extraction itself:** `place_order` ALWAYS reserves
over gRPC (there is no `local`/in-process `INVENTORY_MODE` here -- this
service has no in-process inventory to fall back to) and ALWAYS stops at
`PENDING` with an `order.placed` outbox row (there is no `synchronous`
`PAYMENT_MODE` either -- this service never charges payment itself).
Checkout mirrors the monolith's `choreographed` flavor exactly, and the four
reactions mirror the monolith's `orchestrated`-shipping flavor exactly (this
service transitions `PENDING -> AWAITING_SHIPMENT` on `payment.captured`,
never straight to `CONFIRMED` -- the standalone shipping-service dispatches,
and THIS service reacts to ITS outcome event in turn).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app import repository
from app.errors import ResourceNotFound
from app.inventory_client import AsyncInventoryClient
from app.models import (
    STATUS_AWAITING_SHIPMENT,
    STATUS_CONFIRMED,
    STATUS_PAYMENT_DECLINED,
    STATUS_PENDING,
    STATUS_SHIPPING_FAILED,
    Order,
    OrderItem,
)
from app.schemas import (
    OrderLineIn,
    PaymentCapturedEvent,
    PaymentDeclinedEvent,
    ShipmentDispatchedEvent,
    ShipmentFailedEvent,
)

logger = logging.getLogger("order_service.service")


async def place_order(
    session_factory,
    *,
    inventory_grpc_target: str,
    grpc_timeout_s: float,
    customer_id: int,
    items: list[OrderLineIn],
    payment_method: str,
    shipping_address: str,
) -> Order:
    """The command: validate the customer against this service's OWN
    `customers` table, reserve every line over gRPC OUTSIDE any local
    transaction, then persist the aggregate + `order_view` + the
    `order.placed` outbox row in ONE local transaction
    (`repository.create_order_with_outbox_and_view`). Any failure from that
    transaction triggers a compensating Release for every sku reserved this
    checkout, restoring net-zero stock -- the SAME discipline
    `00-monolith/order/services.py::_place_order_remote`/
    `_place_order_choreographed` already establish for the gRPC cutover.

    Raises `ResourceNotFound` for an unknown customer (no reservation
    attempted), `InsufficientStock`/`InventoryServiceUnavailable` (via
    `app/inventory_client.py`) for a reservation failure, and re-raises
    whatever the persistence transaction raised after compensating."""
    async with session_factory() as session:
        customer = await repository.get_customer_by_id(session, customer_id)
    if customer is None:
        raise ResourceNotFound(f"No customer with id {customer_id}")

    line_snapshots, reserved = await _reserve_lines_remote(
        inventory_grpc_target, grpc_timeout_s, items
    )

    try:
        created_at = datetime.now(UTC)
        async with session_factory() as session:
            order = await repository.create_order_with_outbox_and_view(
                session,
                customer=customer,
                items=line_snapshots,
                shipping_address=shipping_address,
                payment_method=payment_method,
                created_at=created_at,
            )
        logger.info(
            "place_order order_id=%s customer_id=%s total_cents=%s -> PENDING (checkout)",
            order.id,
            customer_id,
            order.total_cents,
        )
        return order
    except Exception:
        # Net-zero: every sku reserved remotely this checkout gets a
        # compensating Release -- the persistence transaction above has
        # already rolled itself back by the time this except runs.
        await _release_reserved(inventory_grpc_target, grpc_timeout_s, reserved)
        raise


async def _reserve_lines_remote(
    inventory_grpc_target: str, timeout: float, items: list[OrderLineIn]
) -> tuple[list[dict], list[tuple[str, int]]]:
    """Reserve every checkout line over gRPC, in order. The moment any line
    fails, every sku ALREADY reserved earlier in THIS call is compensated
    with a remote Release before the exception propagates. Returns the
    denormalized line snapshots the aggregate needs (sku/quantity/
    unit_price_cents, from inventory-service's `Reserve`+`GetStock` replies)
    plus the full (sku, quantity) reservation list, so the CALLER can
    compensate again if the persistence transaction fails after every line
    reserved cleanly."""
    line_snapshots: list[dict] = []
    reserved: list[tuple[str, int]] = []
    async with AsyncInventoryClient(inventory_grpc_target, timeout) as client:
        for line in items:
            try:
                await client.reserve(line.sku, line.quantity)
                # Only recorded once the remote decrement has actually
                # committed.
                reserved.append((line.sku, line.quantity))
                stock = await client.get_stock(line.sku)
            except Exception:
                await _release_reserved_with_client(client, reserved)
                raise
            line_snapshots.append(
                {
                    "sku": stock.sku,
                    "unit_price_cents": stock.unit_price_cents,
                    "quantity": line.quantity,
                }
            )
    return line_snapshots, reserved


async def _release_reserved(
    inventory_grpc_target: str, timeout: float, reserved: list[tuple[str, int]]
) -> None:
    if not reserved:
        return
    async with AsyncInventoryClient(inventory_grpc_target, timeout) as client:
        await _release_reserved_with_client(client, reserved)


async def _release_reserved_with_client(client: AsyncInventoryClient, reserved) -> None:
    """Best-effort compensating Release for every sku reserved so far this
    checkout -- logged loudly on failure rather than silently swallowed; a
    Release failure does NOT replace the original checkout failure being
    propagated to the caller."""
    for sku, quantity in reserved:
        try:
            await client.release(sku, quantity)
        except Exception:
            logger.exception(
                "compensation FAILED for sku=%s qty=%d -- stock NOT restored", sku, quantity
            )


async def _release_order_lines(
    inventory_grpc_target: str, timeout: float, order_id: int, items: list[OrderItem]
) -> None:
    """Compensating gRPC Release for every line THIS order reserved at
    checkout, recovered from the persisted `OrderItem` snapshot rows (sku,
    quantity) -- a saga reaction runs later, off a Kafka event, in a
    different call stack than the checkout request that did the original
    Reserve, so there is no in-memory `reserved` list to reuse here.

    `idempotency_key` is the SAME stable per-(order, line) key
    (`f"{order_id}:{sku}:release"`) `00-monolith/order/services.py::
    _release_order_lines` uses, so a repeated Release for the same line
    (redelivery, or a race against a concurrent handler) is a no-op against
    inventory-service's own idempotent handling of this field."""
    async with AsyncInventoryClient(inventory_grpc_target, timeout) as client:
        for item in items:
            idempotency_key = f"{order_id}:{item.sku}:release"
            try:
                await client.release(item.sku, item.quantity, idempotency_key=idempotency_key)
            except Exception:
                logger.exception(
                    "compensation FAILED for order_id=%s sku=%s qty=%d -- stock NOT restored",
                    order_id,
                    item.sku,
                    item.quantity,
                )


async def handle_payment_captured(session_factory, event: PaymentCapturedEvent) -> Order | None:
    """Reaction to `payment.captured` (published by `05-payment-service`'s
    own outbox relay). ORCHESTRATED-shipping posture (mirrors
    `00-monolith`'s `SHIPPING_MODE=orchestrated` flavor of
    `handle_payment_captured`): transitions `PENDING -> AWAITING_SHIPMENT`
    and stops -- `06-shipping-service`'s own saga reacts to this SAME event,
    enriches itself via `GET /api/orders/{id}` (this service's own read
    surface), and reports its outcome back over `shipment.dispatched`/
    `shipment.failed`, resolved by `handle_shipment_dispatched`/
    `handle_shipment_failed` below. No gRPC call here -- nothing to
    compensate on a captured payment.

    Idempotent via `transition_order_status_with_view`'s atomic conditional
    `UPDATE`: an order that already left `PENDING` is a no-op."""
    async with session_factory() as session:
        order = await repository.transition_order_status_with_view(
            session,
            order_id=event.order_id,
            expected_status=STATUS_PENDING,
            new_status=STATUS_AWAITING_SHIPMENT,
        )
    if order is None:
        logger.info(
            "payment.captured redelivered/unknown for order_id=%s -- no-op (status guard)",
            event.order_id,
        )
    else:
        logger.info("payment.captured order_id=%s -> AWAITING_SHIPMENT", order.id)
    return order


async def handle_payment_declined(
    session_factory,
    event: PaymentDeclinedEvent,
    *,
    inventory_grpc_target: str,
    grpc_timeout_s: float,
) -> Order | None:
    """Reaction to `payment.declined`. Releases every line this order
    reserved at checkout (compensating gRPC Release, OUTSIDE any DB
    transaction, matching the reserve-outside-tx discipline), then
    transitions `PENDING -> PAYMENT_DECLINED` atomically with the
    `order_view` upsert.

    Idempotent: the read-before-release check
    (`repository.get_order_with_items_if_status_in`) and the final
    conditional `UPDATE` (`transition_order_status_with_view`) both guard on
    `status == PENDING` -- a redelivered `payment.declined` for an order that
    already left `PENDING` never re-releases and never re-transitions. The
    Release itself is additionally protected by its own stable idempotency
    key even if two redeliveries ever raced each other past the read guard."""
    async with session_factory() as session:
        found = await repository.get_order_with_items_if_status_in(
            session, event.order_id, {STATUS_PENDING}
        )
    if found is None:
        logger.info(
            "payment.declined redelivered/unknown for order_id=%s -- no-op (status guard)",
            event.order_id,
        )
        return None
    order, items = found

    await _release_order_lines(inventory_grpc_target, grpc_timeout_s, order.id, items)

    async with session_factory() as session:
        updated = await repository.transition_order_status_with_view(
            session,
            order_id=order.id,
            expected_status=STATUS_PENDING,
            new_status=STATUS_PAYMENT_DECLINED,
        )
    if updated is None:
        logger.info(
            "payment.declined order_id=%s lost the status-transition race -- no-op", order.id
        )
    else:
        logger.info("payment.declined order_id=%s -> PAYMENT_DECLINED", order.id)
    return updated


async def handle_shipment_dispatched(
    session_factory, event: ShipmentDispatchedEvent
) -> Order | None:
    """Reaction to `shipment.dispatched` (published by
    `06-shipping-service`'s own outbox relay). Resolves the
    `AWAITING_SHIPMENT` hand-off `handle_payment_captured` left behind:
    `AWAITING_SHIPMENT -> CONFIRMED`. No gRPC call -- nothing to compensate
    on a successful dispatch.

    Idempotent via the same atomic conditional `UPDATE`: an order that has
    already left `AWAITING_SHIPMENT` is a no-op."""
    async with session_factory() as session:
        order = await repository.transition_order_status_with_view(
            session,
            order_id=event.order_id,
            expected_status=STATUS_AWAITING_SHIPMENT,
            new_status=STATUS_CONFIRMED,
        )
    if order is None:
        logger.info(
            "shipment.dispatched redelivered/unknown for order_id=%s -- no-op (status guard)",
            event.order_id,
        )
    else:
        logger.info("shipment.dispatched order_id=%s -> CONFIRMED", order.id)
    return order


async def handle_shipment_failed(
    session_factory,
    event: ShipmentFailedEvent,
    *,
    inventory_grpc_target: str,
    grpc_timeout_s: float,
) -> Order | None:
    """Reaction to `shipment.failed`. Same compensating-Release-then-transition
    shape as `handle_payment_declined`, gated on `AWAITING_SHIPMENT` instead
    of `PENDING`: releases every line this order reserved at checkout, then
    transitions `AWAITING_SHIPMENT -> SHIPPING_FAILED` atomically with the
    `order_view` upsert.

    KNOWN DEFERRAL (documented, matching
    `00-monolith/order/services.py::handle_shipment_failed`'s docstring): a
    payment that captured and then hits `shipment.failed` here is refunded
    by `05-payment-service`'s own `shipment.failed` consumer
    (`app/refund_consumer.py`, r06/DRQ-054) reacting to the SAME event this
    handler does -- this service has no payment collaborator of its own to
    call."""
    async with session_factory() as session:
        found = await repository.get_order_with_items_if_status_in(
            session, event.order_id, {STATUS_AWAITING_SHIPMENT}
        )
    if found is None:
        logger.info(
            "shipment.failed redelivered/unknown for order_id=%s -- no-op (status guard)",
            event.order_id,
        )
        return None
    order, items = found

    await _release_order_lines(inventory_grpc_target, grpc_timeout_s, order.id, items)

    async with session_factory() as session:
        updated = await repository.transition_order_status_with_view(
            session,
            order_id=order.id,
            expected_status=STATUS_AWAITING_SHIPMENT,
            new_status=STATUS_SHIPPING_FAILED,
        )
    if updated is None:
        logger.info(
            "shipment.failed order_id=%s lost the status-transition race -- no-op", order.id
        )
    else:
        logger.info("shipment.failed order_id=%s -> SHIPPING_FAILED", order.id)
    return updated


async def rebuild_order_view(session_factory, order_id: int):
    """Standalone entry point for rebuilding `order_view` from the current
    aggregate state -- proves the projection is rebuildable, not a second
    source of truth (see `app/models.py::OrderView`'s docstring). Used by
    `tests/unit/test_place_order.py`'s projection-disabled negative test and
    available as an operational repair tool."""
    async with session_factory() as session:
        view = await repository.rebuild_order_view(session, order_id)
        if view is not None:
            await session.commit()
        return view
