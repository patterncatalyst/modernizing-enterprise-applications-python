"""`/api/inventory` contract tests -- the FastAPI sibling of the monolith's
`inventory`-surface coverage. Exercises this service's OWN, already-migrated
AND seeded `inventory` schema (see `conftest.py`), proving the read contract
matches byte-for-byte: field names, array shape, and the 404-uniform-body
case for an unknown sku."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_inventory_returns_camel_case_array(client: TestClient):
    response = client.get("/api/inventory")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 3
    for item in body:
        assert set(item) == {"sku", "name", "priceCents", "quantityOnHand"}

    skus = {item["sku"] for item in body}
    assert skus == {"SKU-WIDGET-001", "SKU-GADGET-002", "SKU-GIZMO-003"}


def test_list_inventory_matches_monolith_seed_values(client: TestClient):
    response = client.get("/api/inventory")
    assert response.status_code == 200
    by_sku = {item["sku"]: item for item in response.json()}

    assert by_sku["SKU-WIDGET-001"]["name"] == "Standard Widget"
    assert by_sku["SKU-WIDGET-001"]["priceCents"] == 1999
    assert by_sku["SKU-WIDGET-001"]["quantityOnHand"] == 100

    assert by_sku["SKU-GADGET-002"]["name"] == "Deluxe Gadget"
    assert by_sku["SKU-GADGET-002"]["priceCents"] == 4999
    assert by_sku["SKU-GADGET-002"]["quantityOnHand"] == 50

    assert by_sku["SKU-GIZMO-003"]["name"] == "Pocket Gizmo"
    assert by_sku["SKU-GIZMO-003"]["priceCents"] == 999
    assert by_sku["SKU-GIZMO-003"]["quantityOnHand"] == 5


def test_get_inventory_item_returns_camel_case_object(client: TestClient):
    response = client.get("/api/inventory/SKU-WIDGET-001")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"sku", "name", "priceCents", "quantityOnHand"}
    assert body["sku"] == "SKU-WIDGET-001"


def test_get_inventory_item_unknown_sku_returns_404_uniform_body(client: TestClient):
    response = client.get("/api/inventory/NOPE")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "NOT_FOUND"


def test_no_trailing_slash_redirect(client: TestClient):
    # `redirect_slashes=False`, same contract posture as the other services:
    # a trailing-slash request must not 307-redirect.
    response = client.get("/api/inventory/", follow_redirects=False)
    assert response.status_code != 307
