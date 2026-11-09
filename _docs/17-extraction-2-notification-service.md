---
title: "Extraction 2: Notification Service (Going Event-Driven)"
order: 17
part: "The Strangler Fig in Practice"
description: "The transactional outbox cures the dual-write hazard, an idempotent aiokafka consumer and an owned schema make notification the first event-driven extraction, and a bounded-wait poll proves the cutover against a real Kafka broker."
duration: 50 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why a synchronous, in-transaction notification call couples checkout's latency and failure domain to the notification path, and why curing it changes when the work happens, not just where it runs.
- Write an `OutboxEvent` row inside the same `@transaction.atomic()` as `place_order()`'s other writes, and say where that atomicity stops: the at-least-once hop from table to Kafka.
- Build an `aiokafka` consumer with two layers of idempotency: a check-then-insert and a partial unique index as the backstop for a race.
- Justify an owned schema with no foreign keys into the monolith's tables, and contrast it with review-service's shared-table reads.
- Write a bounded-wait poll for an eventually consistent read that passes unchanged whichever backend answers, and fails loudly when the backend is down.

## Why this matters

Review moved a process. Notification moves a consistency model. Before this extraction, `order/services.py::place_order()` called notification code synchronously, in-process, inside the same transaction as the rest of checkout. A committed checkout was guaranteed to have attempted a send, at the cost recorded in `examples/00-monolith/SMELLS.md` as smells #5 and #6:

> **Synchronous in-process notification send inside the checkout transaction**: checkout latency was coupled to however long "sending" a notification took, and a failure there would have rolled back the whole order.

> **Dual-write hazard**: the `Notification` DB row (atomic with checkout) and the call to `_dispatch_via_external_provider()` were two independent writes to two independent systems with no shared transaction. A crash between the DB commit and the provider call would have lost the notification silently; a naive retry could have duplicated it.

Moving that code to a new service unchanged would turn an in-process dual write into a network dual write, which is worse. The outbox has to exist before the extraction is safe, and it lives in the monolith.

