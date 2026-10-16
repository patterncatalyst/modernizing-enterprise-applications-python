# The Strangler-Fig Proxy — a thin ASGI reverse proxy

This is the Python/ASGI analogue of the Java/Camel strangler-fig proxy
(`modernizing-enterprise-applications/examples/01-strangler-proxy`,
`StranglerProxyRoute`) — a standalone process that sits in front of the
Django/DRF monolith (`examples/00-monolith/`, port `:8000`) so that bounded
contexts can be peeled off onto their own services **one seam at a time**,
with clients none the wiser about which backend actually answered a given
request.

For r02 this proxy carries exactly one seam: Review (DRQ-019), to be served
by a sibling lane's `examples/02-review-service/` (port `:8001`) once it
cuts over. The shape generalizes the same way the Java version's did across
its six eventual flags — this build intentionally stops at one, per the
r02 scope.

## The pattern

A **facade in front of both systems** decides, per request, which one
answers:

```
            ┌──────────────────┐
 client --> │  strangler proxy │ --> monolith :8000             (default)
            │       :8888      │ --> review-service :8001 (once cut over)
            └──────────────────┘
```

Every request is reverse-proxied **as-is**: same HTTP method, path, raw
query string, headers, and body go out; the backend's actual status code,
body, and headers come straight back. The proxy introduces zero observable
difference versus talking to a backend directly.

## The implementation

One Starlette ASGI app (`app/main.py`), one catch-all route
(`Route("/{path:path}")`, all methods), one shared `httpx.AsyncClient`
created and closed by the app's `lifespan`:

1. **Select the backend** — `_select_backend()` checks the flag and the
   request's full path; never anything else (see "The full-path-prefix
   lesson" below).
2. **Forward** — `client.build_request()` + `client.send(..., stream=True)`
   rebuilds the upstream request from the inbound one: same method, same
   target path + raw query string, same headers (minus the hop-by-hop ones
   listed below), and the request body **buffered** via `await
   request.body()` and forwarded as plain `bytes`. Buffering (rather than
   forwarding `request.stream()` unread) is deliberate: it lets httpx compute
   a correct `Content-Length` for the upstream request instead of falling
   back to `Transfer-Encoding: chunked`. That distinction matters here
   because the monolith is WSGI (Django) — its handler reads `CONTENT_LENGTH`
   and treats a missing one (always the case for a chunked request) as a
   **zero-length body**, since it does not honor the non-standard
   `wsgi.input_terminated` signal gunicorn sets for chunked requests. Without
   this, every `POST`/`PUT`/`PATCH` routed to the monolith through the proxy
   would silently arrive empty. Buffering the whole body in memory is the
   right trade for this teaching proxy's small, API-sized JSON payloads; a
   production proxy fronting large uploads would need a different strategy
   (e.g. forwarding the inbound `Content-Length` when present, or a real
   chunked-aware upstream).
3. **Relay** — the upstream's real `status_code`, headers (same hop-by-hop
   exclusions), and body (streamed back via `StreamingResponse` +
   `upstream.aiter_raw()`) are returned unchanged. A 4xx/5xx from the
   backend is relayed as-is — the proxy itself never raises on it. This is
   the httpx analogue of Camel's `http` producer with
   `bridgeEndpoint=true&throwExceptionOnFailure=false`.
4. **Upstream connect failure is a real 5xx.** If `client.send()` itself
   raises (`httpx.HTTPError` — connection refused, DNS failure, timeout,
   ...), the handler catches it and returns `502 Bad Gateway` with a short
   plain-text body. It never gets swallowed into a `200`.

Hop-by-hop adjustments (the only headers NOT forwarded verbatim):

| Direction | Dropped | Why |
|---|---|---|
| Request | `Host` | Must name the upstream, not the proxy |
| Request | `Content-Length` | The body is buffered and re-sent as `bytes`; httpx computes a fresh, correct `Content-Length` for the upstream request |
| Request/Response | `Transfer-Encoding`, `Connection` | Hop-by-hop per RFC 9110 §7.6.1; an inbound chunked `Transfer-Encoding` must never leak to the (buffered) upstream request, and the response is re-framed by the ASGI server on its own hop |
| Response | `Content-Length` | Recomputed implicitly by the ASGI server for the streamed response |

