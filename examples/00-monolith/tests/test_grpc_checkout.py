"""Unit-level coverage for `settings.INVENTORY_MODE = "grpc"` in
order.services.place_order() -- r04/ch.19. No live gRPC server is needed:
order.inventory_client.RemoteInventoryClient is monkeypatched with an
in-memory fake so the Reserve/Release call ORDERING (the compensation
contract, SMELL[ch.22]'s cure) can be asserted directly, independent of
examples/04-inventory-service (a different lane) actually running."""

import pytest

from common.exceptions import InsufficientStock, PaymentDeclined
from order import inventory_client, services

pytestmark = pytest.mark.django_db


class FakeRemoteInventoryClient:
    """In-memory stand-in for order.inventory_client.RemoteInventoryClient --
    records every Reserve/Release call (in order) so the compensation tests
    below can assert on them directly."""

    def __init__(self, stock: dict):
        self._stock = stock
        self.reserve_calls: list[tuple[str, int]] = []
        self.release_calls: list[tuple[str, int]] = []
        self.closed = False

    def reserve(self, sku: str, quantity: int) -> inventory_client.ReserveResult:
        self.reserve_calls.append((sku, quantity))
        item = self._stock.get(sku)
        on_hand = item["on_hand"] if item else 0
        if item is None or on_hand < quantity:
            raise InsufficientStock(f"Requested {quantity} of {sku} but only {on_hand} on hand")
        item["on_hand"] -= quantity
        return inventory_client.ReserveResult(
            sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"]
        )

    def get_stock(self, sku: str) -> inventory_client.StockSnapshot:
        item = self._stock[sku]
        return inventory_client.StockSnapshot(
            sku=sku,
            name=item["name"],
            unit_price_cents=item["price_cents"],
            on_hand_qty=item["on_hand"],
            available=item["on_hand"] > 0,
        )

    def release(self, sku: str, quantity: int) -> inventory_client.ReserveResult:
        self.release_calls.append((sku, quantity))
        item = self._stock.setdefault(sku, {"name": sku, "price_cents": 0, "on_hand": 0})
        item["on_hand"] += quantity
        return inventory_client.ReserveResult(
            sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"]
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def grpc_mode(settings):
    settings.INVENTORY_MODE = "grpc"
    return settings


def _patch_client(monkeypatch, fake_client):
    monkeypatch.setattr(inventory_client, "RemoteInventoryClient", lambda: fake_client)


def test_grpc_happy_path_confirms_order_with_snapshot_fields(grpc_mode, monkeypatch, customer):
    stock = {"SKU-A": {"name": "Widget A", "price_cents": 1500, "on_hand": 10}}
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    order = services.place_order(
        customer_id=customer.id,
        items=[{"sku": "SKU-A", "quantity": 2}],
        payment_method="CARD-VISA",
        shipping_address="1 Analytical Engine Way",
    )

    assert order.status == "CONFIRMED"
    assert order.total_cents == 3000
    item = order.items.get()
    assert item.sku == "SKU-A"
    assert item.item_name == "Widget A"
    assert item.unit_price_cents == 1500
    assert fake_client.reserve_calls == [("SKU-A", 2)]
    assert not fake_client.release_calls
    assert fake_client.closed


def test_grpc_payment_declined_releases_every_reserved_line(grpc_mode, monkeypatch, customer):
    """The crux case (ch.19): a payment decline happens AFTER both lines
    reserved successfully over gRPC -- SMELL[ch.22]'s single shared
    transaction can no longer roll the remote reservations back for free, so
    place_order() must issue a compensating Release for EVERY line it
    reserved this checkout, one call per line."""
    stock = {
        "SKU-A": {"name": "Widget A", "price_cents": 1000, "on_hand": 10},
        "SKU-B": {"name": "Widget B", "price_cents": 2000, "on_hand": 10},
    }
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(PaymentDeclined):
        services.place_order(
            customer_id=customer.id,
            items=[{"sku": "SKU-A", "quantity": 1}, {"sku": "SKU-B", "quantity": 2}],
            payment_method="CARD-DECLINE",
            shipping_address="1 Analytical Engine Way",
        )

    assert fake_client.reserve_calls == [("SKU-A", 1), ("SKU-B", 2)]
    assert sorted(fake_client.release_calls) == [("SKU-A", 1), ("SKU-B", 2)]
    assert fake_client.closed
    # Net-zero: no Order row left behind by the rolled-back atomic() block.
    from order.models import Order

    assert not Order.objects.filter(customer=customer).exists()


def test_grpc_insufficient_line_releases_prior_reservations(grpc_mode, monkeypatch, customer):
    """A LATER line's insufficient stock must compensate every EARLIER line
    already reserved this same checkout -- and only those, nothing more."""
    stock = {
        "SKU-A": {"name": "Widget A", "price_cents": 1000, "on_hand": 10},
        "SKU-B": {"name": "Widget B", "price_cents": 2000, "on_hand": 1},
    }
    fake_client = FakeRemoteInventoryClient(stock)
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(InsufficientStock):
        services.place_order(
            customer_id=customer.id,
            items=[{"sku": "SKU-A", "quantity": 1}, {"sku": "SKU-B", "quantity": 5}],
            payment_method="CARD-VISA",
            shipping_address="1 Analytical Engine Way",
        )

    assert fake_client.reserve_calls == [("SKU-A", 1), ("SKU-B", 5)]
    assert fake_client.release_calls == [("SKU-A", 1)]
    assert fake_client.closed
