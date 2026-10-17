---
title: "The Strangler Fig Pattern"
order: 14
part: "The Strangler Fig in Practice"
description: "Fowler's pattern, the three steps, the proxy/redirection/shared-database variants, and the FastAPI-based strangler proxy used for cutover in this book."
duration: 35 minutes
---

Every extraction in Part 5 depends on one piece of plumbing getting built
first: something that sits in front of the monolith, sees every request,
and can hand any one of them to a different backend without the client
ever noticing. That's the strangler fig proxy, and it's the one new idea
this chapter teaches — everything from ch.15 onward (the Review service,
and every extraction after it) cuts over through the same mechanism this
chapter builds and proves.

The code is in `examples/01-strangler-proxy/`. The run script there builds/
sets up and runs it; its `README.md` covers what it does and how to drive
it.

{% include excalidraw.html file="strangler-four-moves" alt="Four ordered moves of the strangler fig pattern: intercept, route, incrementally replace, retire, with a reversibility window spanning the first three and a warning about retiring too early" caption="Figure 14.1 — The strangler fig's four moves, in the order that matters" %}

## Fowler's pattern, and why incremental beats big-bang

Martin Fowler named this pattern after the strangler fig tree, which
germinates in the canopy of a host tree, sends roots down around the
trunk, and over years grows into a free-standing structure — at which
point the original tree, no longer needed, can rot away inside the fig's
shell without the whole structure ever coming down. The metaphor earns its
keep because it names what a rewrite doesn't have: **the host keeps
standing, and keeps doing its job, for the entire time the replacement is
growing around it.**

A big-bang rewrite bets the whole migration on one cutover event: build
the new system in isolation, flip a switch, and hope every behavior you
didn't think to test still matches. If it doesn't, there's no graceful way
back — the old system is usually already decommissioned, or decommissioning
it was the point of flipping the switch at all. The strangler fig pattern
replaces that one high-stakes bet with many small, independently
reversible ones: extract one bounded context, prove it behaves identically
to the monolith's version of that context, cut traffic for *that context
only* over to the new service, and keep the monolith's old code in place
(unused, but present) until the cutover has been proven in production. If
something's wrong, you flip the traffic back. Nothing was deleted, so
nothing has to be rebuilt to recover.

That's also why this book builds the walking skeleton the way it does:
ch.08-ch.13 built one over-coupled monolith with six bounded
contexts in one shared schema, `review` among them — not because a
six-context monolith is a good design, but because it's the thing a real
strangler fig migration has to incrementally dismantle without ever taking
the system down. This chapter builds the first piece of that dismantling
machinery; ch.15 uses it to pull `review` out of the running system.

Three mechanics make this work, and all three show up concretely in
`examples/01-strangler-proxy`:

1. **Asset capture.** Before anything moves, you need a precise, executable
   definition of what "behaves identically" means — not a description, a
   suite that can fail. For this book that's the Newman behavior-equivalence
   collection (`tooling/newman/mea.postman_collection.json`), captured once
   against the monolith and never rewritten per extraction, only re-pointed
   at whichever backend is live ({% raw %}`{{baseUrl}}`{% endraw %} is the one thing that
   changes). ch.10 built the monolith-side tests that gave this collection
   something real to assert against; this chapter is the first time the
   same collection gets pointed at something *other* than the monolith.
2. **Intercept.** Something has to see every request before the monolith
   does, so that *it* — not a DNS change, not a load-balancer rule touched
   per extraction — decides which backend actually answers. That's the
   proxy this chapter builds: a single process on `:8888` in front of the
   monolith's `:8000`.
