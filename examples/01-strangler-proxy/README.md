# The Strangler-Fig Proxy — a thin ASGI reverse proxy

This is the Python/ASGI analogue of the Java/Camel strangler-fig proxy
(`modernizing-enterprise-applications/examples/01-strangler-proxy`,
`StranglerProxyRoute`) — a standalone process that sat in front of the
Django/DRF monolith (`examples/00-monolith/`, port `:8000`) so that bounded
contexts could be peeled off onto their own services **one seam at a time**,
with clients none the wiser about which backend actually answered a given
request.

**r07 status: FLAGLESS EDGE ROUTER.** The strangler-fig arc this proxy was
built for is complete — Review, Notification, Inventory, Payment, Shipping,
and (as of r07) Order have all cut over, and the monolith is decommissioned
from the running topology (frozen in-repo; see
`examples/00-monolith/README.md`). There is no more "default backend" to
fall through to, so every `*_ENABLED` cutover flag and the
`STRANGLER_MONOLITH_BASE_URL` fallback are gone. This proxy is now a plain,
unconditional edge router: six path prefixes, six owning backends, no other
destination exists. The r02-r06 narrative below (the pattern, the flags, the
per-seam cutover history) is preserved as the historical record of how each
seam got here — see `CUTOVER.md` for the full reversibility evidence trail,
including r07's order-cutover proof (the LAST reversible flag flip before
this decommission).

## The pattern (historical — r02 through r07's reversible window)

Through r02-r07, a **facade in front of both systems** decided, per request
and per context, which one answered, gated by that context's own cutover
flag:

```
            ┌──────────────────┐
 client --> │  strangler proxy │ --> monolith :8000             (flag off)
            │       :8888      │ --> review-service :8001 (flag on, once cut over)
            └──────────────────┘
```

As of r07, the flags are gone and the monolith is no longer in the running
topology — see "The flagless edge router (r07)" below for today's shape.

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

## The flagless edge router (r07)

As of r07, `_select_backend()` (`app/main.py`) is an unconditional,
per-context lookup — no boolean flag, no monolith fallback:

```
            ┌──────────────────┐
 client --> │  strangler proxy │ --> review-service       :8001  (/api/reviews*)
            │       :8888      │ --> notification-service :8002  (/api/notifications*)
            │   (flagless)     │ --> inventory-service     :8084  (/api/inventory*)
            │                  │ --> payment-service       :8085  (/api/payments*)
            │                  │ --> shipping-service      :8087  (/api/shipments*)
            │                  │ --> order-service         :8088  (/api/orders*)
            └──────────────────┘ --> (anything else)             404
```

## Configuration (operator-only — never request-derived)

Every target is read once from the environment at process start
(`app/config.py`). The route **never** builds a target URI from request
data (header, query string, path segment) — only from these fixed,
operator-configured values — which keeps the dynamic-URI seam closed to
SSRF: no caller can redirect the proxy to an arbitrary host.

| Variable | Default | Meaning |
|---|---|---|
| `STRANGLER_PORT` | `8888` | Port uvicorn binds |
| `STRANGLER_REVIEW_BASE_URL` | `http://localhost:8001` | Review backend — owns `/api/reviews*`, unconditionally |
| `STRANGLER_NOTIFICATION_BASE_URL` | `http://localhost:8002` | Notification backend — owns `/api/notifications*`, unconditionally |
| `STRANGLER_INVENTORY_BASE_URL` | `http://localhost:8084` | Inventory backend — owns `/api/inventory*`, unconditionally |
| `STRANGLER_PAYMENT_BASE_URL` | `http://localhost:8085` | Payment backend — owns `/api/payments*`, unconditionally |
| `STRANGLER_SHIPPING_BASE_URL` | `http://localhost:8087` | Shipping backend — owns `/api/shipments*`, unconditionally |
| `STRANGLER_ORDER_BASE_URL` | `http://localhost:8088` | Order backend — owns `/api/orders*`, unconditionally |

There is no `STRANGLER_MONOLITH_BASE_URL` and no `*_ENABLED` flag anymore —
removed in r07, along with the monolith itself from the running topology
(see `examples/00-monolith/README.md`'s frozen-status section). A request
whose path matches none of the six prefixes above gets a real `404` straight
from the proxy — never a silent pass-through to some default backend,
because there is no longer a default backend to pass through to. A request
whose owning backend is unreachable gets a real `502` (unchanged from the
pre-r07 behavior) — see "The implementation" above.

`STRANGLER_INVENTORY_BASE_URL` only ever carried the REST read surface
(`/api/inventory*`) through this proxy — gRPC reserve/release calls are, and
always were, a separate internal path that never goes through the proxy.
Likewise `STRANGLER_PAYMENT_BASE_URL`/`STRANGLER_SHIPPING_BASE_URL` only ever
carried their own REST read surfaces; the payment-capture and
shipment-dispatch paths are internal, Kafka-driven sagas that never went
through the proxy either.

See `CUTOVER.md` for the full per-seam reversibility evidence trail,
including r07's: the order seam proven reversible (flag ON → order-service
serves checkout+reads through the proxy; flag OFF → the monolith still
served them) BEFORE the flag, and the monolith, were removed for good.

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
# review-, notification-, inventory-, payment-, shipping-, and order-service
# all already up on their own ports -- no monolith, no flags.
cd examples/01-strangler-proxy
uv sync
uv run uvicorn app.main:app --port 8888
# proxy now listening on :8888, routing all six context prefixes
# unconditionally; anything else is a 404.
```

Each backend's base URL can be overridden independently (e.g. pointing at a
different host/port in a container or CI runner) via the `STRANGLER_*_BASE_URL`
variables in the table above — there is nothing left to "cut over"; every
seam already has.

## Testing

```bash
uv run pytest       # in-process ASGI stub backends, no network sockets
uv run ruff check .
```

`tests/test_routing.py` (rewritten for r07's flagless shape) builds one
fully-wired proxy instance via the `create_app()` factory, with all six
owning backends mounted as in-process stub ASGI apps (no real sockets, no
running servers), and asserts: every `/api/*` prefix routes to its one
owning backend unconditionally (parametrized over all six contexts, plus a
same-instance, all-six-at-once coexistence check); an unmatched path (root,
`/api/unknown`, a near-miss like `/api/order` that is NOT a prefix of
`/api/orders`) is a real `404`, never a silent pass-through — there is no
monolith backend anywhere in this test module; pass-through fidelity
(method, path, query string, headers, body); a real upstream 4xx/5xx relayed
unchanged; and upstream-down cases for all six backends, each surfacing a
real `502`, never a masked `200`, with the failure scoped to only the dead
backend.
