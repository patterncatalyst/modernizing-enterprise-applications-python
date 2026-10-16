# The r07 NEWMAN-BASELINE lane — the FINAL monolith-anchored baseline

This file is **new at r07** and does **not** touch or supersede
`GOLDEN-BASELINE.md` (the r01-anchored record of the r01 golden baseline plus
the r02/r03/r04/r05/r06 cutover lanes recorded in that same file). This is a
separate, standalone record for a different moment in the project's
lifecycle: **the last time the monolith is the system of record for the order
context.** The order context is about to be extracted into its own
order-service, fronted by a GraphQL gateway that aggregates it with
inventory, payment, shipping, and reviews — and once that extraction lands,
the monolith's order module is decommissioned. This is the final
"monolith-is-the-referent" snapshot everything in that later extraction will
be held equivalent to, the same role r01's baseline played for every
extraction before it.

This lane is scoped to `tooling/newman/` only (per the Phase-2 build
contract). It does **not** perform the extraction, the decommission, or the
conversion of this suite into an order-service-vs-monolith equivalence
contract — that is explicitly later-lane work. This lane only:

1. Adds an **Order Context Contract** folder (O1–O4) that proves the
   monolith's existing `/api/orders` surface against the shape the later
   order-service must reproduce.
2. Adds a **STAGED, inert-by-default GraphQL Gateway Contract** folder (G1)
   — a placeholder for the gateway that lands in a later lane, wired but
   never executed against anything live in this lane.
3. Adds forward-reference environment files for both of those later lanes'
   own services.
4. Proves the whole, now-larger suite is still green against the live
   monolith, with the new folders behaving exactly as designed.

## What's new vs. r06

- **Doesn't change:** Smoke, the four checkout scenarios, Review, Inventory,
  Payment, Shipping, and Notification Context Contract — byte-for-byte.
- **New collection folders:** `Order Context Contract` (O1–O4), inserted
  between Shipping Context Contract and Notification Context Contract (the
  same non-terminal slot and guard idiom Inventory/Payment/Shipping already
  use); `GraphQL Gateway Contract` (G1), inserted as the new LAST folder
  (after Notification), STAGED and inert by default.
- **New collection variables:** `orderContractOrderId` (default `""`),
  `graphqlUrl` (default `http://localhost:8090`, so the GraphQL folder's URL
  always resolves to something even when no environment file sets it).
