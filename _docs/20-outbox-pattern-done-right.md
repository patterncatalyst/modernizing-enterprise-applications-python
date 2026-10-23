---
title: "The Outbox Pattern, Done Right"
order: 20
part: "Data Across the Seam"
description: "Transactional outbox vs. dual-write; idempotent consumers as its necessary counterpart; ordering, redelivery, and the project's first multi-service outbox choreography."
duration: 40 minutes
---

Chapter 17 introduced the transactional outbox at the exact moment the
monolith needed it: the Notification extraction had to stop running a
synchronous, out-of-process side effect inside checkout's own
`transaction.atomic()`, and the outbox was the mechanism that let the write
survive without smuggling a second system into that transaction's blast
radius. That chapter earned the pattern by building it, but it only ever had to
prove it once, in one direction: one outbox, one relay, one consumer. This
chapter's subject is the outbox itself: not what it is, but what it takes to
trust it in production, and what changes once a second service starts
writing one of its own. None of the code below is new. It is the same
`examples/00-monolith/common/management/commands/outbox_relay.py` ch.17
built, read again at the depth a reader needs before trusting this pattern
with their own checkout flow, plus its first independent sibling,
`examples/05-payment-service/app/relay.py`, which the payment extraction
needed for a reason ch.17's Notification extraction never did: this is the
first service in this book that both *consumes* an event and *produces* one
of its own.

The code is in `examples/00-monolith/` (the original outbox and relay) and
`examples/05-payment-service/` (the second, independent instance, plus the
first consumer-and-producer outbox this book has built). There is no new run
script for this chapter: the run scripts already there build, migrate, and
run the outbox write, the relay, and the consumers exactly as described
below, and each directory's `README.md` covers how to drive them.

## The dual-write problem: two systems, one guarantee you don't have

Here is the version of "save to the database, then publish to Kafka" that
looks correct and isn't:

```python
# NOT what this project does -- the pattern this chapter explains the cure for
order = Order.objects.create(...)               # write 1: Postgres
kafka_producer.send("order.placed", event)       # write 2: Kafka, a DIFFERENT system
```

Two writes, two different systems, no transaction spanning both. Four
failure windows exist between them, and every one is a real outage mode, not
a theoretical one: the process can crash after the Postgres commit but
before the Kafka send (the order exists; nobody downstream ever hears about
it); the Kafka send itself can time out or the broker can be unreachable
(the same gap, just earlier); the Postgres commit can fail *after* a naive
implementation already sent the Kafka message (a notification goes out for
an order that was never actually placed); or a retry wrapped around the
whole two-step sequence can re-run the Postgres write a second time because
the caller can't tell which half failed. None of these require unusual bad
luck; they are what "two independent systems, no shared transaction" means
by definition. A team that ships this and never notices is a team that
hasn't yet had a process restart at the wrong millisecond.

## The transactional outbox: moving the guarantee inside one transaction

The fix ch.17 landed is to never make the second write cross a process
boundary in the first place. `order.services._write_order_placed_outbox_event`
writes one more row to one more table, `common.OutboxEvent`, in the *same*
Postgres transaction as everything else checkout is already doing:

```python
# order/services.py -- the write that replaced the dual-write
OutboxEvent.objects.create(
    aggregate_type="order",
    aggregate_id=str(order.id),
    event_type="order.placed",
    payload=payload,
)
```

That `.create()` call has no special transaction handling of its own; it
doesn't need any, because it executes inside the surrounding
`transaction.atomic()` block checkout already opened for the order row, the
line items, and (in synchronous mode) the payment charge. Postgres's own
write-ahead log is the entire mechanism: either every row in that block
commits together, including the outbox row, or none of them do. There is no
longer a second system in the loop at transaction time at all: "publish an
event" has been rewritten as "write a row," and a row is something Postgres
already knows how to make atomic with everything else. This
*doesn't* make the event delivery synchronous, and it doesn't
make Kafka part of the transaction (Kafka can't be: there is no two-phase
commit between Postgres and a message broker in this stack, by design, the
same way there isn't one anywhere in this book's event-driven chapters).
What it buys is narrower and more valuable: the *decision* to emit the event
is now exactly as durable as the order itself. If the order exists, the
outbox row recording that fact exists too, because they share one commit.

A second process, `common.management.commands.outbox_relay`, is the piece
that actually gets the row out of Postgres and onto Kafka, a separate
process by design, decoupled from the request/response cycle that wrote it:

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