## Configuration (operator-only — never request-derived)

All three targets are read once from the environment at process start
(`app/config.py`). The route **never** builds a target URI from request
data (header, query string, path segment) — only from these fixed,
operator-configured values — which keeps the dynamic-URI seam closed to
SSRF: no caller can redirect the proxy to an arbitrary host.

| Variable | Default | Meaning |
|---|---|---|
| `STRANGLER_PORT` | `8888` | Port uvicorn binds |
| `STRANGLER_REVIEW_ENABLED` | `false` | Cutover flag for the Review seam |
| `STRANGLER_MONOLITH_BASE_URL` | `http://localhost:8000` | Default backend |
| `STRANGLER_REVIEW_BASE_URL` | `http://localhost:8001` | Review backend, once cut over |
| `STRANGLER_NOTIFICATION_ENABLED` | `false` | Cutover flag for the Notification seam |
| `STRANGLER_NOTIFICATION_BASE_URL` | `http://localhost:8002` | Notification backend, once cut over |
| `STRANGLER_INVENTORY_ENABLED` | `false` | Cutover flag for the Inventory REST-read seam (`/api/inventory*`) |
| `STRANGLER_INVENTORY_BASE_URL` | `http://localhost:8084` | Inventory backend, once cut over |
| `STRANGLER_PAYMENT_ENABLED` | `false` | Cutover flag for the Payment REST-read seam (`/api/payments*`) |
| `STRANGLER_PAYMENT_BASE_URL` | `http://localhost:8085` | Payment backend, once cut over |
| `STRANGLER_SHIPPING_ENABLED` | `false` | Cutover flag for the Shipping REST-read seam (`/api/shipments*`) |
| `STRANGLER_SHIPPING_BASE_URL` | `http://localhost:8087` | Shipping backend, once cut over |

