"""Downstream clients for the GraphQL gateway.

The gateway federates by *calling* the services it composes -- it owns no
data of its own:

  - order-service    GET /api/orders/{id}            (REST, httpx)
  - payment-service  GET /api/payments?orderId=       (REST, httpx)
  - shipping-service GET /api/shipments?orderId=      (REST, httpx)
  - review-service   GET /api/reviews?sku=            (REST, httpx)
  - inventory-service GetStock(stock_keeping_unit)    (gRPC, grpc.aio)

Every function here either returns the downstream's parsed payload or raises
`DownstreamUnavailable`. Resolvers in `app/schema.py` deliberately do NOT
catch that exception -- they let it propagate out of the field resolver.
Strawberry/graphql-core's default null-propagation then nulls JUST that
field (every federated field below the order's own read-model fields is
declared nullable in the schema for exactly this reason) and appends an
entry to the GraphQL response's top-level `errors[]` array. The one
exception is `fetch_order`: a 404 there means the order genuinely doesn't
exist, so it returns `None` rather than raising -- an absent order is not a
downstream failure, it's a legitimate "no such id" answer with no error.
"""

from __future__ import annotations

import logging

import grpc
import httpx
from grpc import aio as grpc_aio

from app.config import Settings
from app.grpc_gen import inventory_pb2, inventory_pb2_grpc

logger = logging.getLogger("graphql_gateway.clients")


class DownstreamUnavailable(RuntimeError):
    """Raised when a downstream REST call fails/times out, returns a non-2xx
    status, or a downstream gRPC call raises `grpc.RpcError`. Left
    uncaught by the calling field resolver on purpose -- see module
    docstring for why that's the partial-failure contract, not a bug."""


async def fetch_order(settings: Settings, order_id: str) -> dict | None:
    """GET /api/orders/{id} from order-service. Returns `None` on a 404
    (the order doesn't exist -- not a downstream failure). Any other
    non-2xx status, timeout, or connection error raises
    `DownstreamUnavailable`."""
    url = f"{settings.order_service_url}/api/orders/{order_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.rest_timeout_s) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error("order-service call failed: %s", exc)
        raise DownstreamUnavailable(f"order-service unavailable: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.is_error:
        raise DownstreamUnavailable(f"order-service returned {resp.status_code}")
    return resp.json()


async def fetch_payments(settings: Settings, order_id: str) -> list[dict]:
    """GET /api/payments?orderId= from payment-service -- every
    CAPTURED/DECLINED payment attempt against this order."""
    url = f"{settings.payment_service_url}/api/payments"
    try:
        async with httpx.AsyncClient(timeout=settings.rest_timeout_s) as client:
            resp = await client.get(url, params={"orderId": order_id})
    except httpx.HTTPError as exc:
        logger.error("payment-service call failed: %s", exc)
        raise DownstreamUnavailable(f"payment-service unavailable: {exc}") from exc
    if resp.is_error:
        raise DownstreamUnavailable(f"payment-service returned {resp.status_code}")
    return resp.json()


async def fetch_shipments(settings: Settings, order_id: str) -> list[dict]:
    """GET /api/shipments?orderId= from shipping-service -- every shipment
    recorded against this order."""
    url = f"{settings.shipping_service_url}/api/shipments"
    try:
        async with httpx.AsyncClient(timeout=settings.rest_timeout_s) as client:
            resp = await client.get(url, params={"orderId": order_id})
    except httpx.HTTPError as exc:
        logger.error("shipping-service call failed: %s", exc)
        raise DownstreamUnavailable(f"shipping-service unavailable: {exc}") from exc
    if resp.is_error:
        raise DownstreamUnavailable(f"shipping-service returned {resp.status_code}")
    return resp.json()


async def fetch_reviews(settings: Settings, sku: str) -> list[dict]:
    """GET /api/reviews?sku= from review-service -- every review posted for
    this line item's sku."""
    url = f"{settings.review_service_url}/api/reviews"
    try:
        async with httpx.AsyncClient(timeout=settings.rest_timeout_s) as client:
            resp = await client.get(url, params={"sku": sku})
    except httpx.HTTPError as exc:
        logger.error("review-service call failed: %s", exc)
        raise DownstreamUnavailable(f"review-service unavailable: {exc}") from exc
    if resp.is_error:
        raise DownstreamUnavailable(f"review-service returned {resp.status_code}")
    return resp.json()


async def fetch_stock(settings: Settings, sku: str) -> dict:
    """Full read of one sku's current stock record from inventory-service's
    `GetStock` RPC -- the real-time availability figure, never a cached or
    denormalized copy. The same read-only RPC `07-order-service`'s
    `AsyncInventoryClient.get_stock` dials."""
    try:
        async with grpc_aio.insecure_channel(settings.inventory_grpc_target) as channel:
            stub = inventory_pb2_grpc.InventoryGrpcServiceStub(channel)
            reply = await stub.GetStock(
                inventory_pb2.GetStockRequest(stock_keeping_unit=sku),
                timeout=settings.grpc_timeout_s,
            )
    except grpc.RpcError as exc:
        code = exc.code() if hasattr(exc, "code") else None
        details = exc.details() if hasattr(exc, "details") else str(exc)
        logger.error("inventory-service gRPC call failed: %s %s", code, details)
        raise DownstreamUnavailable(f"inventory-service unavailable: {code} {details}") from exc
    return {
        "sku": reply.stock_keeping_unit,
        "display_name": reply.display_name,
        "unit_price_cents": reply.unit_price_cents,
        "on_hand_qty": reply.on_hand_qty,
        "available": reply.available,
    }
