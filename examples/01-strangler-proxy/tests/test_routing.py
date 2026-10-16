"""Routing + pass-through-fidelity tests for the strangler proxy -- the r07
FLAGLESS edge-router shape.

Through r02-r07's cutover window this suite exercised BOTH flag states (per
context) against in-process stub ASGI backends. r07 decommissions the
monolith: there is no more flag to flip and no more monolith backend to fall
through to. This module is a full rewrite (not an incremental diff) for that
flagless shape: every `/api/*` prefix this proxy has ever fronted now routes
unconditionally to its one owning backend, and a path matching none of them
is a real `404` -- never a silent pass-through to a default backend, because
there is no longer a default backend to pass through to.

Each test builds its own ``Settings`` + ``httpx.AsyncClient`` (mounted onto
stub ASGI apps) and passes them into ``create_app``, proving the proxy is
reconfigurable per-instance (different backend base URLs) rather than
hard-wired to a single process-global state -- the same posture the pre-r07
suite proved, minus the flags.
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

REVIEW_URL = "http://review.test"
DEAD_REVIEW_URL = "http://review-down.test"
NOTIFICATION_URL = "http://notification.test"
DEAD_NOTIFICATION_URL = "http://notification-down.test"
INVENTORY_URL = "http://inventory.test"
DEAD_INVENTORY_URL = "http://inventory-down.test"
PAYMENT_URL = "http://payment.test"
DEAD_PAYMENT_URL = "http://payment-down.test"
SHIPPING_URL = "http://shipping.test"
DEAD_SHIPPING_URL = "http://shipping-down.test"
ORDER_URL = "http://order.test"
DEAD_ORDER_URL = "http://order-down.test"


def make_stub_app(name: str):
    """A minimal raw-ASGI stub backend: echoes request shape as JSON.

    Any path ENDING in ``/boom`` (e.g. ``/api/orders/boom``) always answers
    500, to prove the proxy relays a real upstream error status verbatim
    instead of raising or masking it -- a suffix match rather than an exact
    ``/api/boom`` match, so this works through any of the six real context
    prefixes the flagless router actually knows about.
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
        if path.endswith("/boom"):
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


def _settings() -> Settings:
    """The one, flagless, fully-wired Settings instance every routing test
    below shares -- every one of the six owning backends is a healthy stub,
    so each test only has to override what it specifically wants down."""
    return Settings(
        review_base_url=REVIEW_URL,
        notification_base_url=NOTIFICATION_URL,
        inventory_base_url=INVENTORY_URL,
        payment_base_url=PAYMENT_URL,
        shipping_base_url=SHIPPING_URL,
        order_base_url=ORDER_URL,
    )


def _mounts() -> dict[str, httpx.AsyncBaseTransport]:
    return {
        REVIEW_URL: httpx.ASGITransport(app=make_stub_app("review")),
        NOTIFICATION_URL: httpx.ASGITransport(app=make_stub_app("notification")),
        INVENTORY_URL: httpx.ASGITransport(app=make_stub_app("inventory")),
        PAYMENT_URL: httpx.ASGITransport(app=make_stub_app("payment")),
        SHIPPING_URL: httpx.ASGITransport(app=make_stub_app("shipping")),
        ORDER_URL: httpx.ASGITransport(app=make_stub_app("order")),
    }


@pytest.mark.parametrize(
    ("path", "backend"),
    [
        ("/api/reviews/5", "review"),
        ("/api/reviews?sku=SKU-WIDGET-001", "review"),
        ("/api/notifications/5", "notification"),
        ("/api/notifications?customerId=42", "notification"),
        ("/api/inventory/5", "inventory"),
        ("/api/inventory?sku=SKU-WIDGET-001", "inventory"),
        ("/api/payments/5", "payment"),
        ("/api/payments?orderId=42", "payment"),
        ("/api/shipments/5", "shipping"),
        ("/api/shipments?orderId=42", "shipping"),
        ("/api/orders/5", "order"),
        ("/api/orders?customerId=1", "order"),
    ],
)
async def test_every_context_prefix_routes_to_its_one_owning_backend(path, backend):
    """The flagless router's core contract: every `/api/*` prefix this proxy
    has ever fronted maps unconditionally to exactly one backend -- no flag,
    no monolith fallback, anywhere."""
    async with running_proxy(_settings(), _mounts()) as client:
        resp = await client.get(path)
        assert resp.status_code == 200
        assert resp.json()["backend"] == backend


