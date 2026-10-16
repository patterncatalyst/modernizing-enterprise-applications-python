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
