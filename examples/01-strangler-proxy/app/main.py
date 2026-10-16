"""The strangler-fig edge: a thin ASGI reverse proxy in front of the monolith.

One catch-all route forwards every request -- method, full path, raw query
string, headers, and body -- to whichever backend is configured for it, and
relays that backend's real status code, body, and headers back (streamed)
unchanged. This is the ASGI analogue of a Camel `platform-http` consumer
paired with an `http` producer using `bridgeEndpoint=true&
throwExceptionOnFailure=false`: the proxy never raises on an upstream 4xx/5xx,
it just carries that response straight through.

THE FULL-PATH-PREFIX LESSON (see CUTOVER.md and README.md for the full story):
content-based routing here matches ``request.url.path`` -- the full path the
client sent, e.g. ``/api/reviews/5`` -- NOT a value relative to some mount
point or stripped prefix. Starlette's catch-all ``Route("/{path:path}")`` is
mounted at the application root, so this is the natural, correct thing to do.
But it is still worth naming the trap explicitly: ``request.path_params["path"]``
is the *route-pattern-relative* value (``"api/reviews/5"``, no leading
slash) -- if a future refactor mounts this route under a sub-application or
a path prefix and someone switches the predicate to check that value against
a bare ``"reviews"`` prefix instead of ``"api/reviews"``, the predicate will
silently stop matching and every request will fall through to the monolith,
exactly like the Camel route's original ``CamelHttpPath``-relative-prefix bug.
Always match the FULL request path.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from app.config import Settings
from app.config import settings as default_settings

logger = logging.getLogger("strangler_proxy")

# Hop-by-hop / framing headers that must never be blindly forwarded: their
# value on one hop (e.g. a Content-Length computed for the client's framing)
# is not valid on the other hop once the proxy re-frames the message. RFC
# 9110 section 7.6.1 lists Connection and friends; we also drop Host (it
# must name the upstream, not the proxy) and the framing pair
# Content-Length/Transfer-Encoding. The request body is read into memory and
# forwarded as a plain `bytes` payload (see `proxy_handler`), so httpx always
# computes its own correct Content-Length for the upstream request -- the
# inbound Content-Length (sized for the client's own framing, which may
# differ, e.g. if the client itself used chunked transfer-encoding) and any
# inbound Transfer-Encoding are both dropped rather than forwarded. This
# also sidesteps a real WSGI-upstream defect: Django's WSGI handler treats a
# chunked request (no Content-Length) as a zero-length body, since it does
# not honor gunicorn's non-standard `wsgi.input_terminated` signal -- see
# CUTOVER.md. Response-side, Content-Length is recomputed implicitly by the
# ASGI server for the streamed response.
_HOP_BY_HOP_REQUEST_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}
_HOP_BY_HOP_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "connection"}

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _select_backend(settings: Settings, path: str) -> str:
    """Operator-configured, request-independent target selection.

    Never builds a target from request data (header, query string, path
    segment) -- only ever from the two fixed base URLs in ``settings`` --
    which keeps this proxy's dynamic-URI seam closed to SSRF: no caller can
    redirect it to an arbitrary host.
    """
    if settings.review_enabled and path.startswith("/api/reviews"):
        return settings.review_base_url
    if settings.notification_enabled and path.startswith("/api/notifications"):
        return settings.notification_base_url
    if settings.inventory_enabled and path.startswith("/api/inventory"):
        return settings.inventory_base_url
    if settings.payment_enabled and path.startswith("/api/payments"):
        return settings.payment_base_url
    if settings.shipping_enabled and path.startswith("/api/shipments"):
        return settings.shipping_base_url
    return settings.monolith_base_url


def _forward_request_headers(request: Request) -> list[tuple[bytes, bytes]]:
    return [
        (name, value)
        for name, value in request.headers.raw
        if name.decode("latin-1").lower() not in _HOP_BY_HOP_REQUEST_HEADERS
    ]


def _forward_response_headers(upstream: httpx.Response) -> list[tuple[str, str]]:
    return [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in upstream.headers.raw
        if name.decode("latin-1").lower() not in _HOP_BY_HOP_RESPONSE_HEADERS
    ]


async def _iter_upstream_body(upstream: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await upstream.aclose()


async def proxy_handler(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    client: httpx.AsyncClient = request.app.state.http_client

    path = request.url.path
    base_url = _select_backend(settings, path)
    query = request.scope.get("query_string", b"")
    target_url = base_url.rstrip("/") + path + (f"?{query.decode('latin-1')}" if query else "")

    # Buffer the inbound body rather than forwarding `request.stream()`
    # unread: for the small, API-sized payloads this teaching proxy handles,
    # this lets httpx compute a correct Content-Length for the upstream
    # request instead of falling back to chunked transfer-encoding, which a
    # WSGI upstream (the monolith) does not reliably decode -- see the note
    # above `_HOP_BY_HOP_REQUEST_HEADERS`.
    body = await request.body()

    upstream_request = client.build_request(
        method=request.method,
        url=target_url,
        headers=_forward_request_headers(request),
        content=body,
    )

    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        # Bridge semantics, httpx-flavored: an unreachable/broken upstream is
        # a real 502, never a swallowed 200. This is what the negative-check
        # test (review-service down) depends on.
        logger.warning("upstream request failed: %s %s -> %s", request.method, target_url, exc)
        return Response(
            content=f"strangler-proxy: upstream unavailable ({exc.__class__.__name__})",
            status_code=502,
            media_type="text/plain",
        )

    return StreamingResponse(
        _iter_upstream_body(upstream_response),
        status_code=upstream_response.status_code,
        headers=dict(_forward_response_headers(upstream_response)),
    )


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> Starlette:
    """App factory. ``settings``/``http_client`` overrides exist for tests --
    they let a test stand up two independently configured proxy instances
    (flag off / flag on) in the same process, each wired to in-process stub
    backends via a custom ``httpx.AsyncClient`` transport, without touching
    environment variables or module-level global state.
    """
    resolved_settings = settings if settings is not None else default_settings

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.settings = resolved_settings
        # Exactly ONE shared AsyncClient for the lifetime of the app: reused
        # connections (keep-alive pooling) instead of one client per request.
        client = http_client if http_client is not None else httpx.AsyncClient()
        app.state.http_client = client
        try:
            yield
        finally:
            await client.aclose()

    return Starlette(
        routes=[Route("/{path:path}", proxy_handler, methods=_ALL_METHODS)],
        lifespan=lifespan,
    )


app = create_app()
