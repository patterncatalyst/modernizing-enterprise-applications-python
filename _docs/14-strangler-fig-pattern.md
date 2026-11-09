---
title: "The Strangler Fig Pattern"
order: 14
part: "The Strangler Fig in Practice"
description: "Fowler's pattern, its three mechanics, and the FastAPI-era strangler proxy: content-based routing from configuration, a 502 fail-safe, and a reversible cutover."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Name the strangler fig's three mechanics (asset capture, intercept, reversible cutover) and the one move that breaks its safety property: retiring the old code before the cutover is proven.
- Read the Starlette and httpx reverse proxy in `app/main.py`: the catch-all route, `_select_backend()` and exclusion-list header forwarding.
- Explain why routing reads only from a frozen `Settings` dataclass, and how that closes an SSRF seam by construction.
- Diagnose the chunked-body bug that left an in-process suite green while every POST, PUT and PATCH reached Django empty.
- Prove a routing decision with a negative check: kill the new backend and require a real 502.
- Match the full `request.url.path`, not a route-relative value.

## Why this matters

Every extraction depends on one piece of plumbing built first: something in front of the monolith that sees every request and can hand any one of them to a different backend without the client noticing. That is the strangler proxy, and every later cutover goes through it. The code is in `examples/01-strangler-proxy/`; its `README.md` covers how to drive it.

{% include excalidraw.html file="strangler-four-moves" alt="Four ordered moves of the strangler fig pattern: intercept, route, incrementally replace, retire, with a reversibility window spanning the first three and a warning about retiring too early" caption="Figure 14.1: The strangler fig's four moves, in the order that matters" %}

## Pattern: Strangler Fig

Martin Fowler named the pattern after the fig that germinates in a host tree's canopy, grows roots around the trunk and eventually stands free while the host rots away inside it. The host keeps standing and doing its job for the entire time the replacement grows around it.

A big-bang rewrite bets the whole migration on one cutover: build the new system in isolation, flip a switch, and hope every untested behavior still matches. If it doesn't, there is no way back, because decommissioning the old system was the point of the flip. The strangler fig replaces that bet with many small reversible ones. Extract one bounded context, prove it behaves identically to the monolith's version, move traffic for that context only, and keep the old code in place, unused but present, until production has proven the cutover. If something is wrong you flip the traffic back and nothing has to be rebuilt.

Three mechanics make it work:

1. **Asset capture.** "Behaves identically" needs an executable definition, a suite that can fail. Here it is the Newman behavior-equivalence collection (`tooling/newman/mea.postman_collection.json`), captured once against the monolith and never rewritten per extraction. Only {% raw %}`{{baseUrl}}`{% endraw %} changes as it is re-pointed at whichever backend is live.
2. **Intercept.** Something must see every request before the monolith does, so that it, not a DNS change or a per-extraction load-balancer rule, decides which backend answers. That is a single process on `:8888` in front of the monolith's `:8000`.
3. **Reversible cutover.** Which backend answers is a configuration value, flippable without a redeploy in either direction while both backends exist. The moment that stops being true, when the old code is deleted, is the one irreversible step, and it comes last.

## The proxy: Starlette and httpx

The proxy is one ASGI application (`app/main.py`) with a single catch-all route:

```python
Route("/{path:path}", proxy_handler, methods=_ALL_METHODS)
```

Every method and path goes to one handler, because a strangler proxy has to be invisible to a client that doesn't know it's there. `_ALL_METHODS` is `GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD`, everything DRF's `APIView` routes already handle, so the proxy never rejects what the monolith would accept.

### Selecting the backend from configuration only

```python
def _select_backend(settings: Settings, path: str) -> str:
    """Operator-configured, request-independent target selection.

    Never builds a target from request data (header, query string, path
    segment) -- only ever from the two fixed base URLs in ``settings`` --
    which keeps this proxy's dynamic-URI seam closed to SSRF: no caller can
    redirect it to an arbitrary host.
    """
    if settings.review_enabled and path.startswith("/api/reviews"):
        return settings.review_base_url
    return settings.monolith_base_url
```

`settings` is a frozen dataclass (`app/config.py`) read once from the environment at start (`STRANGLER_PORT`, `STRANGLER_REVIEW_ENABLED`, `STRANGLER_MONOLITH_BASE_URL`, `STRANGLER_REVIEW_BASE_URL`):

```python
@dataclass(frozen=True, slots=True)
class Settings:
    port: int = 8888
    review_enabled: bool = False
    monolith_base_url: str = "http://localhost:8000"
    review_base_url: str = "http://localhost:8001"
```

| Flag | Backend for `/api/reviews*` | Backend for everything else |
|---|---|---|
| `false` (default) | monolith `:8000` | monolith `:8000` |
| `true` | review-service `:8001` | monolith `:8000` |