3. **Reversible cutover.** The decision of which backend answers a given
   request has to be a configuration value, not a code change — flippable
   without a redeploy, in either direction, for as long as both backends
   still exist side by side. The moment that stops being true (the old
   backend's code is deleted) is the one irreversible step in the whole
   pattern, and it comes last, never first.

## How it's implemented here: a Starlette + httpx reverse proxy

The proxy is one ASGI application (`app/main.py`), built on Starlette (for
routing and request/response types) and httpx (for the outbound HTTP
calls), with a single catch-all route:

```python
Route("/{path:path}", proxy_handler, methods=_ALL_METHODS)
```

Every method, every path, one handler. That's deliberate: a strangler
proxy's job is to be *invisible* to a client that doesn't know it's there,
which means it can't afford to special-case anything the client might
plausibly send. `_ALL_METHODS` is `GET, POST, PUT, PATCH, DELETE, OPTIONS,
HEAD` — the full set DRF's `APIView` routes already handle on the monolith
side, so nothing the monolith would accept gets rejected by the proxy
first.

### Selecting the backend: operator config only, never request data

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

Two things matter here beyond the obvious if/else. First, `settings` is a
frozen dataclass (`app/config.py`) read once from the environment at
process start — `STRANGLER_PORT`, `STRANGLER_REVIEW_ENABLED`,
`STRANGLER_MONOLITH_BASE_URL`, `STRANGLER_REVIEW_BASE_URL` — and never
touched again while the process runs. That's not just tidiness: a proxy
that built its forwarding target from anything on the inbound request (a
header, a query parameter, a path segment) would hand an attacker a
request-driven redirect to an arbitrary host — a textbook server-side
request forgery (SSRF) vector. Pinning the target set to operator
configuration, fixed at startup, closes that seam by construction, not by
convention. Second, the match is against `path` — `request.url.path`, the
**full** path the client sent (`/api/reviews/5`), never a value relative to
some mount point. The "full-path-prefix lesson" sidebar below explains why
that distinction gets its own callout, not just a comment.

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

{% include excalidraw.html file="strangler-proxy-routing" alt="The strangler proxy's content-based routing with STRANGLER_REVIEW_ENABLED off versus on, shown as two stacked topologies, each routing client requests through the proxy to either the monolith or the review-service, both against a shared Postgres schema" caption="Figure 14.2 — Content-based routing: the flag OFF vs ON" %}

### Forwarding the request, verbatim — including the body

`proxy_handler` rebuilds the upstream request from the inbound one: same
method, same target path plus raw query string, the same headers (minus a
short hop-by-hop exclusion list), and the body:

```python
body = await request.body()

upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=body,
)
```

`await request.body()` fully reads the inbound request into memory before
forwarding it, rather than passing Starlette's `request.stream()` through
unread. That choice is the subject of this chapter's teaching sidebar below
— it isn't free, but the alternative silently breaks every `POST`/`PUT`/
`PATCH` the proxy sends to the monolith. Buffering the whole body is the
right trade for this teaching proxy's small, API-sized JSON payloads; a
proxy fronting large file uploads would need a different strategy (for
example, forwarding the inbound `Content-Length` when the client already
supplied one).

Headers get a short, deliberate exclusion list — not a allowlist, an
exclusion list, because the default for a transparent proxy is to forward
*everything* and only drop what's actively wrong to forward:

| Direction | Dropped | Why |
|---|---|---|
| Request | `Host` | Must name the upstream, not the proxy |
| Request | `Content-Length` | The body is buffered and re-sent as `bytes`; httpx computes a fresh, correct `Content-Length` for the upstream request |
| Request/Response | `Transfer-Encoding`, `Connection` | Hop-by-hop per RFC 9110 §7.6.1; an inbound chunked `Transfer-Encoding` must never leak to the (buffered) upstream request, and the response is re-framed by the ASGI server on its own hop |
| Response | `Content-Length` | Recomputed implicitly by the ASGI server for the streamed response |

### Relaying the response, verbatim

The upstream's real status code, headers (same exclusions, mirrored), and
body come straight back, streamed rather than buffered a second time:

```python
return StreamingResponse(
    _iter_upstream_body(upstream_response),
    status_code=upstream_response.status_code,
    headers=dict(_forward_response_headers(upstream_response)),
)
```

A 4xx or 5xx from the backend is relayed exactly as the backend sent it —
the proxy never raises on it, never rewrites it, never adds its own
opinion. This is the httpx analogue of a bridging HTTP gateway that passes
failure responses through rather than converting them into its own error
shape: from the client's point of view, talking to the proxy must be
indistinguishable from talking to the backend directly, failures included.

### The 502 fail-safe

Everything above assumes `client.send()` succeeds. When it doesn't —
connection refused, DNS failure, a timeout — that's a different class of
failure, and the proxy treats it as one:

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

This is the one place the proxy *does* have its own opinion, and it's a
narrow one: an unreachable backend is a real `502 Bad Gateway`, never a
swallowed `200`. That distinction is what makes the negative check later
in this chapter meaningful — a cutover gate that can't fail loudly when the
thing it's supposed to be testing is down isn't proving anything.

### The full-path-prefix lesson

`_select_backend()` matches `request.url.path`, not
`request.path_params["path"]` — Starlette hands both back for a catch-all
route like `Route("/{path:path}")`, and they are *not* the same string.
`request.url.path` is the full path the client sent (`/api/reviews/5`,
leading slash and all); `request.path_params["path"]` is the
route-pattern-relative value (`api/reviews/5`, no leading slash — whatever
is left over after Starlette strips the pattern's own fixed prefix, which
here is nothing, because the route is mounted at the application root).
Today those two values happen to differ only by a leading slash, because
this proxy has no mount point to be relative to. But the distinction is
worth naming explicitly, because getting it backwards is a known failure
mode in exactly this kind of code — a sibling Camel-based strangler proxy
in this book's sister project matched a route-relative path against a bare
`"reviews"` prefix instead of the full `"/api/reviews"`, and every request
silently fell through to the old backend regardless of the flag, for weeks,
because the review candidate happened to read and write the same shared
table the monolith did (a false positive masked by the shared schema — see
ch.18 for why that shared-schema situation is itself a smell this book
cures later). If a future refactor ever mounts this route under a
sub-application or a path prefix, and someone "simplifies" the predicate to
check the relative value against a bare `"reviews"` string, this proxy
would fail exactly the same way. `tests/test_routing.py` asserts the
routing decision against the real `request.url.path` behavior, both with
and without the flag, specifically so this cannot regress silently.

**Always match the full request path — never a value relative to a route,
mount point, or consumer prefix.**

## The chunked-body bug: in-process green is not real-socket green

> **Lesson.** A test suite that never puts a real request on a real socket
> against a real server can be green while the system it's testing is
> broken. Equivalence has to be proven against the real thing.

`examples/01-strangler-proxy/tests/test_routing.py` drives the proxy
entirely in-process, via `httpx.ASGITransport` — no TCP connection, no real
server, both the proxy and its stub backends living in the same Python
process. That suite was fully green, every case covered: routing under
both flag states, pass-through fidelity, a relayed 4xx/5xx, the 502
fail-safe. And it was green for a version of `proxy_handler` that forwarded
the inbound body as `request.stream()` — an unread async generator —
instead of buffering it.

Here's the defect that hid underneath the green suite. httpx cannot know
the length of an async generator ahead of time, so it always sends a
request built from one with `Transfer-Encoding: chunked` and no
`Content-Length`. The monolith is Django behind gunicorn — WSGI, not ASGI —
and Django's `WSGIRequest.__init__` reads `environ["CONTENT_LENGTH"]`
directly; when that key is absent (which it always is for a chunked
request), Django falls back to treating the body as **zero bytes**, because
it doesn't honor gunicorn's non-standard `wsgi.input_terminated` signal for
chunked requests. The result: every `POST`, `PUT`, or `PATCH` the proxy
forwarded to the monolith arrived empty, no matter what the client actually
sent — and it reproduces with zero proxy involvement at all, just httpx
talking directly to the monolith with a chunked body versus a
`Content-Length`-bearing one.

The in-process test suite could never have caught this, by construction:
`httpx.ASGITransport` hands the request straight to the ASGI application
object in-memory, and an ASGI server decodes a chunked body correctly
regardless of framing — there's no WSGI `CONTENT_LENGTH` quirk to trip over
inside that transport. The defect only exists on the wire, between a real
httpx client and a real WSGI socket, which is exactly the gap between
"the proxy's own unit tests pass" and "the equivalence suite passes against
the live stack." It surfaced the first time the Newman behavior-equivalence
collection ran against the real monolith and the real proxy together, over
real sockets — see `tooling/newman/GOLDEN-BASELINE.md` for the full
reproduction.

The fix buffers the body instead of streaming it through unread:

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

Forwarding `bytes` instead of an unread stream lets httpx compute a
correct, accurate `Content-Length` for the upstream request — no extra
header manipulation needed, because `Content-Length` and `Transfer-Encoding`
were already in the hop-by-hop drop list on the inbound side. A new
regression test, `test_post_body_forwarded_with_content_length_not_chunked`,
captures the actual outbound request the proxy builds via
`httpx.MockTransport` and asserts directly on its framing: it must carry a
`Content-Length` equal to the real body length, must *not* carry
`Transfer-Encoding: chunked`, and must deliver the exact bytes the client
sent. That test closes the specific gap `ASGITransport` could never see —
not by replacing the in-process suite, but by adding the one assertion that
only matters at the wire level.

## The reversibility window and the cutover evidence

{% include excalidraw.html file="strangler-cutover-timeline" alt="Timeline of four Newman runs against the strangler proxy: flag off baseline, flag on cutover, flag off reverted, and a negative check with the review-service killed returning 502s by design, with decommission ghosted as a future irreversible step" caption="Figure 14.3 — The cutover evidence trail: one unedited Newman suite, four runs" %}

`examples/01-strangler-proxy/CUTOVER.md` is the narrative record of the
claim this whole chapter exists to support: that `STRANGLER_REVIEW_ENABLED`
is a safe, reversible cutover switch, not just in theory but against a live
stack (Postgres, the monolith, and `examples/02-review-service`, all
actually running). The same unedited Newman collection ran four times,
changing only the flag and whether a backend was up:

1. **Baseline, flag off.** Reviews served by the monolith:
   **19 requests / 38 test-scripts / 58 assertions, 0 failed.**
2. **Cutover, flag on.** Reviews served by `examples/02-review-service`,
   everything else still the monolith: **58/58, 0 failed** — identical in
   shape to run 1.
3. **Reverted, flag off.** Flip back, restart: **58/58, 0 failed.** The
   reversibility window is still open — flipping back is a config
   change plus a restart, right up until the monolith's `review` app is
   decommissioned, which has not happened yet.
4. **Negative check.** Flag on, `examples/02-review-service` killed, only
   the Review folder run: every `/api/reviews*` request gets the proxy's
   real `502`, not a soft pass — **6/6 assertions failed, exit code 1**, as
   required. Restart the review-service and re-run: **16/16 green.**

That fourth run matters most. An equivalence gate that
can't go red when the thing it's gating is actually broken isn't an
equivalence gate — it's a suite that happens to pass. Proving the gate
fails *loudly*, by design, in a controlled negative test, is what makes
every one of the green runs around it trustworthy.

## Decommission: the one step this chapter doesn't take yet

Nothing in this chapter's build removes the monolith's `review` module.
That's deliberate — the whole premise of a reversible cutover is that both
backends keep existing, side by side, until the new one has been proven in
production for long enough that reverting is no longer a realistic
contingency. Decommissioning the monolith's `review` app (smell #7's
eventual full cure) is a later, separate step: delete the code, drop it
from the schema's reach, and the flag stops being a choice between two
live backends and becomes a historical artifact of how the cutover
happened. Until that happens, the fallback stays real.