| Flag | Backend for `/api/reviews*` | Backend for `/api/notifications*` | Backend for `/api/inventory*` | Backend for `/api/payments*` | Backend for `/api/shipments*` | Backend for everything else |
|---|---|---|---|---|---|---|
| review `false`, notification `false`, inventory `false`, payment `false`, shipping `false` (default) | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` |
| review `true`, notification `false`, inventory `false`, payment `false`, shipping `false` | review-service `:8001` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` |
| review `false`, notification `true`, inventory `false`, payment `false`, shipping `false` | monolith `:8000` | notification-service `:8002` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` |
| review `false`, notification `false`, inventory `true`, payment `false`, shipping `false` | monolith `:8000` | monolith `:8000` | inventory-service `:8084` | monolith `:8000` | monolith `:8000` | monolith `:8000` |
| review `false`, notification `false`, inventory `false`, payment `true`, shipping `false` | monolith `:8000` | monolith `:8000` | monolith `:8000` | payment-service `:8085` | monolith `:8000` | monolith `:8000` |
| review `false`, notification `false`, inventory `false`, payment `false`, shipping `true` | monolith `:8000` | monolith `:8000` | monolith `:8000` | monolith `:8000` | shipping-service `:8087` | monolith `:8000` |
| review `true`, notification `true`, inventory `true`, payment `true`, shipping `true` | review-service `:8001` | notification-service `:8002` | inventory-service `:8084` | payment-service `:8085` | shipping-service `:8087` | monolith `:8000` |

The five flags are independent: each gates its own path prefix, and any one
can be flipped without affecting the others. Note that `STRANGLER_INVENTORY_ENABLED`
only governs the REST read surface (`/api/inventory*`) through this proxy —
the monolith's gRPC reserve/release calls to the inventory service are a
separate internal path that never goes through the proxy (see `CUTOVER.md`).
Similarly, `STRANGLER_PAYMENT_ENABLED` only governs the REST read surface
(`/api/payments*`) through this proxy — the monolith's asynchronous payment
capture path is gated by its own `PAYMENT_MODE` setting and never goes
through the proxy (see `CUTOVER.md`). Likewise, `STRANGLER_SHIPPING_ENABLED`
only governs the REST read surface (`/api/shipments*`) through this proxy —
the monolith's shipment-orchestration path is gated by its own
`SHIPPING_MODE` setting and never goes through the proxy (see `CUTOVER.md`).

Flipping the flag is a config change plus a restart, not a code change —
that is what makes the cutover (and, while the monolith's Review module
still exists, rolling it back) a *reversible* operation. See `CUTOVER.md`
for the evidence trail.

## The full-path-prefix lesson

The Java proxy's `CUTOVER.md` documents a real defect: `platform-http`'s
`CamelHttpPath` carries the request's **full** incoming path (e.g.
`/api/reviews`), not a value relative to the route's own consumer prefix.
The original predicate checked a route-relative `/reviews` prefix, which
never matched `/api/reviews` — every request silently fell through to the
monolith, regardless of the flag, and the bug went unnoticed because the
review-service candidate still read/wrote the same shared table as the
monolith (a false positive masked by the shared schema).

This Python proxy avoids the Camel-specific mechanism that caused that bug
(there is no separate "consumer prefix" to be relative to — Starlette's
catch-all route is mounted at the application root), but the discipline it
teaches still applies directly:

- `_select_backend()` matches **`request.url.path`** — the full path the
  client actually sent, e.g. `/api/reviews/5` — against the full prefix
  `/api/reviews`.
- It deliberately does **not** match `request.path_params["path"]`, which
  is the *route-pattern-relative* value Starlette extracts for
  `{path:path}` (`"api/reviews/5"`, with no leading slash). If a future
  refactor mounts this route under a sub-application or a path prefix, and
  someone switches the predicate to check that relative value against a
  bare `"reviews"` prefix instead of `"api/reviews"`, the predicate will
  silently stop matching and every request will fall through to the
  monolith — the exact same failure mode as the Camel bug, just in a
  different framework's relative-path trap.
- `tests/test_routing.py` asserts routing decisions against the real
  `request.url.path` behavior, both with and without the flag, so this
  cannot regress silently.

**Always match the full request path, never a value relative to a route,
mount point, or consumer prefix.**

## Running it

```bash
# 1. monolith (and, once built, the review-service) already up
cd examples/01-strangler-proxy
uv sync
uv run uvicorn app.main:app --port 8888
# proxy now listening on :8888, STRANGLER_REVIEW_ENABLED defaults to false (-> monolith)
```

To cut Review over:

```bash
STRANGLER_REVIEW_ENABLED=true uv run uvicorn app.main:app --port 8888
```

To cut Notification over (independently of Review):

```bash
STRANGLER_NOTIFICATION_ENABLED=true uv run uvicorn app.main:app --port 8888
```

To cut the Inventory REST-read surface over (independently of the others):

```bash
STRANGLER_INVENTORY_ENABLED=true uv run uvicorn app.main:app --port 8888
```

To cut the Payment REST-read surface over (independently of the others):

```bash
STRANGLER_PAYMENT_ENABLED=true uv run uvicorn app.main:app --port 8888
```

To cut the Shipping REST-read surface over (independently of the others):

```bash
STRANGLER_SHIPPING_ENABLED=true uv run uvicorn app.main:app --port 8888
```

## Testing

```bash
uv run pytest       # in-process ASGI stub backends, no network sockets
uv run ruff check .
```

`tests/test_routing.py` builds two independently configured proxy instances
(flag off / flag on) in the same process via the `create_app()` factory,
each wired to its own `httpx.AsyncClient` mounted onto in-process stub ASGI
backends (no real sockets, no running servers) — proving the proxy is
reconfigurable per-instance, not hard-wired to a single process-global flag.
It covers: routing under the Review/Notification/Inventory/Payment/Shipping
flag combinations (each flag independent of the others), pass-through
fidelity (method, path, query string, headers, body), a real upstream 4xx/5xx
relayed unchanged, and upstream-down cases (Review, Notification, Inventory,
Payment, and Shipping) that must surface a real `502`, never a masked `200`.
