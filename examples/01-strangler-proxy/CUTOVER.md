# CUTOVER.md — Review strangler-fig cutover evidence trail (r02)

This file records the evidence for the single most load-bearing claim in r02:
that `STRANGLER_REVIEW_ENABLED` behind this proxy is a **safe, reversible
cutover switch**. The full run logs live in
`tooling/newman/GOLDEN-BASELINE.md`; this file is the narrative summary.

All runs below used the unedited Postman/Newman collection
(`tooling/newman/mea.postman_collection.json`) through the proxy on `:8888`
(`tooling/newman/proxy.postman_environment.json`, `baseUrl=http://localhost:8888`),
against a live stack: Postgres 18.6-alpine, the monolith on `:8000` (gunicorn/WSGI),
and `examples/02-review-service` on `:8001`. Only `STRANGLER_REVIEW_ENABLED` and
whether a backend is up changed between runs.

## The flag

`STRANGLER_REVIEW_ENABLED`, read by `app/config.py` from the environment.
Routing matches the **full** request path against `/api/reviews` (see README's
"The full-path-prefix lesson").

| Flag | Backend for `/api/reviews*` | Backend for everything else |
|---|---|---|
| `false` (default) | monolith `:8000` | monolith `:8000` |
| `true` | review-service `:8001` | monolith `:8000` |

## A bug this cutover caught (and why it matters)

The in-process routing tests (`tests/test_routing.py`, via `httpx.ASGITransport`)
passed while a real defect hid underneath: the proxy forwarded the request body
as an unread async stream, so httpx sent it upstream with
`Transfer-Encoding: chunked` and no `Content-Length`. The monolith is Django/WSGI,
which reads `CONTENT_LENGTH` and treats a missing one as an empty body — so every
`POST` routed to the monolith **through the proxy** arrived empty. It surfaced only
when the Newman suite ran against the real WSGI server over a real socket. Fixed by
buffering the body (`content = await request.body()`) so bounded requests carry a
correct `Content-Length`; a regression test now asserts the outbound upstream
request is non-chunked with the body intact. This is the strangler-fig lesson in
miniature: equivalence must be proven against the real thing, not a mock.

## Evidence trail (all green, post-fix)

### 1. Baseline — flag OFF (reversibility window)
Full suite through the proxy, reviews served by the monolith:
**19 requests / 38 test-scripts / 58 assertions, 0 failed (exit 0).**

### 2. Cutover — flag ON
Same unedited suite, `STRANGLER_REVIEW_ENABLED=true`, reviews now served by
`examples/02-review-service`, everything else still the monolith:
**19 / 38 / 58, 0 failed (exit 0)** — byte-identical in shape to run 1.

### 3. Reversibility — flip back to OFF
Restart the proxy with the flag off; monolith serves reviews again:
**19 / 38 / 58, 0 failed (exit 0).** The reversibility window is genuinely open —
flipping back is a config change plus a restart, right up until the monolith's
Review app is deliberately decommissioned (a later iteration).

### 4. Negative check — review-service down, the Review folder MUST go RED
Flag ON, `examples/02-review-service` killed, run only the `Review Context
Contract` folder: every `/api/reviews*` request gets the proxy's real `502`
(upstream unavailable), not a soft pass. **5 requests, 6/6 assertions failed,
newman exit code 1** (status-code and JSON-body assertions both fail). Restart
the review-service and re-run the same folder: **16 assertions, 0 failed (exit 0).**
The equivalence gate does not quietly pass when the extracted service is down.

## Summary of the suite runs

| # | Flag | Review served by | Everything else | Result |
|---|---|---|---|---|
| 1 | `false` | monolith | monolith | 58/58 green |
| 2 | `true` | review-service | monolith | 58/58 green |
| 3 | `false` (reverted) | monolith | monolith | 58/58 green |
| 4a | `true`, review-service **down** | *(nothing — 502)* | monolith | RED, exit 1 (as required) |
| 4b | `true`, review-service restarted | review-service | monolith | 16/16 green |