The code is in `examples/03-notification-service/` (the FastAPI service) and `examples/00-monolith/` (the outbox model, the relay and the monolith's own `order.placed` consumer). The service's `README.md` and `MIGRATION.md` cover how to drive it and the measured numbers cited below.

{% include excalidraw.html file="outbox-write-in-transaction" alt="Before and after inside place_order()'s single transaction: the before panel ends with a synchronous out-of-process notification send, the dual-write hazard; the after panel ends with one ordinary OutboxEvent row, atomic with everything else" caption="Figure 17.1: The outbox cure changes the last write inside checkout's transaction, not the transaction itself" %}

## Pattern: Transactional Outbox

The cure for a dual write is to stop writing twice. `common/models.py::OutboxEvent` is an ordinary Django model, and that is its value: it is subject to the transaction checkout already runs in.

```python
class OutboxEvent(models.Model):
    """The transactional outbox (the cure for SMELL #5/#6, see SMELLS.md):
    the ONLY notification-related side effect written inside
    `order.services.place_order()`'s `@transaction.atomic()`. A separate
    process (`common.management.commands.outbox_relay`) polls the
    unpublished rows oldest-first and publishes them to Kafka
    at-least-once, stamping `published_at` on success -- decoupling both
    checkout latency and failure domain from the notification path, and
    curing the dual-write hazard by making this row the only thing inside
    the local transaction."""

    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "outbox"
        indexes = [
            models.Index(
                fields=["created_at"],
                name="idx_outbox_unpublished",
                condition=Q(published_at__isnull=True),
            ),
        ]
```

`aggregate_type` and `aggregate_id` identify what the event is about without a foreign key into every context that might publish through the table, so payment's or shipping's events can use it later. `event_type` (`"order.placed"`) becomes the topic name. `payload` is a `JSONField` because the outbox carries an already-serialized event; its shape belongs to whoever writes the row. `published_at` is the whole state machine: null means waiting, set means done. There is no `PUBLISHING`, `FAILED` or retry-count column, because the relay treats "still null" as the entire signal to try again.

The partial index tracks only unpublished rows, a tiny sliver of a table that otherwise grows forever. The relay's "oldest unpublished first" query stays cheap at the hundredth row and at the ten-millionth.

On the checkout side the change is a replacement. The old synchronous call is gone:

```python
confirmation_message = f"Order #{order.id} confirmed, total ${order.total_cents / 100:.2f}"
OutboxEvent.objects.create(
    aggregate_type="order",
    aggregate_id=str(order.id),
    event_type="order.placed",
    payload={
        "orderId": order.id,
        "customerId": customer.id,
        "customerEmail": customer.email,
        "totalCents": order.total_cents,
        "confirmationMessage": confirmation_message,
        "placedAt": datetime.now(tz=UTC).isoformat(),
    },
)

return order
```

This is the last write in the same `@transaction.atomic()` that reserves inventory, creates the order and charges payment. A `DECLINE` payment method or a `SHIP-FAIL` address still rolls the row back with everything else. What changed is that the last write is now an `INSERT` into the same database instead of a call that leaves the process. Checkout's HTTP contract is unchanged: `POST /api/orders` still returns a synchronous `201 CONFIRMED`, not a `202 Accepted`.

Something still has to get the row to Kafka. `common/management/commands/outbox_relay.py` is a plain polling loop:

```python
async def _publish_one(producer: AIOKafkaProducer, topic: str, event: OutboxEvent) -> None:
    key = str(event.aggregate_id).encode("utf-8")
    value = json.dumps(event.payload).encode("utf-8")
    await producer.send_and_wait(topic, key=key, value=value)
    # A crash here -- after the publish, before the stamp -- re-sends this
    # row on the relay's next poll. That's the documented at-least-once
    # tradeoff; see the module docstring and SMELLS.md.
    await _mark_published(event.id)
```

Three decisions matter:

- **The message key is `aggregate_id`**, the order id as a string. Every event about one order lands on the same partition in publish order, which matters once a second event type exists for the same aggregate.
- **Publish, confirm, then mark.** A crash between the last two lines republishes an already-sent event, because the row still shows `published_at IS NULL`. That is at-least-once. Marking first would be at-most-once: a crash would lose the only record that the event still needs sending. At-least-once with a cheap consumer-side dedupe is the right trade, and silent loss never is.
- **A polling relay, not Debezium.** A one-second poll against a condition-indexed table is adequate here. Tailing Postgres's write-ahead log (CDC) pays for itself when polling latency or the database load from polling becomes the bottleneck, which it is not at this traffic.

## The idempotent consumer

{% include excalidraw.html file="event-driven-notification-topology" alt="End-to-end pipeline: checkout writes an outbox row, the relay publishes it to Kafka at-least-once, and two independent consumer groups (monolith-notification and notification-service) each consume the same topic into their own read model, with the strangler proxy flag choosing which one answers GET /api/notifications" caption="Figure 17.2: One outbox row, two independent consumer groups, one flag choosing who answers the read" %}

At-least-once is a promise about the producer. What a consumer does with a duplicate is its own obligation, met in `examples/03-notification-service/app/consumer.py::OrderPlacedConsumer`:

```python
async def start(self) -> None:
    self._consumer = AIOKafkaConsumer(
        self._settings.order_placed_topic,
        bootstrap_servers=self._settings.kafka_bootstrap_servers,
        group_id=self._settings.consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    await self._consumer.start()
    self._task = asyncio.create_task(self._consume_loop(), name="order-placed-consumer")
```

| Setting | Effect | Cost |
| --- | --- | --- |
| `group_id="notification-service"` | Within a group, one member reads each partition, so replicas divide the topic instead of duplicating it | None |
| `auto_offset_reset="earliest"` | A new deployment with no committed offset starts at the beginning of the topic and misses nothing | Reprocesses history on a true cold start, which idempotency makes safe |
| `enable_auto_commit=True` | Offsets commit in the background | A crash before the next commit redelivers a record, the at-least-once case the idempotency layer absorbs |
| `asyncio.create_task` | The consumer runs in the background, decoupled from the read routes in `app/routes.py` | One side can be slow or briefly down without the other noticing |

One bad record is logged, not fatal:

```python
async def _consume_loop(self) -> None:
    assert self._consumer is not None
    async for record in self._consumer:
        try:
            event = OrderPlacedEvent.model_validate(record.value)
            await service.record_order_placed(self._session_factory, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "failed to process order.placed record at offset %s", record.offset
            )
```

A malformed payload raises a `ValidationError` at the ACL, gets logged with its offset, and the loop moves on instead of halting delivery for every later order. `asyncio.CancelledError` is re-raised because it means the service is shutting down, and swallowing it would turn a clean shutdown into a hang.

Idempotency lives in `app/service.py::record_order_placed`:

```python
async def record_order_placed(
    session_factory: async_sessionmaker[AsyncSession], event: OrderPlacedEvent
) -> None:
    async with session_factory() as session:
        existing = await repository.get_by_order_id(session, event.order_id)
        if existing is not None:
            logger.info(
                "order.placed for order %s already recorded, skipping (idempotent no-op)",
                event.order_id,
            )
            return

        message = event.confirmation_message
        try:
            await repository.create(
                session,
                customer_id=event.customer_id,
                order_id=event.order_id,
                channel="EMAIL",
                message=message,
                sent_at=datetime.now(UTC),
            )
        except IntegrityError:
            await session.rollback()
            logger.info(
                "order.placed for order %s raced a concurrent insert, discarding duplicate",
                event.order_id,
            )
```

{% include excalidraw.html file="idempotent-consumer-dedupe" alt="What happens on a redelivered order.placed event: application-level check-then-insert handles the common case, and a database-level partial unique index on order_id backstops the narrow window where two redeliveries race the check itself, so exactly one Notification row survives either way" caption="Figure 17.3: At-least-once delivery, exactly-once effect" %}

Two layers, because each alone leaves a gap:

- **Check-then-insert** handles the common case: a republished event finds its row and returns without another write.
- **The partial unique index** closes the race. Two deliveries processed concurrently (a second replica, say) can both pass the check and both insert. The index `uq_notifications_order_id` (`UNIQUE (order_id) WHERE order_id IS NOT NULL`, in `migrations/versions/0001_create_notification_schema.py`) rejects the second insert, and the `IntegrityError` handler rolls back and discards the duplicate. By then a notification for that order already exists, so it isn't an error.

A database constraint alone would send every redelivery to the database as a doomed `INSERT`. Together the common case is cheap and the rare race is still correct. The monolith's `notification/services.py::record_order_placed` has the same structure.

## Own the schema

`examples/02-review-service` reads and writes the monolith's shared tables. `examples/03-notification-service` touches none of them, and `app/models.py` states why:

> `customer_id` / `order_id` are plain `BIGINT` columns, NOT foreign keys into the monolith's `customers`/`orders` tables: this service's schema must not reach across into tables it does not own.

Review stays synchronously consistent by construction: every request is a live round trip against the same tables. Notification is asynchronous, and a second writer to the monolith's `notifications` table racing the monolith's own writer, with no shared transaction, is a split-brain. Owning the table with exactly one writer removes the reconciliation problem.

The schema is set at two levels:

```python
def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        resolve_database_url(database_url),
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "notification,public"}},
    )
```

```python
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_customer_id", "customer_id"),
        Index(
            "uq_notifications_order_id", "order_id", unique=True,
            postgresql_where=text("order_id IS NOT NULL"),
        ),
        {"schema": "notification"},
    )
```

`search_path=notification,public` is a convenience for ad hoc `psql` sessions. The correctness guarantee is `{"schema": "notification"}`: every query SQLAlchemy generates is schema-qualified, so a misconfigured search path can't redirect writes into `public.notifications`, the monolith's table in the same Postgres instance.

Creating the schema is this project's first Alembic migration. Review has none because it never changes the schema it reads.

```python
def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notification")
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        schema="notification",
    )
    op.create_index("idx_notifications_customer_id", "notifications", ["customer_id"], schema="notification")
    op.create_index(
        "uq_notifications_order_id", "notifications", ["order_id"],
        unique=True, schema="notification",
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
```

`order_id` stays nullable to match the monolith's `Notification.order` (`null=True`), so a future non-order notification needs no migration.

## The relay and the consumer, side by side

{% include codetabs.html langs="Monolith: Django outbox_relay (producer)|notification-service: aiokafka consumer" %}

```python
# common/management/commands/outbox_relay.py -- the monolith's producer side
async def _publish_one(producer: AIOKafkaProducer, topic: str, event: OutboxEvent) -> None:
    key = str(event.aggregate_id).encode("utf-8")
    value = json.dumps(event.payload).encode("utf-8")
    await producer.send_and_wait(topic, key=key, value=value)
    await _mark_published(event.id)   # after publish -- at-least-once


async def _run() -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()
    while not stop_event.is_set():
        batch = await _fetch_unpublished_batch()
        for event in batch:
            await _publish_one(producer, topic, event)
        if not batch:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_ms / 1000)
```

```python
# app/consumer.py -- notification-service's consumer side
class OrderPlacedConsumer:
    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._settings.order_placed_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.consumer_group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop())

    async def _consume_loop(self) -> None:
        async for record in self._consumer:
            event = OrderPlacedEvent.model_validate(record.value)
            await service.record_order_placed(self._session_factory, event)
```

Both sides use `aiokafka`, so the Django and FastAPI split is only about which framework answers HTTP. The relay polls a table and pushes to Kafka; the consumer subscribes to Kafka and pushes to a table. They are mirror images of one at-least-once contract. The monolith's self-consumer (`notification/management/commands/order_placed_consumer.py`, group `monolith-notification`) is a third party to the same topic, writing the same kind of idempotent row into the monolith's shared schema.

## The measured cost of Phase B

The same two-phase discipline applies as for Review: document Phase A, ship only Phase B. `examples/03-notification-service/MIGRATION.md` measures what a Django-ORM-lifted Phase A would have cost. No Phase A server was built, so its numbers are a proxy: `django.setup()` against the monolith's real settings plus `import fastapi, uvicorn`. Notification adds a problem Review didn't have. Review's Phase A had a monolith REST view to lift; notification's write path has no monolith original, because the monolith never consumed its own `order.placed` event. A faithful Phase A can only cover the read surface, and the consumer is net-new in either phase.

| Metric | Phase A (proxy measurement) | Phase B (shipped) |
|---|---|---|
| Cold interpreter floor | 0.02 s | 0.02 s |
| Import/startup time (3-run avg) | 0.36 s | 0.39 s |
| Import-only RSS | ~74.5 MB | ~77.3 MB |
| Running server RSS (after 20 requests) | not measured (no server built) | ~90.0 MB |

Import time and import RSS are close, as they were for Review: the FastAPI and Pydantic import graph dominates both, and `aiokafka` adds about 3 MB and 0.03 s in Phase B. The running-RSS row is the real difference, and Phase A's proxy can't capture it. About 90 MB reflects a live consumer holding a broker connection, group membership and buffers. That is the price of a subscriber that is actually subscribed, not a regression.

## The cutover: one flag

Two independent switches are involved, and only one is an operator's decision. The outbox path (`OutboxEvent`, `outbox_relay`, the monolith's `order_placed_consumer`) has no feature flag. Once shipped, checkout always writes the row and the relay always publishes it.

