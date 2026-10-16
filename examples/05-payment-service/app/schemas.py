"""Pydantic v2 models -- the FastAPI sibling of the monolith's camelCase DRF
`PaymentSerializer` (`00-monolith/payment/serializers.py`), plus this
service's own copy of the frozen `order.placed` Kafka event payload. Every
field maps explicitly via `Field(alias=...)`, same convention as
`03-notification-service`'s `app/schemas.py` and the monolith's `source=`
mapping.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PaymentOut(BaseModel):
    """`GET /api/payments` / `GET /api/payments/{id}` response. Matches
    `payment.serializers.PaymentSerializer`'s field list exactly:
    `id, orderId, amountCents, method, status, createdAt`."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    order_id: int = Field(alias="orderId")
    amount_cents: int = Field(alias="amountCents")
    method: str
    status: str
    created_at: datetime = Field(alias="createdAt")


class OrderPlacedEvent(BaseModel):
    """This service's own copy of the frozen `order.placed` JSON payload:
    topic `order.placed`, key = `orderId` (string). Field names and types
    match the producer side byte-for-byte so Pydantic round-trips the JSON
    value without any custom deserializer. There is no shared module between
    the monolith and this service (each is an independently deployable
    project) -- this duplication is the honest cost of a hand-maintained
    JSON wire contract with no schema registry until ch.28/Apicurio.

    `payment_method` is OPTIONAL and net-new in r05 (the monolith's order
    context does not populate it as of this extraction) -- an event with no
    `paymentMethod` field, or an explicit `null`, is a non-DECLINE method as
    far as `app/service.py::charge` is concerned: CAPTURE, never crash. See
    `EVENTS.md` for the full contract.
    """

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
    payment_method: str | None = Field(default=None, alias="paymentMethod")
