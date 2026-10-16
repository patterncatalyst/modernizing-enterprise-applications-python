"""r07's client-side anti-corruption layer for the order<->inventory gRPC
seam -- the direct descendant of `00-monolith/order/inventory_client.py`'s
`RemoteInventoryClient`, re-authored on `grpc.aio` instead of a blocking
`grpc.insecure_channel`: FastAPI's request path runs on an asyncio event
loop, so (unlike the monolith's synchronous Django/WSGI request path) there
IS a loop here for an async stub to plug into -- a blocking stub would stall
that loop for the RPC's full round trip.

Wraps the generated `inventory_pb2`/`inventory_pb2_grpc` stubs (`app/grpc_gen/`,
vendored from `../proto/dev/patterncatalyst/inventory/v1/inventory.proto`,
byte-identical to `04-inventory-service/proto/.../inventory.proto` --
`scripts/check-proto-drift.sh`'s convention, extended to this service) and
translates their wire vocabulary (`stock_keeping_unit`/`display_name`/
`unit_price_cents`/`on_hand_qty`/`reservation_ok`) into the two plain
dataclasses below -- the generated proto message types never leak past this
module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import grpc
from grpc import aio as grpc_aio

from app.errors import InsufficientStock, InventoryServiceUnavailable
from app.grpc_gen import inventory_pb2, inventory_pb2_grpc

logger = logging.getLogger("order_service.inventory_client")

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class StockSnapshot:
    """Clean translation of `StockReply` -- the raw proto type never leaks
    past this client. `name`/`unit_price_cents` are exactly the denormalized
    snapshot fields `app/models.py::OrderItem` captures at checkout time."""

    sku: str
    name: str
    unit_price_cents: int
    on_hand_qty: int
    available: bool


@dataclass(frozen=True)
class ReserveResult:
    """Clean translation of `ReserveReply` -- the raw proto type never leaks
    past this client."""

    sku: str
    reservation_ok: bool
    on_hand_qty: int


class AsyncInventoryClient:
    """r07's `grpc.aio`-based collaborator for `app/service.py::place_order`
    and the four saga reactions' compensating `release`.

    `reserve` performs the server-side atomic check-and-decrement;
    `reservation_ok=False` is translated into `InsufficientStock` (409) --
    the SAME outcome the monolith's `grpc`-mode `RemoteInventoryClient.reserve`
    raises, so this service's checkout contract matches it. `release` is the
    compensating re-increment, supporting a stable `idempotency_key` so a
    saga-reaction redelivery never double-credits. A `grpc.RpcError` (timeout,
    UNAVAILABLE, ...) on any call is translated to `InventoryServiceUnavailable`
    (503) -- never confused with a logical "insufficient stock" outcome.
    """

    def __init__(self, target: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._channel = grpc_aio.insecure_channel(target)
        self._stub = inventory_pb2_grpc.InventoryGrpcServiceStub(self._channel)

    async def close(self) -> None:
        await self._channel.close()

    async def __aenter__(self) -> AsyncInventoryClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def reserve(self, sku: str, quantity: int) -> ReserveResult:
        """Server-side atomic check-and-decrement against inventory-service's
        OWN database. Raises `InsufficientStock` when `reservation_ok=False`
        -- no decrement happened server-side in that case, so there is
        nothing for the caller to compensate for THIS line."""
        request = inventory_pb2.ReserveRequest(stock_keeping_unit=sku, requested_qty=quantity)
        reply = await self._unary(self._stub.Reserve, request)
        if not reply.reservation_ok:
            raise InsufficientStock(
                f"Requested {quantity} of {sku} but only {reply.on_hand_qty} on hand"
            )
        return ReserveResult(
            sku=reply.stock_keeping_unit,
            reservation_ok=reply.reservation_ok,
            on_hand_qty=reply.on_hand_qty,
        )

    async def release(self, sku: str, quantity: int, idempotency_key: str = "") -> ReserveResult:
        """Compensating re-increment. `idempotency_key` (ReleaseRequest field
        3) is OPTIONAL: `place_order`'s own pre-confirmation compensation
        (reserve-outside-tx failure) calls this with none -- it runs once,
        synchronously, inside the same request that did the Reserve, so
        there is nothing to redeliver. The four saga reactions
        (`app/service.py::handle_payment_declined`/`handle_shipment_failed`),
        which run later off at-least-once Kafka events, pass a STABLE
        per-(order, line) key -- `f"{order_id}:{sku}:release"`, the exact
        same key format `00-monolith/order/services.py::_release_order_lines`
        uses -- so a repeated Release against inventory-service's own
        idempotent handling of this field is a no-op, never a double
        credit."""
        request = inventory_pb2.ReleaseRequest(
            stock_keeping_unit=sku, requested_qty=quantity, idempotency_key=idempotency_key
        )
        reply = await self._unary(self._stub.Release, request)
        return ReserveResult(
            sku=reply.stock_keeping_unit,
            reservation_ok=reply.reservation_ok,
            on_hand_qty=reply.on_hand_qty,
        )

    async def get_stock(self, sku: str) -> StockSnapshot:
        """Full read of one sku's current stock record -- the
        content-enricher fetch `place_order()` uses to populate `OrderItem`'s
        denormalized `unit_price_cents` snapshot (`ReserveReply` carries no
        price; only `GetStock`/`CheckStock` do)."""
        request = inventory_pb2.GetStockRequest(stock_keeping_unit=sku)
        reply = await self._unary(self._stub.GetStock, request)
        return self._to_snapshot(reply)

    async def _unary(self, rpc, request):
        try:
            return await rpc(request, timeout=self._timeout)
        except grpc.RpcError as exc:
            code = exc.code() if hasattr(exc, "code") else None
            details = exc.details() if hasattr(exc, "details") else str(exc)
            logger.error("inventory gRPC call failed: %s %s", code, details)
            raise InventoryServiceUnavailable(
                f"Inventory service unavailable: {code} {details}"
            ) from exc

    @staticmethod
    def _to_snapshot(reply) -> StockSnapshot:
        return StockSnapshot(
            sku=reply.stock_keeping_unit,
            name=reply.display_name,
            unit_price_cents=reply.unit_price_cents,
            on_hand_qty=reply.on_hand_qty,
            available=reply.available,
        )
