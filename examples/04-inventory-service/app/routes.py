"""`/api/inventory` endpoints -- the FastAPI sibling of the monolith's
`inventory/views.py::InventoryListView`/`InventoryDetailView`.

Route shapes match the monolith byte-for-byte: no trailing slash, no query
params, a 404 (uniform error body) for an unknown sku.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import service
from app.db import get_session
from app.schemas import StockOut

router = APIRouter()


@router.get("/api/inventory", response_model=list[StockOut])
async def list_inventory(
    session: AsyncSession = Depends(get_session),
) -> list[StockOut]:
    rows = await service.list_all(session)
    return [StockOut.model_validate(row) for row in rows]


@router.get("/api/inventory/{sku}", response_model=StockOut)
async def get_inventory_item(
    sku: str,
    session: AsyncSession = Depends(get_session),
) -> StockOut:
    item = await service.get_by_sku(session, sku)
    return StockOut.model_validate(item)
