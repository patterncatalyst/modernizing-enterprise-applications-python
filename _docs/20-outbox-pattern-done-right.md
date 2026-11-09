---
title: "The Outbox Pattern, Done Right"
order: 20
part: "Data Across the Seam"
description: "The transactional outbox against the dual write, idempotent consumers as its required counterpart, ordering and redelivery, and the first two outboxes chained across services."
duration: 40 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain the dual-write problem as two writes to two systems with no sequencing that closes the gap, and why "exactly once" means at-least-once delivery plus an idempotent consumer.
- Trace the four pieces of an outbox pipeline: the `OutboxEvent` row, the transactional write, the polling relay and the idempotent consumer, and say why `published_at` is stamped only after `send_and_wait()` succeeds.
- Build a service that both consumes and produces events (`create_payment_with_outbox_event` plus `app/relay.py`) and choose among three idempotency idioms by the kind of write.
- Key every event by `aggregate_id` for in-order delivery within one order while Kafka still parallelizes across partitions.
- Tune the relay's poll interval (`DEFAULT_POLL_MS`) as a latency-versus-read-load trade-off, and name the gaps left open: no dead-letter topic, no retry ceiling, no cleanup job.
- Choose between a polling relay and Debezium-style log-based CDC from a named latency or read-load requirement.

## Why this matters

The Notification extraction needed the outbox the moment the monolith had to stop running an out-of-process side effect inside checkout's own `transaction.atomic()`. That was one outbox, one relay and one consumer. Trusting the pattern in production means asking what its failure windows are, which half protects against which, and what changes when a second service starts writing an outbox of its own.

The code is in `examples/00-monolith/` (the original outbox and relay) and `examples/05-payment-service/` (the second, independent instance, and the first service that both consumes and produces events). The existing run scripts and each directory's `README.md` cover how to drive them.

## Pattern: Transactional Outbox

### The dual write

This version of "save to the database, then publish to Kafka" looks correct and isn't:

```python
# The dual write: not what checkout does
order = Order.objects.create(...)               # write 1: Postgres
kafka_producer.send("order.placed", event)       # write 2: Kafka, a DIFFERENT system
```

Two writes to two systems with no transaction spanning both. Four failure windows exist:

- The process crashes after the Postgres commit and before the Kafka send. The order exists and nobody downstream hears about it.
- The send times out or the broker is unreachable. Same gap, one step earlier.
- The Postgres commit fails after a naive implementation already sent the message. A notification goes out for an order that was never placed.
- A retry around the two-step sequence re-runs the Postgres write because the caller can't tell which half failed.

None of these need unusual bad luck. They are what "two systems, no shared transaction" means.

### The outbox row

The fix is to never make the second write cross a process boundary. `order.services._write_order_placed_outbox_event` writes one more row to `common.OutboxEvent` in the same Postgres transaction as everything else checkout does:

```python
# order/services.py -- the write that replaced the dual-write
OutboxEvent.objects.create(
    aggregate_type="order",
    aggregate_id=str(order.id),
    event_type="order.placed",
    payload=payload,
)
```

The `.create()` call needs no transaction handling of its own, because it runs inside the `transaction.atomic()` block already open for the order row, the line items and the charge. Either every row commits, outbox row included, or none does. "Publish an event" has become "write a row," which Postgres already makes atomic.

Delivery stays asynchronous, and Kafka isn't part of the transaction: there is no two-phase commit between Postgres and a broker here. What the outbox buys is narrower: the decision to emit the event is as durable as the order. If the order exists, the row recording it exists.

### The relay and the order of publish and stamp

`common.management.commands.outbox_relay` is a separate process that moves rows from Postgres to Kafka, decoupled from the request that wrote them:

```python
# common/management/commands/outbox_relay.py
async def _publish_one(producer, topic, event):
    key = str(event.aggregate_id).encode("utf-8")
    value = json.dumps(event.payload).encode("utf-8")
    await producer.send_and_wait(topic, key=key, value=value)
    # A crash here -- after the publish, before the stamp -- re-sends this
    # row on the relay's next poll.
    await _mark_published(event.id)
```

Publish, then stamp `published_at`. Stamp first and a crash between the steps loses the event: the row reads as done, the relay never looks again and nothing downstream hears about the order. Publish first and the same crash re-publishes the event on the next poll, because the row still reads `published_at IS NULL`. One ordering can lose a message and the other can only duplicate one. Duplication is solvable and loss isn't, so pick the ordering that duplicates. `consumer.ack(); process()` against `process(); consumer.ack()` is the same choice from the other side of a queue.