The proxy flag `STRANGLER_NOTIFICATION_ENABLED` decides whether `GET /api/notifications*` is answered by the monolith's consumer or by notification-service. Both consumer groups (`monolith-notification` and `notification-service`) run for the whole strangle window, so flipping the flag back and forth costs a proxy restart. It is reversible because the monolith's read model keeps getting fed whether or not the flag points at it.

## The false-equivalence trap

Every earlier equivalence check could assert immediately after the triggering request, because every path was synchronously consistent. Notification breaks that. `POST /api/orders` returns `201 CONFIRMED` at once, but the notification reaches `GET /api/notifications` only after the outbox, relay, Kafka and consumer have all run, an unbounded amount of wall-clock time later. An immediate check would fail a correct system for running too early, with output indistinguishable from a broken one.

`tooling/newman/mea.postman_collection.json` solves this with a bounded-wait poll, not a fixed sleep. After a plain synchronous checkout it polls `GET /api/notifications?customerId=` for a notification whose `orderId` matches, on a budget of 20 attempts at 750 ms (about 15 seconds). It delays only on a retry, so the first attempt is immediate. The helper resolves quickly when the system is healthy and fails promptly when it isn't. It does not hang, and it does not treat an empty result as "keep waiting" forever.

The collection, run against the real stack in both flag states:

