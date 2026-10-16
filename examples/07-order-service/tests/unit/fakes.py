"""`FakeInventoryClient` -- a Kafka-free, gRPC-free test double for
`app.inventory_client.AsyncInventoryClient`, used by every unit test that
exercises `app.service.place_order`/the four saga reactions without a real
inventory-service process. Mirrors the real client's public async
context-manager shape (`reserve`/`release`/`get_stock`) and in-memory stock
levels seeded to match `04-inventory-service`'s own demo seed
(`SKU-WIDGET-001`/`SKU-GADGET-002`/`SKU-GIZMO-003`), so test data lines up
with the rest of this project's demo dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.errors import InsufficientStock, InventoryServiceUnavailable
from app.inventory_client import ReserveResult, StockSnapshot

DEFAULT_STOCK = {
    "SKU-WIDGET-001": {"name": "Standard Widget", "unit_price_cents": 1999, "on_hand": 100},
    "SKU-GADGET-002": {"name": "Deluxe Gadget", "unit_price_cents": 4999, "on_hand": 50},
    "SKU-GIZMO-003": {"name": "Pocket Gizmo", "unit_price_cents": 999, "on_hand": 5},
}


@dataclass
class FakeInventoryClient:
    stock: dict[str, dict] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_STOCK.items()}
    )
    unavailable: bool = False
    reserve_calls: list[tuple[str, int]] = field(default_factory=list)
    release_calls: list[tuple[str, int, str]] = field(default_factory=list)

    async def __aenter__(self) -> FakeInventoryClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def reserve(self, sku: str, quantity: int) -> ReserveResult:
        self.reserve_calls.append((sku, quantity))
        if self.unavailable:
            raise InventoryServiceUnavailable("fake inventory-service unavailable")
        item = self.stock.get(sku)
        if item is None or item["on_hand"] < quantity:
            on_hand = item["on_hand"] if item else 0
            raise InsufficientStock(f"Requested {quantity} of {sku} but only {on_hand} on hand")
        item["on_hand"] -= quantity
        return ReserveResult(sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"])

    async def get_stock(self, sku: str) -> StockSnapshot:
        item = self.stock[sku]
        return StockSnapshot(
            sku=sku,
            name=item["name"],
            unit_price_cents=item["unit_price_cents"],
            on_hand_qty=item["on_hand"],
            available=item["on_hand"] > 0,
        )

    async def release(self, sku: str, quantity: int, idempotency_key: str = "") -> ReserveResult:
        self.release_calls.append((sku, quantity, idempotency_key))
        item = self.stock.setdefault(sku, {"name": sku, "unit_price_cents": 0, "on_hand": 0})
        item["on_hand"] += quantity
        return ReserveResult(sku=sku, reservation_ok=True, on_hand_qty=item["on_hand"])


def install_fake_inventory_client(monkeypatch, fake: FakeInventoryClient) -> None:
    """Patches `app.service.AsyncInventoryClient` (the only place
    `app/service.py` constructs the real gRPC client) so every call
    (`place_order`'s reserve-outside-tx, the two compensating-Release
    reactions) resolves to the SAME fake instance regardless of the
    `(target, timeout)` constructor args passed at each call site."""
    import app.service as service_module

    monkeypatch.setattr(service_module, "AsyncInventoryClient", lambda *args, **kwargs: fake)