{% include excalidraw.html file="outbox-relay-at-least-once" alt="One DB transaction commits the state row and the outbox row together, a relay polls and publishes at-least-once, and an idempotent consumer in the idiom that fits the write is the required counterpart" caption="Figure 20.1: The transactional bridge, the relay, and the idempotent consumer that makes at-least-once safe." %}

The relay's loop is a plain poll:

```python
async def _run() -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()
    while not stop_event.is_set():
        batch = await _fetch_unpublished_batch()
        for event in batch:
            topic = TOPIC_FOR_EVENT_TYPE[event.event_type]
            await _publish_one(producer, topic, event)
        if not batch:
            await asyncio.sleep(DEFAULT_POLL_MS / 1000)
```

`_fetch_unpublished_batch` is an ORM query: `OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at", "id")[:BATCH_SIZE]`, the oldest hundred unpublished rows. The `id` tiebreaker makes rows written in the same millisecond sort deterministically. A partial index on `WHERE published_at IS NULL` keeps the query cheap forever: with a million published rows and ten unpublished, it scans ten. A published row leaves the index but isn't deleted.

The `if not batch: sleep` branch is the backpressure valve. Without it an empty result would spin the loop as fast as the event loop and the connection pool allow. `DEFAULT_POLL_MS = 1000` means a fresh row waits at most one second before the relay looks for it. That is the latency floor the design accepts in exchange for decoupling the write from the publish.

## Payment-service's outbox: a consumer that is also a producer

The earlier outboxes had a producer (the monolith) and consumers (Review, Notification's read model, Inventory's CDC backfill) that never published anything back. `examples/05-payment-service` produces `payment.captured` and `payment.declined`, so it needs its own outbox and its own relay. `app/service.py::process_order_placed` is the write side:

```python
# examples/05-payment-service/app/service.py
async def process_order_placed(session_factory, event: OrderPlacedEvent) -> None:
    async with session_factory() as session:
        existing = await repository.get_by_order_id(session, event.order_id)
        if existing is not None:
            return  # idempotent no-op -- see below

        status = charge(event.payment_method)
        payment = await repository.create_payment_with_outbox_event(
            session, order_id=event.order_id, amount_cents=event.total_cents,
            method=_effective_method(event.payment_method), status=status,
            created_at=now, event_type=_event_type_for(status),
            build_payload=lambda p: _build_event_payload(p, occurred_at=now),
        )
```

`create_payment_with_outbox_event` writes the `Payment` row and the `payment.outbox` row in one SQLAlchemy session commit, the same guarantee `_write_order_placed_outbox_event` gives the monolith. `app/relay.py::OutboxRelay._publish_one` copies the monolith's publish-then-stamp ordering because it solves the same problem. The framework (Django ORM or SQLAlchemy) doesn't change the pattern. It needs the write and the publish decoupled in the same way.

{% include excalidraw.html file="multi-outbox-saga-topology" alt="The monolith's order.placed outbox feeds payment-service's consumer, which writes its own outbox, which the monolith's saga listener consumes in turn: two outboxes chained end to end with no orchestrator" caption="Figure 20.2: Two outboxes chained: the first multi-service outbox choreography." %}

The monolith's checkout writes `order.placed`. Payment-service reacts and writes `payment.captured` or `payment.declined`. The monolith's `order_saga_listener` reacts to that. That is three hops with three independent at-least-once guarantees, and the monolith is both the first producer and the final consumer of a round trip that began as one HTTP request. No hop knows the whole path; each knows only the topic it reads and the topic it writes. That is choreography without a coordinator.

## Idempotent consumers

At-least-once is a promise about the pipe, not the effect. It guarantees arrival, not arrival once. The relay's crash-and-republish window, a consumer-group rebalance replaying the last uncommitted offset, or a message redelivered by hand can each deliver twice. An idempotent consumer is what turns "one or more times" into "applied once." Three idioms are in use, and the right one depends on the write:

| Idiom | Fits | Where | How it handles a duplicate |
|---|---|---|---|
| Check-then-insert plus a unique-index backstop | A write that either happened or didn't | `process_order_placed` (Payment), Notification | Looks up `order_id` first and returns if a row exists. `uq_payments_order_id` catches two concurrent deliveries as an `IntegrityError`, which is discarded as a duplicate. |
| `INSERT ... ON CONFLICT` upsert | A row update with no natural "seen before" marker | Inventory's CDC consumer | Applying the same upsert twice converges to the same state; a read-modify-write can't offer that. |
| Status-transition guard | A state machine | The monolith's `order_saga_listener` | An order already out of `PENDING` treats a redelivery of the same event, or of the other outcome event, as a no-op, with no dedupe table. |

None is more correct in the abstract. Picking the one that matches the write is the skill.

