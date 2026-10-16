"""Pydantic v2 models -- the FastAPI sibling of the monolith's camelCase DRF
`ShipmentSerializer` (`00-monolith/shipping/serializers.py`), plus this
service's own copy of the frozen `payment.captured` Kafka event payload
(the saga's trigger). Every field maps explicitly via `Field(alias=...)`,
same convention as every other standalone service's `app/schemas.py` in this
project.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShipmentOut(BaseModel):
    """`GET /api/shipments` / `GET /api/shipments/{id}` response. Matches
    `shipping.serializers.ShipmentSerializer`'s field list exactly:
    `id, orderId, address, status, createdAt`."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    order_id: int = Field(alias="orderId")
    address: str
    status: str
    created_at: datetime = Field(alias="createdAt")


class PaymentCapturedEvent(BaseModel):
    """This service's own copy of the frozen `payment.captured` JSON payload
    (`05-payment-service/EVENTS.md`): topic `payment.captured`, key =
    `orderId` (string). Field names and types match the producer side
    byte-for-byte so Pydantic round-trips the JSON value without any custom
    deserializer. There is no shared module between payment-service and this
    service (each is an independently deployable project) -- this
    duplication is the honest cost of a hand-maintained JSON wire contract
    with no schema registry until ch.28/Apicurio, same as every other
    event-consuming service in this project.

    This event is the saga's TRIGGER (`app/consumer.py` ->
    `app/service.py::handle_payment_captured`) -- it carries no shipping
    address of its own; the saga's `enrich` step (`app/steps.py`) fetches
    that separately from the monolith's `GET /api/orders/{orderId}`.
    """

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    payment_id: int = Field(alias="paymentId")
    amount_cents: int = Field(alias="amountCents")
    method: str
    status: str
    occurred_at: datetime = Field(alias="occurredAt")
