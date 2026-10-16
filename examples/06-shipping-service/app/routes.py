"""`/api/shipments` endpoints -- the FastAPI sibling of the monolith's
`shipping/views.py` (`ShipmentListView`/`ShipmentDetailView`, reached via
`shipping/urls.py`).

Route shapes match the monolith byte-for-byte: no trailing slash, required
`?orderId=` query parameter on the list route, `{id}` path parameter on the
detail route, response body `{id, orderId, address, status, createdAt}`
(`app/schemas.py::ShipmentOut`, matching `shipping.serializers.ShipmentSerializer`
field-for-field). There is no write endpoint here: this service's only write
path is the orchestrated saga (`app/consumer.py` -> `app/service.py` ->
`app/orchestrator.py`) -- shipments are a consequence of the saga, never
created via a direct API call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.db import get_session
from app.errors import ResourceNotFound
from app.schemas import ShipmentOut

router = APIRouter()


@router.get("/api/shipments", response_model=list[ShipmentOut])
async def list_shipments(
    orderId: int = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ShipmentOut]:
    rows = await repository.list_shipments_by_order_id(session, orderId)
    return [ShipmentOut.model_validate(row) for row in rows]


@router.get("/api/shipments/{shipment_id}", response_model=ShipmentOut)
async def get_shipment(
    shipment_id: int,
    session: AsyncSession = Depends(get_session),
) -> ShipmentOut:
    row = await repository.get_shipment_by_id(session, shipment_id)
    if row is None:
        raise ResourceNotFound(f"No shipment with id {shipment_id}")
    return ShipmentOut.model_validate(row)
