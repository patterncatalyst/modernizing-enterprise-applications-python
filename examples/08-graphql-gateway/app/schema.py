"""GraphQL schema for the gateway (Strawberry) -- the unified graph a client
queries with a single `order(id)` request instead of five separate calls.

`Query.order` resolves the order read model over REST from order-service;
404 there maps to a plain `null` (no error -- the id just doesn't exist).
Every OTHER field below the order's own read-model fields is a SEPARATE
federated fetch, resolved lazily only when a client actually selects it:

  - `OrderView.payments`         -> payment-service   (REST)
  - `OrderView.shipments`        -> shipping-service  (REST)
  - `OrderItemView.reviews`      -> review-service     (REST, by sku)
  - `OrderItemView.stock`        -> inventory-service  (gRPC `GetStock`)

Each of those four is declared as an OPTIONAL field (`X | None`). A
downstream failure (`app/clients.py::DownstreamUnavailable`, raised and
deliberately left uncaught here) is caught by Strawberry/graphql-core's own
null-propagation: because the field type is nullable, only THAT field
resolves to `null` and an entry is appended to the response's top-level
`errors[]` array -- siblings still resolve, and the whole query never
crashes into a 500. This is the GraphQL Gateway Contract this gateway
honors: `data.<field>: null` + a populated `errors[]`, never a silent null
with no error, and never an unhandled exception.

Strawberry auto-converts snake_case Python fields to camelCase in the schema
(`total_cents` -> `totalCents`, `customer_id` -> `customerId`), matching the
camelCase wire contract every REST service in this project already uses.
"""

from __future__ import annotations

import strawberry
from strawberry.extensions import MaxTokensLimiter, QueryDepthLimiter

from app.clients import fetch_order, fetch_payments, fetch_reviews, fetch_shipments, fetch_stock
from app.config import Settings


@strawberry.type
class StockView:
    """Federated from inventory-service's `GetStock` RPC -- the real-time
    on-hand figure for one sku, never a cached snapshot."""

    sku: str
    display_name: str
    unit_price_cents: int
    on_hand_qty: int
    available: bool


@strawberry.type
class PaymentView:
    """Federated from payment-service: one CAPTURED/DECLINED attempt against
    the order. Matches `05-payment-service`'s `PaymentOut` field-for-field."""

    id: strawberry.ID
    order_id: strawberry.ID
    amount_cents: int
    method: str
    status: str
    created_at: str


@strawberry.type
class ShipmentView:
    """Federated from shipping-service: one shipment recorded against the
    order. Matches `06-shipping-service`'s `ShipmentOut` field-for-field."""

    id: strawberry.ID
    order_id: strawberry.ID
    address: str
    status: str
    created_at: str


@strawberry.type
class ReviewView:
    """Federated from review-service: one review posted for a line item's
    sku. Matches `02-review-service`'s `ReviewOut` field-for-field."""

    id: strawberry.ID
    customer_id: strawberry.ID
    sku: str
    rating: int
    comment: str | None
    created_at: str


@strawberry.type
class OrderItemView:
    """One line of the order's read model (`07-order-service`'s
    `OrderItemOut`), plus two federated fields resolved per-item: the
    sku's live stock (inventory, gRPC) and every review posted for it
    (review-service, REST)."""

    sku: str
    quantity: int
    unit_price_cents: int

    @strawberry.field
    async def stock(self, info: strawberry.Info) -> StockView | None:
        settings = info.context["settings"]
        data = await fetch_stock(settings, self.sku)
        return _stock_from_grpc(data)

    @strawberry.field
    async def reviews(self, info: strawberry.Info) -> list[ReviewView] | None:
        settings = info.context["settings"]
        rows = await fetch_reviews(settings, self.sku)
        return [_review_from_rest(row) for row in rows]


@strawberry.type
class OrderView:
    """The order read model (`07-order-service`'s `OrderOut`), plus two
    federated list fields resolved by order id: every payment attempt
    (payment-service) and every shipment (shipping-service)."""

    id: strawberry.ID
    customer_id: strawberry.ID
    status: str
    total_cents: int
    created_at: str
    shipping_address: str
    items: list[OrderItemView]

    @strawberry.field
    async def payments(self, info: strawberry.Info) -> list[PaymentView] | None:
        settings = info.context["settings"]
        rows = await fetch_payments(settings, str(self.id))
        return [_payment_from_rest(row) for row in rows]

    @strawberry.field
    async def shipments(self, info: strawberry.Info) -> list[ShipmentView] | None:
        settings = info.context["settings"]
        rows = await fetch_shipments(settings, str(self.id))
        return [_shipment_from_rest(row) for row in rows]


