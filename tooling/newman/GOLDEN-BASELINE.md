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
here until the monolith's own contract changes deliberately (in which case
this collection changes with it, in the same commit).

## What was run, and against what

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine` container, empty volume, migrated + seeded fresh |
| `examples/00-monolith` (Django 5.2 + DRF) | `:8000` | `uv run python manage.py runserver 0.0.0.0:8000`; checkout is **fully synchronous** — `POST /api/orders` returns the terminal state (`201 CONFIRMED` or the appropriate error) in the same HTTP round-trip, no polling |

The suite was run against `{{baseUrl}}=http://localhost:8000` — the monolith
directly, since no proxy or extracted service exists at r01.

Stock levels were whatever `manage.py seed` produced (`SKU-WIDGET-001` 100,
`SKU-GADGET-002` 50, `SKU-GIZMO-003` 5 — deliberately low to exercise the
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
between — proves the suite's "capture stock before" pattern is genuinely
idempotent, not an artifact of a clean database):

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
   reservation and the payment capture, so a decline unwinds both for free.
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
