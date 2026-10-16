"""Read-path business logic -- the FastAPI sibling of the monolith's
`inventory/services.py`. The mutating `reserve`/`release` concern
deliberately does NOT live here: it stays server-side on the gRPC path
(`app/grpc_server.py`), calling `app/repository.py` directly, not a
REST-surface concern -- same split the Java sibling's `InventoryService`
(read-only) vs. `InventoryGrpcServiceImpl` (mutating) makes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.errors import ResourceNotFound
from app.models import InventoryItem


async def list_all(session: AsyncSession) -> list[InventoryItem]:
    return await repository.list_all(session)


async def get_by_sku(session: AsyncSession, sku: str) -> InventoryItem:
    item = await repository.get_by_sku(session, sku)
    if item is None:
        raise ResourceNotFound(f"No inventory item with sku {sku}")
    return item
