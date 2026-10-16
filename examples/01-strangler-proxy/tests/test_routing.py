"""Routing + pass-through-fidelity tests for the strangler proxy.

Exercises BOTH flag states (review disabled / enabled) against two in-process
stub ASGI backends standing in for the monolith and the review service, all
driven through the real app factory (``app.main.create_app``) and a real
httpx ``ASGITransport`` -- no network sockets, no running servers.

Each test builds its own ``Settings`` + ``httpx.AsyncClient`` (mounted onto
the stub ASGI apps) and passes them into ``create_app``, proving the proxy is
reconfigurable per-instance rather than hard-wired to a single process-global
flag state.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from starlette.applications import Starlette

from app.config import Settings
from app.main import create_app

MONOLITH_URL = "http://monolith.test"
REVIEW_URL = "http://review.test"
DEAD_REVIEW_URL = "http://review-down.test"
NOTIFICATION_URL = "http://notification.test"
DEAD_NOTIFICATION_URL = "http://notification-down.test"
INVENTORY_URL = "http://inventory.test"
DEAD_INVENTORY_URL = "http://inventory-down.test"


def make_stub_app(name: str):
    """A minimal raw-ASGI stub backend: echoes request shape as JSON.

    ``GET/POST/... /api/boom`` always answers 500, to prove the proxy relays
    a real upstream error status verbatim instead of raising or masking it.
    """

    async def stub(scope, receive, send):
        assert scope["type"] == "http"
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        path = scope["path"]
        if path == "/api/boom":
            status = 500
            payload = {"backend": name, "path": path, "error": "boom"}
        else:
            status = 200
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]
            }
            payload = {
                "backend": name,
                "path": path,
                "method": scope["method"],
                "query": scope["query_string"].decode("latin-1"),
                "body": body.decode("utf-8") if body else "",
                "x_test_header": headers.get("x-test-header"),
            }

        body_bytes = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-stub-backend", name.encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body_bytes})

    return stub


def _raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused (stub)", request=request)


class _OnceByteStream(httpx.AsyncByteStream):
    """A response body that is genuinely unread until iterated.

    ``httpx.Response(..., content=...)`` / ``json=...`` reads the body
    eagerly in ``__init__`` (so the response can be used without an async
    context), which also marks it ``is_stream_consumed`` before the proxy's
    own ``aiter_raw()`` ever runs -- fine for a real socket-backed transport,
    but it trips ``httpx.StreamConsumed`` when paired with
    ``httpx.MockTransport`` and ``client.send(..., stream=True)``. Passing
    ``stream=`` instead defers reading to the one real iteration the proxy
    performs, matching how a real upstream response behaves.
    """

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._data


@asynccontextmanager
async def lifespan_context(app: Starlette) -> AsyncIterator[None]:
    """Drive a Starlette app's lifespan protocol with no extra dependency.

    httpx's ``ASGITransport`` only forwards ``http`` scope requests -- it
    does not trigger ASGI lifespan events -- so a plain ASGITransport-backed
    client would never run ``create_app``'s lifespan function and
    ``app.state.http_client`` would stay unset. This replays the lifespan
    protocol by hand (startup, then shutdown on exit) using only stdlib
    asyncio, matching what a real ASGI server does at process start/stop.
    """
    startup_complete = asyncio.Event()
    shutdown_complete = asyncio.Event()
    shutdown_requested = asyncio.Event()
    sent_startup = False

    async def receive():
        nonlocal sent_startup
        if not sent_startup:
            sent_startup = True
            return {"type": "lifespan.startup"}
        await shutdown_requested.wait()
        return {"type": "lifespan.shutdown"}

    async def send(message):
        if message["type"] == "lifespan.startup.complete":
            startup_complete.set()
        elif message["type"] == "lifespan.shutdown.complete":
            shutdown_complete.set()

    task = asyncio.create_task(app({"type": "lifespan"}, receive, send))
    await startup_complete.wait()
    try:
        yield
    finally:
        shutdown_requested.set()
        await shutdown_complete.wait()
        await task


def _build_client(mounts: dict[str, httpx.AsyncBaseTransport]) -> httpx.AsyncClient:
    return httpx.AsyncClient(mounts=mounts)


@asynccontextmanager
async def running_proxy(settings: Settings, mounts: dict[str, httpx.AsyncBaseTransport]):
    """Stand up one proxy instance: real lifespan, real ASGITransport, mocked upstreams."""
    http_client = _build_client(mounts)
    app = create_app(settings=settings, http_client=http_client)
    async with lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://proxy.test") as client:
            yield client


def _mounts() -> dict[str, httpx.AsyncBaseTransport]:
    return {
        MONOLITH_URL: httpx.ASGITransport(app=make_stub_app("monolith")),
        REVIEW_URL: httpx.ASGITransport(app=make_stub_app("review")),
        NOTIFICATION_URL: httpx.ASGITransport(app=make_stub_app("notification")),
        INVENTORY_URL: httpx.ASGITransport(app=make_stub_app("inventory")),
    }


async def test_flag_off_routes_reviews_path_to_monolith():
    settings = Settings(
        review_enabled=False, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/reviews/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "monolith"


async def test_flag_off_routes_other_paths_to_monolith():
    settings = Settings(
        review_enabled=False, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/orders/1")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "monolith"


async def test_flag_on_routes_reviews_path_to_review_service():
    settings = Settings(
        review_enabled=True, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/reviews/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "review"

        # A sibling path under /api/reviews/* must also cut over, not just
        # the exact prefix.
        resp2 = await client.get("/api/reviews?sku=SKU-WIDGET-001")
        assert resp2.status_code == 200
        assert resp2.json()["backend"] == "review"


async def test_flag_on_routes_other_paths_to_monolith():
    settings = Settings(
        review_enabled=True, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/orders/1")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "monolith"


async def test_notification_flag_off_routes_notifications_path_to_monolith():
    settings = Settings(
        notification_enabled=False,
        monolith_base_url=MONOLITH_URL,
        notification_base_url=NOTIFICATION_URL,
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/notifications/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "monolith"


async def test_notification_flag_on_routes_notifications_path_to_notification_service():
    settings = Settings(
        review_enabled=True,
        notification_enabled=True,
        monolith_base_url=MONOLITH_URL,
        review_base_url=REVIEW_URL,
        notification_base_url=NOTIFICATION_URL,
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/notifications/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "notification"

        # A sibling path under /api/notifications/* must also cut over, not
        # just the exact prefix.
        resp2 = await client.get("/api/notifications?customerId=42")
        assert resp2.status_code == 200
        assert resp2.json()["backend"] == "notification"

        # The notification flag must be independent of the review flag: both
        # cut-over paths route correctly in the same proxy instance ...
        review_resp = await client.get("/api/reviews/5")
        assert review_resp.status_code == 200
        assert review_resp.json()["backend"] == "review"

        # ... and every other path still falls through to the monolith.
        other_resp = await client.get("/api/orders/1")
        assert other_resp.status_code == 200
        assert other_resp.json()["backend"] == "monolith"


async def test_notification_down_surfaces_real_5xx_not_masked_200():
    settings = Settings(
        notification_enabled=True,
        monolith_base_url=MONOLITH_URL,
        notification_base_url=DEAD_NOTIFICATION_URL,
    )
    mounts = {
        MONOLITH_URL: httpx.ASGITransport(app=make_stub_app("monolith")),
        DEAD_NOTIFICATION_URL: httpx.MockTransport(_raise_connect_error),
    }
    async with running_proxy(settings, mounts) as client:
        down_resp = await client.get("/api/notifications/5")
        assert down_resp.status_code == 502
        assert down_resp.status_code != 200

        # The failure is scoped to the dead backend -- everything else on
        # this same proxy instance keeps working.
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "monolith"


async def test_inventory_flag_off_routes_inventory_path_to_monolith():
    settings = Settings(
        inventory_enabled=False,
        monolith_base_url=MONOLITH_URL,
        inventory_base_url=INVENTORY_URL,
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/inventory/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "monolith"


async def test_inventory_flag_on_routes_inventory_path_to_inventory_service():
    settings = Settings(
        review_enabled=True,
        notification_enabled=True,
        inventory_enabled=True,
        monolith_base_url=MONOLITH_URL,
        review_base_url=REVIEW_URL,
        notification_base_url=NOTIFICATION_URL,
        inventory_base_url=INVENTORY_URL,
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/inventory/5")
        assert resp.status_code == 200
        assert resp.json()["backend"] == "inventory"

        # A sibling path under /api/inventory/* must also cut over, not just
        # the exact prefix.
        resp2 = await client.get("/api/inventory?sku=SKU-WIDGET-001")
        assert resp2.status_code == 200
        assert resp2.json()["backend"] == "inventory"

        # The inventory flag must be independent of the review and
        # notification flags: all three cut-over paths route correctly in
        # the same proxy instance ...
        review_resp = await client.get("/api/reviews/5")
        assert review_resp.status_code == 200
        assert review_resp.json()["backend"] == "review"

        notification_resp = await client.get("/api/notifications/5")
        assert notification_resp.status_code == 200
        assert notification_resp.json()["backend"] == "notification"

        # ... and every other path still falls through to the monolith.
        other_resp = await client.get("/api/orders/1")
        assert other_resp.status_code == 200
        assert other_resp.json()["backend"] == "monolith"


async def test_inventory_down_surfaces_real_5xx_not_masked_200():
    settings = Settings(
        inventory_enabled=True,
        monolith_base_url=MONOLITH_URL,
        inventory_base_url=DEAD_INVENTORY_URL,
    )
    mounts = {
        MONOLITH_URL: httpx.ASGITransport(app=make_stub_app("monolith")),
        DEAD_INVENTORY_URL: httpx.MockTransport(_raise_connect_error),
    }
    async with running_proxy(settings, mounts) as client:
        down_resp = await client.get("/api/inventory/5")
        assert down_resp.status_code == 502
        assert down_resp.status_code != 200

        # The failure is scoped to the dead backend -- everything else on
        # this same proxy instance keeps working.
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "monolith"


async def test_pass_through_fidelity_method_path_query_headers_body():
    settings = Settings(
        review_enabled=True, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.post(
            "/api/reviews/5?sort=desc&limit=10",
            content=b'{"comment": "great product"}',
            headers={"x-test-header": "trace-id-123", "content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"] == "review"
        assert data["path"] == "/api/reviews/5"
        assert data["method"] == "POST"
        assert data["query"] == "sort=desc&limit=10"
        assert data["body"] == '{"comment": "great product"}'
        assert data["x_test_header"] == "trace-id-123"
        # Response header set by the upstream backend is relayed verbatim.
        assert resp.headers["x-stub-backend"] == "review"


async def test_upstream_4xx_5xx_is_relayed_not_swallowed():
    """The httpx analogue of bridgeEndpoint=true&throwExceptionOnFailure=false:
    a real upstream error status must come back as-is, never masked into 200."""
    settings = Settings(
        review_enabled=False, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    async with running_proxy(settings, _mounts()) as client:
        resp = await client.get("/api/boom")
        assert resp.status_code == 500
        assert resp.json()["error"] == "boom"


async def test_post_body_forwarded_with_content_length_not_chunked():
    """Regression test for the WSGI-upstream empty-body bug.

    Forwarding the inbound body as ``request.stream()`` (an async generator)
    makes httpx send the upstream request as ``Transfer-Encoding: chunked``
    with no ``Content-Length`` -- which a WSGI backend (the real monolith,
    Django/gunicorn) decodes as a zero-length body, since it does not honor
    gunicorn's non-standard ``wsgi.input_terminated`` signal. That gap can't
    be seen by driving the proxy purely over ``httpx.ASGITransport`` (what
    every other test in this module does): ASGI decodes chunked bodies fine,
    so the bug is invisible there too.

    This test instead captures the *actual outbound upstream request* the
    proxy builds, via ``httpx.MockTransport``, and asserts directly on its
    framing and bytes -- no live WSGI server required. Before the fix (body
    forwarded via ``request.stream()``), this fails: the captured request
    carries ``Transfer-Encoding: chunked`` and no ``Content-Length`` header.
    """
    captured: dict[str, httpx.Request] = {}
    response_body = b'{"ok": true}'

    def capture_upstream(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            headers=[
                (b"content-type", b"application/json"),
                (b"content-length", str(len(response_body)).encode("latin-1")),
            ],
            stream=_OnceByteStream(response_body),
        )

    settings = Settings(
        review_enabled=False, monolith_base_url=MONOLITH_URL, review_base_url=REVIEW_URL
    )
    mounts = {MONOLITH_URL: httpx.MockTransport(capture_upstream)}
    body = b'{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "great"}'

    async with running_proxy(settings, mounts) as client:
        resp = await client.post(
            "/api/orders",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

    upstream_request = captured["request"]

    # (a) the upstream request carries a correct Content-Length ...
    assert upstream_request.headers.get("content-length") == str(len(body))
    # (b) ... and NOT Transfer-Encoding: chunked.
    assert "transfer-encoding" not in upstream_request.headers
    # (c) the upstream receives the exact body bytes the client sent.
    assert upstream_request.content == body


async def test_upstream_down_surfaces_real_5xx_not_masked_200():
    settings = Settings(
        review_enabled=True, monolith_base_url=MONOLITH_URL, review_base_url=DEAD_REVIEW_URL
    )
    mounts = {
        MONOLITH_URL: httpx.ASGITransport(app=make_stub_app("monolith")),
        DEAD_REVIEW_URL: httpx.MockTransport(_raise_connect_error),
    }
    async with running_proxy(settings, mounts) as client:
        down_resp = await client.get("/api/reviews/5")
        assert down_resp.status_code == 502
        assert down_resp.status_code != 200

        # The failure is scoped to the dead backend -- everything else on
        # this same proxy instance keeps working.
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "monolith"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
