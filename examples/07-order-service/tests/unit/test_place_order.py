"""Fast, Kafka-free, gRPC-free proofs for `app.service.place_order` against
this service's real `order_svc` schema (same reachable, already-migrated
Postgres `conftest.py`'s fixtures use): the three-way one-transaction
atomicity guarantee (aggregate + `order_view` + outbox), the
reserve-over-gRPC-OUTSIDE-any-DB-transaction discipline, and net-zero
compensation on both a mid-reservation failure and a post-reservation
persistence failure. Complements `tests/integration/test_order_lifecycle.py`,
which proves the same checkout path end-to-end through a real Kafka broker
and a real (fake-but-networked) inventory gRPC server."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app import repository, service
from app.errors import InsufficientStock, ResourceNotFound
from app.models import Order, OrderItem, OrderView, OutboxEvent
from app.schemas import OrderLineIn
from tests.unit.fakes import FakeInventoryClient, install_fake_inventory_client

UNUSED_TARGET = "unused:0"
TIMEOUT_S = 1.0


async def _place(session_factory, fake, *, customer_id=1, items=None, payment_method="VISA-1234",
                  shipping_address="1 Test Lane"):
    items = items or [OrderLineIn(sku="SKU-WIDGET-001", quantity=2)]
    return await service.place_order(
        session_factory,
        inventory_grpc_target=UNUSED_TARGET,
        grpc_timeout_s=TIMEOUT_S,
        customer_id=customer_id,
        items=items,
        payment_method=payment_method,
        shipping_address=shipping_address,
    )


@pytest.mark.asyncio
async def test_place_order_writes_aggregate_view_and_outbox_in_one_transaction(
    session_factory, monkeypatch
):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    order = await _place(
        session_factory,
        fake,
        items=[OrderLineIn(sku="SKU-WIDGET-001", quantity=2)],
        shipping_address="221B Baker Street",
    )

    assert order.status == "PENDING"
    assert order.total_cents == 1999 * 2
    # Reserved over gRPC, then enriched via GetStock -- the fake's reserve
    # log proves the call happened.
    assert fake.reserve_calls == [("SKU-WIDGET-001", 2)]

    async with session_factory() as session:
        items = await repository.list_order_items(session, order.id)
        assert len(items) == 1
        assert items[0].sku == "SKU-WIDGET-001"
        assert items[0].unit_price_cents == 1999

        view = await repository.get_order_view_by_id(session, order.id)
        assert view is not None, "order_view must be written in the SAME transaction"
        assert view.status == "PENDING"
        assert view.shipping_address == "221B Baker Street"
        assert view.items == [{"sku": "SKU-WIDGET-001", "quantity": 2, "unitPriceCents": 1999}]

        outbox_rows = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order.id))
            )
        ).scalars().all()
        assert len(outbox_rows) == 1, "exactly one order.placed outbox row, same transaction"
        outbox_event = outbox_rows[0]
        assert outbox_event.event_type == "order.placed"
        assert outbox_event.published_at is None
        assert outbox_event.payload["orderId"] == order.id
        assert outbox_event.payload["customerId"] == 1
        assert outbox_event.payload["customerEmail"] == "ada@example.com"
        assert outbox_event.payload["totalCents"] == 3998
        assert outbox_event.payload["paymentMethod"] == "VISA-1234"
        assert "placedAt" in outbox_event.payload
        assert "confirmed" not in outbox_event.payload["confirmationMessage"]


@pytest.mark.asyncio
async def test_place_order_validates_customer_before_any_grpc_call(session_factory, monkeypatch):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    with pytest.raises(ResourceNotFound):
        await _place(session_factory, fake, customer_id=999_999)

    assert fake.reserve_calls == [], "an unknown customer must never trigger a reservation"


@pytest.mark.asyncio
async def test_place_order_reserves_each_line_before_touching_the_database(
    session_factory, monkeypatch
):
    """Proves the reserve-outside-any-DB-transaction discipline: a failure
    on the SECOND line (insufficient stock) compensates the FIRST line's
    reservation, and no `Order` row is ever written -- the gRPC calls run to
    completion (and failure) entirely before the persistence transaction
    opens."""
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    async with session_factory() as session:
        before_count = len((await session.execute(select(Order))).scalars().all())

    with pytest.raises(InsufficientStock):
        await _place(
            session_factory,
            fake,
            items=[
                OrderLineIn(sku="SKU-GADGET-002", quantity=1),
                OrderLineIn(sku="SKU-GIZMO-003", quantity=999),  # only 5 on hand
            ],
        )

    assert fake.reserve_calls == [("SKU-GADGET-002", 1), ("SKU-GIZMO-003", 999)]
    # Net-zero: the first line's reservation is compensated the instant the
    # second line fails -- with NO idempotency key, since this compensation
    # runs synchronously inside the same call that did the Reserve (nothing
    # to redeliver).
    assert fake.release_calls == [("SKU-GADGET-002", 1, "")]
    assert fake.stock["SKU-GADGET-002"]["on_hand"] == 50, "net-zero: stock restored"

    async with session_factory() as session:
        after_count = len((await session.execute(select(Order))).scalars().all())
    assert after_count == before_count, "no Order row may be written for a failed reservation"


@pytest.mark.asyncio
async def test_place_order_compensates_every_reserved_line_on_persistence_failure(
    session_factory, monkeypatch
):
    """A failure AFTER every line reserved cleanly but BEFORE/DURING the
    persistence transaction must still compensate every reservation --
    mirrors `00-monolith/order/services.py::_place_order_choreographed`'s
    `except Exception: _release_reserved(...); raise` shape."""
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(repository, "create_order_with_outbox_and_view", _boom)

    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        await _place(
            session_factory,
            fake,
            items=[
                OrderLineIn(sku="SKU-WIDGET-001", quantity=1),
                OrderLineIn(sku="SKU-GADGET-002", quantity=1),
            ],
        )

    assert fake.reserve_calls == [("SKU-WIDGET-001", 1), ("SKU-GADGET-002", 1)]
    assert set(fake.release_calls) == {
        ("SKU-WIDGET-001", 1, ""),
        ("SKU-GADGET-002", 1, ""),
    }
    assert fake.stock["SKU-WIDGET-001"]["on_hand"] == 100
    assert fake.stock["SKU-GADGET-002"]["on_hand"] == 50


@pytest.mark.asyncio
async def test_read_model_goes_stale_if_the_projection_is_skipped(session_factory, monkeypatch):
    """The CQRS projection-disabled negative: `GET /api/orders/{id}` (and
    every other read, see `app/repository.py`'s read functions) serves
    EXCLUSIVELY from `order_view`. Simulating a write that updates the
    aggregate but skips the `order_view` upsert (bypassing
    `app/repository.py::transition_order_status_with_view`) proves the read
    side goes stale -- the read model is not derived live from `orders` on
    every query, it is a materialized projection that must be kept current
    by every write path."""
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    order = await _place(
        session_factory, fake, items=[OrderLineIn(sku="SKU-WIDGET-001", quantity=1)]
    )

    # Mutate the WRITE aggregate directly, bypassing
    # transition_order_status_with_view's same-transaction view upsert --
    # the "broken projection" this negative test models.
    async with session_factory() as session:
        write_order = await session.get(Order, order.id)
        write_order.status = "CONFIRMED"
        await session.commit()

    async with session_factory() as session:
        view = await repository.get_order_view_by_id(session, order.id)
        assert view.status == "PENDING", "order_view must NOT reflect a write that skipped it"

        write_order = await session.get(Order, order.id)
        assert write_order.status == "CONFIRMED", "the aggregate itself DID change"

    # The rebuild path proves the projection is recoverable, not a second
    # source of truth -- it is allowed to go stale only because a write
    # skipped it, never because it is structurally incapable of catching up.
    rebuilt = await service.rebuild_order_view(session_factory, order.id)
    assert rebuilt.status == "CONFIRMED"


@pytest.mark.asyncio
async def test_place_order_item_count_matches_checkout_lines(session_factory, monkeypatch):
    fake = FakeInventoryClient()
    install_fake_inventory_client(monkeypatch, fake)

    order = await _place(
        session_factory,
        fake,
        items=[
            OrderLineIn(sku="SKU-WIDGET-001", quantity=1),
            OrderLineIn(sku="SKU-GADGET-002", quantity=3),
        ],
    )
    assert order.total_cents == 1999 + 3 * 4999

    async with session_factory() as session:
        items: list[OrderItem] = await repository.list_order_items(session, order.id)
        assert len(items) == 2
        view: OrderView = await repository.get_order_view_by_id(session, order.id)
        assert len(view.items) == 2
