# The r01 Golden Baseline — the FIRST monolith-anchored run

This file freezes the run of `mea.postman_collection.json` captured at **r01**
(the walking skeleton) against the Django monolith (`examples/00-monolith`) —
the only backend that exists at this point in the project. There is nothing
to be "equivalent to" yet in the sense the Java sibling project's later
baselines mean it (no extracted service exists to compare against); this run
establishes the **contract itself**: the externally-observable HTTP behavior
every later extraction will be held to, request-for-request, assertion-for-
assertion, as contexts are pulled out of this monolith one at a time.

**This collection is never rewritten per extraction — only re-pointed.** The
`{{baseUrl}}` variable is the one thing every later iteration changes; every
request and every assertion in `mea.postman_collection.json` stays as written
here until the monolith's own contract itself changes (in which case
this collection changes with it, in the same commit).

## What was run, and against what

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine` container, empty volume, migrated + seeded fresh |
| `examples/00-monolith` (Django 5.2 + DRF) | `:8000` | `uv run python manage.py runserver 0.0.0.0:8000`; checkout is **fully synchronous** — `POST /api/orders` returns the terminal state (`201 CONFIRMED` or the appropriate error) in the same HTTP round-trip, no polling |

The suite was run against `{{baseUrl}}=http://localhost:8000` — the monolith
directly, since no proxy or extracted service exists at r01.

Stock levels were whatever `manage.py seed` produced (`SKU-WIDGET-001` 100,
`SKU-GADGET-002` 50, `SKU-GIZMO-003` 5 — seeded low to exercise the
over-order path with no extra setup). No manual data manipulation was needed
before or between runs: every scenario captures its own "before" stock level
as a collection variable rather than asserting an absolute number, so the
suite is safe to run repeatedly against the same long-lived process.

## Result: fully green, confirmed on two consecutive runs

First run:

```
┌─────────────────────────┬──────────────────┬──────────────────┐
│                         │         executed │           failed │
├─────────────────────────┼──────────────────┼──────────────────┤
│              iterations │                1 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│                requests │               14 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│            test-scripts │               28 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│      prerequest-scripts │               14 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│              assertions │               42 │                0 │
├─────────────────────────┴──────────────────┴──────────────────┤
│ total run duration: 1019ms                                    │
├───────────────────────────────────────────────────────────────┤
│ total data received: 1.71kB (approx)                          │
├───────────────────────────────────────────────────────────────┤
│ average response time: 55ms [min: 34ms, max: 69ms, s.d.: 7ms] │
└───────────────────────────────────────────────────────────────┘
```

Second, back-to-back run against the same process (no database reset in
between — proves the suite's "capture stock before" pattern is idempotent,
not an artifact of a clean database):

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                14 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                28 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                14 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                42 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 1055ms                                     │
├────────────────────────────────────────────────────────────────┤
│ total data received: 1.7kB (approx)                            │
├────────────────────────────────────────────────────────────────┤
│ average response time: 57ms [min: 31ms, max: 95ms, s.d.: 12ms] │
└────────────────────────────────────────────────────────────────┘
```

Zero failures on both runs, newman 6.2.3.

## Folders/scenarios and what each strictly asserts

1. **Smoke** — target reachable; `GET /api/inventory` returns `200` with all
   three seeded SKUs present (`SKU-WIDGET-001`, `SKU-GADGET-002`,
   `SKU-GIZMO-003`).
2. **Scenario 1 — Happy-Path Checkout** — stock read before; `POST
   /api/orders` for an in-stock line returns `201 Created` + `Location:
   /api/orders/{id}` + `status: "CONFIRMED"` (immediately — no intermediate
   `PENDING` to observe at this synchronous baseline) + correct total/line
   items; `GET /api/orders/{id}` confirms the persisted status; final stock
   read confirms `quantityOnHand` dropped by exactly the ordered quantity.
   Sets `happyPathOrderId`.
3. **Scenario 2 — Out-of-Stock** — stock read before (seeded low on
   `SKU-GIZMO-003`, quantity 5); over-ordering (`999999`) returns `409
   Conflict` / `OUT_OF_STOCK` naming the offending SKU; stock read after
   confirms it is **left untouched** — `InsufficientStock` is raised in
   `inventory/services.py`'s `reserve()` before any write.
4. **Scenario 3 — Payment-Declined** — stock read before; checkout with
   `paymentMethod: "DECLINE"` returns `402 Payment Required` /
   `PAYMENT_DECLINED`; stock read after confirms it is **rolled back to the
   same value** — the single `@transaction.atomic()` in
   `order/services.py`'s `place_order()` (SMELL[ch.22]) spans the inventory
   reservation and the payment capture, so a decline unwinds both together.
5. **Scenario 4 — Shipping-Failure** — stock read before; checkout with a
   `shippingAddress` containing the `SHIP-FAIL` sentinel returns `422
   Unprocessable Entity` / `SHIPPING_FAILED`; stock read after confirms
   **net-zero** — the same `transaction.atomic()` unwinds the inventory
   reservation, the payment capture, and the order row itself (no order is
   ever persisted for this path).

## Why there is no bounded-wait polling here

Every assertion above is a single, immediate check performed right after the
triggering request completes. That is correct at r01: the monolith's checkout
is one synchronous HTTP round-trip inside one Django process talking to one
Postgres database — there is no second service, no message broker, and no
eventual consistency to wait out. The Java sibling project's suite only grows
bounded-wait helpers once *it* reaches an iteration where checkout crosses a
real asynchronous service boundary (its r06). Expect this collection to gain
the same pattern, for the same reason, once this project's own extractions
make `POST /api/orders` return before the terminal state is reached.

## What changes, and what doesn't, as extractions land

- **Doesn't change:** every request path, every request body shape, every
  assertion in this collection's five folders.
- **Does change:** `{{baseUrl}}` — re-pointed at whatever currently fronts the
  system (an extracted service directly, or a strangler-style proxy once one
  exists), the same mechanism the Java sibling project uses.
- **Grows:** new folders get added for each extracted context's own surface
  (payments, shipments, notifications, reviews, inventory list/get-by-sku) the
  same way the Java project's suite grew a "Context Contract" folder per
  extraction — not attempted here at r01 because those surfaces are already
  covered implicitly by Scenarios 1-4's checkout flow and there is nothing yet
  to extract them against.

This run is the first, not the last, time this suite is captured against a
monolith-shaped system. Unlike the Java project's final baseline, this one
does not freeze a "last chance to compare against the monolith" moment — it
freezes the starting contract everything else in this project is built to
preserve.

---

# The r02 NEWMAN-CUTOVER lane — the Review Context Contract, live against the proxy

This section records the **first live run of the behavior-equivalence suite
against real, separately-running processes** for r02's review extraction:
the Django monolith (`examples/00-monolith`), the FastAPI review-service
(`examples/02-review-service`), and the Starlette strangler proxy
(`examples/01-strangler-proxy`) in front of both. It fills in the `TODO`
placeholders in `examples/01-strangler-proxy/CUTOVER.md` with real run
output, per that file's own instructions.

`mea.postman_collection.json` gained one new folder, **Review Context
Contract** (5 requests, R1–R5) — see `README.md` for exactly what each
request asserts. The four pre-existing checkout scenarios and Smoke were
**not edited**.

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, migrated + seeded fresh |
| `examples/00-monolith` | `:8000` | `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000` (also reproduced with `manage.py runserver`, see below) |
| `examples/02-review-service` | `:8001` | `uv run uvicorn app.main:app --port 8001`, `DATABASE_URL` pointed at the same Postgres |
| `examples/01-strangler-proxy` | `:8888` | `uv run uvicorn app.main:app --port 8888`, `STRANGLER_REVIEW_ENABLED` toggled per run below |

## Control run — collection validated directly against the monolith (no proxy)

Before touching the proxy at all, the full collection (existing four
scenarios + the new Review folder) was run straight against `:8000`
(`local.postman_environment.json`) to prove the new folder and the
unedited existing folders are correct on their own terms:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                58 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 777ms                                      │
├────────────────────────────────────────────────────────────────┤
│ total data received: 2.55kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 25ms [min: 2ms, max: 130ms, s.d.: 34ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman 6.2.2.** This is the collection's own
correctness baseline, independent of the proxy.

## Run A — flag OFF, through the proxy (`proxy.postman_environment.json`, `baseUrl=http://localhost:8888`)

`STRANGLER_REVIEW_ENABLED` unset (defaults `false`): reviews should be
served by the monolith, reached through the proxy.

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                1 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                56 │               20 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 793ms                                      │
└──────────────────────────────────────────────────────────────── ┘
```

**Review Context Contract folder: R1, R2, R3, R5 green; R4 (`POST
/api/reviews` with valid auth → `201`) RED** — the proxy returned `400`
instead of `201`, with a DRF `VALIDATION_FAILED` body claiming
`customerId`/`sku`/`rating`/`comment` were all missing, even though the
client sent a complete, valid JSON body. **All four checkout scenarios
also failed for the identical reason** (e.g. Scenario 1b's `POST
/api/orders` got `400` instead of `201`, cascading into 1c/1d; Scenario
2b/3b/4b each got `400 VALIDATION_FAILED` instead of their documented
`409`/`402`/`422` codes). This is not a regression in the four pre-existing
scenarios' own assertions — newman confirmed byte-identical request bodies
reach the monolith directly and produce `201`/`409`/`402`/`422` correctly
(see the control run above and the root cause below).

## Run B — flag ON, through the proxy (same, unedited collection + environment)

Proxy restarted with `STRANGLER_REVIEW_ENABLED=true`, `examples/02-review-service`
running on `:8001`:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                1 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                56 │               17 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 745ms                                      │
└──────────────────────────────────────────────────────────────── ┘
```

**Review Context Contract folder: fully green, 16/16 assertions, R1–R5 all
pass** — including R4 (`201` + `Location` + camelCase echo) and R5 (`400
VALIDATION_FAILED` for `rating: 99`), both now routed to
`examples/02-review-service`. This is the cutover proof: **the identical,
unedited collection and environment, with only the proxy's own
`STRANGLER_REVIEW_ENABLED` flag changed, went from RED to GREEN on exactly
the review-write requests, and nothing else changed** (checkout-scenario
failure count dropped from 20 to 17 — exactly R4's 3 assertions — because
checkout still targets the monolith in both flag states and is unaffected
by the flag).