| Run | Flag | Served by | Result |
|---|---|---|---|
| A | `false` | monolith's own consumer | 66/66 assertions green |
| B | `true` | notification-service | 66/66 assertions green, same shape as A |

Both resolved on attempt 2 of 20 (about 750 ms) with essentially the same latency, whichever backend served the read. The unedited collection can't tell the two apart.

The negative run kills `examples/03-notification-service` with the flag at `true`:

```
21. AssertionError  Order-confirmation notification for orderId=19 is observable
                    within the bounded-wait budget (20 x 750ms, attempt 20/20)
                    no notification with orderId=19 found after 20 attempt(s):
                    expected undefined not to be undefined
```

21 of 23 assertions failed and newman exited 1. The poll used its full 20 attempts (about 14.7 seconds observed against the 15 second design figure), every attempt got the proxy's real `502`, and the final assertion failed on its own terms. After restarting the service, the same folder went back to 9/9 green, resolving on attempt 3 because the restarted consumer needed a moment to rejoin its group and rebalance. A check that can't go red when the target is broken proves nothing, so this run is what makes the green ones trustworthy.

At-least-once delivery and the decorating collaborator fit together here. At-least-once is the relay's named guarantee, made safe by idempotent consumers on both ends, each backstopped by a unique constraint. Two consumer groups on one topic is the permanent shape of this seam for the whole strangle window, until the monolith's notification module is decommissioned.

