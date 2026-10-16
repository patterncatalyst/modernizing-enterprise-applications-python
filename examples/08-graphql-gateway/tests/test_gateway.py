"""Unit tests for the GraphQL gateway -- the downstream clients are MOCKED
(monkeypatched at the point `app/schema.py` imported them), so these tests
never touch a real order-/payment-/shipping-/review-/inventory-service.
Live cross-service proof is the later cutover lane's job (see the GRAPHQL-
GATEWAY lane's prompt); this suite proves the STITCHING, the PARTIAL-FAILURE
contract, the DEPTH LIMIT, and the unknown-id-is-null contract.

Every test builds its own schema via `app.schema.build_schema(settings)`
and calls `schema.execute(...)` directly (no FastAPI TestClient, no running
server) -- `app.schema.Query.order`'s resolvers read
`info.context["settings"]`, so `context_value={"settings": settings}` is
all a test needs to wire in.
"""

from __future__ import annotations

import pytest

from app.clients import DownstreamUnavailable
from app.config import Settings
from app.schema import build_schema

ORDER_DATA = {
    "id": 42,
    "customerId": 7,
    "status": "CONFIRMED",
    "totalCents": 5000,
    "createdAt": "2026-01-01T00:00:00Z",
    "shippingAddress": "1 Infinite Loop",
    "items": [{"sku": "WIDGET-1", "quantity": 2, "unitPriceCents": 2500}],
}

PAYMENT_ROWS = [
    {
        "id": 1,
        "orderId": 42,
        "amountCents": 5000,
        "method": "CARD",
        "status": "CAPTURED",
        "createdAt": "2026-01-01T00:01:00Z",
    }
]

SHIPMENT_ROWS = [
    {
        "id": 9,
        "orderId": 42,
        "address": "1 Infinite Loop",
        "status": "DISPATCHED",
        "createdAt": "2026-01-01T00:02:00Z",
    }
]

REVIEW_ROWS = [
    {
        "id": 5,
        "customerId": 3,
        "sku": "WIDGET-1",
        "rating": 5,
        "comment": "great widget",
        "createdAt": "2026-01-01T00:03:00Z",
    }
]

STOCK_DATA = {
    "sku": "WIDGET-1",
    "display_name": "Widget",
    "unit_price_cents": 2500,
    "on_hand_qty": 17,
    "available": True,
}

FULL_QUERY = """
query ($id: ID!) {
  order(id: $id) {
    id
    customerId
    status
    totalCents
    createdAt
    shippingAddress
    items {
      sku
      quantity
      unitPriceCents
      stock { sku displayName onHandQty available }
      reviews { id sku rating comment }
    }
    payments { id orderId amountCents method status }
    shipments { id orderId address status }
  }
}
"""


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env()


async def _fake_fetch_order(_settings, _order_id):
    return ORDER_DATA


async def _fake_fetch_payments(_settings, _order_id):
    return PAYMENT_ROWS


async def _fake_fetch_shipments(_settings, _order_id):
    return SHIPMENT_ROWS


async def _fake_fetch_reviews(_settings, _sku):
    return REVIEW_ROWS


async def _fake_fetch_stock(_settings, _sku):
    return STOCK_DATA


def _patch_all_clients_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.schema.fetch_order", _fake_fetch_order)
    monkeypatch.setattr("app.schema.fetch_payments", _fake_fetch_payments)
    monkeypatch.setattr("app.schema.fetch_shipments", _fake_fetch_shipments)
    monkeypatch.setattr("app.schema.fetch_reviews", _fake_fetch_reviews)
    monkeypatch.setattr("app.schema.fetch_stock", _fake_fetch_stock)


async def test_order_stitches_all_five_sources(monkeypatch, settings):
    """order(id) must federate order (REST) + payments (REST) + shipments
    (REST) + per-item reviews (REST) + per-item stock (gRPC) into one
    response, with no errors when every downstream succeeds."""
    _patch_all_clients_healthy(monkeypatch)
    schema = build_schema(settings)

    result = await schema.execute(
        FULL_QUERY, variable_values={"id": "42"}, context_value={"settings": settings}
    )

    assert result.errors is None
    order = result.data["order"]
    assert order["id"] == "42"
    assert order["customerId"] == "7"
    assert order["status"] == "CONFIRMED"
    assert order["totalCents"] == 5000
    assert order["shippingAddress"] == "1 Infinite Loop"

    assert len(order["items"]) == 1
    item = order["items"][0]
    assert item["sku"] == "WIDGET-1"
    assert item["quantity"] == 2
    assert item["unitPriceCents"] == 2500

    # gRPC-federated field.
    assert item["stock"] == {
        "sku": "WIDGET-1",
        "displayName": "Widget",
        "onHandQty": 17,
        "available": True,
    }

    # REST-federated fields.
    assert len(item["reviews"]) == 1
    assert item["reviews"][0]["sku"] == "WIDGET-1"
    assert item["reviews"][0]["rating"] == 5

    assert len(order["payments"]) == 1
    assert order["payments"][0]["status"] == "CAPTURED"

    assert len(order["shipments"]) == 1
    assert order["shipments"][0]["status"] == "DISPATCHED"


