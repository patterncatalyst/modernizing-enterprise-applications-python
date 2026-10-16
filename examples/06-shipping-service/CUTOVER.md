# shipping-service -- Cutover Notes (ch.23-25, r06)

This service has **two independent cutover dimensions**, same posture as
`../04-inventory-service/CUTOVER.md` and `../05-payment-service/CUTOVER.md`
-- don't conflate them. Flipping one does not require flipping the other.

## Dimension 1: the read surface (strangler proxy)

`../01-strangler-proxy`'s `STRANGLER_SHIPPING_ENABLED` flag (already wired,
default base URL `http://localhost:8087` -- this service's own port) routes
`GET /api/shipments*` to this service instead of the monolith's Django view.
Pure read traffic, safe to flip independently and roll back instantly (flip
the flag back). This service's read contract (`GET /api/shipments?orderId=`,
`GET /api/shipments/{id}`) matches the monolith's `shipping/views.py`
byte-for-byte (camelCase, same uniform error body), so flipping this flag
alone changes nothing observable to a caller as long as both surfaces agree
on what's been shipped -- which they do only once `SHIPPING_MODE=orchestrated`
is also flipped (Dimension 2), since otherwise the monolith is still the one
writing `shipping.Shipment` rows in ITS OWN shared schema, not this
service's owned one.

## Dimension 2: who dispatches shipping (`settings.SHIPPING_MODE`)

This is the REAL cutover -- a checkout-behavior change, not just a read-path
redirect, and it is NOT a strangler-proxy flag. It is a monolith-side
environment variable (`examples/00-monolith/config/settings.py`,
`SHIPPING_MODE`, default `inprocess`) read only inside
`order.services.handle_payment_captured` -- the THIRD, ORTHOGONAL axis on top
of `INVENTORY_MODE` (r04) and `PAYMENT_MODE` (r05):

| `SHIPPING_MODE` | Who dispatches | Order's terminal path | Shipment persisted where? |
|---|---|---|---|
| `inprocess` (default) | the monolith, synchronously, inside `handle_payment_captured` (itself already reacting to `05-payment-service`'s `payment.captured`) | straight to `CONFIRMED`/`SHIPPING_FAILED` | the monolith's own shared schema (`shipping.Shipment`, FK into `order.Order`) |
| `orchestrated` | `examples/06-shipping-service` (this service), reacting to the SAME `payment.captured` event | stops at `AWAITING_SHIPMENT`; the monolith's `order_saga_listener` later reacts to THIS service's own `shipment.dispatched`/`shipment.failed` events (`handle_shipment_dispatched`/`handle_shipment_failed`) to reach the terminal state | this service's OWNED `shipping` Postgres schema (no FK into the monolith's `orders` table) |

Flipping `SHIPPING_MODE` is **fully reversible with no data migration**:
restart the monolith with the other value. It is ORTHOGONAL to
`PAYMENT_MODE`: both `inprocess` and `orchestrated` shipping react to the
monolith's own `handle_payment_captured`/this service's consumer
respectively off the SAME `payment.captured` event, regardless of whether
payment itself was charged synchronously or choreographed.

## The refund gap -- CLOSED (r06/DRQ-054)

Earlier drafts of this file carried over r05's documented gap verbatim ("a
captured payment stays on the books for a `SHIPPING_FAILED` order, no Refund
RPC/event anywhere in this project"). That gap is closed:
`../05-payment-service/app/refund_consumer.py`'s `ShipmentFailedConsumer`
subscribes to this service's own `shipment.failed` topic and
`app/service.py::process_shipment_failed` refunds a `CAPTURED` payment
(`CAPTURED -> REFUNDED`, a `payment.refunded` event emitted) the instant this
service's saga compensates a `SHIP-FAIL` order. See the CUTOVER lane below
for the live proof, including the redelivery/idempotency check (a redelivered
`shipment.failed` does not double-refund).

## CUTOVER lane -- the orchestrated dispatch cutover, proven live end-to-end

`tooling/newman/GOLDEN-BASELINE.md`'s "r06 CUTOVER lane" section is the full
record: the FULL topology (monolith, inventory-service, payment-service,
THIS service, the strangler proxy, real Kafka) was brought up with
`SHIPPING_MODE=orchestrated` + `PAYMENT_MODE=choreographed`, and the full
behavior-equivalence suite was run live through the proxy. In short:

- **Fully-orchestrated GREEN** (100/100 assertions, newman exit 0): a happy
  checkout genuinely goes `PENDING -> AWAITING_SHIPMENT -> CONFIRMED` (poll
  attempt 2/40, a real multi-hop Kafka round trip, not an instant resolve); a
  `SHIP-FAIL` checkout goes `PENDING -> AWAITING_SHIPMENT -> SHIPPING_FAILED`
  AND its captured payment reaches `REFUNDED` (poll attempt 1/20) -- the r06
  win. Shipping Context Contract (S1-S3) green against this service's own
  `/api/shipments` surface.
- **Reversibility GREEN**: `SHIPPING_MODE=inprocess` + `PAYMENT_MODE=synchronous`
  with the proxy's shipping/payment flags off restores the original
  synchronous contract (`201`/`402`/`422` in one round trip), no data
  migration, no restart needed on this service's own side.
- **Crash-resume proven**: a `Saga` row seeded `RUNNING` (mirroring
  `tests/integration/test_crash_resume.py`'s own technique -- simulating a
  crash right after `enrich` committed but before `dispatch` ran) survived a
  real process restart; `resume_running_sagas()` picked up at the persisted
  `step_index` without re-invoking `enrich`, and the order genuinely reached
  `CONFIRMED`.
- **Negative, honesty proof**: with this service killed, a checkout gets
  stuck at `AWAITING_SHIPMENT` forever -- Scenario 1 run alone goes RED
  (newman exit 1), not a false green -- and drains to `CONFIRMED` the instant
  this service restarts.
- **Refund idempotency proven**: a redelivered `shipment.failed` for an
  already-`REFUNDED` payment is a safe no-op (no double refund, no second
  `payment.refunded` event).

**One honest finding, not papered over**: `tooling/newman/mea.postman_collection.json`'s
bounded-wait poll scripts (`1c`/`3c`/`4c`) retry only while an order's status
is `PENDING` -- they have no knowledge of the `AWAITING_SHIPMENT`
intermediate status this service's orchestrated path introduces, so a poll
landing in that (sub-second) window can report a false RED on an otherwise
healthy saga. Reproduced once, root-caused, and left unfixed on purpose (this
lane's scope excludes editing the collection) -- see `GOLDEN-BASELINE.md` for
the full writeup and the mechanical fix a future lane should make.

## What this lane did NOT touch

Per scope: only `examples/06-shipping-service/` was built here. The
monolith-side `SHIPPING_MODE`/`AWAITING_SHIPMENT`/`handle_shipment_dispatched`/
`handle_shipment_failed`/`order/serializers.py`'s `shippingAddress` wiring
already exists (`../00-monolith`, a sibling lane) and this service's
`GET /api/orders/{id}` enrichment call and `payment.captured`/
`shipment.dispatched`/`shipment.failed` contracts were built against that
existing contract, not speculatively invented. `../01-strangler-proxy`'s
`STRANGLER_SHIPPING_ENABLED` flag was likewise already wired by a sibling
lane; this service's own port (`:8087`) matches its existing default
`STRANGLER_SHIPPING_BASE_URL`.
