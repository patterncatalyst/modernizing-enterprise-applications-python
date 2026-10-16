"""Review write endpoint's HTTP Basic-auth gate -- SMELL[ch.15] (see
review/views.py), realized in r02 per Option B: faithfully match the Java
sibling's original contract (401 unauthenticated / 201 authenticated on
`POST /api/reviews`), while `GET /api/reviews` and `GET /api/reviews/{id}`
stay fully open, with no auth required at all."""

import base64

import pytest

pytestmark = pytest.mark.django_db


def _post_review(api_client, customer, widget, **kwargs):
    return api_client.post(
        "/api/reviews",
        {"customerId": customer.id, "sku": widget.sku, "rating": 5, "comment": "Great"},
        format="json",
        **kwargs,
    )


def test_post_review_without_auth_returns_401(api_client, customer, widget):
    response = _post_review(api_client, customer, widget)
    assert response.status_code == 401
    # Still the uniform error body shape, via common/exceptions.py's wrapping
    # of DRF's own auth exceptions.
    body = response.json()
    assert set(body) == {"error", "message", "timestamp"}


def test_post_review_with_basic_auth_returns_201(
    api_client, customer, widget, reviewer_auth_header
):
    response = _post_review(api_client, customer, widget, **reviewer_auth_header)
    assert response.status_code == 201
    assert response["Location"] == f"/api/reviews/{response.json()['id']}"


def test_post_review_with_bad_credentials_returns_401(api_client, customer, widget, reviewer_user):
    token = base64.b64encode(b"reviewer:wrong-password").decode()
    response = _post_review(api_client, customer, widget, HTTP_AUTHORIZATION=f"Basic {token}")
    assert response.status_code == 401


def test_reads_require_no_auth(api_client, customer, widget, reviewer_auth_header):
    created = _post_review(api_client, customer, widget, **reviewer_auth_header).json()

    list_response = api_client.get("/api/reviews")
    assert list_response.status_code == 200
    assert any(review["id"] == created["id"] for review in list_response.json())

    detail_response = api_client.get(f"/api/reviews/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]


def test_get_with_garbage_auth_header_still_serves(api_client, widget):
    # A malformed/garbage Authorization header on a READ must never 401 --
    # GET has no permission gate, and perform_authentication is skipped for
    # non-POST methods specifically so this can't happen (see
    # ReviewListCreateView.perform_authentication).
    response = api_client.get("/api/reviews", HTTP_AUTHORIZATION="Basic not-valid-base64!!")
    assert response.status_code == 200