- **New environment files:** `order-service.postman_environment.json`
  (`baseUrl=http://localhost:8088`, forward-ref, not yet exercised — same
  pattern as r06's `shipping-service.postman_environment.json`) and
  `graphql-gateway.postman_environment.json`
  (`graphqlUrl=http://localhost:8090`, forward-ref, not yet exercised).
- **New env-var flags:** `orderContractEnabled` (Order Context Contract),
  `graphqlContractEnabled` (GraphQL Gateway Contract) — both default off.

## The Order Context Contract folder (O1–O4)

Mirrors the monolith's actual `order/views.py` + `order/serializers.py`
contract directly (read, not guessed):

- **O1** — `POST /api/orders` (one `SKU-WIDGET-001`, `CARD-VISA`) → `201
  Created` today (the monolith's default `PAYMENT_MODE=synchronous` /
  `SHIPPING_MODE=inprocess`) **or `202 Accepted`** (tolerant of the upcoming
  choreographed path, same `[201, 202]` tolerance idiom Scenario 1/N1
  already use), plus a `Location: /api/orders/{id}` header and a numeric
  `id`. Captures `orderContractOrderId`.
- **O2** — `GET /api/orders/{id}` → `200` with the camelCase read-model
  shape straight off `OrderSerializer`: `id, customerId, status,
  totalCents, createdAt, shippingAddress, items:[{sku, quantity,
  unitPriceCents}]`. Deliberately asserts **shape**, not a specific terminal
  `status` value — this folder holds unchanged whether checkout is
  synchronous (`CONFIRMED` immediately) or choreographed (`PENDING`
  observed here, `CONFIRMED` later), with no bounded-wait poll of its own
  needed for a shape-only contract check.
- **O3** — `GET /api/orders` → `200` with an array containing the order O1
  created (`order/views.py::OrderListCreateView.get` → `services.list_all()`).
- **O4** — `GET /api/orders/999999999` → `404` with the uniform
  `{error, message, timestamp}` body and `error: "NOT_FOUND"` (confirmed
  directly against `order/services.py::get_by_id` raising
  `ResourceNotFound` → `common/exceptions.py`'s `api_exception_handler`).

Guard idiom: identical to Inventory/Payment/Shipping — each item's **test
script** (not pre-request script) checks `pm.environment.get('orderContractEnabled')
!== 'true'` and returns immediately, asserting nothing, when it isn't set. No
`postman.setNextRequest` anywhere in this folder, so it can never strand the
Notification Context Contract folder that follows it, in any flag
combination. O1's `POST` (and O2–O4's `GET`s) fire unconditionally even with
the guard off — the same way Scenario 1/3/4 and N1 already fire real
checkouts unconditionally on every single run, flag or no flag.

## The GraphQL Gateway Contract folder (G1) — STAGED, inert

A single placeholder request for the order-service + GraphQL gateway that
lands in a **later** lane:

```graphql
{
  order(id: <id>) {
    id
    status
    totalCents
    items { sku stock { quantityOnHand } }
    payments { status }
    shipments { status }
    reviews { rating }
  }
}
```

`POST {{graphqlUrl}}/graphql`, env-guarded by `graphqlContractEnabled ===
'true'`, default off. Unlike every test-script-only-guarded folder above,
this one deliberately reuses the Notification Context Contract folder's own
**terminal** guard idiom (`postman.setNextRequest(null)` in the
pre-request script when the flag is off) instead of the non-terminal,
fire-unconditionally idiom Order/Inventory/Payment/Shipping use. Reason: a
pre-request script can choose what runs *next*, but it cannot skip the
*current* request's send — so an unconditionally-firing `POST` against a
gateway that does not exist yet (`:8090`, nothing listening) would turn a
plain connection refusal into a spurious request-level failure on every
run, including the no-flags control run below. Placing this folder
**terminal** (the new last folder in the collection, after Notification)
lets the guard stop the run cleanly *before* G1 is ever reached whenever the
flag is off — which, in this lane's proof runs below, it always is: both
runs leave `notificationContractEnabled` unset too, so Notification's own
pre-existing `N1` guard already ends the run one request earlier, and G1's
own `POST` is **never even attempted** (confirmed below: identical request
count, 33, in both the order-guard-on and no-flags runs — a 34th request
would appear if G1 ever fired).

## What was running

| Component | Address | Mode |
|---|---|---|
| Postgres | `localhost:5432` (`monolith`/`monolith`/`monolith`) | throwaway `postgres:18.6-alpine`, empty volume, migrated + seeded fresh |
| `examples/00-monolith` (Django 5.2 + DRF) | `:8000` | `uv run python manage.py runserver 0.0.0.0:8000`, **default config** — `PAYMENT_MODE=synchronous`, `SHIPPING_MODE=inprocess`, `INVENTORY_MODE=local` (unset/defaults) — checkout is fully synchronous, `POST /api/orders` returns `201 CONFIRMED` in the same HTTP round-trip |

newman 6.2.2 for both runs below. `mea.postman_collection.json` was the
collection file edited by this lane itself (the Order Context Contract and
GraphQL Gateway Contract folders being proven here).

## Run 1 — required acceptance proof: `orderContractEnabled=true`, GraphQL OFF

```bash
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json \
    --env-var orderContractEnabled=true
```

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│                requests │                33 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│            test-scripts │                66 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│      prerequest-scripts │                37 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│              assertions │                72 │                 0 │
├─────────────────────────┴───────────────────┴───────────────────┤
│ total run duration: 2.6s                                        │
├─────────────────────────────────────────────────────────────────┤
│ total data received: 12.44kB (approx)                           │
├─────────────────────────────────────────────────────────────────┤
│ average response time: 61ms [min: 29ms, max: 180ms, s.d.: 29ms] │
└─────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0.** The Order Context Contract
folder's own 13 assertions all pass:

```
❏ Order Context Contract
↳ O1. Checkout for the order contract -> 201 or 202 Accepted
  POST http://localhost:8000/api/orders [201 Created, 555B, 65ms]
  ✓  Order creation returns 201 (synchronous) or 202 (choreographed)
  ✓  Content-Type is application/json
  ✓  Location header present and references the created order
  ✓  Order id is a number

↳ O2. Get the created order by id -> 200, read-model shape (camelCase)
  GET http://localhost:8000/api/orders/6 [200 OK, 519B, 57ms]
  ✓  Order lookup returns 200
  ✓  Returned order id matches the created id
  ✓  Read-model shape is camelCase: id, customerId, status, totalCents, createdAt, shippingAddress, items
  ✓  Items are camelCase: sku, quantity, unitPriceCents

↳ O3. List all orders -> 200, array
  GET http://localhost:8000/api/orders [200 OK, 977B, 57ms]
  ✓  Order list returns 200
  ✓  Response is an array containing the order created by O1

↳ O4. Get unknown order id -> 404, uniform error body
  GET http://localhost:8000/api/orders/999999999 [404 Not Found, 407B, 52ms]
  ✓  Unknown order id returns 404
  ✓  Uniform error body: error/message/timestamp present
  ✓  Documented error contract: error=NOT_FOUND
```

O1 returned the synchronous `201 Created` (today's default config, as
expected — `PAYMENT_MODE`/`SHIPPING_MODE` were left unset). The run then
proceeded into the Notification Context Contract folder's N1 (a plain
checkout that fires unconditionally regardless of any guard) and stopped
there — `notificationContractEnabled` was not set, so N1's own pre-existing
`postman.setNextRequest(null)` guard ended the run at that point, exactly as
designed. **The GraphQL Gateway Contract folder's G1 was never reached and
never fired** — 33 total requests executed, matching the pre-existing
folders (Smoke 1 + Scenario 1–4's 13 + Review's 5 + Inventory's 3 +
Payment's 3 + Shipping's 3 + Order's 4 + Notification's N1 = 33); a 34th
request would appear in this count if G1 had fired.

