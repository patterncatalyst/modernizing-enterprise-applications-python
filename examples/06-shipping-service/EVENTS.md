# shipping-service -- Event Contracts

This service is on BOTH sides of Kafka: it **consumes** `payment.captured`
(the saga's trigger) and **produces** `shipment.dispatched` /
`shipment.failed` (the saga's terminal outcome). All three are plain JSON,
camelCase, with no shared schema module between this service and
payment-service/the monolith (or any future consumer) -- each side
hand-authors a structurally identical copy. There is no schema registry
until ch.28/Apicurio.

## Consumes: `payment.captured`

Topic `payment.captured`, key = `orderId` (string). Published by
`05-payment-service`'s own transactional outbox + relay (see
`../05-payment-service/EVENTS.md`). `app/schemas.py::PaymentCapturedEvent` is
this service's own copy of the shape.

```json
{
  "orderId": 555123,
  "paymentId": 42,
  "amountCents": 4999,
  "method": "VISA-1234",
  "status": "CAPTURED",
  "occurredAt": "2026-10-16T05:26:45.400000+00:00"
}
```

Receiving this event starts (or, on redelivery, idempotently no-ops for) a
saga -- see `app/service.py::handle_payment_captured`. This event carries no
shipping address; the saga's `enrich` step fetches that separately.

## Enrichment: `GET {MONOLITH_BASE_URL}/api/orders/{orderId}`

Not a Kafka contract, but equally frozen for this saga: the saga's `enrich`
step (`app/steps.py::enrich` via `app/enrich_client.py`) calls the
monolith's `GET /api/orders/{id}` and reads `shippingAddress` off the
response -- an ADDITIVE field a sibling lane added to
`00-monolith/order/serializers.py::OrderSerializer` specifically so this
saga can enrich itself without reaching into the monolith's database
directly.

```json
{
  "id": 555123,
  "customerId": 777456,
  "status": "AWAITING_SHIPMENT",
  "totalCents": 4999,
  "createdAt": "2026-10-16T05:26:40.000000+00:00",
  "shippingAddress": "42 Wallaby Way, Sydney",
  "items": [ ... ]
}
```

**The SHIP-FAIL sentinel lives in the address, not a separate flag:** if
`shippingAddress` contains the literal substring `SHIP-FAIL`
(case-insensitive), the saga's `book_carrier` step (step 3, AFTER `dispatch`
has already persisted a `Shipment` row) raises -- deterministic failure
injection, lifted byte-for-byte from the monolith's original
`shipping.services.dispatch`'s `SHIP_FAIL_SENTINEL` rule (now moot in the
monolith once `SHIPPING_MODE=orchestrated`, since this saga does the
dispatching instead).

## Produces: `shipment.dispatched`

Topic `shipment.dispatched`, key = `orderId` (string). Written atomically
with the `Shipment` row's transition to `DISPATCHED` AND the saga's own
`COMPLETED` status update (`app/steps.py::emit` +
`app/orchestrator.py::_advance_one_step`'s terminal-transition fold) via
this service's own transactional outbox (`app/models.py::OutboxEvent`), then
published by `app/relay.py`.

```json
{
  "orderId": 555123,
  "shipmentId": 7,
  "address": "42 Wallaby Way, Sydney",
  "status": "DISPATCHED",
  "occurredAt": "2026-10-16T05:26:45.900000+00:00"
}
```

## Produces: `shipment.failed`

Topic `shipment.failed`, key = `orderId` (string). Written atomically with
the saga's own `COMPENSATED` status update
(`app/orchestrator.py::compensate`) -- whether or not a `Shipment` row ever
existed for this order (see the field notes below).

```json
{
  "orderId": 555124,
  "shipmentId": 8,
  "address": "1 SHIP-FAIL Lane",
  "status": "FAILED",
  "reason": "carrier booking failed for order 555124: SHIP-FAIL sentinel detected",
  "occurredAt": "2026-10-16T05:27:10.100000+00:00"
}
```

- `shipmentId`/`address` are present (and the `Shipment` row itself is
  `CANCELLED`, never deleted) when `dispatch` (step 2) ran before the saga
  aborted -- the common case, since the only forward-progress failure point
  (`book_carrier`) runs AFTER `dispatch`.
- `shipmentId`/`address` are `null` if the saga aborted before `dispatch`
  ever ran (e.g. a hypothetical future `enrich` failure mode) -- there is
  nothing to compensate, but the terminal event is still emitted rather than
  silently dropped.
- `status` is always the literal `"FAILED"` on the wire, even though the
  `Shipment` row itself (when one exists) is marked `CANCELLED` -- the event
  describes the SAGA's outcome, the row's `status` column describes the
  AGGREGATE's own state. Same split the Java sibling's `ShipmentFailed`/
  `ShipmentStatus` pair documents.
- `reason` distinguishes the deterministic `SHIP-FAIL` sentinel from any
  other abort (`app/orchestrator.py::_emit_shipment_failed`).

## Delivery guarantees

Both directions are **at-least-once**, never exactly-once:

- `app/consumer.py::PaymentCapturedConsumer` is idempotent by `order_id`
  (check-then-insert + a database-level unique index backstop,
  `uq_sagas_order_id`) -- a redelivered `payment.captured` event starts at
  most one saga per order (`app/service.py::handle_payment_captured`).
- `app/relay.py::OutboxRelay` publishes, then stamps `published_at` -- a
  crash between those two steps republishes the identical outbox row on the
  next poll. Any consumer of `shipment.dispatched`/`shipment.failed` must be
  idempotent by `orderId`, the same discipline this service's own consumer
  follows.
- Independently, the SAGA ITSELF survives a process crash mid-flow: every
  step commits its own transaction, and `app/orchestrator.py::resume_running_sagas`
  re-drives any `RUNNING`/`COMPENSATING` saga on startup from its persisted
  `step_index`/`context` -- see `MIGRATION.md` for why this is a durability
  upgrade over the Java sibling's in-memory saga coordinator.
