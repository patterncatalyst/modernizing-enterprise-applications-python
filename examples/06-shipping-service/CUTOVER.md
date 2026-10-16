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

## Known deferral carried over from `05-payment-service/CUTOVER.md`

A payment that captures and THEN hits a shipping failure (`SHIP-FAIL`) is
handled identically to r05's documented gap: this service emits
`shipment.failed`, but there is still no Refund RPC/event anywhere in this
project as of r06 -- a captured payment stays on the books for a
`SHIPPING_FAILED` order. Documented, not a bug; a future ch.26+ lane's job.

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