## Flip-back — flag OFF again (reversibility)

Proxy restarted with `STRANGLER_REVIEW_ENABLED` unset again, same suite:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                1 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                56 │               20 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 790ms                                      │
└──────────────────────────────────────────────────────────────── ┘
```

Back to the Run A shape exactly (R4 red again, routed back to the
monolith) — confirming the flag is a genuine, reversible config switch: no
restart-order dependency, no leftover state from Run B.

## Negative check — review-service down, flag ON: the Review folder MUST go RED

With `STRANGLER_REVIEW_ENABLED=true` and `examples/02-review-service`
killed, only the Review folder was re-run:

```
┌─────────────────────────┬─────────────────┬─────────────────┐
│                         │        executed │          failed │
├─────────────────────────┼─────────────────┼─────────────────┤
│              iterations │               1 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│                requests │               5 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│            test-scripts │              10 │               5 │
├─────────────────────────┼─────────────────┼─────────────────┤
│              assertions │               6 │               6 │
├─────────────────────────┴─────────────────┴─────────────────┤
│ total run duration: 138ms                                   │
└───────────────────────────────────────────────────────────── ┘
```

**newman exited non-zero, 6/6 assertions failed.** Every request got a
real `502 Bad Gateway` from the proxy, e.g.:

```
01. AssertionError  Review list returns 200
                    expected response to have status code 200 but got 502
                    inside "Review Context Contract / R1. List reviews by sku -> 200, camelCase array"
03. JSONError
                    Unexpected token 's' at 1:1
                    strangler-proxy: upstream unavailable (ConnectError)
                    inside "Review Context Contract / R1. List reviews by sku -> 200, camelCase array"
```

(identically for R2–R5: `502` instead of `200`/`401`/`201`/`400`, plus a
`JSONError` parsing the proxy's plain-text `strangler-proxy: upstream
unavailable (ConnectError)` body). This is a real, un-swallowed upstream
failure — exactly the "bridge semantics" `app/main.py` documents — not a
false positive. Restarting `examples/02-review-service` and re-running the
same folder returned to fully green:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                 5 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                10 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                 5 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                16 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 385ms                                      │
└──────────────────────────────────────────────────────────────── ┘
```

newman 6.2.2 for every run above.

## A pre-existing defect discovered while proving this

**UPDATE — fixed.** This section is kept verbatim as the historical record
of how this defect was *found* (good teaching material for ch.14/15: a
real-socket, real-WSGI-upstream cutover run catches a class of bug an
in-process ASGI-only test suite structurally cannot). It was **not** fixed
in the run captured below — see "The r02 PHASE-2 repair lane" at the end of
this file for the fix itself and the corrected, fully-green re-run of this
exact same suite through this exact same proxy, in both flag states, plus
the negative check re-confirmed.

**The full suite could not be made fully green through the proxy in either
flag state at the time this section was written, and this was not a
Review-folder problem.** Root cause, reproduced independently of newman and
of this collection:

`examples/01-strangler-proxy/app/main.py`'s `proxy_handler` always forwards
the inbound request body as `content=request.stream()` — an async
generator — regardless of whether the original client request carried a
known `Content-Length`. Because httpx cannot know the length of an async
generator ahead of time, it always sends the forwarded request with
`Transfer-Encoding: chunked` instead of a `Content-Length` header. This is
correct, RFC-compliant behavior on the wire (confirmed by capturing the raw
bytes the proxy sent to a bare TCP listener standing in for the monolith:
a well-formed chunked body arrived intact). The break is on the **monolith
side**: Django's WSGI handler
(`django/core/handlers/wsgi.py:WSGIRequest.__init__`) does
`content_length = int(environ.get("CONTENT_LENGTH"))`, falling back to `0`
on the `TypeError` raised when `CONTENT_LENGTH` is absent — which it always
is for a chunked request, since gunicorn signals "read until EOF" via the
non-standard `environ["wsgi.input_terminated"] = True` extension instead,
which Django does not honor. The result: Django wraps `wsgi.input` in a
`LimitedStream` capped at **0 bytes**, so it reads an empty body no matter
what the client actually sent, and every `POST` field comes back
`"This field is required."` — reproduced identically whether the monolith
runs under `gunicorn` (sync worker) or `manage.py runserver`, and
independently of the proxy entirely:

```python
# Reproduces with ZERO proxy involvement -- direct httpx against :8000:
async def gen():
    yield b'{"customerId":1,...}'
# content=gen() (chunked)   -> 400 VALIDATION_FAILED, "field required" for everything
# content=b'{"customerId":1,...}' (Content-Length) -> 201 Created, correct
```

