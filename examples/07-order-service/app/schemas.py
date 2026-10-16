"""Pydantic v2 models -- camelCase wire contracts, the FastAPI sibling of
`00-monolith/order/serializers.py`'s `OrderCreateSerializer`/`OrderSerializer`,
plus this service's own copies of the FOUR consumed saga-outcome event shapes
(`payment.captured`/`payment.declined`/`shipment.dispatched`/
`shipment.failed`) and the ONE produced `order.placed` shape. Every field
maps explicitly via `Field(alias=...)`, same convention as every other
standalone service's `app/schemas.py` in this project -- there is no shared
schema module between order-service and payment-/shipping-service (or the
monolith); each side hand-authors a structurally identical copy, the honest
cost of a hand-maintained JSON wire contract with no schema registry until
ch.28/Apicurio.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.models import OrderView


class OrderLineIn(BaseModel):
    """One checkout line -- `{sku, quantity}`, matching the monolith's
    `OrderLineSerializer` byte-for-byte."""

    sku: str
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    """`POST /api/orders` request body -- matches
    `00-monolith/order/serializers.py::OrderCreateSerializer`'s field list
    exactly: `customerId, items, paymentMethod, shippingAddress`."""

    model_config = ConfigDict(populate_by_name=True)

    customer_id: int = Field(alias="customerId")
    items: list[OrderLineIn] = Field(min_length=1)
    payment_method: str = Field(alias="paymentMethod")
    shipping_address: str = Field(alias="shippingAddress")


class OrderItemOut(BaseModel):
    """One line of the `GET /api/orders[/{id}]` response -- matches
    `OrderItemSerializer`'s field list exactly: `sku, quantity,
    unitPriceCents`. Served from `order_view.items`' denormalized JSON, never
    from `order_items` directly -- see `app/models.py::OrderView`."""

    model_config = ConfigDict(populate_by_name=True)

    sku: str
    quantity: int
    unit_price_cents: int = Field(alias="unitPriceCents")


class OrderOut(BaseModel):
    """`GET /api/orders/{id}` / `GET /api/orders` response -- matches
    `00-monolith/order/serializers.py::OrderSerializer`'s field list exactly:
    `id, customerId, status, totalCents, createdAt, shippingAddress, items`.
    Built from `order_view` rows (`app/repository.py`'s read functions),
    never from the `orders`/`order_items` write tables -- the CQRS read-side
    contract this lane's acceptance criteria calls out directly."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    customer_id: int = Field(alias="customerId")
    status: str
    total_cents: int = Field(alias="totalCents")
    created_at: datetime = Field(alias="createdAt")
    shipping_address: str = Field(alias="shippingAddress")
    items: list[OrderItemOut]


def order_view_to_out(view: OrderView) -> OrderOut:
    """Converts an `app/models.py::OrderView` row into the wire contract --
    the ONE place that bridges the read-model's column names (`order_id`)
    onto `OrderOut`'s frozen field names (`id`). `view.items` is already
    stored camelCase (`app/repository.py::_item_view_payload`), so each
    element validates directly against `OrderItemOut`'s alias."""
    return OrderOut(
        id=view.order_id,
        customerId=view.customer_id,
        status=view.status,
        totalCents=view.total_cents,
        createdAt=view.created_at,
        shippingAddress=view.shipping_address,
        items=[OrderItemOut(**item) for item in view.items],
    )


# ---------------------------------------------------------------------------
# Consumed saga-outcome events -- the FROZEN contracts this service's four
# reactions (`app/service.py::handle_payment_captured`/`handle_payment_declined`/
# `handle_shipment_dispatched`/`handle_shipment_failed`) react to, the exact
# same four topics `00-monolith/order/management/commands/order_saga_listener.py`
# subscribes to in one consumer group.
# ---------------------------------------------------------------------------


class PaymentCapturedEvent(BaseModel):
    """`payment.captured` -- published by `05-payment-service`'s own outbox
    relay (see `../05-payment-service/EVENTS.md`)."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    payment_id: int = Field(alias="paymentId")
    amount_cents: int = Field(alias="amountCents")
    method: str
    status: str
    reason: str | None = None
    occurred_at: datetime = Field(alias="occurredAt")


class PaymentDeclinedEvent(BaseModel):
    """`payment.declined` -- published by `05-payment-service`'s own outbox
    relay."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    payment_id: int = Field(alias="paymentId")
    amount_cents: int = Field(alias="amountCents")
    method: str
    status: str
    reason: str | None = None
    occurred_at: datetime = Field(alias="occurredAt")


class ShipmentDispatchedEvent(BaseModel):
    """`shipment.dispatched` -- published by `06-shipping-service`'s own
    outbox relay (see `../06-shipping-service/EVENTS.md`)."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    shipment_id: int | None = Field(default=None, alias="shipmentId")
    address: str | None = None
    status: str
    reason: str | None = None
    occurred_at: datetime = Field(alias="occurredAt")


class ShipmentFailedEvent(BaseModel):
    """`shipment.failed` -- published by `06-shipping-service`'s own outbox
    relay."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    shipment_id: int | None = Field(default=None, alias="shipmentId")
    address: str | None = None
    status: str
    reason: str | None = None
    occurred_at: datetime = Field(alias="occurredAt")


class OrderPlacedEvent(BaseModel):
    """`order.placed` -- THIS service's own produced event (own outbox +
    relay, see `app/relay.py`), the frozen contract every downstream
    consumer (payment-/notification-service) already reacts to:
    `{orderId, customerId, customerEmail, totalCents, confirmationMessage,
    placedAt, paymentMethod}`. Used by `app/service.py` to build the outbox
    payload and by the test suite to validate it round-trips."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
    payment_method: str = Field(alias="paymentMethod")