A proxy that built its target from a header, a query parameter or a path segment would hand an attacker a request-driven redirect to an arbitrary host, a server-side request forgery (SSRF) vector. Pinning the target set to operator configuration fixed at startup closes that seam by construction, not by convention.

{% include excalidraw.html file="strangler-proxy-routing" alt="The strangler proxy's content-based routing with STRANGLER_REVIEW_ENABLED off versus on, shown as two stacked topologies, each routing client requests through the proxy to either the monolith or the review-service, both against a shared Postgres schema" caption="Figure 14.2: Content-based routing with the flag off and on" %}

### Forwarding the request, body included

`proxy_handler` rebuilds the upstream request: same method, same path plus raw query string, the inbound headers minus a short exclusion list, and the body:

```python
body = await request.body()

upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=body,
)
```

`await request.body()` reads the whole inbound body into memory before forwarding. Buffering is the right trade for API-sized JSON payloads. A proxy fronting large uploads needs another strategy, such as forwarding the client's own `Content-Length`. Headers use an exclusion list, not an allowlist, because a transparent proxy forwards everything and drops only what is wrong to forward:

| Direction | Dropped | Why |
|---|---|---|
| Request | `Host` | Must name the upstream, not the proxy |
| Request | `Content-Length` | The body is buffered and re-sent as `bytes`; httpx computes a fresh, correct `Content-Length` for the upstream request |
| Request/Response | `Transfer-Encoding`, `Connection` | Hop-by-hop per RFC 9110 §7.6.1; an inbound chunked `Transfer-Encoding` must never leak to the (buffered) upstream request, and the response is re-framed by the ASGI server on its own hop |
| Response | `Content-Length` | Recomputed implicitly by the ASGI server for the streamed response |

### Relaying the response

The upstream's status, headers (same exclusions, mirrored) and body come back streamed, not buffered a second time:

```python
return StreamingResponse(
    _iter_upstream_body(upstream_response),
    status_code=upstream_response.status_code,
    headers=dict(_forward_response_headers(upstream_response)),
)
```

A 4xx or 5xx from the backend is relayed exactly as sent. The proxy never raises on it, rewrites it or adds an opinion, so talking to the proxy is indistinguishable from talking to the backend, failures included.

### The 502 fail-safe

When `client.send()` itself fails (connection refused, DNS failure, timeout) the proxy does have an opinion, and a narrow one:

```python
try:
    upstream_response = await client.send(upstream_request, stream=True)
except httpx.HTTPError as exc:
    logger.warning("upstream request failed: %s %s -> %s", request.method, target_url, exc)
    return Response(
        content=f"strangler-proxy: upstream unavailable ({exc.__class__.__name__})",
        status_code=502,
        media_type="text/plain",
    )
```

An unreachable backend is a real `502 Bad Gateway`, never a swallowed `200`. A cutover gate that can't fail loudly when the thing it tests is down proves nothing.

### Match the full path

`_select_backend()` matches `request.url.path`, not `request.path_params["path"]`. For a catch-all route they differ: `request.url.path` is the full path the client sent (`/api/reviews/5`), while `request.path_params["path"]` is the route-relative remainder (`api/reviews/5`). Here they differ only by the leading slash, because the route is mounted at the root. The failure this guards against is real: a strangler proxy matched a route-relative path against a bare `"reviews"` prefix instead of `"/api/reviews"`, and every request fell through to the old backend regardless of the flag, for weeks. The candidate service read and wrote the same shared table as the monolith, so the shared schema masked the false positive. A refactor that mounts this route under a sub-application and "simplifies" the predicate would fail the same way.

**Match the full request path, never a value relative to a route, mount point or consumer prefix.**

## The chunked-body bug

An in-process test suite that never puts a request on a real socket can be green while the system is broken. Equivalence has to be proven against the real thing.

The proxy's in-process suite drives it through `httpx.ASGITransport`, with the proxy and its stub backends in one Python process. It stayed green for a version of `proxy_handler` that forwarded the body as `request.stream()`, an unread async generator. httpx can't know an async generator's length, so it sends such a request with `Transfer-Encoding: chunked` and no `Content-Length`. The monolith is Django behind gunicorn (WSGI), and `WSGIRequest.__init__` reads `environ["CONTENT_LENGTH"]` directly. When the key is absent, as it always is for a chunked request, Django treats the body as zero bytes, because it doesn't honor gunicorn's non-standard `wsgi.input_terminated` signal. Every POST, PUT and PATCH arrived empty, whatever the client sent. The same happens with httpx talking straight to the monolith, no proxy involved.

The in-process transport can't see this: an ASGI server decodes a chunked body correctly, and there is no WSGI `CONTENT_LENGTH` quirk to trip over. The defect exists only on the wire, between a real httpx client and a real WSGI socket. It surfaced the first time the Newman collection ran against the real monolith and real proxy together; `tooling/newman/GOLDEN-BASELINE.md` has the reproduction.

The fix buffers the body:

