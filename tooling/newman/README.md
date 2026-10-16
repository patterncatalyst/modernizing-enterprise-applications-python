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
| `mea.postman_collection.json` | The collection itself: Smoke + four checkout scenarios (the four checkout scenarios' terminal states/201→202-tolerant conversion and bounded-wait polls landed at r05, see below; Scenario 1's own poll got a wider, dedicated budget and Scenario 4 gained a new env-guarded refund poll at r06) + the r02 **Review Context Contract** folder + the r04 **Inventory Context Contract** folder + the r05 **Payment Context Contract** folder + the r06 **Shipping Context Contract** folder + the r03 **Notification Context Contract** folder (the suite's first bounded-wait/async folder). Every request is parameterized by `{{baseUrl}}`. |
| `local.postman_environment.json` | Points `{{baseUrl}}` at the monolith, `http://localhost:8000`. |
| `proxy.postman_environment.json` | Points `{{baseUrl}}` at the strangler proxy (`examples/01-strangler-proxy`), `http://localhost:8888` — the re-pointing target for the cutover evidence below. |
| `shipping-service.postman_environment.json` | Forward-ref: points `{{baseUrl}}` at the standalone shipping-service's own address, `http://localhost:8087` — not yet exercised (the shipping-service hasn't landed live), added at r06 for the later cutover lane to re-point at, same as every other extracted-service environment file in this directory. |
| `GOLDEN-BASELINE.md` | The frozen record of the r01 baseline run, PLUS the r02 NEWMAN-CUTOVER lane's evidence trail (the exact `newman` summaries for the proxy flag-off/flag-on/flip-back/negative-check sequence, and the chunked-body defect discovered while proving it), PLUS the r02 PHASE-2 repair lane's evidence trail (the fix, the regression test, and the corrected re-run — fully green through the proxy in both flag states), PLUS the r03 NEWMAN-ASYNC lane's evidence trail (the Notification Context Contract's bounded-wait poll, live against a real Kafka broker, in both proxy flag states, plus its own negative check), PLUS the r05 NEWMAN-ASYNC CONVERSION lane's evidence trail (converting the four checkout scenarios to tolerate the upcoming 201→202 async flip, with every new bounded-wait poll resolving on attempt 1/0 retries against today's still-synchronous monolith), PLUS the r06 NEWMAN-SHIP Phase-2 lane's evidence trail (Scenario 1's widened poll budget, Scenario 4's new env-guarded refund poll, and the Shipping Context Contract folder, proven GREEN against the in-process monolith with the shipping guard off). |

## Scenarios asserted

1. **Smoke** — the target is reachable and serves all three seeded SKUs
   (`SKU-WIDGET-001`, `SKU-GADGET-002`, `SKU-GIZMO-003`).
