# payment-service -- Event Contracts

This service is on BOTH sides of Kafka: it **consumes** `order.placed` and
**produces** `payment.captured` / `payment.declined`. All three are plain
JSON, camelCase, with no shared schema module between this service and the
monolith (or any future consumer) -- each side hand-authors a structurally
identical copy. There is no schema registry until ch.28/Apicurio.

## Consumes: `order.placed`

Topic `order.placed`, key = `orderId` (string). `app/schemas.py::OrderPlacedEvent`
is this service's own copy of the shape.

```json
{
  "orderId": 555123,
  "customerId": 777456,
  "customerEmail": "customer@example.com",
  "totalCents": 4999,
  "confirmationMessage": "Order #555123 confirmed, total $49.99",
  "placedAt": "2026-10-16T05:26:45.253590+00:00",
  "paymentMethod": "VISA-1234"
}
```

`paymentMethod` is **optional and net-new in r05** -- the monolith's order
context does not populate it as of this extraction. An event with no
`paymentMethod` field, or an explicit `null`, is treated as a normal,
capturable method (`app/service.py::UNSPECIFIED_METHOD`, literally
`"CARD-UNSPECIFIED"`) -- never a crash, never a decline. See
`app/service.py::charge`'s docstring.

## Produces: `payment.captured`

Topic `payment.captured`, key = `orderId` (string). Written atomically with
the `CAPTURED` `Payment` row via this service's own transactional outbox
(`app/models.py::OutboxEvent`), then published by `app/relay.py`.

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

## Produces: `payment.declined`

Topic `payment.declined`, key = `orderId` (string). Written atomically with
the `DECLINED` `Payment` row via the same outbox, then published by
`app/relay.py`. Identical shape to `payment.captured` plus a `reason`.

```json
{
  "orderId": 555124,
  "paymentId": 43,
  "amountCents": 2500,
  "method": "CARD-DECLINE",
  "status": "DECLINED",
  "reason": "Payment method 'CARD-DECLINE' was declined",
  "occurredAt": "2026-10-16T05:27:10.100000+00:00"
}
```

## Decline rule (deterministic demo rule, lifted from the monolith)

Any `method` value containing `DECLINE`, case-insensitively, is declined --
`app/service.py::DECLINE_SENTINEL`, byte-for-byte the same rule as the
monolith's `payment.services.charge`'s `DECLINE_SENTINEL`. Everything else,
including a missing/`null` `paymentMethod`, captures. This is a demo rule for
driving the Newman/test scenarios deterministically, not a real payment
gateway integration.

## Delivery guarantees

Both directions are **at-least-once**, never exactly-once:

- `app/consumer.py::OrderPlacedConsumer` is idempotent by `order_id`
  (check-then-insert + a database-level unique index backstop,
  `uq_payments_order_id`) -- a redelivered `order.placed` event neither
  double-charges nor emits a second outcome event.
- `app/relay.py::OutboxRelay` publishes, then stamps `published_at` -- a
  crash between those two steps republishes the identical outbox row on the
  next poll. Any consumer of `payment.captured`/`payment.declined` must be
  idempotent by `orderId`, the same discipline this service's own consumer
  follows.