> **Decision**
>
> When a seam is asynchronous, write one outbox row inside the local transaction and publish it from a separate relay at-least-once. Make every consumer idempotent with a check plus a unique constraint, give the new service its own schema, and prove the cutover with a bounded-wait poll that can go red.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith`, add an `order.shipped` outbox event written in the same transaction as the shipment, and extend `examples/03-notification-service` with an idempotent consumer for it: a check-then-insert plus a partial unique index in a new Alembic migration."
>
> Check: redeliver the same event twice and run `cd examples/03-notification-service && uv run pytest -m "not integration"` and `uv run ruff check .`; exactly one row should exist for that order.

## Build, run, observe

```bash
# Postgres + Kafka (see tooling/newman/README.md for exact container
# commands, or scripts/stack-up.sh).

cd examples/00-monolith
uv run python manage.py migrate && uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &
uv run python manage.py outbox_relay &
uv run python manage.py order_placed_consumer &

cd ../03-notification-service
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002 &
```

```bash
curl "http://localhost:8002/health"
curl "http://localhost:8002/api/notifications?customerId=777456"
curl -i "http://localhost:8002/api/notifications"   # 400, missing customerId
```

Place an order with `POST /api/orders` against the monolith. The notification appears on both read models independently: the monolith's `GET /api/notifications` through its own consumer, and the service's on `:8002`.

```bash
cd examples/03-notification-service
uv run pytest -m "not integration"   # REST contract + idempotency, no Kafka
uv run pytest -m integration          # Testcontainers: real Kafka, redelivery proof
uv run ruff check .
```

The integration run uses a Testcontainers-managed Kafka broker and the real `OrderPlacedConsumer`: the same `order.placed` payload published twice leaves exactly one `Notification` row.

- Stop `examples/03-notification-service` with the proxy flag at `true`: the poll uses all 20 attempts and fails, and `/api/notifications*` returns the proxy's `502`.
- Stop the relay: `POST /api/orders` still returns `201 CONFIRMED`, and the outbox row stays unpublished until the relay returns.
