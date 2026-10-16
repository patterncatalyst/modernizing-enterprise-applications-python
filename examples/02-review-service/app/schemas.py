"""Pydantic v2 request/response models -- the FastAPI sibling of the
monolith's camelCase DRF serializers (`review/serializers.py`). Every field
maps explicitly via `Field(alias=...)`, same convention as the monolith's
`source=` mapping: don't reach for a camelCase-rename middleware, the
explicit per-field alias is the point (it's what a reader greps to find the
wire contract).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    """`POST /api/reviews` request body. Matches
    `review.serializers.ReviewCreateSerializer` field-for-field, including
    the `rating` 1..5 bound (DRF's `min_value=1, max_value=5` ->
    `ge=1, le=5`)."""

    customer_id: int = Field(alias="customerId")
    sku: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None)


class ReviewOut(BaseModel):
    """`GET /api/reviews`, `GET /api/reviews/{id}`, and the `POST` echo.
    Matches `review.serializers.ReviewSerializer`'s field list exactly:
    `id, customerId, sku, rating, comment, createdAt`."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    customer_id: int = Field(alias="customerId")
    sku: str
    rating: int
    comment: str
    created_at: datetime = Field(alias="createdAt")