{% include codetabs.html langs="Before (chunked, silently empties POSTs to the monolith)|After (buffered, correct Content-Length)" %}

```python
upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=request.stream(),
)
```

```python
body = await request.body()

upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=body,
)
```

Passing `bytes` lets httpx compute an accurate `Content-Length`, with no header manipulation, because `Content-Length` and `Transfer-Encoding` are already on the inbound drop list. The upstream request now carries a `Content-Length` equal to the body length, no `Transfer-Encoding: chunked`, and the exact bytes the client sent. A framing check on the outbound request through `httpx.MockTransport` guards it, the one wire-level check the in-process suite lacked.

## The reversibility window and the cutover evidence

{% include excalidraw.html file="strangler-cutover-timeline" alt="Timeline of four Newman runs against the strangler proxy: flag off baseline, flag on cutover, flag off reverted, and a negative check with the review-service killed returning 502s by design, with decommission ghosted as a future irreversible step" caption="Figure 14.3: The cutover evidence trail, one unedited Newman suite run four times" %}

`examples/01-strangler-proxy/CUTOVER.md` records that `STRANGLER_REVIEW_ENABLED` is a safe, reversible switch against a live stack: Postgres, the monolith and `examples/02-review-service`, all running. The same unedited Newman collection ran four times, changing only the flag and whether a backend was up:

| Run | Setup | Result (CUTOVER.md) |
|---|---|---|
| Baseline | Flag off, monolith serves reviews | 19 requests, 38 test scripts, 58 assertions, 0 failed |
| Cutover | Flag on, `examples/02-review-service` serves reviews | 58/58, 0 failed |
| Reverted | Flag off again, restart | 58/58, 0 failed. Flipping back is a config change and a restart |
| Negative check | Flag on, review-service killed, Review folder only | 6/6 assertions failed, exit code 1, every `/api/reviews*` request answered by the proxy's real 502. After restarting the service: 16/16 green |

The fourth run matters most. A gate that can't go red when the thing it gates is broken is a suite that happens to pass, and proving that it fails loudly is what makes the green runs around it trustworthy.

## Decommission comes last

Nothing in this build removes the monolith's `review` module. A reversible cutover means both backends exist side by side until the new one has run in production long enough that reverting is no longer a realistic contingency. Decommissioning, the full cure for the monolith's smell #7, means deleting the code and dropping it from the schema's reach. The flag then stops choosing between two live backends and becomes a historical artifact. Until then the fallback is real, because reversibility is a property of what still exists, not of good intentions.

> **Decision**
>
> Put the proxy in front first, route by operator configuration only, and cut over one context behind a flag. Delete the old code only after the same unedited equivalence suite has passed in both directions and failed with the new backend stopped.

> **🤖 Explore with your agent**
>
> "On the `stage/01-review` tag, in `examples/01-strangler-proxy/`, add a route that sends `/api/inventory` to a second backend behind its own `STRANGLER_INVENTORY_ENABLED` flag, read only from the frozen `Settings` dataclass and matched against `request.url.path`. Show the routing result with the flag off and on, and what the client receives when that backend is down."
>
> Check: `curl -i` through `:8888` returns the monolith's response with the flag off, the new backend's with it on, and a `502` with the new backend stopped.

## Build, run, observe

The proxy on `main` is now a flagless edge router, because every context has since been cut over. The flag-gated proxy described here is at the `stage/01-review` tag (`git checkout stage/01-review`).

```bash
cd examples/01-strangler-proxy
uv sync
uv run uvicorn app.main:app --port 8888
```

With the monolith on `:8000`, every request through `:8888` reaches it unchanged, because `STRANGLER_REVIEW_ENABLED` defaults to `false`. To cut Review over, with `examples/02-review-service` running on `:8001`:

```bash
STRANGLER_REVIEW_ENABLED=true uv run uvicorn app.main:app --port 8888
```

`/api/reviews*` now answers from the review service and every other path is unaffected. Set the variable back and restart to revert. Run the in-process checks:

```bash
uv run pytest       # 8 tests, in-process ASGI stub backends, no real sockets
uv run ruff check .
```

Then drive the real socket path:

```bash
curl -i -X POST http://localhost:8888/api/reviews \
  -u reviewer:review-pw-r02 -H 'Content-Type: application/json' \
  -d '{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "Great"}'
```

With the flag off the request reaches the monolith, with it on the review service. Both answer `201` with the same response shape. A green pytest run with a failing `curl` is the gap the chunked-body bug hid in.

- **Stop the review service** with the flag on and repeat the `curl`: the proxy answers `502`, not a soft pass.
- **Forward `request.stream()`** instead of the buffered body: POSTs to the monolith arrive empty while the in-process tests stay green.

## For deeper coverage

Martin Fowler's [StranglerFigApplication](https://martinfowler.com/bliki/StranglerFigApplication.html) names the pattern. The bibliography page lists the books.