2. **Scenario 1 — Happy-Path Checkout** — `POST /api/orders` with an in-stock
   line item returns `201 Created` (today's synchronous monolith) **or `202
   Accepted`** (the upcoming choreographed/async checkout, tolerated since
   r05 — see "The r05 NEWMAN-ASYNC CONVERSION lane" in `GOLDEN-BASELINE.md`)
   with a `Location` header (`/api/orders/{id}`); a bounded-wait poll of `GET
   /api/orders/{id}` then strictly asserts the order reaches terminal
   `CONFIRMED` (never a naked `2xx`, never able to pass on a stuck `PENDING`)
   plus the correct total/line items; `GET /api/inventory/{sku}` confirms
   `quantityOnHand` dropped by exactly the ordered quantity. Against today's
   synchronous monolith the poll resolves on attempt 1 with 0 retries. This
   poll's budget (`happyPathPollMaxAttempts` x `happyPathPollDelayMs` = `40 x
   750ms`, a ~30s budget) was widened at r06 — its own, dedicated variable,
   not the shared `checkoutPollMaxAttempts`/`checkoutPollDelayMs` Scenarios
   3/4 still use — to tolerate the orchestrated shipping saga's extra Kafka
   hops downstream of `CONFIRMED` (`order.placed` -> `payment.captured` ->
   shipping saga -> `shipment.dispatched` -> `CONFIRMED`); the terminal
   `CONFIRMED` assertion itself was never relaxed, only given more retries.
3. **Scenario 2 — Out-of-Stock** — ordering more than `quantityOnHand` (against
   the low-stock seeded `SKU-GIZMO-003`, quantity 5) returns
   `409 Conflict` with `{ "error": "OUT_OF_STOCK", "message": "...<sku>...",
   "timestamp": ... }`, and stock is confirmed **unchanged** afterward —
   `inventory/services.py`'s `reserve()` raises `InsufficientStock` before any
   write happens. Left unconverted since r05 (see below) — the reservation
   rejects before any async work could begin, so there's nothing to tolerate.
4. **Scenario 3 — Payment-Declined** — a checkout whose `paymentMethod` is the
   `DECLINE` sentinel returns `402 Payment Required` (today) **or `202
   Accepted`** (async, tolerated since r05) with
   `{ "error": "PAYMENT_DECLINED", "message": "...", "timestamp": ... }` on
   the `402` path. Today's monolith rolls back the ENTIRE
   `@transaction.atomic()` (SMELL[ch.22]) on a decline — including the
   `Order` row itself — so there is no order id to poll; the suite detects
   this and jumps straight to a bounded-wait poll of `GET
   /api/inventory/{sku}` that strictly asserts stock nets back to zero
   (0 retries against today's monolith). Only on the future `202` response
   does the suite also bounded-wait poll `GET /api/orders/{id}` for terminal
   `PAYMENT_DECLINED` first.
5. **Scenario 4 — Shipping-Failure** — a checkout whose `shippingAddress`
   contains the `SHIP-FAIL` sentinel returns `422 Unprocessable Entity`
   (today) **or `202 Accepted`** (async, tolerated since r05) with
   `{ "error": "SHIPPING_FAILED", "message": "...", "timestamp": ... }` on
   the `422` path. Same shape as Scenario 3: today's monolith rolls back the
   order row itself too, so the suite jumps straight to the bounded-wait
   net-zero stock poll (0 retries today); only the future `202` response also
   bounded-wait polls the order for terminal `SHIPPING_FAILED` first — see
   "Why Scenario 4's `SHIPPING_FAILED` poll never runs against today's
   monolith" in `GOLDEN-BASELINE.md` for why that's by design, not a gap.
   **r06** added a fifth item, 4e: an env-guarded (`shippingContractEnabled`)
   bounded-wait poll of `GET /api/payments?orderId=<the order>` until the
   payment reaches `REFUNDED` — the orchestrated shipping saga's compensating
   action once a payment has already been captured before the saga fails.
   Inert both by its own guard and structurally: 4d's test script jumps
   straight past 4e whenever `shipFailOrderId` is empty (today's sync `422`
   path never persists an order, same reason 4c is already skipped on that
   branch), so 4e never fires a malformed request. Against today's in-process
   monolith 4e never actually asserts anything, guard on or off — see "The
   r06 NEWMAN-SHIP Phase-2 lane" in `GOLDEN-BASELINE.md`.

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

7. **Notification Context Contract** (added at r03, see
   `examples/03-notification-service`) — the suite's first async,
   env-guarded, bounded-wait folder. N1 is a plain checkout (`POST
   /api/orders`, `201 CONFIRMED` — checkout itself stays synchronous; only
   notification delivery moved off the request path and onto `order.placed`
   via the outbox) that captures the created order's `id`/`customerId`. N2
   polls `GET /api/notifications?customerId=` with a bounded-wait self-loop
   (`notificationPollMaxAttempts` x `notificationPollDelayMs` = 20 x 750ms,
   a ~15s budget; only delays on a *retry*, never on attempt 0) until a
   notification whose `orderId` matches the one N1 created appears, then
   strictly asserts its camelCase shape (`id, customerId, orderId, channel,
   message, sentAt`), `channel: "EMAIL"`, and that `message` contains the
   order id. If the budget is exhausted the final assertion fails strictly
   — it never hangs and never soft-passes. The whole folder is env-guarded
   and INERT by default: each request's pre-request script checks
   `pm.environment.get('notificationContractEnabled') === 'true'` (note:
   `pm.environment.get`/`pm.variables.get`, NOT `pm.collectionVariables.get`
   — `--env-var` populates the *environment* scope, verified empirically
   against this newman build; a collection-variable read would silently
   never see it) and calls `postman.setNextRequest(null)` when it isn't
   set. Because this is the LAST folder in the collection, that cleanly
   ends the run right there for any existing, unmodified invocation (CI
   gates that predate this folder, local smoke runs, etc.) — N1 itself
   still fires even when the guard is off (it's a plain synchronous
   checkout that needs no Kafka, the same kind of request Scenario 1
   already proves safe), but N2's bounded-wait poll — the one request that
   actually needs Kafka — is never reached, and its own test script also
   no-ops immediately if it somehow is. This is the folder that gets
   re-pointed, unedited, at the strangler proxy to prove the notification
   cutover, enabled per run via `--env-var notificationContractEnabled=true`
   — see "The r03 NEWMAN-ASYNC lane" in `GOLDEN-BASELINE.md`.

8. **Inventory Context Contract** (added at r04, see
   `examples/04-inventory-service`) — three plain, synchronous reads, no
   bounded-wait needed (unlike Notification, the read path here has no
   eventual-consistency boundary: `GET /api/inventory*` is served either by
   the monolith directly or, once `STRANGLER_INVENTORY_ENABLED=true`, by
   `examples/04-inventory-service`'s own `inventory` schema — both are a
   single synchronous DB read). `GET /api/inventory` returns `200` with a
   camelCase array (`sku, name, priceCents, quantityOnHand`) containing all
   three seeded SKUs; `GET /api/inventory/SKU-WIDGET-001` returns the same
   shape for one item; `GET /api/inventory/NOPE` returns `404` with the
   uniform `{error,message,timestamp}` body and `error: "NOT_FOUND"` (the
   same code both the monolith's `common/exceptions.py::ResourceNotFound`
   and `examples/04-inventory-service/app/errors.py::ResourceNotFound`
   produce). Env-guarded by `inventoryContractEnabled === 'true'`, enabled
   per run via `--env-var inventoryContractEnabled=true` — see "The r04
   NEWMAN-GRPC lane" in `GOLDEN-BASELINE.md`.

   **Guard mechanism — a deliberate, documented departure from the
   Notification folder's literal idiom.** The Notification folder's guard
   (each item's pre-request script calling `postman.setNextRequest(null)`
   when its flag is unset) only works safely because Notification is the
   collection's *last* folder — ending the run there strands nothing, since
   nothing comes after it. `postman.setNextRequest(null)` stops the entire
   collection run, not just the current folder (confirmed empirically by the
   r03 NEWMAN-ASYNC lane's own "inert-guard control run": the run ends
   exactly at the Notification folder's first request). The Inventory
   Context Contract folder is placed **between Review Context Contract and
   Notification Context Contract** (so that `--env-var
   inventoryContractEnabled=true` alone — with no `notificationContractEnabled`
   — exercises Smoke, all four checkout scenarios, Review, and Inventory
   before falling through into Notification's own, untouched guard exactly
   as before). Reusing the literal `setNextRequest(null)` idiom from this
   non-terminal position would strand the Notification folder every time
   Inventory's flag is off — including the r03 lane's own previously-working,
   documented `--env-var notificationContractEnabled=true`-only invocation,
   which does not set `inventoryContractEnabled`. Instead, each Inventory
   item's **test script** (not its pre-request script) checks
   `pm.environment.get('inventoryContractEnabled') === 'true'` and returns
   immediately, asserting nothing, when it isn't set — no
   `postman.setNextRequest` call anywhere in this folder, so it can never end
   the run early and can never strand anything placed before or after it, in
   any flag combination. The three requests themselves still fire
   unconditionally even when the guard is off (confirmed safe: they are the
   same idempotent, side-effect-free `GET`s Smoke and the checkout scenarios'
   own stock-capture steps already exercise on every single run, flag or no
   flag). This is a stricter, simpler safety property than the Notification
   folder's terminal-only idiom affords, not a weaker one — it was the
   deliberate choice precisely because this folder does **not** occupy the
   terminal position.

9. **Payment Context Contract** (added at r05) — `GET
   /api/payments?orderId={{happyPathOrderId}}` returns `200` with a camelCase
   array (`id, orderId, amountCents, method, status, createdAt`) scoped to
   the Scenario 1 happy-path order, and captures the payment id; `GET
   /api/payments/{id}` returns the same shape for that payment with
   `status: "CAPTURED"`; `GET /api/payments/999999999` returns `404` with the
   uniform `{error,message,timestamp}` body and `error: "NOT_FOUND"`.
   Env-guarded by `paymentContractEnabled === 'true'`, enabled per run via
   `--env-var paymentContractEnabled=true` — see "The r05 NEWMAN-ASYNC
   CONVERSION lane" in `GOLDEN-BASELINE.md`. Uses the same test-script-level,
   no-`setNextRequest` guard idiom as the Inventory Context Contract folder
   (it sits in the same non-terminal position, between Inventory and
   Notification, so it can never strand Notification when its own flag is
   off).

10. **Shipping Context Contract** (added at r06, see
    `examples/06-shipping-service`) — `GET
    /api/shipments?orderId={{happyPathOrderId}}` returns `200` with a
    camelCase array (`id, orderId, address, status, createdAt`) scoped to the
    Scenario 1 happy-path order, and captures the shipment id; `GET
    /api/shipments/{id}` returns the same shape for that shipment with
    `status: "DISPATCHED"` (the in-process monolith's
    `shipping.services.dispatch()` default); `GET /api/shipments/999999999`
    returns `404` with the uniform `{error,message,timestamp}` body and
    `error: "NOT_FOUND"`. Env-guarded by `shippingContractEnabled === 'true'`,
    enabled per run via `--env-var shippingContractEnabled=true` — see "The
    r06 NEWMAN-SHIP Phase-2 lane" in `GOLDEN-BASELINE.md`. Uses the same
    test-script-level, no-`setNextRequest` guard idiom as Inventory/Payment
    (it sits in the same non-terminal position, between Payment and
    Notification, so it can never strand Notification when its own flag is
    off).

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

### Running the r03 NEWMAN-ASYNC evidence through the strangler proxy

The Notification Context Contract folder is env-guarded and does nothing
unless `notificationContractEnabled=true` is passed on the command line —
every invocation below adds `--env-var notificationContractEnabled=true`.
This lane needs a real Kafka broker, in addition to everything r02 needed:

```bash
# Postgres + Kafka (the repo's apache/kafka:4.3.1 pin, KRaft, single node):
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine
docker run -d --name mea-mono-kafka -p 9092:9092 \
  -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT \
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true -e CLUSTER_ID=MkU3OEVBNTcwNTJENDM2Qk \
  docker.io/apache/kafka:4.3.1
# (or scripts/stack-up.sh, which brings up the same Postgres + Kafka + LGTM.)

# Monolith on :8000, PLUS its outbox relay and its own order.placed
# self-consumer (the flag-OFF read model depends on the consumer):
cd examples/00-monolith
uv run python manage.py migrate && uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &
uv run python manage.py outbox_relay &
uv run python manage.py order_placed_consumer &

# notification-service on :8002 (needs its own migration first):
cd ../03-notification-service
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8002 &

# Proxy on :8888, flag OFF (default) or ON (STRANGLER_NOTIFICATION_ENABLED=true):
cd ../01-strangler-proxy
uv run uvicorn app.main:app --port 8888 &

# Flag OFF -- notifications served by the monolith's own order.placed
# consumer, through the proxy:
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var notificationContractEnabled=true

# Flag ON (restart the proxy with STRANGLER_NOTIFICATION_ENABLED=true) --
# notifications now served by examples/03-notification-service. Same
# collection, same environment file, only the proxy's own flag changed:
STRANGLER_NOTIFICATION_ENABLED=true uv run uvicorn app.main:app --port 8888
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var notificationContractEnabled=true
```

See "The r03 NEWMAN-ASYNC lane" in `GOLDEN-BASELINE.md` for the full, real
evidence trail: the full suite fully green through the proxy in both flag
states (byte-identical collection, only the flag changed), the bounded-wait
attempt counts actually observed, and the notification-service-down negative
check (a real `502` from the proxy, the bounded-wait budget exhausting
cleanly, and `newman` exiting non-zero) going RED then back to green.

### Running the r04 NEWMAN-GRPC evidence through the strangler proxy

The Inventory Context Contract folder is env-guarded the same way as
Notification (see above for the mechanism) — every invocation below adds
`--env-var inventoryContractEnabled=true`. This lane needs the inventory
service's own gRPC server (`:9004`) in addition to its HTTP surface
(`:8084`); no Kafka broker is needed for any of this (inventory's
transition-only CDC consumer, `INVENTORY_CDC_ENABLED`, stays off by
default).

There are **two independent cutover dimensions** for inventory, not one:

| Dimension | Lives in | Values |
|---|---|---|
| Where checkout-time **reserve/release** happens | the monolith's own `INVENTORY_MODE` | `local` (default — in-process, same `transaction.atomic()` as r01-r03) / `grpc` (remote, over `order.inventory_client.RemoteInventoryClient` to `INVENTORY_GRPC_TARGET`) |
| Where `GET /api/inventory*` **reads** are served | the proxy's own `STRANGLER_INVENTORY_ENABLED` | unset/`false` (default — monolith) / `true` (routed to `examples/04-inventory-service`'s HTTP surface) |

These two flags are independent and were proven in both the fully-local
(`INVENTORY_MODE=local`, proxy flag unset) and fully-gRPC
(`INVENTORY_MODE=grpc`, proxy flag `true`) combinations below — a mixed
combination (reads from inventory-service, reserve/release still local) is
possible but was not exercised here: it would split reads and writes onto
two different databases with no replication between them, which is only
sound during the brief, CDC-backfilled transition window
`examples/04-inventory-service/app/cdc_consumer.py` exists for (see its
docstring and `../CUTOVER.md`), not as a steady-state configuration.

```bash
# Postgres (no Kafka needed for this lane):
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine

# Monolith: migrate + seed (owns `public.inventory_items` as always)
cd examples/00-monolith
uv run python manage.py migrate && uv run python manage.py seed

# inventory-service: its OWN `inventory` schema, same Postgres instance --
# `alembic upgrade head` both creates the schema/table AND seeds the same
# three demo SKUs (idempotent, ON CONFLICT DO NOTHING), so GET /api/inventory
# returns an identical dataset whichever side currently serves the route.
cd ../04-inventory-service
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8084 &
# wait for grpcServerListening=true before issuing any gRPC call against :9004:
curl -s http://localhost:8084/health

# FULLY-gRPC: monolith reserves/releases over gRPC, proxy routes reads to
# inventory-service:
cd ../00-monolith
INVENTORY_MODE=grpc INVENTORY_GRPC_TARGET=localhost:9004 \
  uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 &
cd ../01-strangler-proxy
STRANGLER_INVENTORY_ENABLED=true uv run uvicorn app.main:app --port 8888 &

newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var inventoryContractEnabled=true

# FULLY-LOCAL (reversibility): restart the monolith with INVENTORY_MODE=local
# (or unset) and the proxy with STRANGLER_INVENTORY_ENABLED unset -- same
# command, same collection, same environment file:
INVENTORY_MODE=local uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 &
uv run uvicorn app.main:app --port 8888 &   # no STRANGLER_INVENTORY_ENABLED
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var inventoryContractEnabled=true
```

See "The r04 NEWMAN-GRPC lane" in `GOLDEN-BASELINE.md` for the full, real
evidence trail: the full suite fully green through the proxy in both
reserve/release-mode x read-routing combinations (byte-identical collection,
23 requests / 71 assertions, 0 failed in both), direct proof that Scenario
3 (payment-declined) and Scenario 4 (shipping-failed) net stock back to zero
in gRPC mode via the compensating `Release` RPC (not just that the suite's
own "before"/"after" assertions happened to match), and the inventory-
service-down negative check (a real proxy `502` on every read, and the
checkout's remote `Reserve` call failing with gRPC `UNAVAILABLE` mapped to a
real `503 INVENTORY_UNAVAILABLE` — never a masked success) going RED then
back to green.

### Running the r05 conversion evidence against the bare monolith

The Payment Context Contract folder is env-guarded the same way as Inventory
— add `--env-var paymentContractEnabled=true` (the monolith's `/api/payments`
surface is in-process and always up, so there's no reason to leave it off
when running locally). No proxy, Kafka, or extracted service is needed for
this lane; it runs straight against the bare monolith, same as r01:

```bash
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine

cd examples/00-monolith
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &

newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json \
    --env-var paymentContractEnabled=true
```

See "The r05 NEWMAN-ASYNC CONVERSION lane" in `GOLDEN-BASELINE.md` for the
full evidence trail: the converted four checkout scenarios' `201|402|422` OR
`202` tolerance, each new bounded-wait poll resolving on attempt 1 (0
retries) against today's still-synchronous monolith, the Payment Context
Contract folder's own evidence, the no-flags control run proving existing
callers are unaffected, and why Scenario 4's `SHIPPING_FAILED` poll is gated
behind the async branch rather than weakened to pass today.

### Running the r06 shipping evidence against the bare monolith

The Shipping Context Contract folder (and Scenario 4's new 4e refund poll)
are env-guarded the same way as Payment — add `--env-var
shippingContractEnabled=true`. No proxy, Kafka, or standalone shipping-
service is needed for this lane either; it runs straight against the bare
monolith, with `SHIPPING_MODE` left **unset** (`inprocess`, the zero-
regression default this lane must not disturb):

```bash
docker run -d --name mea-mono-pg -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  postgres:18.6-alpine

cd examples/00-monolith
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &

# Required acceptance proof -- guard OFF, no --env-var at all:
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json

# Exploratory -- guard ON, same monolith (Shipping Context Contract genuinely
# exercised; 4e's refund poll stays structurally inert -- no order id exists
# on today's synchronous SHIP-FAIL path regardless of the flag):
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json \
    --env-var shippingContractEnabled=true
```

See "The r06 NEWMAN-SHIP Phase-2 lane" in `GOLDEN-BASELINE.md` for the full
evidence trail: Scenario 1's widened, dedicated bounded-wait budget (`40 x
750ms`) resolving on attempt 1 (0 retries) against today's still-synchronous
monolith, the Shipping Context Contract folder's own evidence (genuinely
green with the guard on), why 4e's refund poll stays inert against this
monolith either way, the no-flags control run proving existing callers are
unaffected, and a robustness fix made while capturing this (4d now skips 4e
entirely rather than firing a malformed request on the sync branch).

## How this collection will be used going forward

- **Per-extraction acceptance:** once a bounded context is pulled out of the
  monolith into its own service, this exact collection (only `baseUrl`
  changed, nothing else) must pass before that context's monolith module is
  decommissioned.
- **Versioned with the monolith:** when the monolith's contract changes,
  this collection changes with it in the same commit; an
  extracted service that still diverges afterward is a real regression, not
  suite drift.
- **Bounded-wait polling, since r03:** r01 and r02 had no asynchrony to wait
  on — checkout was one synchronous HTTP round-trip, and the Review
  extraction only ever served a synchronously-consistent read. r03's
  Notification Context Contract is the first folder where a write
  (checkout) and the read that observes its effect (the notification) are
  connected only by an eventually-consistent path (outbox -> Kafka ->
  consumer), so it is the first to need a bounded-wait poll: retry on a
  fixed budget (`notificationPollMaxAttempts` x `notificationPollDelayMs`),
  never sleep on the first attempt, and fail strictly — never hang, never
  soft-pass — if the budget runs out. The Java sibling project's suite
  earned this same idiom the same way, at its own first async boundary
  (its r06); expect later folders here (payment, shipping, the order
  extraction's own eventual cutover) to reuse it unchanged.
