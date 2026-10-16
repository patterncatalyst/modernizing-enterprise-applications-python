# order-service -- Event Contracts

This service is on BOTH sides of Kafka: it **consumes** FOUR saga-outcome
topics (the exact four `00-monolith/order/management/commands/
order_saga_listener.py` subscribes to) and **produces** ONE
(`order.placed`, via its own transactional outbox + relay). All five are
plain JSON, camelCase, with no shared schema module between this service and
payment-/shipping-service (or the monolith) -- each side hand-authors a
structurally identical copy. There is no schema registry until
ch.28/Apicurio.

## Produces: `order.placed`

Topic `order.placed`, key = `orderId` (string). Written atomically with the
aggregate's `PENDING` insert AND the `order_view` `PENDING` row
(`app/repository.py::create_order_with_outbox_and_view`) -- the FROZEN
contract every downstream consumer already reacts to
(`05-payment-service`'s own `order.placed` consumer,
`03-notification-service`'s read-model consumer).

```json
{
  "orderId": 555123,
  "customerId": 1,
  "customerEmail": "ada@example.com",
  "totalCents": 3998,
  "confirmationMessage": "Order #555123 placed, total $39.98",
  "placedAt": "2026-10-16T05:26:40.000000+00:00",
  "paymentMethod": "VISA-1234"
}
```

`confirmationMessage` always says "placed" (never "confirmed") -- this
service NEVER writes an outbox row after a `CONFIRMED` transition, unlike
the monolith's synchronous flavors that could; checkout always stops at
`PENDING`.

## Consumes: `payment.captured`

Topic `payment.captured`, key = `orderId` (string). Published by
`05-payment-service`'s own transactional outbox + relay (see
`../05-payment-service/EVENTS.md`).

```json
{
  "orderId": 555123,
  "paymentId": 42,
  "amountCents": 3998,
  "method": "VISA-1234",
  "status": "CAPTURED",
  "occurredAt": "2026-10-16T05:26:45.400000+00:00"
}
```

Reaction: `app/service.py::handle_payment_captured` transitions
`PENDING -> AWAITING_SHIPMENT`. No gRPC call -- nothing to compensate on a
captured payment. `06-shipping-service`'s own saga reacts to this SAME
event, enriching itself via `GET /api/orders/{id}` (this service's own read
surface, serving `shippingAddress` from `order_view`).

## Consumes: `payment.declined`

Topic `payment.declined`, key = `orderId` (string). Published by
`05-payment-service`'s own outbox relay.

```json
{
  "orderId": 555124,
  "paymentId": 43,
  "amountCents": 1999,
  "method": "CARD-DECLINE",
  "status": "DECLINED",
  "reason": "Payment method 'CARD-DECLINE' was declined",
  "occurredAt": "2026-10-16T05:26:50.100000+00:00"
}
```

Reaction: `app/service.py::handle_payment_declined` releases every line this
order reserved at checkout (compensating gRPC `Release`, stable key
`f"{orderId}:{sku}:release"`) and transitions `PENDING -> PAYMENT_DECLINED`.

## Consumes: `shipment.dispatched`

Topic `shipment.dispatched`, key = `orderId` (string). Published by
`06-shipping-service`'s own outbox relay (see
`../06-shipping-service/EVENTS.md`).

```json
{
  "orderId": 555123,
  "shipmentId": 7,
  "address": "1 Analytical Engine Way, London",
  "status": "DISPATCHED",
  "occurredAt": "2026-10-16T05:26:55.900000+00:00"
}
```

Reaction: `app/service.py::handle_shipment_dispatched` resolves the
`AWAITING_SHIPMENT` hand-off: `AWAITING_SHIPMENT -> CONFIRMED`. No gRPC call.

## Consumes: `shipment.failed`

Topic `shipment.failed`, key = `orderId` (string). Published by
`06-shipping-service`'s own outbox relay. `shipmentId`/`address` may be
`null` if the saga aborted before a `Shipment` row was ever created.

```json
{
  "orderId": 555125,
  "shipmentId": 8,
  "address": "1 SHIP-FAIL Lane",
  "status": "FAILED",
  "reason": "carrier booking failed for order 555125: SHIP-FAIL sentinel detected",
  "occurredAt": "2026-10-16T05:27:10.100000+00:00"
}
```

Reaction: `app/service.py::handle_shipment_failed` releases every line this
order reserved at checkout (same stable-key compensation as
`handle_payment_declined`) and transitions
`AWAITING_SHIPMENT -> SHIPPING_FAILED`.

**Refund note:** this event is ALSO consumed by `05-payment-service`'s own
`shipment.failed` consumer (r06/DRQ-054), which refunds a `CAPTURED` payment
for the same order. This service's reaction and payment-service's reaction
are independent, idempotent consumers of the SAME broadcast event -- neither
calls the other.

## Delivery guarantees

Both directions are **at-least-once**, never exactly-once:

- `app/consumer.py::OrderSagaConsumer` dispatches each of the four topics to
  an idempotent reaction -- every `handle_*` function in `app/service.py`
  guards its transition with an atomic conditional `UPDATE ... WHERE status
  = <expected>` (`app/repository.py::transition_order_status_with_view`), so
  a redelivered event for an order that already left the expected status is
  a safe no-op. The two reactions that compensate over gRPC additionally
  pass a STABLE per-(order, line) `idempotency_key`
  (`f"{orderId}:{sku}:release"`), so even a race that slips past the status
  guard cannot double-credit stock.
- `app/relay.py::OutboxRelay` publishes, then stamps `published_at` -- a
  crash between those two steps republishes the identical outbox row on the
  next poll. `05-payment-service`'s own `order.placed` consumer is
  responsible for its own idempotency on redelivery (it already is, by
  design).