See `tooling/newman/GOLDEN-BASELINE.md` for the verbatim newman tables, and
`examples/00-monolith/SMELLS.md` (#7) for the smell this cutover begins to cure.

## Notification seam (r03)

`STRANGLER_NOTIFICATION_ENABLED` gates `/api/notifications*` to
`examples/03-notification-service` the same way `STRANGLER_REVIEW_ENABLED`
gates `/api/reviews*` to the review service — a second, independent flag in
the same proxy (`app/config.py`, `_select_backend()` in `app/main.py`). It
follows the identical OFF → ON → reversible → negative-check discipline
documented above: baseline with the flag off, cut over, flip back to prove
reversibility, then kill the notification service and confirm the proxy
returns a real `502` rather than a masked `200`. The full Newman evidence
trail for this seam (the four-run table and negative-check output) lands in
`tooling/newman/GOLDEN-BASELINE.md` from a separate lane; this file only
records that the same discipline applies.

## Inventory seam (r04) — two cutover dimensions

Inventory is the first seam with **two independent cutover switches**,
because it has two distinct call paths into the monolith:

1. **REST reads** (`GET /api/inventory*`, browsing/display traffic) — go
   through *this* proxy, gated by `STRANGLER_INVENTORY_ENABLED` exactly like
   `STRANGLER_REVIEW_ENABLED`/`STRANGLER_NOTIFICATION_ENABLED` gate their
   seams: `app/config.py` reads the flag and base URL, `_select_backend()`
   in `app/main.py` matches the full path against `/api/inventory` and
   routes to `examples/04-inventory-service` once cut over.
2. **gRPC reserve/release** (stock decrement/increment during order
   placement/cancellation) — called directly by the monolith over gRPC, and
   gated by the monolith's own `INVENTORY_MODE` setting. This path never
   goes through the strangler proxy at all — it is internal
   monolith-to-service traffic, not browser/client-facing HTTP, so there is
   nothing for `_select_backend()` to intercept.

Both switches follow the identical OFF → ON → reversible → negative-check
discipline documented above for Review and Notification: baseline with the
flag off, cut over, flip back to prove reversibility, then kill the
inventory service and confirm the affected path fails loudly (a real `502`
from this proxy for REST reads; the monolith-side equivalent for gRPC
reserve/release) rather than silently degrading. The two dimensions are
verified independently — flipping `STRANGLER_INVENTORY_ENABLED` has no
effect on `INVENTORY_MODE` or vice versa — because a design that requires
flipping both in lockstep to stay correct is not actually two independent
seams, it is one seam with an extra step.

## Payment seam (r05) — two cutover dimensions

Like Inventory, Payment is a seam with **two independent cutover switches**,
because it has two distinct call paths into the monolith:

1. **REST reads** (`GET /api/payments*`, browsing/display traffic — e.g.
   payment status/history lookups) — go through *this* proxy, gated by
   `STRANGLER_PAYMENT_ENABLED` exactly like the other three flags gate their
   seams: `app/config.py` reads the flag and base URL, `_select_backend()`
   in `app/main.py` matches the full path against `/api/payments` and
   routes to the payment-service once cut over.
2. **Asynchronous payment capture** (the write path that actually charges a
   payment method during order placement) — driven internally by the
   monolith and gated by the monolith's own `PAYMENT_MODE` setting. This
   path never goes through the strangler proxy at all — it is internal
   monolith-side processing, not browser/client-facing HTTP, so there is
   nothing for `_select_backend()` to intercept.

Both switches follow the identical OFF → ON → reversible → negative-check
discipline documented above: baseline with the flag off, cut over, flip back
to prove reversibility, then kill the payment service and confirm the
affected path fails loudly (a real `502` from this proxy for REST reads; the
monolith-side equivalent for async capture) rather than silently degrading.
The two dimensions are verified independently — flipping
`STRANGLER_PAYMENT_ENABLED` has no effect on `PAYMENT_MODE` or vice versa —
for the same reason as Inventory: a design that requires flipping both in
lockstep to stay correct is not actually two independent seams, it is one
seam with an extra step.

## Shipping seam (r06) — two cutover dimensions

Like Inventory and Payment, Shipping is a seam with **two independent
cutover switches**, because it has two distinct call paths into the
monolith:

1. **REST reads** (`GET /api/shipments*`, browsing/display traffic — e.g.
   shipment status/tracking lookups) — go through *this* proxy, gated by
   `STRANGLER_SHIPPING_ENABLED` exactly like the other four flags gate their
   seams: `app/config.py` reads the flag and base URL, `_select_backend()`
   in `app/main.py` matches the full path against `/api/shipments` and
   routes to the shipping-service once cut over.
2. **Shipment orchestration** (the write path that actually creates and
   advances a shipment during order fulfillment) — driven internally by the
   monolith and gated by the monolith's own `SHIPPING_MODE` setting. This
   path never goes through the strangler proxy at all — it is internal
   monolith-side processing, not browser/client-facing HTTP, so there is
   nothing for `_select_backend()` to intercept.

Both switches follow the identical OFF → ON → reversible → negative-check
discipline documented above: baseline with the flag off, cut over, flip back
to prove reversibility, then kill the shipping service and confirm the
affected path fails loudly (a real `502` from this proxy for REST reads; the
monolith-side equivalent for orchestration) rather than silently degrading.
The two dimensions are verified independently — flipping
`STRANGLER_SHIPPING_ENABLED` has no effect on `SHIPPING_MODE` or vice versa —
for the same reason as Inventory and Payment: a design that requires
flipping both in lockstep to stay correct is not actually two independent
seams, it is one seam with an extra step.

## Order seam (r07) — the LAST reversible flag, then the irreversible cut

Order was the final seam, and the only one proven reversible with the
**write path itself** cut over through this proxy — `POST /api/orders`
(checkout) routed to `examples/07-order-service` exactly like every `GET`
under the same prefix, not split into a separate internal dimension the way
Inventory/Payment/Shipping's write paths were. `STRANGLER_ORDER_ENABLED`
gated `/api/orders*` to order-service the same way the five prior flags
gated their own seams.

### Reversibility proof (recorded before the irreversible step)

Full topology live for both runs: Postgres 18.6-alpine, Kafka (KRaft,
single-node), review-/notification-/inventory-/payment-/shipping-/
order-service, through the proxy on `:8888`
(`tooling/newman/proxy.postman_environment.json`). `examples/06-shipping-service`
was already re-pointed (`ORDER_BASE_URL=http://localhost:8088`) — its saga's
`enrich` step reads `shippingAddress` from order-service's `order_view`, not
the monolith.

**Run 1 — `STRANGLER_ORDER_ENABLED=true` (+ review/notification/inventory/
payment/shipping flags all `true`), order served by order-service:**

```
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var reviewContractEnabled=true --env-var inventoryContractEnabled=true \
    --env-var paymentContractEnabled=true --env-var shippingContractEnabled=true \
    --env-var orderContractEnabled=true
```

**44 requests / 88 test-scripts / 117 assertions, 0 failed, exit code 0.**
O1's checkout returned `202 Accepted` (order-service's always-choreographed
path); N1b's bounded-wait poll independently confirmed a real order reaching
terminal `CONFIRMED` via the full Kafka saga (payment.captured →
AWAITING_SHIPMENT → shipment.dispatched → CONFIRMED) on attempt 4/20 — proof
the lifted reactions (`07-order-service/app/service.py`) drive the lifecycle
correctly standing alone, with no monolith process running at all.

