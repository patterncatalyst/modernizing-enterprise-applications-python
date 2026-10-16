"""r04/ch.19 -- the client-side anti-corruption layer for the order<->
inventory gRPC seam.

`RemoteInventoryClient` wraps the generated `inventory_pb2`/
`inventory_pb2_grpc` stubs (see `order/grpc_gen/`, PROTO lane) and translates
their wire vocabulary (`stock_keeping_unit`/`display_name`/
`unit_price_cents`/`on_hand_qty`/`reservation_ok`) into the two plain
dataclasses below -- the generated proto message types never leak past this
module, mirroring the Java monolith's own `RemoteInventoryClient` (see
~/Dev/modernizing-enterprise-applications's `examples/00-monolith`, quoted in
Chapters 19 and 25) and its already-extracted descendant in
`examples/07-order-service`.

A synchronous `grpc.insecure_channel` + blocking stub is deliberate: Django's
request path (`order.services.place_order`) is itself synchronous/WSGI, so
there is no event loop here for an async stub to plug into.
"""

import logging
from dataclasses import dataclass

import grpc
from django.conf import settings

from common.exceptions import InsufficientStock, InventoryServiceUnavailable

from .grpc_gen import inventory_pb2, inventory_pb2_grpc

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class StockSnapshot:
    """Clean translation of `StockReply` -- the raw proto type never leaks
    past this client. `name`/`unit_price_cents` are exactly the denormalized
    snapshot fields `order.OrderItem` captures at checkout time (r04/ch.19:
    `OrderItem.inventory_item` FK -> `OrderItem.sku`/`item_name`/
    `unit_price_cents`)."""

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


class RemoteInventoryClient:
    """r04/ch.19 -- order.services.place_order()'s `grpc`-mode collaborator.

    `check_stock`/`get_stock` are read-only. `reserve` performs the
    server-side atomic check-and-decrement; `reservation_ok=False` is
    translated into the SAME `InsufficientStock` exception the `local`-mode
    in-process path raises (`inventory.services.reserve()`), so
    `place_order()`'s 409 contract is identical regardless of mode. `release`
    is the compensating re-increment place_order() calls for every sku it
    already reserved this checkout when something later fails. A
    `grpc.RpcError` (timeout, UNAVAILABLE, ...) on any call is translated to
    `InventoryServiceUnavailable` (503) -- it is not a logical "insufficient
    stock" outcome and must never be confused with one.
    """

    def __init__(self, target: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._timeout = timeout
        self._channel = grpc.insecure_channel(target or settings.INVENTORY_GRPC_TARGET)
        self._stub = inventory_pb2_grpc.InventoryGrpcServiceStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    def __enter__(self) -> RemoteInventoryClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def check_stock(self, sku: str, quantity: int) -> StockSnapshot:
        """Read-only availability probe: is at least `quantity` on hand for
        `sku`? Does not mutate state."""
        request = inventory_pb2.CheckStockRequest(stock_keeping_unit=sku, requested_qty=quantity)
        reply = self._unary(self._stub.CheckStock, request)
        return self._to_snapshot(reply)

    def reserve(self, sku: str, quantity: int) -> ReserveResult:
        """Server-side atomic check-and-decrement against the inventory
        service's OWN database. Raises `InsufficientStock` when
        `reservation_ok=False` -- no decrement happened server-side in that
        case, so there is nothing for the caller to compensate for THIS
        line."""
        request = inventory_pb2.ReserveRequest(stock_keeping_unit=sku, requested_qty=quantity)
        reply = self._unary(self._stub.Reserve, request)
        if not reply.reservation_ok:
            raise InsufficientStock(
                f"Requested {quantity} of {sku} but only {reply.on_hand_qty} on hand"
            )
        return ReserveResult(
            sku=reply.stock_keeping_unit,
            reservation_ok=reply.reservation_ok,
            on_hand_qty=reply.on_hand_qty,
        )

    def release(self, sku: str, quantity: int) -> ReserveResult:
        """Compensating re-increment -- order.services.place_order() calls
        this for every sku it successfully reserved remotely this checkout,
        on a pre-confirmation failure (insufficient stock on a LATER line,
        PaymentDeclined, ShippingFailed, or an outbox write failure)."""
        request = inventory_pb2.ReleaseRequest(stock_keeping_unit=sku, requested_qty=quantity)
        reply = self._unary(self._stub.Release, request)
        return ReserveResult(
            sku=reply.stock_keeping_unit,
            reservation_ok=reply.reservation_ok,
            on_hand_qty=reply.on_hand_qty,
        )

    def get_stock(self, sku: str) -> StockSnapshot:
        """Full read of one sku's current stock record -- the
        content-enricher fetch `place_order()` uses to populate `OrderItem`'s
        denormalized `sku`/`item_name`/`unit_price_cents` snapshot."""
        request = inventory_pb2.GetStockRequest(stock_keeping_unit=sku)
        reply = self._unary(self._stub.GetStock, request)
        return self._to_snapshot(reply)

    def _unary(self, rpc, request):
        try:
            return rpc(request, timeout=self._timeout)
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
