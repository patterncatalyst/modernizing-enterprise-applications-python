"""Testcontainers fixtures for the end-to-end lifecycle proof -- an isolated
Kafka + Postgres pair per test session (does NOT touch whatever
`DATABASE_URL` the throwaway Postgres used by `tests/unit/` points at), plus
a REAL (networked, in-process) gRPC inventory server standing in for
`04-inventory-service` -- this service's own gRPC stubs (`app/grpc_gen/`)
talk to it over `localhost`, proving the `grpc.aio` client wiring end to end
rather than mocking it away. Requires a reachable Docker daemon; run with
`uv run pytest -m integration`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from grpc import aio as grpc_aio

# `testcontainers.kafka`/`testcontainers.postgres` are deprecated redirects
# in testcontainers 4.15.0 -- import the non-deprecated `community` modules
# directly.
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

from app.grpc_gen import inventory_pb2, inventory_pb2_grpc

_SERVICE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18.6-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def kafka_container() -> Iterator[KafkaContainer]:
    # `.with_kraft()` is required for this image tag -- see every other
    # service's `tests/integration/conftest.py` in this project for why.
    with KafkaContainer("confluentinc/cp-kafka:8.3.2").with_kraft() as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    raw = postgres_container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture(scope="session")
def kafka_bootstrap_servers(kafka_container: KafkaContainer) -> str:
    return kafka_container.get_bootstrap_server()


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema(database_url: str) -> None:
    """Runs this service's own Alembic migration (schema + seed customers)
    against the Testcontainers Postgres, in-process, before any integration
    test executes."""
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(_SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_SERVICE_ROOT / "migrations"))
    command.upgrade(config, "head")


# ---------------------------------------------------------------------------
# A minimal, REAL gRPC inventory server (grpc.aio) -- stands in for
# `04-inventory-service` so this service's own `app/inventory_client.py`
# talks over an actual network socket during integration tests, instead of
# being monkeypatched away like `tests/unit/`'s `FakeInventoryClient`.
# ---------------------------------------------------------------------------


class _FakeInventoryServicer(inventory_pb2_grpc.InventoryGrpcServiceServicer):
    def __init__(self) -> None:
        self.stock = {
            "SKU-WIDGET-001": {"name": "Standard Widget", "price_cents": 1999, "on_hand": 100},
            "SKU-GADGET-002": {"name": "Deluxe Gadget", "price_cents": 4999, "on_hand": 50},
        }
        self._applied_release_keys: set[str] = set()

    async def CheckStock(self, request, context):
        item = self.stock.get(request.stock_keeping_unit)
        return self._reply(request.stock_keeping_unit, item, item is not None)

    async def Reserve(self, request, context):
        item = self.stock.get(request.stock_keeping_unit)
        ok = item is not None and item["on_hand"] >= request.requested_qty
        if ok:
            item["on_hand"] -= request.requested_qty
        on_hand = item["on_hand"] if item else 0
        return inventory_pb2.ReserveReply(
            stock_keeping_unit=request.stock_keeping_unit,
            reservation_ok=ok,
            on_hand_qty=on_hand,
        )

    async def Release(self, request, context):
        item = self.stock.setdefault(
            request.stock_keeping_unit,
            {"name": request.stock_keeping_unit, "price_cents": 0, "on_hand": 0},
        )
        key = request.idempotency_key
        if not key or key not in self._applied_release_keys:
            item["on_hand"] += request.requested_qty
            if key:
                self._applied_release_keys.add(key)
        return inventory_pb2.ReserveReply(
            stock_keeping_unit=request.stock_keeping_unit,
            reservation_ok=True,
            on_hand_qty=item["on_hand"],
        )

    async def GetStock(self, request, context):
        item = self.stock.get(request.stock_keeping_unit)
        return self._reply(request.stock_keeping_unit, item, item is not None)

    @staticmethod
    def _reply(sku, item, available):
        if item is None:
            return inventory_pb2.StockReply(
                stock_keeping_unit=sku, display_name="", unit_price_cents=0,
                on_hand_qty=0, available=False,
            )
        return inventory_pb2.StockReply(
            stock_keeping_unit=sku,
            display_name=item["name"],
            unit_price_cents=item["price_cents"],
            on_hand_qty=item["on_hand"],
            available=available,
        )


@pytest.fixture
async def fake_inventory_server() -> AsyncIterator[tuple[str, _FakeInventoryServicer]]:
    """A real `grpc.aio.server()` bound to an ephemeral localhost port,
    implementing the SAME `InventoryGrpcServiceServicer` interface
    `04-inventory-service/app/grpc_server.py` does -- this service's
    `AsyncInventoryClient` connects to it exactly as it would the real
    service."""
    servicer = _FakeInventoryServicer()
    server = grpc_aio.server()
    inventory_pb2_grpc.add_InventoryGrpcServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        await server.stop(grace=None)
