"""`/api/notifications` endpoint -- the FastAPI sibling of the monolith's
`notification/views.py::NotificationListView`.

Route shape matches the monolith byte-for-byte: no trailing slash, required
`?customerId=` query parameter. FastAPI's `Query(...)` (no default) makes the
parameter required, so a request without it raises `RequestValidationError`
-- remapped by `app/errors.py` to `400 VALIDATION_FAILED`, the same status
and error code DRF's `ValidationError` produces for the monolith's own
`if customer_id is None: raise ValidationError(...)` check. There is no auth
gate here (contrast with review-service's `POST /api/reviews`): this
service's only HTTP surface is a read, and the monolith's
`NotificationListView` requires none either.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.db import get_session
from app.schemas import NotificationOut

router = APIRouter()


@router.get("/api/notifications", response_model=list[NotificationOut])
async def list_notifications(
    customerId: int = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[NotificationOut]:
    rows = await repository.list_by_customer_id(session, customerId)
    return [NotificationOut.model_validate(row) for row in rows]
