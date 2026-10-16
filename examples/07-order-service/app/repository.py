"""Async SQLAlchemy queries/writes against this service's OWN `order_svc`
schema -- the CQRS command-side persistence (aggregate + outbox + the
SAME-TRANSACTION `order_view` projection) AND the read-side queries
(`order_view` only -- `app/routes.py` never touches `orders`/`order_items`
directly).

Every write function here either commits internally (the ONE-transaction
boundary this lane's acceptance criteria calls out: aggregate + view +
outbox together, or status-transition + view together) or explicitly rolls
back a no-op guard miss -- the same convention `05-payment-service/app/
repository.py`'s `transition_payment_status_with_outbox_event` establishes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Order, OrderItem, OrderView, OutboxEvent

_RELAY_BATCH_SIZE = 100

ORDER_PLACED_EVENT_TYPE = "order.placed"
AGGREGATE_TYPE = "order"


# ---------------------------------------------------------------------------
# Command-side reads (validation / internal lookups -- NOT the HTTP read
# surface, which is served from order_view exclusively, see below).
# ---------------------------------------------------------------------------


async def get_customer_by_id(session: AsyncSession, customer_id: int) -> Customer | None:
    return await session.get(Customer, customer_id)


async def list_order_items(session: AsyncSession, order_id: int) -> list[OrderItem]:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_order_with_items_if_status_in(
    session: AsyncSession, order_id: int, statuses: set[str]
) -> tuple[Order, list[OrderItem]] | None:
    """The FIRST half of a saga reaction's idempotency guard: a plain read
    (no row lock -- the gRPC compensation that may follow this call must run
    OUTSIDE any DB transaction, so there is nothing useful to hold a lock
    across). Returns `None` for an unknown order OR one that has already
    left `statuses` (an earlier delivery of this, or the other outcome's,
    event already resolved it) -- the caller treats both as a safe no-op.
    The actual idempotency BACKSTOP against two concurrent redeliveries is
    `transition_order_status_with_view`'s atomic conditional `UPDATE`,
    called after any compensation this check gates."""
    order = await session.get(Order, order_id)
    if order is None or order.status not in statuses:
        return None
    items = await list_order_items(session, order_id)
    return order, items


# ---------------------------------------------------------------------------
# Read side -- order_view ONLY. `app/routes.py`'s GET handlers call these and
# nothing else.
# ---------------------------------------------------------------------------


async def get_order_view_by_id(session: AsyncSession, order_id: int) -> OrderView | None:
    return await session.get(OrderView, order_id)


async def list_order_views(session: AsyncSession) -> list[OrderView]:
    stmt = select(OrderView).order_by(OrderView.order_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Command side -- writes. Every function below owns its own transaction
# boundary (commits or rolls back internally); callers never wrap these in a
# further-outer transaction.
# ---------------------------------------------------------------------------


def _item_view_payload(items: Sequence[OrderItem]) -> list[dict[str, Any]]:
    """Builds `OrderView.items`' denormalized JSON shape -- already
    camelCase (`unitPriceCents`), matching `app/schemas.py::OrderItemOut`'s
    wire alias exactly, so `order_view_to_out` below needs no further
    translation."""
    return [
        {"sku": item.sku, "quantity": item.quantity, "unitPriceCents": item.unit_price_cents}
        for item in items
    ]


def _sync_view_from_order(view: OrderView, order: Order, items: Sequence[OrderItem]) -> None:
    view.customer_id = order.customer_id
    view.status = order.status
    view.total_cents = order.total_cents
    view.shipping_address = order.shipping_address
    view.created_at = order.created_at
    view.items = _item_view_payload(items)


async def _upsert_order_view(
    session: AsyncSession, order: Order, items: Sequence[OrderItem]
) -> OrderView:
    view = await session.get(OrderView, order.id)
    if view is None:
        view = OrderView(order_id=order.id, items=[])
        session.add(view)
    _sync_view_from_order(view, order, items)
    await session.flush()
    return view


async def create_order_with_outbox_and_view(
    session: AsyncSession,
    *,
    customer: Customer,
    items: list[dict[str, Any]],
    shipping_address: str,
    payment_method: str,
    created_at: datetime,
) -> Order:
    """Persists the write aggregate (`orders` + `order_items`), the
    `order_view` PENDING row, and the `order.placed` outbox row -- all THREE
    in ONE local transaction (this lane's three-way atomicity guarantee: a
    reader can never observe the aggregate without its matching view row,
    and the outbox row is never written without the aggregate landing too).

    `items` is the gRPC-reserved line snapshot
    (`app/service.py::_reserve_lines_remote`'s return value) -- `sku`/
    `quantity`/`unit_price_cents` already resolved from inventory-service's
    `Reserve`/`GetStock` replies, captured here as a point-in-time snapshot
    (no FK to any inventory table, same cure r04/ch.19 established)."""
    total_cents = sum(item["unit_price_cents"] * item["quantity"] for item in items)

    order = Order(
        customer_id=customer.id,
        customer_email=customer.email,
        status="PENDING",
        total_cents=total_cents,
        shipping_address=shipping_address,
        created_at=created_at,
    )
    session.add(order)
    await session.flush()  # populates order.id via INSERT ... RETURNING

    order_items = [
        OrderItem(
            order_id=order.id,
            sku=item["sku"],
            quantity=item["quantity"],
            unit_price_cents=item["unit_price_cents"],
        )
        for item in items
    ]
    session.add_all(order_items)
    await session.flush()

    view = OrderView(
        order_id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_cents=order.total_cents,
        shipping_address=order.shipping_address,
        created_at=order.created_at,
        items=_item_view_payload(order_items),
    )
    session.add(view)

    confirmation_message = f"Order #{order.id} placed, total ${order.total_cents / 100:.2f}"
    payload = {
        "orderId": order.id,
        "customerId": customer.id,
        "customerEmail": customer.email,
        "totalCents": order.total_cents,
        "confirmationMessage": confirmation_message,
        "placedAt": created_at.isoformat(),
        "paymentMethod": payment_method,
    }
    outbox_event = OutboxEvent(
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=str(order.id),
        event_type=ORDER_PLACED_EVENT_TYPE,
        payload=payload,
        created_at=created_at,
        published_at=None,
    )
    session.add(outbox_event)

    await session.flush()
    await session.commit()
    return order


async def transition_order_status_with_view(
    session: AsyncSession,
    *,
    order_id: int,
    expected_status: str,
    new_status: str,
) -> Order | None:
    """Conditionally transitions `orders.status` (e.g. `PENDING ->
    AWAITING_SHIPMENT`) AND upserts `order_view` to match, in ONE
    transaction -- the saga-reaction half of this lane's atomicity
    guarantee.

    Returns the updated `Order`, or `None` if no row matched BOTH `order_id`
    AND `expected_status` -- the idempotent no-op path for a redelivered
    event whose order already left `expected_status` (resolved by an earlier
    delivery of this event, or of the other terminal outcome for the same
    stage). The `WHERE status = expected_status` guard on the `UPDATE` is
    the database-level backstop against two deliveries racing concurrently --
    only one `UPDATE` can match the row while it is still in
    `expected_status`; the loser's `UPDATE` matches zero rows and this
    returns `None`, same safe no-op as any other idempotent redelivery (see
    `05-payment-service/app/repository.py::transition_payment_status_with_outbox_event`,
    the precedent this mirrors)."""
    stmt = (
        update(Order)
        .where(Order.id == order_id, Order.status == expected_status)
        .values(status=new_status)
        .returning(Order)
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        await session.rollback()
        return None

    items = await list_order_items(session, order_id)
    await _upsert_order_view(session, order, items)

    await session.flush()
    await session.commit()
    return order


async def rebuild_order_view(session: AsyncSession, order_id: int) -> OrderView | None:
    """Recomputes `order_view` from the CURRENT `orders`/`order_items`
    aggregate state -- the CQRS projection is rebuildable at any time, never
    a second source of truth. Returns `None` for an unknown order_id (caller
    decides whether that's an error). Does NOT commit -- callers own the
    transaction boundary (mirrors every other write function's docstring
    convention of documenting commit ownership explicitly; this one is used
    both standalone, with its own commit, by `app/service.py::rebuild_order_view`,
    and inline by a future caller that already holds a transaction open)."""
    order = await session.get(Order, order_id)
    if order is None:
        return None
    items = await list_order_items(session, order_id)
    return await _upsert_order_view(session, order, items)


# ---------------------------------------------------------------------------
# Outbox relay support (publish-side, see app/relay.py).
# ---------------------------------------------------------------------------


async def list_unpublished_outbox_events(
    session: AsyncSession, *, limit: int = _RELAY_BATCH_SIZE
) -> list[OutboxEvent]:
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
    stmt = (
        update(OutboxEvent)
        .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
        .values(published_at=published_at)
    )
    await session.execute(stmt)
    await session.commit()