## Run 2 — required acceptance proof: no flags at all (both guards off)

```bash
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json
```

```
┌─────────────────────────┬───────────────────┬───────────────────┐
│                         │          executed │            failed │
├─────────────────────────┼───────────────────┼───────────────────┤
│              iterations │                 1 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│                requests │                33 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│            test-scripts │                66 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│      prerequest-scripts │                37 │                 0 │
├─────────────────────────┼───────────────────┼───────────────────┤
│              assertions │                59 │                 0 │
├─────────────────────────┴───────────────────┴───────────────────┤
│ total run duration: 2.6s                                        │
├─────────────────────────────────────────────────────────────────┤
│ total data received: 16.81kB (approx)                           │
├─────────────────────────────────────────────────────────────────┤
│ average response time: 62ms [min: 28ms, max: 181ms, s.d.: 30ms] │
└─────────────────────────────────────────────────────────────────┘
```

**Fully green, 0 failed, newman exit code 0 — identical request count (33)
to Run 1, 13 fewer assertions (59 vs. 72) — exactly the Order Context
Contract folder's own 13 assertions that only run when its guard is on.**
O1–O4 still fired (same unconditional-request idiom as Inventory/Payment/
Shipping) but asserted nothing: O1's `POST` still created a real order
(`201 Created`), O2's `GET` hit `/api/orders/` (the stale, never-set default
`orderContractOrderId=""`, resolving to a `404` — harmless, since no
assertion runs against it, the same already-established behavior
Payment/Shipping's own id-lookup items exhibit when their guard is off), O3
still listed orders (`200`), O4 still hit the unknown-id `404`. **The
GraphQL Gateway Contract folder's G1 was, again, never reached and never
fired** — same 33-request count as Run 1, confirming the folder's inertness
holds with or without `orderContractEnabled` set, as long as
`notificationContractEnabled` (the flag that gates reaching the folders
after Notification) is off, which it is by default.

## Conversion plan (for the later lane)

This lane deliberately stops short of the conversion itself — recorded here
so the later lane that performs it has a clear brief:

1. **Extract the order context** into a standalone order-service
   (`examples/07-order-service` or similar), reproducing the exact
   `OrderSerializer`/`OrderCreateSerializer` read/write shape this lane's
   Order Context Contract folder (O1–O4) already pins down byte-for-byte.
   Re-point `order-service.postman_environment.json`'s `baseUrl` at it (the
   file already exists, added by this lane, forward-referencing `:8088`).
2. **Stand up the GraphQL gateway** aggregating order + inventory + payment
   + shipping + reviews, matching the shape G1 already encodes. Flip
   `graphqlContractEnabled=true` and re-point
   `graphql-gateway.postman_environment.json`'s `graphqlUrl` (already
   exists, forward-referencing `:8090`) once it's live; G1's own assertions
   are already written and waiting.
3. **Decommission the monolith's order module** once the order-service
   passes O1–O4 unedited (the same "exact, unedited collection, only
   `baseUrl` re-pointed" rule every prior extraction in this project has
   followed) and the strangler proxy's own order-routing flag is proven in
   both states (the same flag-off/flag-on/flip-back/negative-check sequence
   r02's NEWMAN-CUTOVER lane established — see `GOLDEN-BASELINE.md`).
4. **Convert this equivalence suite into a contract suite** for the order
   context specifically: once the monolith's own `/api/orders` is gone,
   there is nothing left to be "equivalent to" on that surface — O1–O4
   becomes a contract the order-service alone is held to, the same
   terminal state r02–r06's extracted-context folders are already
   structurally ready for (they already assert the externally-observable
   HTTP contract only, never internal DB state, specifically so they
   survive their own context's monolith module disappearing).

## Acceptance criteria met

- Order Context Contract folder added, env-guarded (`orderContractEnabled`),
  genuinely green against the live monolith: `POST /api/orders` tolerant of
  `201|202`, `GET /api/orders/{id}`'s camelCase read-model shape, the list
  endpoint, and the uniform `404` — all confirmed in Run 1.
- GraphQL Gateway Contract folder added, STAGED, and proven inert — never
  even attempted over the wire — in both Run 1 (order guard on) and Run 2
  (no flags at all).
- `order-service.postman_environment.json` and
  `graphql-gateway.postman_environment.json` added.
- `GOLDEN-BASELINE-r07.md` created as a new file; `GOLDEN-BASELINE.md` (the
  r01-anchored record) was not touched.
- Every pre-existing folder (Smoke, Scenario 1–4, Review, Inventory,
  Payment, Shipping, Notification) is unaffected — confirmed by Run 2's
  byte-identical request count and pass/fail shape relative to the r06
  baseline's own no-flags behavior.