**Why it didn't surface in `examples/01-strangler-proxy/tests/test_routing.py`:**
that suite's `test_pass_through_fidelity_method_path_query_headers_body`
drives the proxy entirely in-process via `httpx.ASGITransport`, which never
puts a real chunked-encoded request on a real TCP connection against a
real WSGI server — exactly the gap `examples/01-strangler-proxy/CUTOVER.md`
calls out ("has NOT run the live behavior-equivalence suite against the
real monolith + review-service processes... that is the NEWMAN lane's
job"). This lane's job was to run it live, and this is what that
surfaced.

**Why the Review Context Contract folder still proves the cutover
cleanly despite this:** `examples/02-review-service` is ASGI (FastAPI/
uvicorn), and ASGI servers decode chunked request bodies correctly
regardless of framing (reproduced the same way: the identical
generator-based chunked `POST` against `:8001` returned `201` with the
body intact). So every Review-folder assertion that depends on a POST body
reaching an ASGI backend (Run B, flag ON) is unaffected; only the two
read-asymmetric cases where a review POST has to reach the **monolith**
(Run A, flip-back, and R3's no-body 401 which doesn't touch this
code path at all) are affected, and R3 doesn't exercise a body so it's
unaffected either way.

**One test-design caveat worth flagging honestly:** R5 (`rating: 99` →
expected `400 VALIDATION_FAILED`) happens to still assert `400
VALIDATION_FAILED` when routed to the broken monolith path, because an
*empty* body also fails DRF serializer validation with that same status
and error code (missing required fields) — so R5 passes in Run A/flip-back
for the wrong underlying reason (empty body, not an out-of-range rating).
This was only caught by comparing R5's response body across runs; it does
not affect R4, which has a `Location`-header and echo-body assertion no
empty-body response could satisfy by accident.

**This defect was not fixed as part of the NEWMAN-CUTOVER lane captured
above** — that build was scoped to `tooling/newman/` only, so it blocked the
"full suite green through the proxy in both flag states" acceptance
criterion at the time; the review-specific cutover evidence (the actual
subject of r02's Review extraction) was already genuinely green, reversible,
and failing safely in both directions. **It was fixed in a follow-up
PHASE-2 repair pass** — see below for the fix and the corrected, fully-green
re-run of this identical suite.

## What's new vs. r01

- **Doesn't change:** Smoke and the four checkout scenarios, byte-for-byte.
- **New:** the Review Context Contract folder (R1–R5) and
  `proxy.postman_environment.json`.
- **Confirmed:** the collection re-points cleanly at a third `baseUrl`
  (the proxy, in addition to the monolith and, implicitly, the
  review-service) with zero edits, exactly as r01's "doesn't change" promise
  requires.

---

# The r02 PHASE-2 repair lane — the chunked-body bug, fixed, full suite now GREEN

This section records the follow-up pass that fixes the defect documented
above ("A pre-existing defect discovered while proving this") and re-proves
the full behavior-equivalence suite — Smoke, all four checkout scenarios,
and the Review Context Contract — **fully green through the proxy in both
flag states**, closing the one acceptance criterion the NEWMAN-CUTOVER lane
left open.

## The fix

`examples/01-strangler-proxy/app/main.py`'s `proxy_handler` forwarded the
inbound request body unread, as `content=request.stream()` (an async
generator). httpx cannot know the length of an async generator ahead of
time, so it always sent the upstream request as `Transfer-Encoding: chunked`
with no `Content-Length`. The monolith is WSGI (Django/gunicorn); Django's
`WSGIRequest.__init__` reads `environ["CONTENT_LENGTH"]` and falls back to a
**zero-length body** when it's absent (it does not honor gunicorn's
non-standard `wsgi.input_terminated` signal for chunked requests) — so every
`POST`/`PUT`/`PATCH` the proxy routed to the monolith arrived empty,
regardless of what the client actually sent.

The fix buffers the body instead of streaming it through unread:

```python
# app/main.py, proxy_handler() -- before:
upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=request.stream(),
)

# after:
body = await request.body()

upstream_request = client.build_request(
    method=request.method,
    url=target_url,
    headers=_forward_request_headers(request),
    content=body,
)
```

Forwarding `bytes` instead of a stream lets httpx compute a correct,
accurate `Content-Length` for the upstream request. The inbound
`Content-Length` and `Transfer-Encoding` headers were already stripped by
the existing hop-by-hop header set (`_HOP_BY_HOP_REQUEST_HEADERS` already
included both — no header-stripping change was needed, only the body-
forwarding mechanism). This is a deliberate, scoped trade for a teaching
proxy handling small, API-sized JSON payloads — see
`examples/01-strangler-proxy/README.md` for the fuller rationale and the
production caveat (large uploads would need a different strategy).

## The regression test

`examples/01-strangler-proxy/tests/test_routing.py` gained
`test_post_body_forwarded_with_content_length_not_chunked`. It captures the
*actual outbound upstream request* the proxy builds, via
`httpx.MockTransport` (no live WSGI server needed — the gap this closes is
exactly that the pre-existing suite only ever drove the proxy over
`httpx.ASGITransport`, which decodes chunked bodies fine and so could never
see this class of bug), and asserts directly on its framing and bytes:

- the upstream request carries `Content-Length` equal to the body length;
- it does **not** carry `Transfer-Encoding: chunked`;
- the upstream receives the exact body bytes the client sent.

Confirmed to fail against the pre-fix code (`content=request.stream()`):

```
AssertionError: assert None == '75'
 +  where None = get('content-length')
 +    where get = Headers({..., 'transfer-encoding': 'chunked'}).get
```

— i.e., exactly the bug: no `Content-Length`, `Transfer-Encoding: chunked`
present. Passes against the fix. Full local suite: `uv run pytest` → **8
passed** (the 7 pre-existing tests, unchanged and still green, plus this
one); `uv run ruff check .` → **all checks passed**.

## What was running

Same shape as the NEWMAN-CUTOVER lane above: throwaway `postgres:18.6-alpine`
on `:5432` (`monolith`/`monolith`/`monolith`, migrated + seeded fresh),
`examples/00-monolith` via `uv run gunicorn config.wsgi:application --bind
0.0.0.0:8000` (WSGI — the backend that actually exposed this bug),
`examples/02-review-service` via `uv run uvicorn app.main:app --port 8001`
(same `DATABASE_URL`), and `examples/01-strangler-proxy` via `uv run
uvicorn app.main:app --port 8888` with `STRANGLER_REVIEW_ENABLED` toggled
per run below. `mea.postman_collection.json` was **not edited** — identical
to the NEWMAN-CUTOVER lane's run, only the proxy's code and the flag
changed between runs. newman 6.2.2 for every run below.

## Run A — flag OFF, through the proxy

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                58 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 865ms                                      │
├────────────────────────────────────────────────────────────────┤
│ total data received: 2.43kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 29ms [min: 4ms, max: 133ms, s.d.: 34ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0.** Smoke, all four checkout
scenarios (previously RED — e.g. 1b's `POST /api/orders` had been getting
`400 VALIDATION_FAILED` instead of `201`), and the Review Context Contract's
R4 (`POST /api/reviews` with valid auth, routed to the monolith with the
flag off) are all now green — R4 was the request that most directly proved
the bug, and it now passes.

## Run B — flag ON, through the proxy (same, unedited collection + environment)

Proxy restarted with `STRANGLER_REVIEW_ENABLED=true`,
`examples/02-review-service` running on `:8001`:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                58 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 802ms                                      │
├────────────────────────────────────────────────────────────────┤
│ total data received: 2.65kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 26ms [min: 3ms, max: 123ms, s.d.: 32ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0 — byte-identical shape to Run A**
(same 19 requests / 38 test-scripts / 19 prerequest-scripts / 58 assertions,
0 failed in both). Checkout still targets the monolith in both flag states
and is unaffected by the flag, as expected; Review now served by
`examples/02-review-service`.

## Flip-back — flag OFF again (reversibility)

Proxy restarted with `STRANGLER_REVIEW_ENABLED` unset again, same suite:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                38 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                19 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                58 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 859ms                                      │
├────────────────────────────────────────────────────────────────┤
│ total data received: 2.92kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 28ms [min: 5ms, max: 134ms, s.d.: 34ms] │
└────────────────────────────────────────────────────────────────┘
```

Back to the Run A shape exactly, still fully green — the flag is a genuine,
reversible config switch with no restart-order dependency and no leftover
state from Run B, and the fix holds in both directions.

## Negative check — review-service down, flag ON: the Review folder MUST still go RED

With `STRANGLER_REVIEW_ENABLED=true` and `examples/02-review-service`
killed, only the Review folder was re-run, to confirm the fix did not
quietly weaken the fail-safe the NEWMAN-CUTOVER lane established:

```
┌─────────────────────────┬─────────────────┬─────────────────┐
│                         │        executed │          failed │
├─────────────────────────┼─────────────────┼─────────────────┤
│              iterations │               1 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│                requests │               5 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│            test-scripts │              10 │               5 │
├─────────────────────────┼─────────────────┼─────────────────┤
│              assertions │               6 │               6 │
├─────────────────────────┴─────────────────┴─────────────────┤
│ total run duration: 136ms                                   │
└───────────────────────────────────────────────────────────── ┘
```

**newman exited non-zero (exit code 1), 6/6 assertions failed.** Every
request got a real `502 Bad Gateway` from the proxy, e.g.:

```
01. AssertionError  Review list returns 200
                    expected response to have status code 200 but got 502
                    inside "Review Context Contract / R1. List reviews by sku -> 200, camelCase array"
03. JSONError
                    Unexpected token 's' at 1:1
                    strangler-proxy: upstream unavailable (ConnectError)
                    inside "Review Context Contract / R1. List reviews by sku -> 200, camelCase array"
```

(identically for R2–R5). The fail-safe is still real and un-swallowed — the
body-forwarding fix touched only the request side, not the upstream-down
`502` path. Restarting `examples/02-review-service` and re-running the same
folder returned to fully green:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                 5 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                10 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                 5 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                16 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 393ms                                      │
└──────────────────────────────────────────────────────────────── ┘
```

## Summary

| # | Flag | Review served by | Everything else served by | Result |
|---|---|---|---|---|
| A | `false` | monolith | monolith | **GREEN** — 58/58 assertions, 0 failed |
| B | `true` | review-service | monolith | **GREEN** — 58/58 assertions, 0 failed, byte-identical shape to A |
| C (flip-back) | `false` | monolith | monolith | **GREEN** — 58/58 assertions, 0 failed, identical to A |
| Negative, `true` + review-service down | *(nothing — 502)* | monolith | **RED** — 6/6 assertions failed, newman exit code 1 |
| Negative, recovered | review-service | monolith | **GREEN** — 16/16 assertions, 0 failed |

The full behavior-equivalence suite is now fully green through the proxy in
every flag state the r02 cutover cares about, the collection itself was
never edited, and the fail-safe (a real `502` on a dead upstream, never a
masked `200`) still holds. The acceptance criterion the NEWMAN-CUTOVER lane
left open — "full suite green through the proxy in both flag states" — is
now met.

---

# The r03 NEWMAN-ASYNC lane — the Notification Context Contract, live against real Kafka

This section records the suite's first genuinely **asynchronous** cutover
proof: `mea.postman_collection.json` gained one new, top-level, **env-guarded**
folder, **Notification Context Contract** (2 requests, N1–N2) — see
`README.md` for exactly what each request asserts and for the full bring-up
commands. The five pre-existing folders (Smoke, the four checkout scenarios,
Review Context Contract) were **not edited**. Unlike every prior lane, this
one needs a real Kafka broker end to end: the monolith's outbox relay
(`manage.py outbox_relay`) publishes `order.placed`, and **two independent
consumers** race to read it — the monolith's own
`manage.py order_placed_consumer` (group `monolith-notification`, feeding the
flag-OFF `GET /api/notifications` read model) and
`examples/03-notification-service`'s `aiokafka` consumer (group
`notification-service`, feeding the flag-ON read model).

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, migrated + seeded fresh |
| Kafka | `localhost:9092` | throwaway `apache/kafka:4.3.1` (the repo's pin), single-node KRaft, `KAFKA_AUTO_CREATE_TOPICS_ENABLE=true` (no manual topic creation needed) |
| `examples/00-monolith` | `:8000` | `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000` (WSGI — same backend the r02 PHASE-2 repair lane proved clean of the chunked-body defect) |
| `examples/00-monolith` outbox relay | — | `uv run python manage.py outbox_relay` (poll ~1s) |
| `examples/00-monolith` self-consumer | — | `uv run python manage.py order_placed_consumer` (group `monolith-notification`) — required for the flag-OFF path; without it the flag-OFF `GET /api/notifications` read model never repopulates |
| `examples/03-notification-service` | `:8002` | `uv run alembic upgrade head` once, then `uv run uvicorn app.main:app --port 8002` (group `notification-service`), `DATABASE_URL`/`KAFKA_BOOTSTRAP_SERVERS` both defaulted (same Postgres instance, `localhost:9092`) |
| `examples/01-strangler-proxy` | `:8888` | `uv run uvicorn app.main:app --port 8888`, `STRANGLER_NOTIFICATION_ENABLED` toggled per run below |

newman 6.2.2 for every run below. Final collection SHA-256:
`90374e8609eb7ec2bf59815e26a51a5d2353ec3c0c74d0cdc04e9bbe0352dd8b` — identical
across every run in this section (only the proxy's flag, and which backend
was reachable, ever changed).

## The inert-guard control run — no `--env-var` at all, against the monolith directly

Before touching Kafka-dependence at all, the full, **completely unmodified**
invocation (`local.postman_environment.json`, no `--env-var` flag) was run to
prove the new folder is a true no-op for every existing caller of this
collection:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                20 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                40 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                21 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                60 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 839ms                                      │
└───────────────────────────────────────────────────────────────┘
```

**20 requests** (the pre-existing 19, plus exactly one: N1 — the plain,
synchronous checkout that fires unconditionally because a pre-request
script's `setNextRequest(null)` can only choose what runs *next*, never
prevent the *current* request; see README.md for why that's still safe).
N2 — the one request that actually needs Kafka — was never reached, and
`newman` exited `0`. This is the literal "existing Kafka-free gates/runs ...
stay unaffected" acceptance criterion, run against this exact, final
collection file.

## Run A — flag OFF, through the proxy, `--env-var notificationContractEnabled=true`

`STRANGLER_NOTIFICATION_ENABLED` unset (default `false`): notifications
should be served by the monolith's own `order.placed` self-consumer, reached
through the proxy.

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                22 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                44 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                25 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                66 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 1729ms                                     │
├────────────────────────────────────────────────────────────────┤
│ total data received: 7.3kB (approx)                            │
├────────────────────────────────────────────────────────────────┤
│ average response time: 28ms [min: 5ms, max: 134ms, s.d.: 33ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0.** Smoke, all four checkout
scenarios, and the Review Context Contract all pass exactly as in the r02
PHASE-2 baseline (58/58 of those assertions unchanged), plus the new
Notification folder's 8 assertions. N2 resolved on **attempt 2/20** (one
retry, ~750ms of added latency) — the notification created by this run's
checkout (`orderId=30`) became observable via the monolith's own consumer
well inside the ~15s budget.

## Run B — flag ON, through the proxy (same, unedited collection + environment)

Proxy restarted with `STRANGLER_NOTIFICATION_ENABLED=true`:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                22 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                44 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                25 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                66 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 1722ms                                     │
├────────────────────────────────────────────────────────────────┤
│ total data received: 6.31kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 26ms [min: 3ms, max: 134ms, s.d.: 32ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0 — byte-identical shape to Run A**
(same 22 requests / 44 test-scripts / 25 prerequest-scripts / 66 assertions,
0 failed in both; the collection file itself was never touched between
runs). Notification-service's own log confirms it, not the monolith,
answered this run's `GET /api/notifications`: `consumed order.placed for
order 25 (customer 1)` followed by the `200 OK` to the poll. N2 again
resolved on **attempt 2/20** — essentially identical latency to the
flag-OFF path, confirming the bounded-wait idiom is correct for either
backend without the collection knowing or caring which one is live.

## Negative check — notification-service down, flag ON: the Notification folder MUST go RED

With `STRANGLER_NOTIFICATION_ENABLED=true` and `examples/03-notification-service`
killed, only the Notification folder was re-run:

```
┌─────────────────────────┬─────────────────┬─────────────────┐
│                         │        executed │          failed │
├─────────────────────────┼─────────────────┼─────────────────┤
│              iterations │               1 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│                requests │              21 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│            test-scripts │              42 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│      prerequest-scripts │              42 │               0 │
├─────────────────────────┼─────────────────┼─────────────────┤
│              assertions │              23 │              21 │
├─────────────────────────┴─────────────────┴─────────────────┤
│ total run duration: 14.7s                                   │
└───────────────────────────────────────────────────────────── ┘
```

**`newman` exited non-zero (exit code 1), 21/23 assertions failed.** N1 still
passed (checkout is synchronous and doesn't touch the notification-service
at all). N2 ran its full **20-attempt bounded-wait budget** (`notificationPollMaxAttempts`
x `notificationPollDelayMs` = 20 x 750ms ≈ 14.7s observed, matching the ~15s
design budget) — every attempt got a real `502 Bad Gateway` from the proxy
(the fail-safe `examples/01-strangler-proxy`'s README documents: a dead
upstream is a real 5xx, never a masked `200`), e.g.:

```
01. AssertionError  Notification list request succeeds
                    expected response to have status code 200 but got 502
                    inside "Notification Context Contract / N2. Bounded-wait poll: ..."
```

— and once the budget was exhausted, the **strict** final assertion failed
cleanly and on its own terms:

```
21. AssertionError  Order-confirmation notification for orderId=19 is observable
                    within the bounded-wait budget (20 x 750ms, attempt 20/20)
                    no notification with orderId=19 found after 20 attempt(s):
                    expected undefined not to be undefined
                    inside "Notification Context Contract / N2. Bounded-wait poll: ..."
```

It never hung and never soft-passed. Restarting
`examples/03-notification-service` and re-running the same folder returned
to fully green:

```
┌─────────────────────────┬──────────────────┬──────────────────┐
│                         │         executed │           failed │
├─────────────────────────┼──────────────────┼──────────────────┤
│              iterations │                1 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│                requests │                4 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│            test-scripts │                8 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│      prerequest-scripts │                8 │                0 │
├─────────────────────────┼──────────────────┼──────────────────┤
│              assertions │                9 │                0 │
├─────────────────────────┴──────────────────┴──────────────────┤
│ total run duration: 1668ms                                    │
└───────────────────────────────────────────────────────────────┘
```

N2 resolved on **attempt 3/20** this time (2 retries, ~1.5s) — slightly
slower than Run A/B because the restarted consumer had to rejoin its
consumer group and complete a partition rebalance before it could see the
earlier-published event, but still comfortably inside the ~15s budget.

## A test-script robustness finding (not an integration bug — fixed before this record)

While first capturing the negative check above, the budget-exhausted path
raised 3 extra `TypeError`s (`Cannot convert undefined or null to object` /
`Cannot read properties of undefined`) from the shape/`channel`/`message`
assertions after `match` was `undefined` — noisy, but it did not change the
RED outcome (`newman` still exited non-zero both times: 24/26 assertions
failed before the fix, 21/23 after). `N2`'s test script was hardened with an
early `return` right after the strict "observable within budget" assertion
when `match` is still `undefined`, so a budget-exhausted run now reports
exactly one clean, diagnostic failure for that path instead of a cascade.
This was caught and fixed **before** capturing the final run numbers
recorded above — every table in this section reflects the hardened script
(collection SHA-256 `90374e86...`).

## Bounded-wait margin, all runs

| Run | Resolved on attempt | Elapsed (approx.) | Budget |
|---|---|---|---|
| Inert-guard control (no `--env-var`) | N2 never reached | — | — |
| Run A (flag OFF) | 2/20 | ~750ms | 15s |
| Run B (flag ON) | 2/20 | ~750ms | 15s |
| Negative (notification-service down) | budget exhausted | ~14.7s | 15s |
| Recovery (flag ON) | 3/20 | ~1.5s | 15s |

Every successful resolution used **well under 10%** of the 15s budget in
either flag state — the 20 x 750ms sizing has substantial headroom even
accounting for consumer-group rebalance latency after a restart (the
recovery run's attempt 3/20).

## Summary

| # | Flag | Notification served by | Everything else served by | Result |
|---|---|---|---|---|
| Inert-guard control | n/a (no `--env-var`) | n/a — N2 never reached | monolith | **GREEN** — 60/60 assertions, 0 failed, N1 only |
| A | `false` | monolith (self-consumer) | monolith | **GREEN** — 66/66 assertions, 0 failed |
| B | `true` | notification-service | monolith | **GREEN** — 66/66 assertions, 0 failed, byte-identical shape to A |
| Negative, `true` + notification-service down | *(nothing — 502)* | monolith | **RED** — 21/23 assertions failed, newman exit code 1 |
| Negative, recovered | notification-service | monolith | **GREEN** — 9/9 assertions, 0 failed |

The behavior-equivalence suite's first asynchronous, env-guarded, bounded-wait
folder is fully proven: green through the proxy in both flag states against
a real Kafka broker and two independently-running consumers, inert (and
`newman`-exit-0) for every existing caller that doesn't opt in, and RED for a
genuinely dead downstream with a strict, non-hanging failure. No unmet
acceptance criterion and no integration bug surfaced in this lane — the only
finding was the test-script robustness item above, fixed prior to this
record. The throwaway Postgres and Kafka containers, and every process
started for this lane (monolith, outbox relay, self-consumer,
notification-service, proxy), were torn down afterward; the host was left
clean.

---

# The r04 NEWMAN-GRPC lane — the Inventory Context Contract, live gRPC reserve/release

This section records the suite's first proof that checkout-time inventory
**reservation and compensation** (not just a read) survives crossing a real
network boundary: `mea.postman_collection.json` gained one new folder,
**Inventory Context Contract** (3 requests, I1–I3, placed between Review
Context Contract and Notification Context Contract — see `README.md` for
exactly what each request asserts and, importantly, for why this folder's
guard mechanism deliberately departs from the Notification folder's literal
`setNextRequest(null)` idiom). The five pre-existing folders (Smoke, the four
checkout scenarios, Review Context Contract, Notification Context Contract)
were **not edited**.

Unlike every prior lane, there are **two independent cutover dimensions** in
play here, not one:

| Dimension | Flag | Lives in |
|---|---|---|
| Checkout-time reserve/release | `INVENTORY_MODE=local` \| `grpc` | the monolith (`config/settings.py`) |
| `GET /api/inventory*` reads | `STRANGLER_INVENTORY_ENABLED` unset \| `true` | the strangler proxy (`examples/01-strangler-proxy/app/config.py`) |

Both combinations exercised below use them **locked together**
(fully-local / fully-gRPC) — see `README.md`'s note on why a split
combination (gRPC reserve, monolith-served reads, or vice versa) is only
sound during the CDC-backfilled transition window, not as a steady-state
configuration, and was not exercised here.

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, migrated + seeded fresh (monolith's `manage.py migrate && seed`) |
| `examples/00-monolith` | `:8000` | `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000`, `INVENTORY_MODE` toggled per run below |
| `examples/04-inventory-service` | HTTP `:8084` / gRPC `:9004` | `uv run alembic upgrade head` once (own `inventory` schema, self-seeds the 3 demo SKUs), then `uv run uvicorn app.main:app --host 0.0.0.0 --port 8084` (the gRPC server starts from the same process's lifespan — `/health` confirms `grpcServerListening: true`); same Postgres instance as the monolith, separate schema |
| `examples/01-strangler-proxy` | `:8888` | `uv run uvicorn app.main:app --port 8888`, `STRANGLER_INVENTORY_ENABLED` toggled per run below |

No Kafka broker was needed or started for this lane. newman 6.2.2 for every
run below.

## Run A — FULLY-gRPC (`INVENTORY_MODE=grpc`, `STRANGLER_INVENTORY_ENABLED=true`)

`newman run tooling/newman/mea.postman_collection.json -e tooling/newman/proxy.postman_environment.json --env-var inventoryContractEnabled=true`:

```
❏ Smoke
❏ Scenario 1 — Happy-Path Checkout      (all green)
❏ Scenario 2 — Out-of-Stock             (all green)
❏ Scenario 3 — Payment-Declined         (all green)
❏ Scenario 4 — Shipping-Failure         (all green)
❏ Review Context Contract               (all green)
❏ Inventory Context Contract            (all green)
❏ Notification Context Contract         (N1 only -- guard off, run ends there)

┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                23 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                46 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                24 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                71 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 1014ms                                     │
├────────────────────────────────────────────────────────────────┤
│ total data received: 3.06kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 27ms [min: 4ms, max: 136ms, s.d.: 37ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0.** Critically: Scenario 2's
over-order on the low-stock `SKU-GIZMO-003` returned `409 OUT_OF_STOCK`
through a real remote `Reserve` RPC whose `reservation_ok=false` the
monolith's `order.inventory_client.RemoteInventoryClient.reserve()` maps
onto the identical `InsufficientStock` exception the `local`-mode in-process
path raises — the checkout's external contract (409/402/422, same error
bodies) is byte-identical to `local` mode even though the reservation now
happens over the network against a different process's database.

**Direct proof of net-zero stock on Scenarios 3 and 4 (not just that the
suite's own before/after assertions matched):** querying
`GET /api/inventory/SKU-WIDGET-001` directly around the suite run confirms
`quantityOnHand` held at the same value (96) across both the Scenario 3
(payment-declined) and Scenario 4 (shipping-failed) checkouts:

```
Before:           {"quantityOnHand": 96}
After decline:     {"quantityOnHand": 96}   (PAYMENT_DECLINED, 402)
After ship-fail:   {"quantityOnHand": 96}   (SHIPPING_FAILED, 422)
```

This is the compensating-saga proof `order/services.py::_place_order_remote`
exists for: a remote `Reserve` is NOT inside the monolith's local
`transaction.atomic()` and cannot be rolled back by Postgres for free once
it commits in the inventory service's own database (SMELL[ch.22]'s "free
rollback" is gone the moment reservation crosses this network boundary); the
observed net-zero stock is a genuine, explicit compensating `Release` RPC
firing on both the payment-declined and shipping-failed paths (`
_place_order_remote`'s `except Exception: _release_reserved(...)`), not an
artifact of one shared in-process transaction undoing everything for free.

## Run B — FULLY-LOCAL, reversibility (`INVENTORY_MODE=local`, `STRANGLER_INVENTORY_ENABLED` unset)

Monolith and proxy restarted with the flags flipped back; same unedited
collection, same environment file, same `--env-var`:

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                23 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                46 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                24 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                71 │                0 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 1010ms                                     │
├────────────────────────────────────────────────────────────────┤
│ total data received: 3.39kB (approx)                           │
├────────────────────────────────────────────────────────────────┤
│ average response time: 27ms [min: 4ms, max: 141ms, s.d.: 34ms] │
└────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0 — byte-identical shape to Run A**
(same 23 requests / 46 test-scripts / 24 prerequest-scripts / 71 assertions,
0 failed in both). Checkout reserves/releases back against the monolith's
own in-process path (the pre-extraction r01-r03 baseline, SMELL[ch.22]'s free
rollback intact) and reads are served by the monolith directly; the flag is
a genuine, reversible config switch across BOTH dimensions at once, with no
restart-order dependency and no leftover state from Run A (the two
`inventory_items` tables — monolith `public` schema and inventory-service's
own `inventory` schema — are independent, so Run A's remote reservations
never touched the row Run B reads from).

## The no-flags control run — existing folders provably unaffected

Before relying on the proof above, the plain default invocation (no
`--env-var` at all) was run to confirm the new Inventory folder is a true
no-op for every existing caller, exactly the same bar the r03 NEWMAN-ASYNC
lane set for the Notification folder:

```
❏ Inventory Context Contract
↳ I1. List inventory -> 200, camelCase array (3 SKUs)
  GET http://localhost:8888/api/inventory [200 OK, 444B, 7ms]
↳ I2. Get SKU-WIDGET-001 by sku -> 200, camelCase object
  GET http://localhost:8888/api/inventory/SKU-WIDGET-001 [200 OK, 274B, 5ms]
↳ I3. Get unknown sku -> 404, uniform error body
  GET http://localhost:8888/api/inventory/NOPE [404 Not Found, 306B, 5ms]

❏ Notification Context Contract
↳ N1. Checkout for the notification contract -> 201 Created, CONFIRMED
  POST http://localhost:8888/api/orders [201 Created, 545B, 35ms]
  ✓  Order created returns 201
  ✓  Order status is CONFIRMED (...)

┌─────────────────────────┬───────────────────┬──────────────────┐
│              iterations │                 1 │                0 │
│                requests │                23 │                0 │
│            test-scripts │                46 │                0 │
│      prerequest-scripts │                24 │                0 │
│              assertions │                60 │                0 │
└─────────────────────────┴───────────────────┴──────────────────┘
```

**All three Inventory requests fire (harmless, idempotent reads) but assert
nothing (guard off), and critically do NOT strand the Notification folder:**
`N1` still fires unconditionally and still halts the run right where it
always has, exactly matching the r03 lane's own documented "inert-guard
control run" precedent (same 60 assertions as that lane's own baseline — the
3 new Inventory requests contribute 0 extra assertions when their guard is
off, by design; see `README.md` for why this folder's guard uses a
test-script-level check rather than `setNextRequest`, specifically so it can
never strand anything placed before or after it).

## Negative check — inventory-service down, fully-gRPC: BOTH the read contract AND the reserve path MUST go RED

With `INVENTORY_MODE=grpc` / `STRANGLER_INVENTORY_ENABLED=true` still active
and `examples/04-inventory-service` killed:

**(a) Inventory Context Contract folder (`--folder "Inventory Context Contract"`):**

```
┌─────────────────────────┬─────────────────┬─────────────────┐
│              iterations │               1 │               0 │
│                requests │               3 │               0 │
│            test-scripts │               6 │               3 │
│              assertions │               4 │               4 │
│ total run duration: 100ms                                   │
└─────────────────────────┴─────────────────┴─────────────────┘
```

**newman exited non-zero (exit code 1), 4/4 assertions failed.** Every
request got a real `502 Bad Gateway` from the proxy, e.g.:

```
01. AssertionError  Inventory list returns 200
                    expected response to have status code 200 but got 502
                    inside "Inventory Context Contract / I1. List inventory -> 200, camelCase array (3 SKUs)"
03. JSONError
                    Unexpected token 's' at 1:1
                    strangler-proxy: upstream unavailable (ConnectError)
                    inside "Inventory Context Contract / I1. List inventory -> 200, camelCase array (3 SKUs)"
```

— the same fail-safe `examples/01-strangler-proxy`'s README documents: a
dead upstream is a real 5xx, never a masked `200`.

**(b) A checkout scenario (`--folder "Scenario 1 — Happy-Path Checkout"`):**

```
┌─────────────────────────┬──────────────────┬─────────────────┐
│              iterations │                1 │               0 │
│                requests │                4 │               0 │
│            test-scripts │                8 │               3 │
│              assertions │               10 │               9 │
│ total run duration: 146ms                                    │
└─────────────────────────┴──────────────────┴─────────────────┘
```

**newman exited non-zero (exit code 1), 9/10 assertions failed.** `1a`'s own
stock-capture `GET` also hit the dead inventory-service through the proxy
(`502`, same as above); `1b`'s `POST /api/orders` got a real `503 Service
Unavailable` instead of `201`, with this exact body (captured directly, not
just via the newman assertion):

```json
{"error":"INVENTORY_UNAVAILABLE","message":"Inventory service unavailable: StatusCode.UNAVAILABLE failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:9004: Failed to connect to remote host: Connection refused","timestamp":"2026-10-16T14:08:22.850691+00:00"}
```

This is `order.inventory_client.RemoteInventoryClient._unary()`'s
`grpc.RpcError` → `InventoryServiceUnavailable` (503) mapping working
exactly as designed: a dead inventory service fails checkout cleanly with a
503, never silently confirming an order whose remote reservation status is
actually unknown, and never getting confused with a logical 409
`OUT_OF_STOCK` (a materially different failure mode `common/exceptions.py`'s
docstring explicitly calls out). `1c`/`1d` then cascade (no order was ever
created to look up; the stock-capture `GET` also 502s) — both expected,
non-misleading consequences of the same root cause, not independent bugs.

**Recovery:** `examples/04-inventory-service` restarted; both folders
re-run and return to fully green:

```
Inventory Context Contract:  3 requests, 11/11 assertions, 0 failed
Scenario 1 — Happy-Path:     4 requests, 14/14 assertions, 0 failed
```

## Summary

| # | `INVENTORY_MODE` | `STRANGLER_INVENTORY_ENABLED` | inventory-service | Result |
|---|---|---|---|---|
| A | `grpc` | `true` | up | **GREEN** — 71/71 assertions, 0 failed; Scenarios 2/3/4 proven correct across the gRPC boundary, net-zero stock confirmed directly on 3 & 4 |
| B (reversibility) | `local` | unset | up (unused by this config) | **GREEN** — 71/71 assertions, 0 failed, byte-identical shape to A |
| No-flags control | `grpc` | `true` | up | **GREEN** — 60/60 assertions, 0 failed; Inventory folder inert (fires, asserts nothing), Notification folder NOT stranded |
| Negative, reads | `grpc` | `true` | **down** | **RED** — 4/4 assertions failed, real `502`s, newman exit code 1 |
| Negative, checkout | `grpc` | `true` | **down** | **RED** — 9/10 assertions failed, real `503 INVENTORY_UNAVAILABLE`, newman exit code 1 |
| Recovery | `grpc` | `true` | up (restarted) | **GREEN** — both folders fully green again |

No unmet acceptance criterion and no integration bug surfaced in this lane:
reserve/release round-trips correctly across the gRPC boundary in both
directions (success and compensation), the two cutover dimensions are
independently reversible, the new folder cannot strand any other folder in
any flag combination, and a dead inventory-service fails both the read path
(proxy `502`) and the write path (checkout `503 INVENTORY_UNAVAILABLE`)
cleanly and loudly rather than silently. The throwaway Postgres container
and every process started for this lane (monolith, inventory-service,
proxy) were torn down afterward; the host was left clean.

---

# The r05 NEWMAN-ASYNC CONVERSION lane — tolerating the upcoming 201→202 flip, GREEN against today's synchronous monolith

This section records the conversion of `mea.postman_collection.json`'s four
checkout scenarios (plus the Notification folder's N1) so the suite will
survive the upcoming **201→202 contract change** (checkout becomes async,
choreographed by a saga) **without losing its value as an honest
before/after equivalence check** — and the proof that the converted suite is
still **fully GREEN against the current, UNMODIFIED, synchronous monolith**
(which still returns `201`/`402`/`422` today; the choreographed flip itself
lands in a sibling lane, not this one). This lane touched only
`tooling/newman/` — no application code changed.

## What changed in the collection

- **Scenario 1 (Happy-Path):** `1b`'s `POST /api/orders` now asserts `201 OR
  202` (capturing `id`/`Location` either way, and — if `201` — asserting
  `CONFIRMED` immediately; if `202` — asserting `PENDING`). The former `1c`
  ("get the order back") is now a **bounded-wait poll** (`1c`, reusing the
  Notification folder's idiom verbatim in shape: busy-wait only on a retry,
  never on attempt 0, `checkoutPollMaxAttempts` x `checkoutPollDelayMs` = 20 x
  750ms budget) that strictly asserts the terminal status is `CONFIRMED` —
  never a naked `2xx` — plus the total/items assertions that used to live in
  `1b`. `1d`'s stock-delta check is unchanged, now reading after the terminal
  poll.
- **Scenario 3 (Payment-Declined):** `3b` now asserts `402 OR 202`. Today's
  monolith rolls back the ENTIRE `transaction.atomic()` on a decline —
  including the `Order` row itself (`order/services.py`,
  `payment/services.py::charge()`) — so a `402` response has **no order id to
  poll**; `3b`'s test script detects this and jumps straight past the new
  `3c` (bounded-wait poll for `PAYMENT_DECLINED`, async-path only) via
  `postman.setNextRequest('3d. ...')`, landing on `3d`, a bounded-wait poll of
  `GET /api/inventory/{sku}` asserting **strict net-zero** stock. `3d` runs
  **unconditionally in both modes** — this is the lane's non-vacuity proof.
- **Scenario 4 (Shipping-Failure):** identical shape to Scenario 3: `4b`
  asserts `422 OR 202`, jumps past `4c` (bounded-wait poll for
  `SHIPPING_FAILED`, async-path only) when sync, lands on `4d` (bounded-wait
  net-zero stock poll, unconditional).
- **Scenario 2 (Out-of-Stock):** left exactly as-is — still strictly `409`,
  unchanged — the reservation rejects before any async work could begin, so
  there is nothing to tolerate here.
- **New "Payment Context Contract" folder** (P1–P3), inserted between
  Inventory Context Contract and Notification Context Contract, env-guarded
  by `paymentContractEnabled === 'true'` using the same test-script-level,
  no-`setNextRequest` guard idiom as the Inventory folder (non-terminal
  position, so it can never strand Notification): `GET
  /api/payments?orderId={{happyPathOrderId}}` → `200` camelCase array
  (`id, orderId, amountCents, method, status, createdAt`), scoped to the
  Scenario 1 happy-path order and capturing its payment id; `GET
  /api/payments/{id}` → `200`, same shape, `status: "CAPTURED"`; `GET
  /api/payments/999999999` → `404` uniform error body, `error: "NOT_FOUND"`.
- **Notification Context Contract N1 fix:** N1 previously assumed
  `POST /api/orders` → `201`/`CONFIRMED` unconditionally. It now asserts `201
  OR 202` only; the terminal `CONFIRMED` check moved to a new **N1b**
  (bounded-wait poll of `GET /api/orders/{id}`, inserted between N1 and N2,
  same inert-guard-when-off idiom as N1 since this folder is still terminal)
  so the folder survives the async flip too, without needing Kafka for N1b's
  own check (only N2's notification poll needs Kafka).
- **New collection variables:** `checkoutPollMaxAttempts` (`20`),
  `checkoutPollDelayMs` (`750`) — the shared bounded-wait budget for every
  new checkout-scenario poll, mirroring `notificationPollMaxAttempts`/
  `notificationPollDelayMs` exactly; plus one poll-attempt counter per new
  poll item (`happyPathPollAttempt`, `declinePollAttempt`,
  `declineStockPollAttempt`, `shipFailPollAttempt`,
  `shipFailStockPollAttempt`, `notificationOrderPollAttempt`), one
  checkout-mode flag per branching scenario (`declineCheckoutMode`,
  `shipFailCheckoutMode`), one captured order id per branching scenario
  (`declineOrderId`, `shipFailOrderId`), and `paymentId` for the new Payment
  folder.

## Why Scenario 4's `SHIPPING_FAILED` poll never runs against today's monolith (and that's by design, not a gap)

`Order.Status` (`order/models.py`) only defines `PENDING`, `CONFIRMED`, and
`PAYMENT_DECLINED` today — there is no `SHIPPING_FAILED` choice yet, because
`shipping.services.dispatch()`'s `ShippingFailed` exception is raised INSIDE
the same `transaction.atomic()` that creates the `Order` row, so that row
never commits and no order ever exists for this path to begin with
(confirmed directly: `tests/test_checkout.py::test_ship_fail_sentinel_...`
and the error-response body contain no `id` field at all). The `SHIPPING_FAILED`
string only has a status to assert once the choreographed saga lands (a
sibling lane), which is also the point at which `POST /api/orders` starts
returning `202` with an order already persisted in `PENDING`. Rather than
weaken `4c`'s assertion to tolerate today's non-existent terminal state, this
lane **gates `4c` entirely behind the async branch** (same mechanism as
`3c`): `4b`'s test script jumps straight to `4d` (the always-on, unconditional
net-zero stock poll) whenever the response is the current synchronous `422`,
and only lets the natural item order fall through into `4c` when the response
is the future `202`. This keeps `4c`'s own assertion strict (`SHIPPING_FAILED`,
never a tolerant "any terminal status") while keeping the baseline green
today, because `4c` is simply never reached today — not because its
assertion was loosened to pass vacuously. Scenario 3's `PAYMENT_DECLINED`
poll (`3c`) is gated identically, for the identical reason (the decline also
never persists an order today).

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, empty volume, migrated + seeded fresh |
| `examples/00-monolith` | `:8000` | `uv run python manage.py runserver 0.0.0.0:8000`, DEFAULT config (`INVENTORY_MODE=local`, the only mode this module ships with by default) — still fully synchronous, returns `201`/`402`/`422` today |

No Kafka, no inventory-service, no strangler proxy — this lane runs the
converted collection straight against the bare monolith, the same way the r01
baseline did, to prove the conversion holds with nothing else in play.

## Run 1

`newman run tooling/newman/mea.postman_collection.json -e tooling/newman/local.postman_environment.json --env-var paymentContractEnabled=true` (the monolith's `/api/payments` surface is in-process and always up, so the flag was enabled for this baseline):

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│                requests │                26 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│            test-scripts │                52 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│      prerequest-scripts │                30 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│              assertions │                70 │                 0 │
├─────────────────────────┴───────────────────┴───────────────────┤
│ total run duration: 2.1s                                        │
├─────────────────────────────────────────────────────────────────┤
│ total data received: 3.42kB (approx)                            │
├─────────────────────────────────────────────────────────────────┤
│ average response time: 63ms [min: 31ms, max: 178ms, s.d.: 32ms] │
└─────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0, newman 6.2.2.** `26` requests:
the pre-existing 19 minus the two scenarios' skipped order-status polls (`3c`,
`4c` never fired — both jumped past as documented above) plus the two new
always-on stock polls (`3d`, `4d` replacing the old `3c`/`4c` stock checks)
plus the three new Payment folder requests (P1–P3) plus N1 (the run still
ends at N1 — `notificationContractEnabled` was not set, so N1's own
pre-existing inert guard still ends the run there exactly as before; N1b/N2
never reached). Critically:

- **Scenario 1** — `1b` got `201` (today's synchronous contract);
  `1c`'s bounded-wait poll resolved `CONFIRMED` **on attempt 1/20 — 0
  retries** — the non-vacuity proof the task set out to capture.
- **Scenario 3** — `3b` got `402`; jumped straight to `3d`, which resolved
  net-zero stock **on attempt 1/20 — 0 retries**.
- **Scenario 4** — `4b` got `422`; jumped straight to `4d`, which resolved
  net-zero stock **on attempt 1/20 — 0 retries**.
- **Payment Context Contract** — P1 found exactly one payment for the
  Scenario 1 happy-path order (`orderId=2` in this run), P2 confirmed its
  `CAPTURED` status by id, P3 confirmed the uniform `404` for an unknown id.

## Run 2 — back-to-back, same process, no database reset (idempotency)

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│                requests │                26 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│            test-scripts │                52 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│      prerequest-scripts │                30 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│              assertions │                70 │                 0 │
├─────────────────────────┴───────────────────┴───────────────────┤
│ total run duration: 2.2s                                        │
├─────────────────────────────────────────────────────────────────┤
│ total data received: 3.75kB (approx)                            │
├─────────────────────────────────────────────────────────────────┤
│ average response time: 65ms [min: 32ms, max: 199ms, s.d.: 36ms] │
└─────────────────────────────────────────────────────────────────┘
```

**Byte-identical shape to Run 1, fully green, 0 failed** — confirms the
conversion's "capture stock/mode before" pattern is still safe to re-run
against a long-lived process with no fresh database reset, exactly the same
property r01's baseline established and every later lane has preserved.

## The no-flags control run — existing callers still unaffected

`newman run tooling/newman/mea.postman_collection.json -e tooling/newman/local.postman_environment.json` (no `--env-var` at all):

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│                requests │                26 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│            test-scripts │                52 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│      prerequest-scripts │                30 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│              assertions │                59 │                 0 │
├─────────────────────────┴───────────────────┴───────────────────┤
│ total run duration: 2.1s                                        │
├─────────────────────────────────────────────────────────────────┤
│ total data received: 7.2kB (approx)                             │
├─────────────────────────────────────────────────────────────────┤
│ average response time: 64ms [min: 40ms, max: 174ms, s.d.: 31ms] │
└─────────────────────────────────────────────────────────────────┘
```

**Still fully green, 0 failed.** The 3 new Payment folder requests fire
(harmless, idempotent `GET`s) but assert nothing (guard off, 70 − 11 = 59
assertions, exactly P1/P2/P3's own 11 assertions worth of difference) and —
critically — do **not** strand the Notification folder: the run still ends
at N1 exactly as it always has. Same bar the r03 and r04 lanes each set for
their own new folders.

## N1/N1b verified independently (no Kafka needed for this half)

`--folder "Notification Context Contract" --env-var notificationContractEnabled=true`, Kafka/outbox-relay/consumer all deliberately NOT started (out of scope for this lane — N1b's own check doesn't need them):

```
↳ N1. Checkout for the notification contract -> 201 or 202 Accepted
  POST http://localhost:8000/api/orders [201 Created, 505B, 51ms]
  ✓  Order created returns 201 or 202

↳ N1b. Bounded-wait poll: order reaches CONFIRMED
  GET http://localhost:8000/api/orders/12 [200 OK, 468B, 52ms]
  ✓  Order lookup returns 200
  ✓  Order reaches terminal status CONFIRMED within the bounded-wait budget (20 x 750ms, attempt 1/20)
```

**N1b resolved CONFIRMED on attempt 1/20 — 0 retries**, confirming the N1 fix
holds against the current synchronous monolith without needing Kafka at all.
N2 (the actual Kafka-dependent notification poll, unchanged by this lane)
then ran its full 20-attempt budget and failed strictly, exactly as expected
with no outbox relay/consumer running to ever populate it — a pre-existing,
out-of-scope behavior this lane did not touch, included here only to show
N1b doesn't regress anything downstream of it.

## Summary

| Scenario | Today's response | Order persisted? | Poll reached | Poll result |
|---|---|---|---|---|
| 1 — Happy-Path | `201 CONFIRMED` | yes | `1c` (order status) | **CONFIRMED, attempt 1/20 — 0 retries** |
| 2 — Out-of-Stock | `409 OUT_OF_STOCK` | n/a (rejected pre-write) | — (unchanged) | n/a |
| 3 — Payment-Declined | `402 PAYMENT_DECLINED` | **no** (whole tx rolled back) | `3c` skipped; `3d` (stock) | **net-zero, attempt 1/20 — 0 retries** |
| 4 — Shipping-Failure | `422 SHIPPING_FAILED` | **no** (whole tx rolled back) | `4c` skipped; `4d` (stock) | **net-zero, attempt 1/20 — 0 retries** |
| N — Notification | `201 CONFIRMED` | yes | `N1b` (order status) | **CONFIRMED, attempt 1/20 — 0 retries** |

Every bounded-wait poll this lane added resolves on its very first attempt
against today's unmodified synchronous monolith — the explicit non-vacuity
proof the task asked for. No acceptance criterion was left unmet: the
converted collection is green against the synchronous monolith (above, twice
over); every checkout folder still strictly asserts a terminal status plus
its side effect (never a naked `2xx`, and never able to pass on a stuck
`PENDING` — the bounded-wait idiom's strict final assertion guarantees that);
the new Payment Context Contract folder is added, env-guarded, and inert
(fires, asserts nothing) when its flag is off; existing folders are
unaffected when all new guards are off (no-flags control run, above); and N1
is now 201/202-tolerant with its own bounded-wait to a confirmed order. The
throwaway Postgres container and the monolith process started for this lane
were torn down afterward; the host was left clean.

---

# The r05 CUTOVER lane — the choreographed payment saga, live end-to-end

This section proves the actual **async cutover**, not just the collection's
tolerance for it (the previous lane). The FULL topology was brought up —
monolith, payment-service, inventory-service, review-service,
notification-service, the strangler proxy, real Kafka — and
`settings.PAYMENT_MODE = "choreographed"` was flipped live. Both cutover
dimensions this lane exercises:

1. **The checkout contract**: `POST /api/orders` answers `202 Accepted` with
   the order `PENDING` instead of a terminal `201`/`402`/`422` in the same
   round trip.
2. **The ownership of payment**: the monolith no longer charges in-process at
   all in this mode — `examples/05-payment-service` reacts to `order.placed`
   asynchronously and emits its own `payment.captured`/`payment.declined`;
   the monolith's `order_saga_listener` reacts to THAT, in turn, to finish
   the order (confirm + ship, or release + decline).

Only `tooling/newman/` (this file) and `examples/05-payment-service/CUTOVER.md`
were touched by this lane — no application code changed; the collection and
the Newman environments are exactly what the r05 NEWMAN-ASYNC CONVERSION lane
(above) already landed.

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, empty volume, migrated + seeded fresh |
| Kafka (KRaft) | `localhost:9092` | throwaway single-node `apache/kafka:4.3.1`, `PLAINTEXT://localhost:9092` |
| `examples/04-inventory-service` | HTTP `:8084` / gRPC `:9004` | `alembic upgrade head`, then `uvicorn` — unchanged from the r04 lane |
| `examples/05-payment-service` | `:8085` | `alembic upgrade head`, then `uvicorn` with its lifespan running BOTH its `order.placed` consumer AND its own outbox relay, `KAFKA_BOOTSTRAP_SERVERS=localhost:9092` |
| `examples/02-review-service` | `:8001` | `uvicorn` against the monolith's already-migrated/seeded schema (no migration of its own) |
| `examples/03-notification-service` | `:8002` | `alembic upgrade head`, then `uvicorn`, Kafka consumer of `order.placed` |
| `examples/00-monolith` | `:8000` | `manage.py migrate && manage.py seed`, then `gunicorn config.wsgi`, `INVENTORY_MODE=grpc INVENTORY_GRPC_TARGET=localhost:9004 PAYMENT_MODE=choreographed KAFKA_BOOTSTRAP_SERVERS=localhost:9092`, PLUS three background `manage.py` processes with the same env: `outbox_relay`, `order_placed_consumer`, `order_saga_listener` |
| `examples/01-strangler-proxy` | `:8888` | `uvicorn`, ALL flags on (`STRANGLER_REVIEW_ENABLED=STRANGLER_NOTIFICATION_ENABLED=STRANGLER_INVENTORY_ENABLED=STRANGLER_PAYMENT_ENABLED=true`) + all five base URLs |

Seed stock: `SKU-WIDGET-001` 100, `SKU-GADGET-002` 50, `SKU-GIZMO-003` 5 (same
seed every lane has used since r01).

## Run 1 — fully-choreographed, through the proxy, GREEN

`newman run tooling/newman/mea.postman_collection.json -e tooling/newman/proxy.postman_environment.json --env-var paymentContractEnabled=true --env-var inventoryContractEnabled=true --env-var notificationContractEnabled=true`:

```
┌─────────────────────────┬────────────────────┬───────────────────┐
│                         │           executed │            failed │
├─────────────────────────┼────────────────────┼───────────────────┤
│              iterations │                  1 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│                requests │                 35 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│            test-scripts │                 70 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│      prerequest-scripts │                 48 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│              assertions │                 95 │                 0 │
├─────────────────────────┴────────────────────┴───────────────────┤
│ total run duration: 5.1s                                         │
├──────────────────────────────────────────────────────────────────┤
│ total data received: 5.47kB (approx)                             │
├──────────────────────────────────────────────────────────────────┤
│ average response time: 20ms [min: 4ms, max: 139ms, s.d.: 29ms]   │
└──────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0.** The async path was REALLY
exercised, not vacuously tolerated:

| Scenario | `*b` response | Poll | Terminal result | Attempts |
|---|---|---|---|---|
| 1 — Happy-Path | `202 Accepted`, order `PENDING` (order id 2) | `1c` | **CONFIRMED** | **attempt 2/20** — the non-vacuity proof: a real Kafka round trip through payment-service and back through the saga listener, not an instant resolve |
| 2 — Out-of-Stock | `409 Conflict`, `OUT_OF_STOCK` | — (unchanged, synchronous reservation rejection, no async path to speak of) | n/a | n/a |
| 3 — Payment-Declined | `202 Accepted`, order `PENDING` (order id 3) | `3c` | **PAYMENT_DECLINED** | **attempt 2/20** |
| 3 (stock) | — | `3d` | net-zero stock (99 → 99, compensating gRPC Release) | attempt 1/20 |
| 4 — Shipping-Failure | `202 Accepted`, order `PENDING` (order id 4) | `4c` | **SHIPPING_FAILED** | **attempt 2/20** |
| 4 (stock) | — | `4d` | net-zero stock (99 → 99, compensating gRPC Release) | attempt 1/20 |

Scenario 1's full round trip, verbatim: `1b` POSTs and gets back
`{"id":2,...,"status":"PENDING",...}` at `202`; `1c`'s first poll attempt
still reads `PENDING`; the SECOND attempt (750ms later) reads `CONFIRMED` —
real asynchronous latency, not an artifact of a fast loop. Scenario 3/4 are
identical in shape: `3b`/`4b` both answer `202`/`PENDING` (today's choreographed
contract persists the order up front, unlike the old synchronous whole-rollback
behavior), the order-status poll resolves at **attempt 2/20** each, and the
UNCONDITIONAL stock poll (`3d`/`4d`) confirms the compensating gRPC Release
actually ran — net-zero, not just "the order's final status looks right."
Payment Context Contract (P1–P3) was green scoped to the Scenario 1 happy-path
order, confirming `status: "CAPTURED"`. Review (R1–R5), Inventory (I1–I3), and
Notification (N1/N1b/N2) folders were all green too — N1b resolved at
**attempt 3/20** (its own fresh checkout, order id 5) and N2's Kafka-backed
notification poll resolved at **attempt 1/20**.

## Run 2 — reversibility: `PAYMENT_MODE=synchronous`, `STRANGLER_PAYMENT_ENABLED` unset

The monolith (`gunicorn`) was restarted with `PAYMENT_MODE=synchronous`
(`INVENTORY_MODE=grpc` UNCHANGED — only the payment axis flips back); the
proxy was restarted with `STRANGLER_PAYMENT_ENABLED` unset (so `/api/payments`
routes straight to the monolith's own, byte-identical payment surface
instead of payment-service). payment-service, its consumer, its relay, and
the monolith's three saga-related background processes were all left
RUNNING, unchanged — proving the reversal is clean even with the rest of the
async topology still live (every `order.placed` event synchronous checkout
still emits gets consumed by payment-service too, which creates its own
redundant `Payment` row/outcome event; the saga listener's status-transition
guard sees the order already `CONFIRMED` and no-ops on it — see the log
excerpt below).

```
┌─────────────────────────┬────────────────────┬───────────────────┐
│                         │           executed │            failed │
├─────────────────────────┼────────────────────┼───────────────────┤
│              iterations │                  1 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│                requests │                 29 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│            test-scripts │                 58 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│      prerequest-scripts │                 36 │                 0 │
├─────────────────────────┼────────────────────┼───────────────────┤
│              assertions │                 89 │                 0 │
├─────────────────────────┴────────────────────┴───────────────────┤
│ total run duration: 2s                                           │
├──────────────────────────────────────────────────────────────────┤
│ total data received: 5.3kB (approx)                              │
├──────────────────────────────────────────────────────────────────┤
│ average response time: 23ms [min: 3ms, max: 130ms, s.d.: 35ms]   │
└──────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed.** Both cutover dimensions reversed:

| Scenario | `*b` response | Poll | Attempts |
|---|---|---|---|
| 1 — Happy-Path | `201 Created`, `CONFIRMED` immediately | `1c` | **attempt 1/20** — back to synchronous, zero async latency |
| 2 — Out-of-Stock | `409 Conflict` | — | n/a |
| 3 — Payment-Declined | `402 Payment Required` (whole tx rolled back, no order persisted) | jumps to `3d` | **attempt 1/20**, net-zero |
| 4 — Shipping-Failure | `422 Unprocessable Content` (whole tx rolled back) | jumps to `4d` | **attempt 1/20**, net-zero |
| N1/N1b | `201 Created` → `CONFIRMED` | `N1b` | **attempt 1/20** |

The 28-requests-vs-35 delta from Run 1 is exactly the three now-skipped
async-only polls (`3c`, `4c` jumped past) plus the no-longer-multi-attempt
`1c`/`N1b` (each needed only 1 request here vs 2–3 in Run 1).
`order_saga_listener.log` confirms the redundant payment-service processing
was harmlessly absorbed:

```
payment.captured redelivered for order_id=9 status=CONFIRMED -- no-op (status guard)
```

(order 9 here is this run's own Scenario 1 happy-path order under the
synchronous monolith — payment-service captured it from the `order.placed`
event same as ever, published `payment.captured`, and the saga listener's own
idempotency guard absorbed it as a no-op since the order was never `PENDING`
from this listener's point of view.)

## Run 3 — negative: payment-service DOWN, stuck-PENDING honesty proof

Back to `PAYMENT_MODE=choreographed` / `STRANGLER_PAYMENT_ENABLED=true`.
payment-service (both its consumer AND its outbox relay — the whole process)
was killed (`kill <pid>`; confirmed down via `GET :8085/health` → connection
refused). A normal checkout was placed directly:

```
POST /api/orders -> 202 Accepted, {"id":10,...,"status":"PENDING",...}
```

confirming the order IS accepted and persisted `PENDING` even with no payment
consumer alive to ever resolve it — exactly the failure mode the bounded-wait
poll exists to catch. `newman run ... --folder "Scenario 1 — Happy-Path
Checkout"` was then run on its own (own fresh order id 11):

```
┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│              iterations │                 1 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                23 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│            test-scripts │                46 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│      prerequest-scripts │                43 │                0 │
├─────────────────────────┼───────────────────┼──────────────────┤
│              assertions │                33 │                1 │
├─────────────────────────┴───────────────────┴──────────────────┤
│ total run duration: 15.1s                                      │
└──────────────────────────────────────────────────────────────────┘

1) AssertionError  Order reaches terminal status CONFIRMED within the bounded-wait budget (20 x 750ms, attempt 20/20)
                   expected 'PENDING' to deeply equal 'CONFIRMED'
                   at assertion:1 in test-script
                   inside "Scenario 1 — Happy-Path Checkout / 1c. Bounded-wait poll: order reaches terminal status -> strictly CONFIRMED"
```

**newman exit code 1 — RED, as required.** `23` requests = `1a`+`1b`+20×`1c`
(the full budget, never resolving) + `1d` — total run duration `15.1s` is
`20 × 750ms`, confirming the poll actually exhausted its budget rather than
failing fast. Order 11 stayed `PENDING` for the entire run (verified directly:
`GET /api/orders/11` → `"status":"PENDING"`). `1d` still passed — the gRPC
inventory reservation happens synchronously inside the checkout request
itself, before payment is ever involved, so stock dropped by exactly 1
(`100 → 99` → in this lane's running numbers, `95 → 94`) regardless of
payment-service being down; only the PAYMENT half of the saga is stuck, which
is exactly the point this negative case proves — a dead payment-service
cannot silently masquerade as a working one by returning a false green.

**Recovery.** payment-service was restarted (`uvicorn`, same env). Its
consumer rejoined the `payment-service` group at `auto_offset_reset=earliest`
(a fresh/empty group offset) and immediately drained BOTH orders stuck during
the outage:

```
processed order.placed for order 10 -> payment CAPTURED (payment id=7)
processed order.placed for order 11 -> payment CAPTURED (payment id=8)
outbox.published id=7 ... event_type=payment.captured topic=payment.captured
outbox.published id=8 ... event_type=payment.captured topic=payment.captured
```

Confirmed directly: `GET /api/orders/10` and `GET /api/orders/11` both now
read `"status":"CONFIRMED"`. The stuck-PENDING failure mode is real,
detectable (RED, not a false green), and self-heals the moment the consumer
comes back — no manual intervention, no lost orders, no stuck-forever state.

## Double-delivery idempotency — the `(order_id,sku)` / idempotency_key ledger

A fresh Payment-Declined checkout was placed (order id 12, `SKU-WIDGET-001`):
stock went `94 → 93` on reservation, then `93 → 94` once the choreographed
decline + compensating Release resolved (`PAYMENT_DECLINED`, attempt 1/20 —
the fastest resolution seen this lane, since payment-service's consumer was
already warm). Two independent redelivery proofs were run against this
already-resolved order, bottom-up:

**1. Saga-level (Kafka at-least-once redelivery).** The exact
`payment.declined` event payment-service originally published for order 12
(`{"orderId":12,"paymentId":9,"amountCents":1999,"method":"DECLINE","status":"DECLINED",...}`)
was re-published to the `payment.declined` topic by hand (simulating a
broker-side redelivery). `order_saga_listener.log`:

```
payment.declined redelivered for order_id=12 status=PAYMENT_DECLINED -- no-op (status guard)
```

Stock **before**: `94`. Stock **after** the redelivered event was consumed:
**`94`** — unchanged. The order's own status-transition guard
(`order.services._is_pending`) stopped the second delivery before it ever
called Release again.

**2. Ledger-level (direct gRPC, bypassing the saga guard entirely).** To prove
the DEEPER mechanism the task named explicitly — inventory-service's own
`inventory.compensations` table, a unique index on `idempotency_key` — the
monolith's compensating `Release` RPC was called directly, twice, over gRPC,
using the SAME stable key the saga listener itself derives
(`f"{order_id}:{sku}:release"` = `"12:SKU-WIDGET-001:release"`), with no order
in the loop at all:

```
BEFORE any direct Release call: on_hand_qty=94
Release call #1 (key='12:SKU-WIDGET-001:release'): reservation_ok=True on_hand_qty=94
Release call #2 (SAME key, simulating redelivery): reservation_ok=True on_hand_qty=94
AFTER both calls: on_hand_qty=94
```

Both calls return `reservation_ok=True` (the RPC itself is designed to answer
success either way — a duplicate is not an error) but `on_hand_qty` never
moves past `94` — the `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING
RETURNING id` in `inventory-service/app/repository.py::release` makes the
re-increment apply AT MOST ONCE no matter how many times this exact key is
replayed, independent of whatever idempotency the CALLER (the saga listener)
also happens to provide. **Stock was never over-restored at either layer —
before `94`, after both redelivery mechanisms `94`.**

## Summary

| Proof | Result |
|---|---|
| Fully-choreographed suite | GREEN (0/95 failed); Scenario 1 `202`→poll attempt 2/20→`CONFIRMED`; Scenario 3 `202`→`PAYMENT_DECLINED`+net-zero; Scenario 4 `202`→`SHIPPING_FAILED`+net-zero; Scenario 2 `409`; Payment Context Contract green |
| Reversibility | GREEN (0/89 failed); Scenario 1 back to `201`/attempt-1; Scenario 3/4 back to `402`/`422` |
| Negative (payment-service down) | RED, newman exit 1, order stuck `PENDING` for the full `20×750ms` budget; self-heals to `CONFIRMED` the instant payment-service restarts |
| Double-delivery idempotency | Stock `94` before, `94` after BOTH a redelivered Kafka event (saga status-guard no-op) AND a direct duplicate gRPC `Release` call with the same key (ledger no-op) |

No integration bug surfaced — every mechanism (the async checkout contract,
the saga listener's compensating Release, the stuck-PENDING detection, and
the two independent layers of idempotency) behaved exactly as the code's own
docstrings describe. The throwaway Postgres and Kafka containers and every
service process started for this lane were torn down afterward; the host was
left clean.

## Independent reproduction: `demos/demo-payment-cutover.sh`

The packaged demo script (bring-up → fully-choreographed run → teardown, a
fresh set of throwaway containers/processes from Run 1 above, built and run
AFTER this lane's manual proof was already complete) reproduced the
fully-choreographed GREEN result unassisted: `39` requests (this run also
included the Notification folder in the same pass), `99` assertions, `0`
failed, exit `0`. Attempt counts varied slightly run-to-run as expected for
real asynchronous latency rather than a canned/instant resolve — `1c`
resolved at attempt `3/20` this time (vs. `2/20` in Run 1), `3c` at `4/20`,
`4c` at `3/20` — still comfortably inside the `20`-attempt budget. The script
tore down its own containers and processes on exit; verified clean afterward
(`docker ps`, `ss -ltnp` for every port this lane used — none left bound).
