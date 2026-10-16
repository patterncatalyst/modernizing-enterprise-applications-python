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
same rule the Java project established applies here from the
start: **this collection is never rewritten per extraction, only re-pointed**
— once later iterations pull a context (review, notification, inventory,
payment, shipping, order) out of the monolith into its own service, this
exact, unedited collection gets re-run against the new `baseUrl` and a
context is only "done" once it passes unchanged.

## Files

| File | Purpose |
|---|---|
| `mea.postman_collection.json` | The collection itself: Smoke + four checkout scenarios + the r02 **Review Context Contract** folder. Every request is parameterized by `{{baseUrl}}`. |
| `local.postman_environment.json` | Points `{{baseUrl}}` at the monolith, `http://localhost:8000`. |
| `proxy.postman_environment.json` | Points `{{baseUrl}}` at the r02 strangler proxy (`examples/01-strangler-proxy`), `http://localhost:8888` — the re-pointing target for the cutover evidence below. |
| `GOLDEN-BASELINE.md` | The frozen record of the r01 baseline run, PLUS the r02 NEWMAN-CUTOVER lane's evidence trail (the exact `newman` summaries for the proxy flag-off/flag-on/flip-back/negative-check sequence, and the chunked-body defect discovered while proving it), PLUS the r02 PHASE-2 repair lane's evidence trail (the fix, the regression test, and the corrected re-run — fully green through the proxy in both flag states). |

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
   the low-stock seeded `SKU-GIZMO-003`, quantity 5) returns
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

6. **Review Context Contract** (added at r02, see `examples/02-review-service`)
   — `GET /api/reviews?sku=...` returns `200` with a camelCase array
   (`id, customerId, sku, rating, comment, createdAt`), scoped to the
   requested SKU, and captures a seeded review id; `GET /api/reviews/{id}`
   returns the same shape for a single review; `POST /api/reviews` with
   **no credentials** returns `401` with the uniform
   `{error,message,timestamp}` body and `error: "ERROR"` (the generic
   auth-failure catch-all code both the monolith's DRF stack and the
   FastAPI review-service's exception handler produce, not a dedicated
   `UNAUTHORIZED` code — see `examples/02-review-service/app/errors.py`);
   `POST /api/reviews` with HTTP Basic **`reviewer:review-pw-r02`** and a
   valid body returns `201` with a `Location: /api/reviews/{id}` header and
   the camelCase echo; the same request with an out-of-range `rating`
   (`99`) returns `400 VALIDATION_FAILED`. This is the folder that gets
   re-pointed, unedited, at `{{baseUrl}}=http://localhost:8888` (the
   strangler proxy) to prove the review cutover — see
   "The r02 NEWMAN-CUTOVER lane" in `GOLDEN-BASELINE.md`.

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

### Running the r02 cutover evidence through the strangler proxy

```bash
# Monolith on :8000, review-service on :8001 (both pointed at the same
# migrated+seeded Postgres), and the proxy on :8888 -- see the "Bringing up
# the monolith" section above and examples/02-review-service/README.md and
# examples/01-strangler-proxy/README.md for each component's own run
# instructions.

# Flag OFF (default) -- reviews served by the monolith, through the proxy:
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/proxy.postman_environment.json

# Flag ON (restart the proxy with STRANGLER_REVIEW_ENABLED=true) -- reviews
# now served by examples/02-review-service, everything else still the
# monolith. Same collection, same environment file, only the proxy's own
# flag changed:
STRANGLER_REVIEW_ENABLED=true uv run uvicorn app.main:app --port 8888
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/proxy.postman_environment.json
```

See "The r02 NEWMAN-CUTOVER lane" in `GOLDEN-BASELINE.md` for the full,
real evidence trail captured this way (flag off / flag on / flip back /
review-service-down negative check) — **and a real defect in
`examples/01-strangler-proxy` discovered while capturing it**: the proxy
forwarded request bodies as `Transfer-Encoding: chunked`, which the WSGI
monolith decoded as a zero-length body, breaking every `POST`/`PUT`/`PATCH`
routed through the proxy to the monolith. See "The r02 PHASE-2 repair lane"
in the same file for the fix (buffer the body, forward it with a correct
`Content-Length`) and the corrected re-run: the full suite — Smoke, all
four checkout scenarios, and the Review Context Contract — is now fully
green through the proxy in **both** flag states, with the review-service-
down fail-safe (a real `502`, never a masked `200`) still confirmed RED then
green.

## How this collection will be used going forward

- **Per-extraction acceptance:** once a bounded context is pulled out of the
  monolith into its own service, this exact collection (only `baseUrl`
  changed, nothing else) must pass before that context's monolith module is
  decommissioned.
- **Versioned with the monolith:** when the monolith's contract changes,
  this collection changes with it in the same commit; an
  extracted service that still diverges afterward is a real regression, not
  suite drift.
- **No bounded-wait polling yet:** the Java sibling project's suite grows
  bounded-wait assertions once checkout goes asynchronous across a real
  service boundary (its r06+). r01 has no asynchrony — checkout is one
  synchronous HTTP round-trip against one process — so every assertion here
  is a plain immediate check. Expect this file to grow bounded-wait helpers
  the same way once this project's own extractions make checkout async.