Publish, *then* stamp `published_at`. That ordering is the whole design
decision, and the two orderings are worth sitting with as a pair. Stamp
first, publish second, and a crash between the two steps loses the event
forever: the row is marked done, the relay will never look at it again, and
nothing downstream ever hears about the order. Publish first, stamp second,
and the same crash instead *re-publishes* the same event the next time the
relay polls, because the row still reads `published_at IS NULL`. One
ordering can silently lose a message; the other can only ever duplicate one.
Given that `consumer.ack(); process()` and `process(); consumer.ack()` is the
same choice phrased from the other side of a queue, and every message-queue
chapter this book could have written lands on the same answer: **never pick
the ordering that can lose a message when the alternative is an ordering
that can duplicate one, because duplication is solvable and loss isn't.**

{% include excalidraw.html file="outbox-relay-at-least-once" alt="One DB transaction commits the state row and the outbox row together, a relay polls and publishes at-least-once, and the necessary counterpart is an idempotent consumer in whichever idiom fits the write" caption="Figure 20.1: The bridge, the relay, and the counterpart that makes at-least-once survive contact with reality" %}

## How the code works: the relay's poll loop, in full

`outbox_relay.py`'s `Command.handle()` is the entry point: a Django
management command, `asyncio.run(_run())`, no different in shape from any
other long-running worker process this project runs (`order_placed_consumer`,
and this chapter's own `order_saga_listener` from ch.23). `_run()` is the
loop itself:

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

`_fetch_unpublished_batch` is a plain Django ORM query:
`OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at",
"id")[:BATCH_SIZE]`, reading the oldest hundred unpublished rows. Ordering
by `created_at, id` rather than just `id` matters for a reason that is easy
to miss: `created_at` is set when the row is written inside the checkout
transaction, so two outbox rows written in the same millisecond (a batch
import, a burst of concurrent checkouts) sort deterministically by the `id`
tiebreaker rather than by whatever order Postgres happened to return them
in. The partial index this book has used since ch.17
(`WHERE published_at IS NULL`) is what keeps this query cheap forever: a
table with a million published rows and ten unpublished ones scans exactly
those ten, not the million, because the index only ever contains rows the
relay still has work to do on. Once a row is marked published, it falls out
of the index entirely, not deleted, just no longer indexed, which is the
right trade for a relay that polls constantly but a reporting query that
runs rarely.

The `if not batch: sleep` branch is the backpressure valve, and its absence
would be a real bug, not a style choice: without it, an empty result set
would spin the loop as fast as the event loop and the database connection
pool allow, burning CPU and connections on a table with nothing left to
read. With it, the relay is idle exactly when there is nothing to do and
busy exactly when there is: `DEFAULT_POLL_MS = 1000` means a freshly
written outbox row waits at most one second before the relay even looks for
it, which is the latency floor this whole mechanism accepts in exchange for
decoupling the write from the publish.

## Payment-service's own outbox: the first consumer that is also a producer

Every outbox this book built through ch.19 shared one shape: a producer (the
monolith) and a consumer (Review's reads, Notification's read model,
Inventory's CDC backfill) that never itself had to publish anything back.
`examples/05-payment-service` breaks that shape for the first time, and its
own `README.md` names the reason directly: "this service also produces
events (`payment.captured`/`payment.declined`), so it needs its own
transactional outbox AND its own relay; notification-service only ever
reads the monolith's outbox-fed topic, it never writes one of its own."
`app/service.py::process_order_placed` is the write side of that second
outbox, and it earns the same atomicity guarantee the monolith's checkout
does, just inside a different service's own schema:

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

`create_payment_with_outbox_event` does for `payment.outbox` exactly what
`_write_order_placed_outbox_event` does for `common.OutboxEvent`: writes the
`Payment` row and the matching `payment.outbox` row in one SQLAlchemy
session commit, so a capture or a decline is exactly as durable as the
outbox row announcing it. `app/relay.py::OutboxRelay._publish_one` is a
structural copy of the monolith's `_publish_one`: publish via
`AIOKafkaProducer.send_and_wait`, *then* stamp `published_at` in a
follow-up statement, because it is solving the identical problem with the
identical ordering guarantee. Nothing about aiokafka, Postgres, or the
publish-then-stamp sequence changes just because the schema moved from
Django's ORM to SQLAlchemy and the service from a monolith app to a
standalone FastAPI process; the *pattern* doesn't care which framework wrote
the row, only that the write and the publish are decoupled the same correct
way every time.

{% include excalidraw.html file="multi-outbox-saga-topology" alt="The monolith's order.placed outbox feeds payment-service's consumer, which writes its own outbox, which the monolith's own saga listener consumes in turn -- two outboxes chained end to end, no orchestrator" caption="Figure 20.2: Two outboxes, chained: this project's first multi-service outbox choreography" %}

This is the shape Figure 20.2 draws out, and it stands as its own
milestone, separate from ch.23's saga mechanics: **this is the first time
this book chains two independently-owned outboxes end to end**, with no
coordinator anywhere in the picture. The monolith's checkout writes
`order.placed`; payment-service's consumer reacts to it and writes its own
`payment.captured`/`payment.declined`; the monolith's own
`order_saga_listener` (ch.23) reacts to *that*. Three hops, three separate
at-least-once guarantees, and the monolith is both the first producer and
the final consumer of a round trip that started as one HTTP request. Nothing
in this topology needs to know the whole path exists; each hop only knows
the topic it publishes to or the topic it subscribes from, which is the
entire argument for choreography over orchestration that ch.23 develops in
full.

## Idempotent consumers: the half of the pattern a diagram of the write side hides

Everything above describes how the outbox makes the *publish* side durable
and at-least-once. It says nothing about what happens when "at least once"
actually means "twice", and in a system that has been running this
mechanism since ch.17, it eventually will, whether from the relay's own
crash-and-republish window, a Kafka consumer group rebalance replaying the
last uncommitted offset, or (as the cutover evidence below records) a
message redelivered by hand to prove the point. **At-least-once is a
promise about the pipe, not about the effect**: it guarantees the message
arrives, not that it arrives once, and the only thing that turns "arrives
one or more times" into "applied exactly once" is an idempotent consumer on
the receiving end. This project has landed three different idioms for that,
and lining them up side by side matters, because picking the wrong
one for a given kind of write is its own class of bug.

**Check-then-insert plus a unique-index backstop** is Notification's answer,
and it fits a write that either happened or didn't: there's no partial
state to merge. `app/service.py::process_order_placed` above is actually
this same idiom, reused for Payment: look up by `order_id` first, and if a
row already exists, return without writing anything. The database-level
`uq_payments_order_id` unique index is the backstop for the narrower race
where two deliveries are being processed *concurrently*: the application
check can't see the other delivery's in-flight insert, so the database
catches it as an `IntegrityError`, caught and discarded as a duplicate
rather than allowed to crash the consumer.

**`INSERT ... ON CONFLICT` upsert** is ch.19's CDC consumer's answer, and it
fits a different shape of write: a row *update*, not a one-time fact, where
there's no natural "have I seen this before" marker the way an `order_id`
is one for a payment. Applying the same upsert twice converges to the same
end state as applying it once, which is exactly the property an idempotent
consumer needs and exactly why a read-modify-write can't offer the same
guarantee under redelivery.

**A status-transition guard** is this chapter's forward reference to ch.23's
`order_saga_listener`: an order that has already left `PENDING`, because an
earlier delivery of this exact event, or of the *other* outcome event for
the same order, already resolved it, treats a redelivery as a no-op by
construction, not by checking a dedupe table. None of these three idioms is
more correct than the others in the abstract; each is the right tool for the
specific write it protects, and knowing which one a given consumer needs is
the actual skill this section is teaching, not "add idempotency" as an
undifferentiated instruction.

## Done right, concern by concern

**Ordering.** Every outbox this book has shipped keys its Kafka messages by
`aggregate_id`: the order ID as a string for `order.placed`, the same order
ID for `payment.captured`/`payment.declined`. Kafka only guarantees ordering
*within* a partition, and keying by aggregate ID is what guarantees every
event about the *same* order lands in the same partition, in the order it
was published, which is the only ordering guarantee any consumer in this
book actually needs. Nothing here needs global ordering across different
orders, and nothing here gets it; the two are independent and this project
has never needed to pay for the stronger, more expensive one.

**Poison messages.** Neither relay in this project bounds how many times it
will retry a batch that keeps failing: a transient broker hiccup or a
dropped connection is logged and retried on the next poll, by design (see
`_relay_loop`'s `except Exception: logger.exception(...)`), but there is no
dead-letter topic and no retry ceiling for a message that fails
*deterministically*, every time, forever. That is a documented gap, not an
oversight: this book's demo scale has never produced a message that fails
structurally rather than transiently, so building a dead-letter mechanism
now would be exactly the speculative infrastructure this project's scope
discipline argues against. A production deployment at real scale should not
copy this gap forward without closing it.

**Cleanup and retention.** Published outbox rows are never deleted. They
fall out of the partial index the moment `published_at` is set, so they stop
costing the relay anything, but they still grow the table forever. A real
operational deployment would add a retention job (delete-or-archive rows
published more than N days ago), which this project has never needed for a
demo-scale table that gets reseeded between runs, but which any team
running this pattern against a table that accumulates real production
traffic should plan for before the table's size becomes its own problem.

**Polling versus log-based CDC.** ch.19 already built this project's one
instance of transaction-log tailing, Debezium reading Postgres's WAL
directly, rather than an application table being polled, for a different
job (backfilling Inventory's schema during its cutover window). The same
technique could replace either relay in this chapter: tail the
`common_outbox`/`payment_outbox` tables' own WAL entries instead of polling
them, trading the relay process and its one-second latency floor for a
Debezium connector and a Kafka Connect runtime. ch.19's retire runbook is
the clear accounting of what that trade costs: more infrastructure, a
slot to manage, a connector's own operational surface, which is exactly why
this project's two application outboxes stay polling-based: CDC earns its
complexity once polling latency or the load polling itself puts on the
database becomes the actual bottleneck, and neither relay in this book has
hit that ceiling yet.

> **ADLC in Action**: The build plan settled the multi-outbox shape
> before a line of payment-service code existed: the
> planning phase decided that payment-service would own its own schema and
> its own outbox, matching the monolith's proven relay shape
> rather than inventing a second delivery mechanism, and recorded *why*
> (no shared-writer split-brain, consistent with notification-service's
> precedent) as a standing decision rather than an implementation detail
> discovered mid-build. The execution phase then reused
> `outbox_relay.py`'s publish-then-stamp ordering byte-for-byte rather than
> re-deriving it, and the verification phase proved the resulting two-hop
> pipeline end to end against a real broker: the GOLDEN-BASELINE.md numbers
> cited below are a verification-phase artifact, not a claim asserted from
> the code alone.

## Evidence: the outbox under real redelivery, not just under code review

`tooling/newman/GOLDEN-BASELINE.md`'s cutover lane is where this
chapter's claims stop being design arguments and start being measurements.
With the full topology running (monolith, payment-service, inventory-service,
the strangler proxy, and a real single-node Kafka broker), a normal
checkout's `order.placed` event made a real round trip through both relays
and both consumers: Scenario 1's bounded-wait poll for the order's terminal
status resolved on **attempt 2/20**, a real multi-hundred-millisecond Kafka
round trip through payment-service and back through ch.23's saga listener,
not an artifact of a fast in-process loop.

The redelivery guarantee was then proven directly, not inferred. The exact
`payment.declined` event payment-service had already published for one order
was re-published to the `payment.declined` topic by hand, simulating a
broker-side redelivery. `order_saga_listener`'s own log recorded the
idempotent no-op this chapter's status-transition-guard idiom promises:

```
payment.declined redelivered for order_id=12 status=PAYMENT_DECLINED -- no-op (status guard)
```

Stock before the redelivered event: 94. Stock after: 94, unchanged,
confirming the guard stopped the second delivery before it ever reached the
compensating `Release` call a second time. A separate negative check killed
payment-service outright (both its consumer and its relay) and placed a
normal checkout against the dead service: the order was still accepted and
persisted `PENDING`, the write side of the outbox doesn't need
payment-service alive at all, but the bounded-wait poll for that order's
terminal status exhausted its full `20 x 750ms` budget and Newman exited
`1`, a real `15.1s` run duration confirming the full budget was spent, not
short-circuited. Restarting payment-service drained every order stuck during
the outage to `CONFIRMED` within seconds, with zero manual intervention: its
consumer simply rejoined its Kafka consumer group and caught up from its own
committed offset, exactly the self-healing property an at-least-once
pipeline with an idempotent consumer is supposed to provide.

## What you learned

- The transactional outbox fixes the dual-write problem by never letting the
  second write cross a process boundary during the transaction at all: an
  ordinary row, in the same commit as everything else, replaces a
  synchronous call to a second system.
- The relay's publish-then-stamp ordering is the one design decision that
  matters most in this pattern: it can only ever duplicate a message on
  crash, never lose one, the same choice every ack-ordering decision in a
  message-driven system eventually reduces to.
- At-least-once delivery is a promise about the pipe, not the effect; an
  idempotent consumer is what turns "delivered one or more times" into
  "applied exactly once," and this project has three different correct
  idioms for it (check-then-insert, upsert, status-transition guard)
  depending on what kind of write is being protected.
- The payment-service is this project's first service that is both a
  consumer and a producer of events, which is what makes two independently
  owned outboxes chain end to end for the first time: no orchestrator
  anywhere in that chain, just three independent at-least-once hops.
- Ordering, poison messages, cleanup, and the polling-versus-CDC trade are
  all real production concerns this pattern raises; this project documents
  rather than hides the gaps it hasn't closed (no dead-letter topic, no
  retention job), because building that machinery now, for a demo-scale
  table that has never needed it, would be speculative infrastructure ahead
  of the problem that earns it.

Next: ch.21 splits reads from writes with CQRS, then ch.22 turns from the mechanism to its cost: what the ACID guarantee
checkout used to take for granted actually loses once a saga, not a single
transaction, is what resolves an order.
