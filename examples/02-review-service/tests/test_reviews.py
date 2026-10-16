"""`/api/reviews` contract tests -- the FastAPI sibling of the monolith's
`tests/test_smoke.py::test_reviews_serves` + `tests/test_review_auth.py`.
Exercises the SAME shared, pre-seeded Postgres database the monolith uses
(`manage.py migrate && manage.py seed`), proving this service's wire
contract matches byte-for-byte: field names, status codes, and the uniform
error body."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import SEEDED_SKU


def _find_existing_customer_id(client: TestClient) -> int:
    """Every seeded review already references a valid, pre-existing
    customer -- reuse one rather than hard-coding an id, so these tests
    don't depend on the exact auto-increment sequence the seed command
    produced."""
    response = client.get("/api/reviews")
    reviews = response.json()
    assert reviews, "expected the monolith's seed command to have run first"
    return reviews[0]["customerId"]


def test_list_reviews_returns_camel_case_array(client: TestClient):
    response = client.get("/api/reviews")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body
    first = body[0]
    assert set(first) == {"id", "customerId", "sku", "rating", "comment", "createdAt"}


def test_list_reviews_filters_by_sku(client: TestClient):
    response = client.get("/api/reviews", params={"sku": SEEDED_SKU})
    assert response.status_code == 200
    body = response.json()
    assert body
    assert all(review["sku"] == SEEDED_SKU for review in body)


def test_get_review_by_id_returns_200(client: TestClient):
    listed = client.get("/api/reviews").json()
    review_id = listed[0]["id"]

    response = client.get(f"/api/reviews/{review_id}")
    assert response.status_code == 200
    assert response.json()["id"] == review_id


def test_get_review_by_id_returns_404_uniform_body(client: TestClient):
    response = client.get("/api/reviews/999999999")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "NOT_FOUND"


def test_post_review_without_auth_returns_401_uniform_body(client: TestClient):
    customer_id = _find_existing_customer_id(client)

    response = client.post(
        "/api/reviews",
        json={"customerId": customer_id, "sku": SEEDED_SKU, "rating": 5, "comment": "Great"},
    )
    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}


def test_post_review_with_bad_credentials_returns_401(client: TestClient):
    customer_id = _find_existing_customer_id(client)

    response = client.post(
        "/api/reviews",
        json={"customerId": customer_id, "sku": SEEDED_SKU, "rating": 5, "comment": "Great"},
        auth=("reviewer", "wrong-password"),
    )
    assert response.status_code == 401


def test_post_review_with_basic_auth_returns_201(
    client: TestClient, reviewer_auth_header: dict[str, str]
):
    customer_id = _find_existing_customer_id(client)

    response = client.post(
        "/api/reviews",
        json={"customerId": customer_id, "sku": SEEDED_SKU, "rating": 5, "comment": "Works great"},
        headers=reviewer_auth_header,
    )
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/reviews/{body['id']}"
    assert set(body) == {"id", "customerId", "sku", "rating", "comment", "createdAt"}
    assert body["customerId"] == customer_id
    assert body["sku"] == SEEDED_SKU
    assert body["rating"] == 5
    assert body["comment"] == "Works great"

    # Reads require no auth and must see the freshly written row.
    get_response = client.get(f"/api/reviews/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_post_review_with_invalid_rating_returns_400(
    client: TestClient, reviewer_auth_header: dict[str, str]
):
    customer_id = _find_existing_customer_id(client)

    response = client.post(
        "/api/reviews",
        json={"customerId": customer_id, "sku": SEEDED_SKU, "rating": 6, "comment": "Too high"},
        headers=reviewer_auth_header,
    )
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}
    assert body["error"] == "VALIDATION_FAILED"


def test_post_review_with_unknown_sku_returns_404(
    client: TestClient, reviewer_auth_header: dict[str, str]
):
    customer_id = _find_existing_customer_id(client)

    response = client.post(
        "/api/reviews",
        json={"customerId": customer_id, "sku": "SKU-DOES-NOT-EXIST", "rating": 5},
        headers=reviewer_auth_header,
    )
    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"


def test_get_with_garbage_auth_header_still_serves(client: TestClient):
    # GET has no auth gate at all -- a malformed Authorization header must
    # never 401 a read, mirroring the monolith's
    # `test_get_with_garbage_auth_header_still_serves`.
    response = client.get(
        "/api/reviews", headers={"Authorization": "Basic not-valid-base64!!"}
    )
    assert response.status_code == 200


def test_no_trailing_slash_redirect(client: TestClient):
    # `redirect_slashes=False`: a trailing-slash request must not
    # 307-redirect (that would be a live protocol change, not just a lint
    # nit -- a redirect silently turns a POST into a GET in some clients).
    response = client.get("/api/reviews/", follow_redirects=False)
    assert response.status_code != 307
