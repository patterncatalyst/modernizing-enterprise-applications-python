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
