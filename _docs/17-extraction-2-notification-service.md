---
title: "Extraction 2 — Notification Service (Going Event-Driven)"
order: 17
part: "The Strangler Fig in Practice"
description: "The transactional outbox cures the dual-write hazard; an idempotent aiokafka consumer and an owned schema give notification its first fully event-driven extraction, proven live against a real Kafka broker in both proxy flag states."
duration: 50 minutes
---

ch.16 named two ideas — content-based routing generalized past a URL path,
and the anti-corruption layer as a contract rather than a request — without
yet building the extraction that needed both. This chapter is that
extraction: `notification` leaves the monolith, not onto another
synchronous REST leaf like ch.15's Review, but onto a service whose entire
reason to exist is consuming an event the monolith publishes. Doing that
safely requires curing a dual-write hazard this book planted as a named
smell back in ch.09, teaching a consumer to survive a delivery guarantee
weaker than "exactly once," and proving — against a real Kafka broker, no
stand-in — that an asynchronous cutover can be just as reversible and just
as provably equivalent as ch.15's synchronous one.

The code is in `examples/03-notification-service/` (the new FastAPI
service) and `examples/00-monolith/` (the outbox model, the relay, and the
monolith's own `order.placed` consumer). The run script there sets up and
runs the service; its `README.md` and `MIGRATION.md` cover what it does,
how to drive it, and the measured before/after numbers cited below.

{% include excalidraw.html file="outbox-write-in-transaction" alt="Before and after inside place_order()'s single transaction: the before panel ends with a synchronous out-of-process notification send, the dual-write hazard; the after panel ends with one ordinary OutboxEvent row, atomic with everything else automatically" caption="Figure 17.1 — The outbox cure changes the LAST write inside checkout's transaction, not the transaction itself" %}

## Why notification leaves second, and why it's harder than it looks

Extraction order in this book is a deliberate ladder, not an arbitrary
list, and `review/models.py`'s own comment named the first rung directly:
Review has no synchronous collaborator, so ch.15 could prove the extraction
*mechanism* — capture the contract, stand up the service, flip the flag —
without also solving a distributed-systems problem in the same chapter.
`notification` is the second rung, and it is harder along an axis Review
never touched: **Review's extraction moved a process; notification's
extraction moves a consistency model.**

Before this chapter, `order/services.py::place_order()` called notification
code *synchronously*, *in-process*, inside the same `@transaction.atomic()`
as everything else in checkout. That bought something real — a checkout
that commits is guaranteed to have at least attempted a notification send,
automatically, by Postgres's own rollback semantics — at a real cost documented
in `examples/00-monolith/SMELLS.md` as smells #5 and #6:

> **Synchronous in-process notification send inside the checkout
> transaction** — checkout latency was coupled to however long "sending" a
> notification took, and a failure there would have rolled back the whole
> order.

> **Dual-write hazard** — the `Notification` DB row (atomic with checkout)
> and the call to `_dispatch_via_external_provider()` were two independent
> writes to two independent systems with no shared transaction. A crash
> between the DB commit and the provider call would have lost the
> notification silently; a naive retry could have duplicated it.

Extracting `notification` onto its own service doesn't just move that
code somewhere else — if it moved unchanged, it would turn an in-process
dual write into a *network* dual write, which is strictly worse: now the
two systems that can't agree on "did this actually happen" are separated
by a network partition, not just a process boundary. That's why this
chapter leads with the outbox, not the new service: the outbox is what has
to exist *before* an extraction like this one is even safe to build, and it
lives in the monolith, not in `examples/03-notification-service` at all.

## The transactional outbox: atomicity now, delivery later

The cure for a dual-write hazard is to stop writing twice. `common/models.py::OutboxEvent`
is a Django model like any other in this schema — which is exactly the
point; the outbox's entire value comes from being an *ordinary row*,
subject to the same transaction the rest of checkout already runs inside:

```python
class OutboxEvent(models.Model):
    """The transactional outbox (ch.17 cure for SMELL #5/#6, see SMELLS.md):
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

Six columns, each earning its place. `aggregate_type`/`aggregate_id`
identify *what* this event is about (`"order"`, the order's id) without the
outbox table needing a foreign key into every context that might ever
publish through it — a generic envelope, not an order-specific one, so the
same table can later carry payment's or shipping's events too.
`event_type` (`"order.placed"`) is the topic name this row will become.
`payload` is a `JSONField`, not a structured set of columns, because the
outbox's job is to carry an already-serialized event, not to re-model it —
the shape of `payload` is owned by whoever writes the row, not by this
table. `created_at`/`published_at` are the whole state machine: a row with
`published_at IS NULL` is waiting; a row with it set is done. That two-value
state machine stays this simple by design — there's no `PUBLISHING`,
`FAILED`, or retry-count column, because the relay below treats "still
null" as the entire signal it needs to try again.

The partial index is not decoration. `idx_outbox_unpublished` only indexes
rows where `published_at IS NULL` — which, in steady state, is a tiny
sliver of a table that otherwise grows forever as an append-only event log.
Without the `condition=Q(...)` filter, this index would have to track every
row the table has ever held; with it, the relay's "give me the unpublished
rows, oldest first" query stays cheap at the table's hundredth row and at
its ten-millionth.

`order/services.py::place_order()`'s side of the cure is a replacement, not
an addition — the old synchronous call is *gone*, not wrapped:

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

This runs at the very end of the same `@transaction.atomic()` that reserves
inventory, creates the order row, and charges payment — so a `DECLINE`
payment method or a `SHIP-FAIL` address still rolls this row back right
along with everything else, the identical net-zero guarantee ch.09's smell
tests already assert. What changed is *what the last write is*: before,
it was a call that left this transaction's process entirely; now, it's an
`INSERT` into a table in the same database, inside the same transaction,
subject to the same all-or-nothing guarantee as the order row it describes.
Checkout's HTTP contract doesn't move either — `POST /api/orders` still
returns a synchronous `201 CONFIRMED` in the same round-trip, not a `202
Accepted`; only the notification *side effect* moved off that path.

Writing the row is half the cure. Something still has to get it to Kafka,
and `common/management/commands/outbox_relay.py` is a plain polling loop,
named as such rather than dressed up as something more sophisticated:

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

Three decisions here each matter. First, the Kafka message key is
`aggregate_id` — the order id, as a string — not some relay-internal id;
every event about the same order lands on the same partition, in
publish order, which matters the moment a second event type about the same
aggregate exists. Second, `send_and_wait()` is called *before*
`_mark_published()`, not after some buffered batch — publish, confirm,
*then* mark. That ordering is precisely what makes this **at-least-once**,
named in the docstring rather than left implicit: a crash between those two
lines republishes an already-sent event on the relay's next poll, because
the row still shows `published_at IS NULL`. The alternative ordering
(mark first, publish second) would be at-most-once instead — a crash there
loses the event's only remaining copy of "still needs sending," silently.
At-least-once with a cheap, correct consumer-side dedupe (below) is the
right trade; silent loss never is. Third, this is a **simple polling
relay, not Debezium/CDC** — the module docstring says so explicitly,
because the more sophisticated alternative (tailing Postgres's write-ahead
log instead of polling a table) is deferred by design, the same way the
Java sibling project sequences it. A one-second poll against a
condition-indexed table is a perfectly adequate relay for this book's
traffic; CDC becomes worth its complexity once polling latency or database load
from polling itself becomes the bottleneck, neither of which is the case
here.

## Consuming it: aiokafka and the idempotency it demands

{% include excalidraw.html file="event-driven-notification-topology" alt="End-to-end pipeline: checkout writes an outbox row, the relay publishes it to Kafka at-least-once, and two independent consumer groups (monolith-notification and notification-service) each consume the same topic into their own read model, with the strangler proxy flag choosing which one answers GET /api/notifications" caption="Figure 17.2 — One outbox row, two independent consumer groups, one flag choosing who answers the read" %}

At-least-once delivery is a promise about the *producer* side; it says
nothing about what a consumer does when the same event arrives twice. That
obligation falls entirely on `examples/03-notification-service/app/consumer.py::OrderPlacedConsumer`,
and it's worth reading its lifecycle in full because every call in it is
answering a specific question a naive `while True: consume()` loop would
get wrong:

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

`group_id=self._settings.consumer_group` (`"notification-service"`) is
what makes this a *consumer group member*, not a free-floating reader:
Kafka guarantees that within one group, exactly one member sees any given
partition's records, so if this service ever runs more than one replica,
they divide the topic's partitions between them rather than each
duplicating every record. `auto_offset_reset="earliest"` means a brand-new
deployment, with no committed offset yet for this group, starts from the
*beginning* of the topic rather than only seeing events published after it
happened to join — the right default for a service whose whole job is
"don't miss anything," at the cost of reprocessing history on a true cold
start (which the idempotency below makes safe). `enable_auto_commit=True`
is the simplest correct starting point for a demo consumer, committing
offsets periodically in the background rather than requiring this code to
manage commit timing itself — the trade is that a crash between processing
a record and the next auto-commit can redeliver that record on restart,
which is exactly the at-least-once case the idempotency layer below exists
to absorb, not a defect introduced by this choice. The background task
(`asyncio.create_task`, not an inline blocking loop in the request path) is
what keeps the read side (`app/routes.py`) and the write side (this
consumer) fully decoupled — one can be slow, or briefly down, without the
other noticing.

The loop itself treats a single bad record as a reason to log, not to die:

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

`OrderPlacedEvent.model_validate(record.value)` is ch.16's ACL doing its
job at the one place it actually runs — a malformed or unexpected payload
raises a `ValidationError` here, caught by the broad `except Exception`
below it, logged with the offset for diagnosis, and the loop moves on to
the *next* record rather than stopping delivery for every order placed
afterward. `asyncio.CancelledError` is re-raised rather than swallowed,
because that exception means "the service is shutting down," not "this
record failed" — catching it here would turn a clean shutdown into a hang.

Idempotency itself lives one layer down, in `app/service.py::record_order_placed`,
and it's a two-layer guarantee, not one:

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

{% include excalidraw.html file="idempotent-consumer-dedupe" alt="What happens on a redelivered order.placed event: application-level check-then-insert handles the common case, and a database-level partial unique index on order_id backstops the narrow window where two redeliveries race the check itself, so exactly one Notification row survives either way" caption="Figure 17.3 — At-least-once delivery, exactly-once effect" %}

**Layer one** is `get_by_order_id(session, event.order_id)` — a plain
lookup, checked *before* any write is attempted. This is the fast,
common-case path: the relay republished an event this consumer already
processed, the lookup finds the row, and the function returns without
touching the database again. **Layer two** is the `IntegrityError` catch
around the insert itself — the backstop for the one window layer one
can't close on its own: two deliveries of the same event, processed
concurrently (a second consumer replica, say), can both run the
`get_by_order_id` check, both see nothing, and both proceed to insert. The
database — not this function's own logic — is what breaks that tie: a
partial unique index on `order_id` (`migrations/versions/0001_create_notification_schema.py`'s
`uq_notifications_order_id`, `UNIQUE (order_id) WHERE order_id IS NOT NULL`)
rejects the second `INSERT` outright, and this function catches that
specific exception, rolls back the half-finished transaction, logs it as a
discarded duplicate, and returns — not an error, because by definition a
notification for that order already exists the moment this exception
fires. Each layer alone would leave a gap: application-level checking alone
races under concurrency; a database constraint alone, with no
check-then-insert, would mean every redelivery hits the database with a
doomed `INSERT` instead of skipping cleanly. Together, the common case is
cheap and the rare race is still correct.

The monolith's own copy of this same idempotency guarantee,
`notification/services.py::record_order_placed`, is structurally
identical — check-then-create, `IntegrityError` as the race backstop — a
detail returned to below, in the Django-relay-versus-FastAPI-consumer
comparison.

## Own-schema ownership: the deliberate contrast with Review

`examples/02-review-service` reads and writes the monolith's own shared
Postgres tables; `examples/03-notification-service` does not touch them at
all. `app/models.py`'s docstring states the reason as a design decision,
not a missing feature:

> `customer_id` / `order_id` are plain `BIGINT` columns, NOT foreign keys
> into the monolith's `customers`/`orders` tables — this service's schema
> must not reach across into tables it does not own.

The reasoning traces straight back to ch.16's dividing line. Review stays
synchronously consistent with the monolith by construction — every request
is a live round-trip against the same tables, so there's no window where
the two could disagree. Notification is asynchronous by its very nature: a
second writer to the monolith's `notifications` table (this service's own
consumer) racing against the monolith's own writer, with no shared
transaction and no request/response relationship tying them together,
*is* a split-brain, not a hypothetical one. Owning the table from the
start — one writer, this service's own consumer, full stop — removes the
question of reconciling two writers by making sure there's never more than
one.

`app/db.py`'s engine sets the schema at the connection level, and
`app/models.py` sets it again at the mapping level — a chosen redundancy,
not an oversight:

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

`search_path=notification,public` is a convenience — it means an ad hoc
`psql` session against this database also defaults to this schema without
typing `notification.notifications` by hand. It is not the correctness
guarantee: `{"schema": "notification"}` in `__table_args__` means every
query SQLAlchemy generates is fully schema-qualified regardless of
whatever search path the connection happens to have, so a misconfigured
`search_path` could never silently redirect this service's writes into
`public.notifications` (the monolith's own table, in the same Postgres
instance) by accident.

Creating that schema is this project's **first** Alembic migration, a
deliberate contrast with review-service, which has no migration tooling at
all because it never changes the schema it reads:

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

`order_id` stays nullable here, matching the monolith's own
`Notification.order` being `null=True` — not every notification this
service might ever send needs to originate from an order, even though
every row the current consumer writes has one. Leaving that door open now
costs nothing and avoids a migration later if a non-order notification type
ever needs this same table.

## The Django relay vs the FastAPI consumer, side by side

{% include codetabs.html langs="Monolith — Django outbox_relay (producer)|notification-service — aiokafka consumer" %}

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

Both sides are `aiokafka` end to end — this project's single Kafka client
on both the producer and the consumer side, Django management command or
not — a fact that matters because it means the Django/FastAPI split
in this book is purely about *which web framework answers HTTP requests*,
not about which async Kafka library each side reaches for. The relay polls
a table and pushes to Kafka; the consumer subscribes to Kafka and pushes to
a table — mirror images of the same at-least-once contract, one on each
side of the topic. The monolith's self-consumer
(`notification/management/commands/order_placed_consumer.py`, group
`monolith-notification`) is the third leg of this same shape, consuming
the identical topic into the identical kind of idempotent write, just
against the monolith's own shared schema instead of an owned one — proof
that "consumer of `order.placed`" is a role any number of independent
subscribers can hold at once, which is precisely the decorating-collaborator
point ch.16 introduced.

## The measured cost of Phase B — not a regression

Following the same two-phase discipline ch.15 established — document Phase
A, ship only Phase B — `examples/03-notification-service/MIGRATION.md`
measures what a Django-ORM-lifted Phase A would have cost, by the same
faithful-proxy method ch.15 used: the real combined weight of
`django.setup()` against the monolith's actual `config.settings` plus
`import fastapi, uvicorn`, since no Phase A server was ever built here
either. Notification's MIGRATION.md adds a third problem Review's never
had, stated directly rather than glossed over: Review's Phase A had something to lift (the
monolith's existing REST view); **notification's write path has no
monolith original at all** — the monolith never consumed its own
`order.placed` event, so a faithful Phase A can only ever cover the *read*
surface, and the consumer is net-new in either phase.

| Metric | Phase A (proxy measurement) | Phase B (shipped) |
|---|---|---|
| Cold interpreter floor | 0.02 s | 0.02 s |
| Import/startup time (3-run avg) | 0.36 s | 0.39 s |
| Import-only RSS | ~74.5 MB | ~77.3 MB |
| Running server RSS (after 20 requests) | not measured (no server built) | ~90.0 MB |

Taken at face value rather than massaged into a cleaner story: import-time and
import-RSS are close between the two phases, same finding as Review's own
comparison — FastAPI/Pydantic v2's import graph dominates both columns, and
`aiokafka`'s added cost on top of that (Phase B only) is a modest ~3 MB and
~0.03 s. What's different from Review's near-wash result is the *running*
row: ~90 MB of RSS that Phase A's proxy measurement structurally cannot
capture at all, because it reflects something Phase A never had — a live
`aiokafka` consumer holding an open broker connection, consumer-group
membership, and its own buffers, running continuously in the background.
That gap is **real runtime capability, not a regression to be optimized
away**: it's the cost of a background subscriber that is actually
subscribed, doing actual work, for as long as the process runs. Reading a
bigger running-RSS number as "notification-service got heavier" would miss
what it's actually measuring — the real price of the thing this chapter
set out to build.

## The cutover: two flags, flipped together

Cutting `notification` over involves two independent switches, not one,
and it's worth being precise about what each one controls. The **outbox
path** (`OutboxEvent` + `outbox_relay` + the monolith's own
`order_placed_consumer`) is not gated by a feature flag at all — once
shipped, checkout always writes the outbox row, and the relay always
publishes it; this is the "going event-driven" change itself, and it
applies identically regardless of which backend eventually answers a read.
The **proxy flag**, `STRANGLER_NOTIFICATION_ENABLED`
(`examples/01-strangler-proxy`, ch.16's generalized `_select_backend()`),
is the only switch an operator actually flips: it decides whether
`GET /api/notifications*` is answered by the monolith's own consumer or by
`examples/03-notification-service`'s. Because both consumer groups
(`monolith-notification` and `notification-service`) run continuously
throughout the strangle window — the decorating-collaborator point again —
flipping that one flag back and forth costs nothing but a proxy restart,
exactly like ch.15's `STRANGLER_REVIEW_ENABLED`. Reversibility here is a
real property of what still exists, not a one-way migration disguised
as a toggle: the monolith's read model keeps getting fed by its own
consumer whether or not the flag currently points at it.

## The async false-equivalence trap, defeated with bounded-wait

Every prior equivalence check in this book — Smoke, the four checkout
scenarios, Review's R1–R5 — could assert correctness with a single,
immediate check right after the triggering request completed, because
every one of those paths was synchronously consistent: the HTTP response
itself was proof the effect had already happened. Notification breaks that
assumption for the first time in this project. `POST /api/orders` still
returns `201 CONFIRMED` synchronously (checkout's own contract hasn't
moved), but the notification that order produces reaches `GET
/api/notifications` only after outbox → relay → Kafka → consumer have all
run — a real, unbounded amount of wall-clock time after the order response
already came back. A test suite that asserted `GET /api/notifications`
immediately after `POST /api/orders` would be exposed to a **false
equivalence**: a correct, working system failing the check purely because
the check ran too early, indistinguishable in the suite's output from the
system actually being broken.

`tooling/newman/mea.postman_collection.json`'s Notification Context
Contract folder defeats that trap with a bounded-wait poll, not a fixed
sleep: N1 fires a plain synchronous checkout and captures the resulting
order's id; N2 polls `GET /api/notifications?customerId=` on a fixed
retry budget — `notificationPollMaxAttempts × notificationPollDelayMs` =
20 × 750ms, a ~15-second ceiling, delaying only on a *retry* (attempt 0
runs immediately) — until a notification whose `orderId` matches N1's
appears, then asserts its full shape strictly. Getting the two failure
modes right is the entire point of a bounded-wait helper: it must resolve
quickly when the system is healthy, and it must fail **loudly and
promptly** when it isn't — not hang forever, and not soft-pass by treating
an empty result as "not yet, keep waiting" indefinitely.

Proven against the real stack, both ways. Healthy:

| Run | Flag | Served by | Result |
|---|---|---|---|
| A | `false` | monolith's own consumer | **66/66 assertions green**, 0 failed |
| B | `true` | notification-service | **66/66 assertions green**, 0 failed, byte-identical shape to A |

Both runs resolved on **attempt 2/20 (~750ms)** — one retry past the
immediate first check, comfortably inside the ~15s budget, and essentially
identical latency whichever backend actually served the read. That
byte-identical outcome across two structurally different backends (a
Django management command's read model versus a FastAPI service's owned
schema) is the cutover proof this chapter needed: the unedited collection,
re-pointed at nothing but a flag, cannot tell the two apart.

A broken run, staged by killing the service — `examples/03-notification-service` down, flag
`true`:

```
21. AssertionError  Order-confirmation notification for orderId=19 is observable
                    within the bounded-wait budget (20 x 750ms, attempt 20/20)
                    no notification with orderId=19 found after 20 attempt(s):
                    expected undefined not to be undefined
```

**21/23 assertions failed, newman exit code 1.** The poll ran its full
20-attempt budget (~14.7 seconds observed, matching the ~15s design
figure), every attempt returned the proxy's real `502` while the service
was down, and the final assertion failed cleanly on its own terms once the
budget was exhausted — it never hung, and it never quietly reported
success. Restarting the service and re-running the same folder returned to
**9/9 green**, resolving on attempt 3/20 this time (the restarted consumer
needed a moment to rejoin its consumer group and complete a partition
rebalance before it could see the already-published event) — still
comfortably inside budget. An equivalence gate that cannot go red when the
thing it is gating is actually broken isn't an equivalence gate; proving
this one fails loudly, on a downstream that is truly unreachable, is what
makes every green run above it trustworthy.

## At-least-once and the decorating collaborator, recapped

Two threads run through this entire chapter, and it's worth naming them
together now that both are built. **At-least-once** is not a compromise
this chapter apologizes for — it's the named delivery guarantee the outbox
relay provides, made safe by idempotent consumers on both ends
(the monolith's own `record_order_placed` and notification-service's),
each backstopped by a database-level unique constraint for the case where
application logic alone can't close a race. **The decorating collaborator**
is what made that guarantee necessary in a way ch.15's extraction never
required: once the monolith became a peer subscriber to its own event
rather than keeping a privileged synchronous path, two independent
consumer groups reading the same topic is the normal, permanent shape of
this seam for the entire strangle window — not a transitional
inconvenience to be cleaned up once notification-service ships, but the
actual architecture this project runs on until Notification's monolith
module is eventually decommissioned.

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

Place an order against the monolith (`POST /api/orders`) and watch it
appear on both read models — the monolith's `GET /api/notifications`
(through its own consumer) and this service's `GET /api/notifications` on
`:8002` — independently, without either depending on the other.

## Cross-check

```bash
cd examples/03-notification-service
uv run pytest -m "not integration"   # REST contract + idempotency, no Kafka
uv run pytest -m integration          # Testcontainers: real Kafka, redelivery proof
uv run ruff check .
```

The integration layer is the cross-check worth trusting most: it publishes
the identical `order.placed` payload twice through an actual Kafka broker
(Testcontainers-managed) and the real `OrderPlacedConsumer`,
then asserts exactly one `Notification` row exists afterward — the same
claim this chapter's idempotency section makes in prose, proven against
the real client library and a real broker rather than taken on faith.

## What you learned

- A dual-write hazard is cured by making sure there is only ever **one**
  write inside the local transaction — the outbox row — and moving
  everything that has to reach a second system onto a separate,
  independently-retriable process (the relay) that publishes
  at-least-once.
- At-least-once delivery pushes idempotency onto the consumer by
  construction. Two layers, not one, make it correct under concurrency:
  check-then-insert for the common case, a database partial unique index
  as the backstop for a real race between two redeliveries.
- Owning a schema from day one (Alembic, this project's first migration)
  is the right call specifically when a seam is asynchronous — a second,
  uncoordinated writer to a shared table is a split-brain, not a
  simplification, which is why Review's shared-schema posture doesn't
  generalize to Notification.
- A bounded-wait poll — fixed retry budget, delay only on retry, strict
  failure on timeout — is what an equivalence suite needs the moment a
  write and the read that observes its effect are connected only by an
  eventually-consistent path; an immediate single check would be a false
  equivalence waiting to misfire.
- The decorating-collaborator pattern makes "two independent consumer
  groups on one topic" the permanent shape of an event-driven strangler
  seam, not a transitional state — both the monolith's own consumer and
  the new service's consumer run for the entire window, and the proxy flag
  only chooses which one answers a read.

Next: Part 6 turns from *how a service gets extracted* to *who owns the
data once it's extracted* — ch.18 starts dismantling the shared schema this
chapter's notification-service was the first to opt entirely out of.

---

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes 8/8 against a real, throwaway `postgres:18.6-alpine`
(5 REST contract tests, 2 service-level idempotency unit tests) plus the
Testcontainers integration test proving redelivery-yields-one-row against a
real Kafka broker; `uv run ruff check .` passes clean; `alembic upgrade
head` confirmed via `psql` to create the `notification` schema, table, and
both indexes, and to no-op correctly on a second run. The full async
cutover is verified live end to end in `tooling/newman/GOLDEN-BASELINE.md`'s
r03 NEWMAN-ASYNC lane: 66/66 assertions green through the proxy in both
flag states (byte-identical shape), bounded-wait resolution on attempt
2/20 (~750ms) in both healthy runs, and the negative check (notification-
service killed) failing strictly at 21/23 failed / exit code 1 after
exhausting its ~15s budget, then recovering to 9/9 green on restart. The
Phase A numbers in this chapter are a measured proxy, not a running
server — Phase A code itself was never built, by design, matching
`examples/02-review-service`'s precedent.*