**Run 2 — flag OFF (no `STRANGLER_*` flags at all), order-service and every
other extracted service stopped, only the bare monolith running
(`PAYMENT_MODE`/`SHIPPING_MODE`/`INVENTORY_MODE` all left at their
synchronous/in-process/local defaults):**

```
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/proxy.postman_environment.json \
    --env-var reviewContractEnabled=true --env-var inventoryContractEnabled=true \
    --env-var paymentContractEnabled=true --env-var shippingContractEnabled=true \
    --env-var orderContractEnabled=true
```

**33 requests / 66 test-scripts / 105 assertions, 0 failed, exit code 0.**
O1's checkout returned a plain `201 Created` (the monolith's synchronous
path) — the same collection, the same environment file, only the proxy's
own configuration and the live backend changed. **This is the last reversible
proof in this project's strangler-fig history**: right up to this point,
turning `STRANGLER_ORDER_ENABLED` off was a config change plus a restart,
and the monolith still answered `/api/orders*` correctly.

### The irreversible step

Immediately after the proof above, `STRANGLER_ORDER_ENABLED` (and every
other `*_ENABLED` flag, and `STRANGLER_MONOLITH_BASE_URL`) were removed from
`app/config.py` entirely — see the README's "The flagless edge router (r07)"
section. `_select_backend()` is now an unconditional six-way lookup with a
real `404` for anything else. The monolith is removed from the running
topology (`compose.yaml`/`scripts/`/`demos/`) but kept, frozen, in-repo —
see `examples/00-monolith/README.md`. There is no flag left to flip back.
