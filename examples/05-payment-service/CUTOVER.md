# payment-service -- Cutover Notes (ch.23-25, r05)

This service has **two independent cutover dimensions**, same posture as
`../04-inventory-service/CUTOVER.md` -- don't conflate them. Flipping one
does not require flipping the other.

## Dimension 1: the read surface (strangler proxy)

`../01-strangler-proxy`'s `STRANGLER_PAYMENT_ENABLED` flag routes `GET
/api/payments*` to this service instead of the monolith's Django view. Pure
read traffic, safe to flip independently and roll back instantly (flip the
flag back). This service's read contract (`GET /api/payments?orderId=`, `GET
/api/payments/{id}`) matches the monolith's `payment/views.py` byte-for-byte
(camelCase, same uniform error body), so flipping this flag alone changes
nothing observable to a caller as long as both surfaces agree on what's been
charged -- which they do, since BOTH write paths funnel through the same
`payment` Postgres schema this service now owns.

## Dimension 2: who charges payment (`settings.PAYMENT_MODE`)

This is the REAL cutover -- a checkout-behavior change, not just a read-path
redirect, and it is NOT a strangler-proxy flag. It is a monolith-side
environment variable (`examples/00-monolith/config/settings.py`,
`PAYMENT_MODE`, default `synchronous`) that changes which of
`order.services.place_order()`'s THREE dispatch paths runs:

| `PAYMENT_MODE` | Who charges | Checkout contract | Order persisted on decline/ship-fail? |
|---|---|---|---|
| `synchronous` (default) | the monolith, in-process, inside the SAME `transaction.atomic()` as inventory/shipping/outbox | `201 Created` / `402 Payment Required` / `422 Unprocessable Content` -- terminal in one round trip | **no** -- whole transaction rolls back |
| `choreographed` | `examples/05-payment-service`, asynchronously, reacting to `order.placed` | `202 Accepted`, order `PENDING` -- terminal state arrives later via `order.services.handle_payment_captured`/`handle_payment_declined`, driven by `order.management.commands.order_saga_listener` consuming this service's own `payment.captured`/`payment.declined` outbox-published events | **yes** -- the order/items/outbox row commit BEFORE any payment decision exists; a decline/ship-fail issues a compensating gRPC `Release` instead of relying on a transaction rollback |

Flipping `PAYMENT_MODE` is **fully reversible with no data migration**:
restart the monolith with the other value. `INVENTORY_MODE` is an
ORTHOGONAL axis (r04) -- choreographed payment always reserves inventory over
gRPC (`_place_order_choreographed` uses the same `_reserve_lines_remote`/
`_release_reserved` helpers `INVENTORY_MODE=grpc` already established)
regardless of which payment mode is active, since the whole point of
choreography is that nothing downstream of the reservation runs in the
checkout request anymore.

## End-to-end proof: `tooling/newman/GOLDEN-BASELINE.md`, "r05 CUTOVER" section

The full topology (monolith + payment-service + inventory-service +
review-service + notification-service + the strangler proxy + real Kafka) was
brought up and both dimensions were exercised live:

1. **Fully-choreographed, GREEN.** Whole suite through the proxy, `0/95`
   assertions failed. Scenario 1's checkout came back `202`/`PENDING` and its
   bounded-wait poll resolved `CONFIRMED` on **attempt 2/20** -- a real
   round trip through Kafka and back, not an instant resolve. Scenario 3/4
   resolved `PAYMENT_DECLINED`/`SHIPPING_FAILED` the same way, each followed
   by an unconditional net-zero stock poll proving the compensating gRPC
   `Release` actually ran.
2. **Reversibility.** Monolith restarted with `PAYMENT_MODE=synchronous`,
   proxy restarted with `STRANGLER_PAYMENT_ENABLED` unset -- suite stayed
   GREEN (`0/89` failed), Scenario 1 back to `201`/attempt-1 (zero async
   latency). Both halves of the cutover reverse independently and together.
3. **The honesty proof: a dead payment-service shows up as RED, not a false
   green.** payment-service (consumer + relay) was killed. A checkout still
   returns `202`/`PENDING` (the reservation and order-persist steps don't
   need payment-service at all), but the bounded-wait poll for Scenario 1
   then exhausted its full `20 x 750ms` budget and newman exited `1` --
   the order was provably stuck `PENDING`, never silently reported as
   `CONFIRMED`. Restarting payment-service drained every order stuck during
   the outage to `CONFIRMED` within seconds, with zero manual intervention
   (its consumer rejoins at `auto_offset_reset=earliest`/its own committed
   offset and simply catches up).
4. **Double-delivery never over-restores stock**, proven at BOTH layers:
   - **Saga-level**: a `payment.declined` event already consumed once was
     re-published to Kafka by hand. `order.services._is_pending`'s
     status-transition guard logged it as a no-op (`redelivered ...
     status=PAYMENT_DECLINED -- no-op (status guard)`); stock stayed
     unchanged across the redelivery.
   - **Ledger-level**: inventory-service's compensating `Release` RPC was
     called TWICE, directly over gRPC, bypassing the saga guard entirely,
     using the identical stable key `order.services._release_order_lines`
     derives (`f"{order_id}:{sku}:release"`). Both calls answered
     `reservation_ok=true` (a duplicate is not an error) but `on_hand_qty`
     never moved past its pre-redelivery value -- the `inventory.compensations`
     table's unique index on `idempotency_key`
     (`INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id`,
     `04-inventory-service/app/repository.py::release`) makes the
     re-increment apply AT MOST ONCE no matter how many times either layer
     replays it.

No integration bug surfaced during this proof -- every mechanism documented
in `order/services.py`'s own docstrings (the status-transition guard, the
compensating Release, the stuck-PENDING failure mode) behaved exactly as
written.

## Known deferral carried over from `order/services.py`

A payment that captures and THEN hits `ShippingFailed` (order ends
`SHIPPING_FAILED`) is **not refunded** -- this service exposes no Refund
RPC/event yet. That's r06's orchestrated saga's job, once shipping itself is
extracted; for now a captured payment stays on the books for a
`SHIPPING_FAILED` order. Documented, not a bug.
