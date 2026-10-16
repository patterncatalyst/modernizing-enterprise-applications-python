"""`/api/orders` endpoints -- the FastAPI sibling of
`00-monolith/order/views.py`. READS are served from `order_view` exclusively
(`app/repository.py`'s read functions) -- this router never touches
`orders`/`order_items` directly, the CQRS read-side contract this lane's
acceptance criteria calls out.

`POST /api/orders` returns **202 Accepted** with a `Location` header,
status `PENDING` -- this service's checkout is ALWAYS the choreographed/
orchestrated flavor (see `app/service.py::place_order`'s docstring); there is
no synchronous, in-process confirm-in-one-request path left to return `201`
for.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app import repository, service
from app.config import Settings
from app.errors import ResourceNotFound
from app.schemas import OrderCreate, OrderOut, order_view_to_out

router = APIRouter()


@router.post("/api/orders", status_code=202, response_model=OrderOut)
async def create_order(payload: OrderCreate, request: Request, response: Response) -> OrderOut:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    order = await service.place_order(
        session_factory,
        inventory_grpc_target=settings.inventory_grpc_target,
        grpc_timeout_s=settings.grpc_timeout_s,
        customer_id=payload.customer_id,
        items=payload.items,
        payment_method=payload.payment_method,
        shipping_address=payload.shipping_address,
    )

    response.headers["Location"] = f"/api/orders/{order.id}"

    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
    assert view is not None, "order_view must exist in the SAME transaction as the aggregate"
    return order_view_to_out(view)


@router.get("/api/orders", response_model=list[OrderOut])
async def list_orders(request: Request) -> list[OrderOut]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        views = await repository.list_order_views(session)
    return [order_view_to_out(view) for view in views]


@router.get("/api/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, request: Request) -> OrderOut:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order_id)
    if view is None:
        raise ResourceNotFound(f"No order with id {order_id}")
    return order_view_to_out(view)
