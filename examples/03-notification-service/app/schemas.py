"""Pydantic v2 models -- the FastAPI sibling of the monolith's camelCase DRF
`NotificationSerializer`, plus this service's own copy of the frozen
`order.placed` Kafka event payload (STEP 0 of the r03 build). Every field
maps explicitly via `Field(alias=...)`, same convention as
`02-review-service`'s `app/schemas.py` and the monolith's `source=` mapping.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    """`GET /api/notifications` response. Matches
    `notification.serializers.NotificationSerializer`'s field list exactly:
    `id, customerId, orderId, channel, message, sentAt`."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    customer_id: int = Field(alias="customerId")
    order_id: int | None = Field(alias="orderId")
    channel: str
    message: str
    sent_at: datetime = Field(alias="sentAt")


class OrderPlacedEvent(BaseModel):
    """This service's own copy of the frozen `order.placed` JSON payload
    (STEP 0 contract): topic `order.placed`, key = `orderId` (string).
    Field names and types match the producer side byte-for-byte so Pydantic
    round-trips the JSON value without any custom deserializer. There is no
    shared module between the monolith and this service (each is an
    independently deployable project) -- this duplication is the honest cost
    of a hand-maintained JSON wire contract with no schema registry until
    ch.28/Apicurio (DRQ-036)."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
