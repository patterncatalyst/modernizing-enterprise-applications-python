"""gRPC SERVER (r04/ch.19, DRQ-039/DRQ-041/DRQ-042/DRQ-044) implementing the
generated `InventoryGrpcServiceServicer` interface (`app/grpc_gen/`, compiled
from `../proto/.../inventory.proto` by the PROTO lane). Idiomatic-from-day-
one -- there is no Django original to lift for RPCs that never existed in
the monolith (the monolith's `reserve` lived in-process against a
pessimistic-lock derived query, a fundamentally different mechanism).

This is the ACL contract's server side: the wire vocabulary here
(`stock_keeping_unit`/`on_hand_qty`/`unit_price_cents`) is deliberately
distinct from the internal `StockOut`/`InventoryItem` shape
(`sku`/`quantity_on_hand`/`price_cents`) so the order-side ACL's message
translator earns its keep converting between the two, instead of the two
shapes happening to already agree.

Each RPC opens its OWN async session (rather than sharing one across calls,
or reusing the HTTP request-scoped session dependency) -- gRPC method
invocations are not bound to FastAPI's request/response cycle, so there is no
natural per-request session scope to hook into here; a short-lived session
per call keeps each RPC's unit of work self-contained, same posture as
`app/db.py::get_session` giving each HTTP request its own session.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import repository
from app.grpc_gen import inventory_pb2, inventory_pb2_grpc
from app.models import InventoryItem

logger = logging.getLogger("inventory_service.grpc")


def _to_stock_reply(
    requested_sku: str, item: InventoryItem | None, available: bool
) -> inventory_pb2.StockReply:
    if item is None:
        return inventory_pb2.StockReply(
            stock_keeping_unit=requested_sku,
            display_name="",
            unit_price_cents=0,
            on_hand_qty=0,
            available=False,
        )
    return inventory_pb2.StockReply(
        stock_keeping_unit=item.sku,
        display_name=item.name,
        unit_price_cents=item.price_cents,
        on_hand_qty=item.quantity_on_hand,
        available=available,
    )


class InventoryGrpcServiceServicer(inventory_pb2_grpc.InventoryGrpcServiceServicer):
    """See module docstring. `session_factory` is the same
    `async_sessionmaker` `app/main.py`'s lifespan builds for the HTTP side
    (`app/db.py::create_session_factory`) -- one engine, two protocol
    surfaces."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def CheckStock(self, request, context):
        """Read-only availability probe: is at least `requested_qty` on hand
        for `sku`? Does NOT mutate state. `available` answers "can
        requested_qty be satisfied right now" -- distinct from `GetStock`'s
        `available`, which reports "is there any stock at all."
        """
        sku = request.stock_keeping_unit
        async with self._session_factory() as session:
            item = await repository.get_by_sku(session, sku)
        can_satisfy = item is not None and item.quantity_on_hand >= request.requested_qty
        return _to_stock_reply(sku, item, can_satisfy)

    async def Reserve(self, request, context):
        """Server-side ATOMIC check-and-decrement -- see
        `app/repository.py::reserve`'s docstring for the concurrency-safety
        argument. `reservation_ok` is true iff exactly one row was affected
        by the conditional `UPDATE`; `on_hand_qty` is always the CURRENT
        value after the attempt (unchanged on failure, decremented on
        success)."""
        sku = request.stock_keeping_unit
        qty = request.requested_qty
        async with self._session_factory() as session:
            rowcount = await repository.reserve(session, sku, qty)
            item = await repository.get_by_sku(session, sku)
        on_hand_qty = item.quantity_on_hand if item is not None else 0
        return inventory_pb2.ReserveReply(
            stock_keeping_unit=sku,
            reservation_ok=rowcount == 1,
            on_hand_qty=on_hand_qty,
        )

    async def Release(self, request, context):
        """Compensating re-increment -- the monolith calls this when
        checkout fails AFTER a successful `Reserve` (notably a payment
        decline): once the decrement lives in this service's own DB, the
        monolith's local transaction can no longer roll it back, so the
        monolith must explicitly restore the observable baseline.

        Idempotent when the caller sends `idempotency_key` (DRQ-043, the
        IDEMPOTENT-COMPENSATION lane): a retried `Release` carrying the SAME
        key is a no-op that returns the CURRENT stock rather than
        over-restoring it a second time -- see
        `app/repository.py::release`'s docstring for the single-statement,
        race-safe dedupe mechanism (an `INSERT ... ON CONFLICT DO NOTHING`
        against `inventory.compensations`'s unique index on
        `idempotency_key`, in the SAME session/transaction as the
        conditional re-increment). An empty/absent key falls back to the
        original unconditional, non-deduped behavior for callers that
        predate this field.
        """
        sku = request.stock_keeping_unit
        qty = request.requested_qty
        idempotency_key = request.idempotency_key
        async with self._session_factory() as session:
            reservation_ok = await repository.release(session, sku, qty, idempotency_key)
            item = await repository.get_by_sku(session, sku)
        on_hand_qty = item.quantity_on_hand if item is not None else 0
        return inventory_pb2.ReserveReply(
            stock_keeping_unit=sku,
            reservation_ok=reservation_ok,
            on_hand_qty=on_hand_qty,
        )

    async def GetStock(self, request, context):
        """Full read of one sku's current stock record -- the content-
        enricher fetch target for the order-side ACL (content-based router ->
        content enricher -> message translator into the monolith's own
        `StockOut`/`StockDto` shape). `available` here means "does this sku
        exist with any stock at all," distinct from `CheckStock`'s
        requested-quantity-aware `available`."""
        sku = request.stock_keeping_unit
        async with self._session_factory() as session:
            item = await repository.get_stock(session, sku)
        available = item is not None and item.quantity_on_hand > 0
        return _to_stock_reply(sku, item, available)
