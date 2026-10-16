"""`/api/payments` endpoints -- the FastAPI sibling of the monolith's
`payment/views.py` (`PaymentListView`/`PaymentDetailView`).

Route shapes match the monolith byte-for-byte: no trailing slash, required
`?orderId=` query parameter on the list route, `{id}` path parameter on the
detail route. There is no write endpoint here: this service's only write
path is the `order.placed` consumer (`app/consumer.py`) -- payments are a
consequence of choreography, never created via a direct API call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.db import get_session
from app.errors import ResourceNotFound
from app.schemas import PaymentOut

router = APIRouter()


@router.get("/api/payments", response_model=list[PaymentOut])
async def list_payments(
    orderId: int = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    rows = await repository.list_by_order_id(session, orderId)
    return [PaymentOut.model_validate(row) for row in rows]


@router.get("/api/payments/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_session),
) -> PaymentOut:
    row = await repository.get_by_id(session, payment_id)
    if row is None:
        raise ResourceNotFound(f"No payment with id {payment_id}")
    return PaymentOut.model_validate(row)
