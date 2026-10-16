"""`/api/reviews` endpoints -- the FastAPI sibling of `review/views.py`.

Route shapes match the monolith byte-for-byte: no trailing slash, `?sku=`
optional filter on the list route, `POST` gated by HTTP Basic auth via
`app.auth.require_basic_auth` (wired per-route, not globally -- GET stays
open, same per-view gating story as the monolith's `get_permissions()`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.auth import require_basic_auth
from app.db import get_session
from app.errors import ResourceNotFound
from app.schemas import ReviewCreate, ReviewOut

router = APIRouter()


@router.get("/api/reviews", response_model=list[ReviewOut])
async def list_reviews(
    sku: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[ReviewOut]:
    rows = await repository.list_reviews(session, sku=sku)
    return [ReviewOut.model_validate(row) for row in rows]


@router.get("/api/reviews/{review_id}", response_model=ReviewOut)
async def get_review(
    review_id: int,
    session: AsyncSession = Depends(get_session),
) -> ReviewOut:
    row = await repository.get_review_by_id(session, review_id)
    if row is None:
        raise ResourceNotFound(f"No review with id {review_id}")
    return ReviewOut.model_validate(row)


@router.post("/api/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    payload: ReviewCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _authenticated_username: str = Depends(require_basic_auth),
) -> ReviewOut:
    customer = await repository.get_customer_by_id(session, payload.customer_id)
    if customer is None:
        raise ResourceNotFound(f"No customer with id {payload.customer_id}")

    item = await repository.get_inventory_item_by_sku(session, payload.sku)
    if item is None:
        raise ResourceNotFound(f"No inventory item with sku {payload.sku}")

    review = await repository.create_review(
        session,
        customer_id=payload.customer_id,
        inventory_item_id=item.id,
        rating=payload.rating,
        comment=payload.comment or "",
    )

    # Matches the monolith's `headers={"Location": f"/api/reviews/{review.id}"}`
    # exactly -- a relative path, not an absolute URL.
    response.headers["Location"] = f"/api/reviews/{review.id}"

    return ReviewOut(
        id=review.id,
        customerId=review.customer_id,
        sku=item.sku,
        rating=review.rating,
        comment=review.comment,
        createdAt=review.created_at,
    )