## Build, run, observe

```bash
cd examples/01-strangler-proxy
uv sync
uv run uvicorn app.main:app --port 8888
```

With the monolith running on `:8000`, every request through `:8888` reaches
it unchanged — `STRANGLER_REVIEW_ENABLED` defaults to `false`. To cut
Review over:

```bash
STRANGLER_REVIEW_ENABLED=true uv run uvicorn app.main:app --port 8888
```

With `examples/02-review-service` also running on `:8001`, `/api/reviews*`
now answers from there instead; every other path is unaffected. Flip the
environment variable back and restart to revert.

## Cross-check

Run the proxy's own test suite alongside a manual check against the live
stack — agreement between the two is the point:

```bash
uv run pytest       # 7 tests, in-process ASGI stub backends, no real sockets
uv run ruff check .
```

Then drive the real path the in-process suite can't see:

```bash
curl -i -X POST http://localhost:8888/api/reviews \
  -u reviewer:review-pw-r02 -H 'Content-Type: application/json' \
  -d '{"customerId": 1, "sku": "SKU-WIDGET-001", "rating": 5, "comment": "Great"}'
```

With the flag off, that request reaches the monolith; with it on, it
reaches `examples/02-review-service`. Both should answer `201` with the
same response shape — if the pytest suite is green but this `curl` against
the real stack isn't, that gap is exactly the kind the chunked-body bug
hid in, and it's worth re-reading that section before trusting the pytest
result alone.

