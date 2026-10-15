# The Behavior-Equivalence Suite

This directory holds the project's **behavior-equivalence suite** — a Newman
(Postman) contract collection captured against the running Django monolith
(`examples/00-monolith/`) that asserts the monolith's externally-observable
HTTP contract: status codes, response-body fields, and content types. It does
**not** inspect internal database state directly — it only observes effects
through the same REST surface a real client would use.

This is the Python sibling of
`~/Dev/modernizing-enterprise-applications/tooling/newman/mea.postman_collection.json`,
scoped to **r01** (the walking skeleton): the monolith is the only backend
that exists yet, so every request is parameterized by `{{baseUrl}}` and that
variable is set to the monolith's own address, `http://localhost:8000`. The
same load-bearing rule the Java project established applies here from the
start: **this collection is never rewritten per extraction, only re-pointed**
— once later iterations pull a context (review, notification, inventory,
payment, shipping, order) out of the monolith into its own service, this
exact, unedited collection gets re-run against the new `baseUrl` and a
context is only "done" once it passes unchanged.

## Files

| File | Purpose |
|---|---|
| `mea.postman_collection.json` | The collection itself: Smoke + four checkout scenarios. Every request is parameterized by `{{baseUrl}}`. |
| `local.postman_environment.json` | Points `{{baseUrl}}` at the monolith, `http://localhost:8000`. |
| `GOLDEN-BASELINE.md` | The frozen record of the r01 baseline run: what was running, the exact `newman` summary, and what each scenario strictly asserts. |

## Scenarios asserted

1. **Smoke** — the target is reachable and serves all three seeded SKUs
   (`SKU-WIDGET-001`, `SKU-GADGET-002`, `SKU-GIZMO-003`).
2. **Scenario 1 — Happy-Path Checkout** — `POST /api/orders` with an in-stock
   line item returns `201 Created` with `status: "CONFIRMED"` immediately (the
   monolith's checkout is fully synchronous at r01 — there is no `PENDING`
   state to observe), the correct total/line items, and a `Location` header
   (`/api/orders/{id}`); a follow-up `GET /api/orders/{id}` confirms the
   persisted status; and `GET /api/inventory/{sku}` confirms
   `quantityOnHand` dropped by exactly the ordered quantity.
3. **Scenario 2 — Out-of-Stock** — ordering more than `quantityOnHand` (against
   the deliberately low-stock seeded `SKU-GIZMO-003`, quantity 5) returns
   `409 Conflict` with `{ "error": "OUT_OF_STOCK", "message": "...<sku>...",
   "timestamp": ... }`, and stock is confirmed **unchanged** afterward —
   `inventory/services.py`'s `reserve()` raises `InsufficientStock` before any
   write happens.
4. **Scenario 3 — Payment-Declined** — a checkout whose `paymentMethod` is the
   `DECLINE` sentinel returns `402 Payment Required` with
   `{ "error": "PAYMENT_DECLINED", "message": "...", "timestamp": ... }`, and
   stock is confirmed **not left decremented**: `order/services.py`'s single
   `@transaction.atomic()` (SMELL[ch.22]) spans inventory + order + payment,
   so a declined payment unwinds the stock reservation too — this is the
   behavior the suite protects across every future extraction, where that
   rollback stops being free and has to be rebuilt explicitly as a saga.
5. **Scenario 4 — Shipping-Failure** — a checkout whose `shippingAddress`
   contains the `SHIP-FAIL` sentinel returns `422 Unprocessable Entity` with
   `{ "error": "SHIPPING_FAILED", "message": "...", "timestamp": ... }`, and
   stock nets back to zero change: the same `transaction.atomic()` unwinds the
   inventory reservation *and* the payment capture *and* the order row itself
   — the deepest of the three failure-injection paths.

All assertions target status codes, response-body fields, and `Content-Type`
— the externally-observable contract — never internal DB rows directly, so
the same assertions hold once `{{baseUrl}}` points at an extracted service
with its own schema.

The collection captures its own baseline state per scenario (e.g. "stock
level before") as collection variables rather than hard-coding absolute
values, so it is safe to re-run against a long-lived service without a fresh
database reset between runs.

## Running it

Start the monolith first (it is not managed by this collection), then:

```bash
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json
```

### Bringing up the monolith for a local run

```bash
# 1. Postgres — either the full r01 stack...
scripts/stack-up.sh
# ...or just a throwaway Postgres container (faster, no Kafka/Grafana needed yet):
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine

# 2. migrate + seed + run the monolith
cd examples/00-monolith
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000

# 3. in another shell, from the project root
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json
```

## How this collection will be used going forward

- **Per-extraction acceptance:** once a bounded context is pulled out of the
  monolith into its own service, this exact collection (only `baseUrl`
  changed, nothing else) must pass before that context's monolith module is
  decommissioned.
- **Versioned with the monolith:** when the monolith's contract changes
  deliberately, this collection changes with it in the same commit; an
  extracted service that still diverges afterward is a real regression, not
  suite drift.
- **No bounded-wait polling yet:** the Java sibling project's suite grows
  bounded-wait assertions once checkout goes asynchronous across a real
  service boundary (its r06+). r01 has no asynchrony — checkout is one
  synchronous HTTP round-trip against one process — so every assertion here
  is a plain immediate check. Expect this file to grow bounded-wait helpers
  the same way once this project's own extractions make checkout async.