## Operating the outbox

**Ordering.** Every outbox keys its Kafka messages by `aggregate_id`: the order ID as a string for `order.placed`, `payment.captured` and `payment.declined`. Kafka orders only within a partition, and the key puts every event about one order in the same partition in publish order. No consumer here needs global ordering across orders, so none pays for it.

**Poison messages.** Neither relay bounds retries. A transient broker error is logged and retried on the next poll (`_relay_loop`'s `except Exception: logger.exception(...)`). A message that fails deterministically retries forever, and there is no dead-letter topic. Demo scale has never produced one. A production deployment should add a retry ceiling and a dead-letter topic before copying this forward.

**Retention.** Published rows are never deleted. They leave the partial index, so they cost the relay nothing, but the table grows without bound. Add a job that deletes or archives rows published more than N days ago.

**Polling versus log-based CDC.** Debezium tailing the `common_outbox` and `payment_outbox` WAL entries could replace either relay, trading the relay process and its one-second latency floor for a connector and a Kafka Connect runtime. The cost is another runtime, a replication slot to manage and a connector's operational surface. CDC earns that once polling latency, or the load polling puts on the database, becomes the bottleneck. Neither relay has reached that ceiling.

## Measured under redelivery

`tooling/newman/GOLDEN-BASELINE.md`'s cutover lane ran with the full topology (monolith, payment-service, inventory-service, the strangler proxy and a single-node Kafka broker):

- A normal checkout's `order.placed` event made the round trip through both relays and both consumers. The bounded-wait poll for the order's terminal status resolved on attempt 2 of 20.
- The `payment.declined` event payment-service had already published for one order was re-published to its topic by hand. `order_saga_listener` logged the status-guard no-op:

```
payment.declined redelivered for order_id=12 status=PAYMENT_DECLINED -- no-op (status guard)
```

Stock was 94 before the redelivery and 94 after, so the guard stopped the second delivery before it reached the compensating `Release` again.

- With payment-service killed (consumer and relay), a checkout was still accepted and persisted `PENDING`, because the outbox write doesn't need it alive. The bounded-wait poll exhausted its `20 x 750ms` budget and Newman exited 1 after 15.1 s. After a restart every order stuck during the outage drained to `CONFIRMED` within seconds, because the consumer rejoined its group and resumed from its committed offset.

> **ADLC in Action**
>
> The plan settled the multi-outbox shape before any payment-service code existed. Payment-service would own its schema and its outbox and reuse the monolith's proven relay shape, with the reason recorded as a standing decision: no shared-writer split-brain, consistent with notification-service. Execution copied the publish-then-stamp ordering from `outbox_relay.py` as it was instead of re-deriving it. Verification then ran the two-hop pipeline against a real broker, so the numbers above come from that run and not from reading the code.

> **Decision**
>
> Write the event as a row in the same transaction as the state change, publish it from a separate relay that stamps after it publishes, and make every consumer idempotent in the idiom that matches its write. Choose log-based CDC over polling only when you can name the latency or read-load requirement polling fails.

> **🤖 Explore with your agent**
>
> "Review examples/05-payment-service/app/relay.py and examples/00-monolith/common/management/commands/outbox_relay.py against this rule: publish first, stamp `published_at` after, and every consumer idempotent. Add a retry ceiling that moves an event to a dead-letter topic after N failed publishes without ever stamping before a publish succeeds."
>
> Check: the diff stamps `published_at` only after `send_and_wait()` returns, and `uv run pytest` in examples/05-payment-service still passes.

## Build, run, observe

Run the full topology and the unedited collection:

```bash
bash demos/demo-payment-cutover.sh
```

To run payment-service alone, which needs Postgres and Kafka (defaults `localhost:5432` and `localhost:9092`):

```bash
cd examples/05-payment-service
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8085
uv run pytest
```

The monolith's relay runs as a management command (`outbox_relay`) next to `order_placed_consumer` and `order_saga_listener`.

Experiments:

- Re-publish a `payment.declined` event by hand to its topic. `order_saga_listener` logs the status-guard no-op and stock doesn't change.
- Kill payment-service and place an order. The order persists `PENDING` and the poll for a terminal status exhausts its budget. Restart it and the order reaches `CONFIRMED`.

## For deeper coverage

- `examples/05-payment-service/EVENTS.md` and `CUTOVER.md`: the event contracts and the payment cutover.
- `tooling/newman/GOLDEN-BASELINE.md`: the cutover lane and negative checks.
- Chris Richardson, *Microservices Patterns*: Transactional Outbox, Polling Publisher and Transaction Log Tailing.
- Debezium documentation: the outbox event router.