async def test_all_six_contexts_coexist_independently_in_one_proxy_instance():
    """All six owning backends answer correctly side by side in the SAME
    proxy instance -- not just one at a time in isolation."""
    async with running_proxy(_settings(), _mounts()) as client:
        for path, backend in [
            ("/api/reviews/5", "review"),
            ("/api/notifications/5", "notification"),
            ("/api/inventory/5", "inventory"),
            ("/api/payments/5", "payment"),
            ("/api/shipments/5", "shipping"),
            ("/api/orders/5", "order"),
        ]:
            resp = await client.get(path)
            assert resp.status_code == 200
            assert resp.json()["backend"] == backend


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api",
        "/api/",
        "/api/unknown",
        "/health",
        "/api/order",  # NOT a prefix of /api/orders -- must not accidentally match
        "/api/review",  # NOT a prefix of /api/reviews -- must not accidentally match
    ],
)
async def test_unmatched_path_is_a_real_404_never_a_silent_passthrough(path):
    """r07's whole point: there is no monolith left to catch what nothing
    else matches. An unrecognized path is a real `404` from the proxy
    itself -- it never reaches any backend (none of the six stub backends
    below are ever hit for these paths; if one of them answered, the
    assertion on `backend` would fail instead of this 404 check even
    mattering)."""
    async with running_proxy(_settings(), _mounts()) as client:
        resp = await client.get(path)
        assert resp.status_code == 404


async def test_review_down_surfaces_real_5xx_not_masked_200():
    mounts = _mounts() | {REVIEW_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/reviews/5")
        assert down_resp.status_code == 502
        assert down_resp.status_code != 200

        # The failure is scoped to the dead backend -- every other context
        # on this same proxy instance keeps working.
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "order"


async def test_notification_down_surfaces_real_5xx_not_masked_200():
    mounts = _mounts() | {NOTIFICATION_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/notifications/5")
        assert down_resp.status_code == 502
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "order"


async def test_inventory_down_surfaces_real_5xx_not_masked_200():
    mounts = _mounts() | {INVENTORY_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/inventory/5")
        assert down_resp.status_code == 502
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "order"


async def test_payment_down_surfaces_real_5xx_not_masked_200():
    mounts = _mounts() | {PAYMENT_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/payments/5")
        assert down_resp.status_code == 502
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "order"


async def test_shipping_down_surfaces_real_5xx_not_masked_200():
    mounts = _mounts() | {SHIPPING_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/shipments/5")
        assert down_resp.status_code == 502
        healthy_resp = await client.get("/api/orders/1")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "order"


async def test_order_down_surfaces_real_5xx_not_masked_200():
    """The context r07 just cut over: order-service down must be a real 502
    through the flagless router -- there is no monolith fallback left for
    `/api/orders` to silently resolve to."""
    mounts = _mounts() | {ORDER_URL: httpx.MockTransport(_raise_connect_error)}
    async with running_proxy(_settings(), mounts) as client:
        down_resp = await client.get("/api/orders/5")
        assert down_resp.status_code == 502
        assert down_resp.status_code != 200

        healthy_resp = await client.get("/api/reviews/5")
        assert healthy_resp.status_code == 200
        assert healthy_resp.json()["backend"] == "review"


async def test_pass_through_fidelity_method_path_query_headers_body():
    async with running_proxy(_settings(), _mounts()) as client:
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
    a real upstream error status must come back as-is, never masked into 200.
    Routed through ``/api/orders/boom`` -- a real, known prefix (order-service's
    stub) -- so this exercises the proxy's pass-through path, not its 404 path.
    """
    async with running_proxy(_settings(), _mounts()) as client:
        resp = await client.get("/api/orders/boom")
        assert resp.status_code == 500
        assert resp.json()["error"] == "boom"


async def test_post_body_forwarded_with_content_length_not_chunked():
    """Regression test for the WSGI-upstream empty-body bug.

    Forwarding the inbound body as ``request.stream()`` (an async generator)
    makes httpx send the upstream request as ``Transfer-Encoding: chunked``
    with no ``Content-Length`` -- which a WSGI backend decodes as a
    zero-length body, since it does not honor gunicorn's non-standard
    ``wsgi.input_terminated`` signal. That gap can't be seen by driving the
    proxy purely over ``httpx.ASGITransport`` (what every other test in this
    module does): ASGI decodes chunked bodies fine, so the bug is invisible
    there too.

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

    mounts = {ORDER_URL: httpx.MockTransport(capture_upstream)}
    body = b'{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "great"}'

    async with running_proxy(_settings(), mounts) as client:
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