async def test_downstream_failure_nulls_only_that_field(monkeypatch, settings):
    """A failing downstream (payment-service, here) must null ONLY the
    `payments` field and add a GraphQL `errors[]` entry -- siblings
    (`shipments`, `items`, the order's own read-model fields) must still
    resolve. The whole query must never come back as a 500/crash -- it
    returns normal `ExecutionResult` with partial `data` plus `errors`."""
    monkeypatch.setattr("app.schema.fetch_order", _fake_fetch_order)
    monkeypatch.setattr("app.schema.fetch_shipments", _fake_fetch_shipments)
    monkeypatch.setattr("app.schema.fetch_reviews", _fake_fetch_reviews)
    monkeypatch.setattr("app.schema.fetch_stock", _fake_fetch_stock)

    async def _failing_fetch_payments(_settings, _order_id):
        raise DownstreamUnavailable("payment-service unavailable: connection refused")

    monkeypatch.setattr("app.schema.fetch_payments", _failing_fetch_payments)
    schema = build_schema(settings)

    result = await schema.execute(
        FULL_QUERY, variable_values={"id": "42"}, context_value={"settings": settings}
    )

    # Partial failure, never a whole-query crash: errors[] is populated...
    assert result.errors is not None
    assert len(result.errors) == 1
    assert "payment-service unavailable" in str(result.errors[0])

    # ...but data is still returned, with ONLY the failing field null.
    order = result.data["order"]
    assert order is not None
    assert order["payments"] is None
    assert order["shipments"] == [
        {"id": "9", "orderId": "42", "address": "1 Infinite Loop", "status": "DISPATCHED"}
    ]
    assert order["items"][0]["stock"] is not None
    assert order["items"][0]["reviews"] is not None


async def test_downstream_grpc_failure_nulls_only_stock_field(monkeypatch, settings):
    """Same partial-failure contract, but for the gRPC-federated `stock`
    field: inventory-service being unavailable must null only `stock`, not
    `reviews` (the sibling REST-federated field on the same item) and not
    the rest of the order."""
    _patch_all_clients_healthy(monkeypatch)

    async def _failing_fetch_stock(_settings, _sku):
        raise DownstreamUnavailable("inventory-service unavailable: UNAVAILABLE deadline exceeded")

    monkeypatch.setattr("app.schema.fetch_stock", _failing_fetch_stock)
    schema = build_schema(settings)

    result = await schema.execute(
        FULL_QUERY, variable_values={"id": "42"}, context_value={"settings": settings}
    )

    assert result.errors is not None
    assert any("inventory-service unavailable" in str(e) for e in result.errors)

    order = result.data["order"]
    assert order["items"][0]["stock"] is None
    assert order["items"][0]["reviews"] is not None
    assert order["payments"] is not None


async def test_unknown_order_id_returns_null(monkeypatch, settings):
    """An id order-service 404s on must come back as `data.order: null` with
    NO errors -- a missing order is a legitimate answer, not a downstream
    failure."""

    async def _fake_fetch_order_404(_settings, _order_id):
        return None

    monkeypatch.setattr("app.schema.fetch_order", _fake_fetch_order_404)
    schema = build_schema(settings)

    result = await schema.execute(
        "query ($id: ID!) { order(id: $id) { id } }",
        variable_values={"id": "999"},
        context_value={"settings": settings},
    )

    assert result.errors is None
    assert result.data == {"order": None}


async def test_depth_bomb_rejected_by_depth_limiter(monkeypatch):
    """A query nested deeper than the operator-configured budget must be
    rejected at validation time -- before any resolver (and therefore
    before any downstream call) ever runs."""
    _patch_all_clients_healthy(monkeypatch)
    strict_settings = Settings.from_env()
    # DEPTH-BOMB-PROOF: force a tiny budget so a legitimate-shaped-but-deep
    # query (order -> items -> stock, depth 3) trips it deterministically,
    # independent of whatever the default production budget happens to be.
    strict_settings = Settings(
        **{**strict_settings.__dict__, "max_query_depth": 2},
    )
    schema = build_schema(strict_settings)

    depth_bomb_query = """
    query ($id: ID!) {
      order(id: $id) {
        items {
          stock { sku }
        }
      }
    }
    """

    result = await schema.execute(depth_bomb_query, variable_values={"id": "42"})

    assert result.data is None
    assert result.errors is not None
    assert any("depth" in str(e).lower() for e in result.errors)


async def test_token_bomb_rejected_by_max_tokens_limiter(monkeypatch):
    """A query padded with many aliased copies of the same subtree (same
    depth, much higher token count) must be rejected by the token budget
    even when it fits within the depth budget -- the second half of the
    amplification-vector mitigation (see `app/config.py`'s docstring)."""
    _patch_all_clients_healthy(monkeypatch)
    base_settings = Settings.from_env()
    strict_settings = Settings(**{**base_settings.__dict__, "max_query_tokens": 20})
    schema = build_schema(strict_settings)

    # Well within the depth budget (depth 2), but each aliased copy adds a
    # full extra selection set's worth of tokens.
    padded_query = """
    query ($id: ID!) {
      a1: order(id: $id) { id status }
      a2: order(id: $id) { id status }
      a3: order(id: $id) { id status }
      a4: order(id: $id) { id status }
      a5: order(id: $id) { id status }
    }
    """

    result = await schema.execute(padded_query, variable_values={"id": "42"})

    assert result.data is None
    assert result.errors is not None