def _item_from_rest(data: dict) -> OrderItemView:
    """Maps order-service's embedded `items[]` REST JSON onto `OrderItemView`
    -- `{sku, quantity, unitPriceCents}`, `07-order-service`'s `OrderItemOut`
    field list exactly."""
    return OrderItemView(
        sku=data["sku"],
        quantity=data["quantity"],
        unit_price_cents=data["unitPriceCents"],
    )


def _order_from_rest(data: dict) -> OrderView:
    """Maps order-service's `GET /api/orders/{id}` REST JSON onto the
    GraphQL `OrderView` -- `07-order-service`'s `OrderOut` field list
    exactly: `id, customerId, status, totalCents, createdAt,
    shippingAddress, items`."""
    return OrderView(
        id=strawberry.ID(str(data["id"])),
        customer_id=strawberry.ID(str(data["customerId"])),
        status=str(data["status"]),
        total_cents=data["totalCents"],
        created_at=str(data["createdAt"]),
        shipping_address=data["shippingAddress"],
        items=[_item_from_rest(item) for item in data["items"]],
    )


def _payment_from_rest(data: dict) -> PaymentView:
    """Maps payment-service's `PaymentOut` REST JSON onto `PaymentView` --
    `{id, orderId, amountCents, method, status, createdAt}`."""
    return PaymentView(
        id=strawberry.ID(str(data["id"])),
        order_id=strawberry.ID(str(data["orderId"])),
        amount_cents=data["amountCents"],
        method=data["method"],
        status=data["status"],
        created_at=str(data["createdAt"]),
    )


def _shipment_from_rest(data: dict) -> ShipmentView:
    """Maps shipping-service's `ShipmentOut` REST JSON onto `ShipmentView` --
    `{id, orderId, address, status, createdAt}`."""
    return ShipmentView(
        id=strawberry.ID(str(data["id"])),
        order_id=strawberry.ID(str(data["orderId"])),
        address=data["address"],
        status=data["status"],
        created_at=str(data["createdAt"]),
    )


def _review_from_rest(data: dict) -> ReviewView:
    """Maps review-service's `ReviewOut` REST JSON onto `ReviewView` --
    `{id, customerId, sku, rating, comment, createdAt}`."""
    return ReviewView(
        id=strawberry.ID(str(data["id"])),
        customer_id=strawberry.ID(str(data["customerId"])),
        sku=data["sku"],
        rating=data["rating"],
        comment=data.get("comment"),
        created_at=str(data["createdAt"]),
    )


def _stock_from_grpc(data: dict) -> StockView:
    """Maps `app/clients.py::fetch_stock`'s translated `StockReply` dict onto
    `StockView`."""
    return StockView(
        sku=data["sku"],
        display_name=data["display_name"],
        unit_price_cents=data["unit_price_cents"],
        on_hand_qty=data["on_hand_qty"],
        available=data["available"],
    )


@strawberry.type
class Query:
    @strawberry.field
    async def order(self, info: strawberry.Info, id: strawberry.ID) -> OrderView | None:
        """Fetch a single order by id. `None` for an unknown id (order-
        service 404s) -- every nested field (`items`, and federated
        `payments`/`shipments`/per-item `stock`/`reviews`) is resolved only
        once a client's selection set asks for it."""
        settings = info.context["settings"]
        data = await fetch_order(settings, str(id))
        return _order_from_rest(data) if data is not None else None


def build_schema(settings: Settings) -> strawberry.Schema:
    """Builds the gateway's schema with operator-configured depth/complexity
    extensions (DRQ-069 analog, see `app/config.py`'s module docstring): a
    query deeper than `settings.max_query_depth`, or whose total parsed token
    count exceeds `settings.max_query_tokens`, is rejected at validation time
    with a GraphQL `errors[]` entry -- it never reaches a resolver at all.
    Taking `settings` as a parameter (rather than reading a module-level
    singleton) is what lets the test suite build a schema with a
    deliberately tiny budget to prove the limiter is actually wired."""
    max_depth = settings.max_query_depth
    max_tokens = settings.max_query_tokens
    return strawberry.Schema(
        query=Query,
        # Factory callables, not instances -- a fresh extension per request,
        # the non-deprecated form (passing instances directly is deprecated
        # as of strawberry-graphql 0.335: an instance would be shared/reused
        # across requests instead of constructed fresh for each one).
        extensions=[
            lambda: QueryDepthLimiter(max_depth=max_depth),
            lambda: MaxTokensLimiter(max_token_count=max_tokens),
        ],
    )