## What you learned

- The strangler fig pattern replaces one high-stakes rewrite with many
  small, independently reversible cutovers — asset capture (the Newman
  suite), intercept (this proxy), reversible cutover (the flag) — in that
  order, with decommission last.
- A transparent reverse proxy forwards verbatim by default and only departs
  from that for a short, deliberate list of hop-by-hop headers; its routing
  decision must come from operator configuration, never from anything on
  the request, or it's an SSRF vector.
- An in-process test suite and a real-socket equivalence suite answer
  different questions. The chunked-body bug was invisible to one and
  obvious to the other — equivalence has to be proven against the real
  thing: the real monolith, over a live socket, not an in-process stand-in.
- Reversibility is not a property of good intentions; it's a property of
  what still exists. The monolith's `review` module stays in place, unused
  but present, until decommission — the one deliberate, irreversible step,
  still ahead.

Next: ch.15 puts this proxy to work against the live stack, pulling the Review bounded
context out from behind it and proving, with the same Newman suite, that
nothing on the outside can tell the difference.

---

*Verification status: <span class="status status--verified">verified</span>.
The proxy's pytest suite and the live Newman equivalence run
(`tooling/newman/GOLDEN-BASELINE.md`) both pass against a real stack:
58/58 assertions green with the flag off, on, and reverted, and the
review-service-down negative check fails loudly as required, then recovers
once restarted.*
