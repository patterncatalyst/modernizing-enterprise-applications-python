"""Pydantic v2 models -- the FastAPI sibling of the monolith's camelCase DRF
`InventoryItemSerializer`. Every field maps explicitly via `Field(alias=...)`,
same convention as `02-review-service`/`03-notification-service`'s
`app/schemas.py` and the monolith's `source=` mapping.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StockOut(BaseModel):
    """`GET /api/inventory` / `GET /api/inventory/{sku}` response. Matches
    `inventory.serializers.InventoryItemSerializer`'s field list exactly:
    `sku, name, priceCents, quantityOnHand`."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    sku: str
    name: str
    price_cents: int = Field(alias="priceCents")
    quantity_on_hand: int = Field(alias="quantityOnHand")
