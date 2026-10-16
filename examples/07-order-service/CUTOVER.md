# order-service -- Cutover Notes (r07, the finale)

This lane has **no reversible flag of its own**, unlike every prior lane's
`INVENTORY_MODE`/`PAYMENT_MODE`/`SHIPPING_MODE`-style axis -- it is the
TERMINUS those axes were always building toward. Flipping `order` itself
over is a one-way decommission of the monolith's `order` app, not a
runtime-togglable mode, because this service's checkout contract
(`202 PENDING`, always gRPC-reserve, always choreographed/orchestrated) is
not a superset of the monolith's synchronous flavors -- it IS the
`PAYMENT_MODE=choreographed` + `SHIPPING_MODE=orchestrated` combination,
made permanent and given its own owned schema.

## What has to be true before cutover

All three of the monolith's upstream extraction flags must ALREADY be
flipped to their extracted values, because this service's checkout path
assumes every one of them:

| Monolith flag | Required value | Why this service assumes it |
|---|---|---|
| `INVENTORY_MODE` | `grpc` (irrelevant once order-service owns checkout -- this service always reserves over gRPC, there is no in-process fallback) | `04-inventory-service` must be the thing actually holding stock |
| `PAYMENT_MODE` | `choreographed` | `05-payment-service` must be the one reacting to `order.placed` and emitting `payment.captured`/`payment.declined` |
| `SHIPPING_MODE` | `orchestrated` | `06-shipping-service` must be the one reacting to `payment.captured` and emitting `shipment.dispatched`/`shipment.failed` |

If any of those three is still at its monolith-default value when
order-service's checkout traffic is cut over, the saga stalls: e.g. with
`PAYMENT_MODE=synchronous` still set, nothing in the system ever publishes
`payment.captured`/`payment.declined` for THIS service's `order.placed`
events (the monolith's own synchronous path charges in-process and never
touches Kafka), so every order placed through order-service would sit at
`PENDING` forever.

## The read-surface flag (strangler proxy)

`../01-strangler-proxy` would gain a `STRANGLER_ORDER_ENABLED` flag (not
built in this lane -- out of scope, see "What this lane did NOT touch"
below) routing `GET /api/orders*`/`POST /api/orders` to this service instead
of the monolith's Django views. Flipping JUST the read routes is safe and
instantly reversible (the monolith's `OrderSerializer` and this service's
`OrderOut` are byte-for-byte compatible on every field this service's
contract still owns). Flipping `POST /api/orders` is NOT purely a read-path
redirect -- it changes checkout's observable contract from whatever the
monolith currently returns (`201`/`402`/`422` for the synchronous flavors,
`202` for the already-choreographed flavor) to ALWAYS `202`, so it should
only be flipped once the operator has confirmed the caller's expectations
already match the choreographed contract (true today if `PAYMENT_MODE` is
already `choreographed`, since that flavor already returns `202`).

## The real cutover: decommissioning `order` from the monolith

Once order-service's checkout and read surfaces are both live and matching
behavior, the monolith's `order` Django app (`order/models.py`,
`order/services.py`, `order/views.py`, `order/serializers.py`,
`order/inventory_client.py`, `order/management/commands/
order_saga_listener.py`) becomes dead code -- there is no "both sides stay
live, pick one at request time" flag for this lane, because `Order` is the
root aggregate every other context's FK pointed at (SMELL[ch.18]'s origin).
Decommissioning it is the terminal step of this entire series' strangler-fig
migration: once `order` is gone, the monolith has no bounded contexts left
to host, and `00-monolith` itself can be retired.

## What this lane did NOT touch

Per scope: only `examples/07-order-service/` was built here. The monolith's
`PAYMENT_MODE`/`SHIPPING_MODE`/`INVENTORY_MODE` flags, `04-inventory-service`'s
gRPC server, `05-payment-service`'s `order.placed` consumer +
`payment.captured`/`payment.declined` producer, and
`06-shipping-service`'s `payment.captured` consumer +
`shipment.dispatched`/`shipment.failed` producer all already exist (sibling
lanes) and this service's contracts were built against those EXISTING
contracts, not speculatively invented. `../01-strangler-proxy`'s
`STRANGLER_ORDER_ENABLED` flag and this service's own OpenShift/CRC appendix
are likewise out of scope for this lane.
