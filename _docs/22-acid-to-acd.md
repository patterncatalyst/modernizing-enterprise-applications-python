---
title: "ACID → ACD: Living Without Isolation"
order: 22
part: "Data Across the Seam"
description: "The consistency just given up -- dirty reads, lost updates, non-repeatable reads -- where it bites and how to bound it; the real cost of checkout's 201-to-202 flip."
duration: 35 minutes
---

Every extraction this book has built so far has been upfront about what it
costs, and most of those costs have been bounded and local: a slower cold
start, a second schema to migrate, a proto contract to keep in sync. ch.19
named a cost of a different kind: the free rollback a single shared
transaction used to give checkout for nothing, and rebuilt it by hand with
an explicit compensating `Release`. This chapter names the cost underneath
that one: the actual consistency *model* checkout runs under has changed,
not just the mechanism that implements it, and the payment extraction is
the first place in this book where that change is unavoidable rather than
deferrable. `PAYMENT_MODE=synchronous` still runs on full ACID, byte for
byte, unchanged from the start. `PAYMENT_MODE=choreographed` runs on something
weaker and more accurate about what a distributed system can actually
promise, and this chapter is about naming exactly what was traded, not
pretending the trade didn't happen.

The code is in `examples/00-monolith/order/services.py` (`_place_order_local`
versus `_place_order_choreographed`) and `examples/00-monolith/order/models.py`
(`Order.Status`). There is no new run script for this chapter; the two
dispatch paths it compares already exist and are already exercised by
`tooling/newman/GOLDEN-BASELINE.md`'s cutover lanes, described below.

## SMELL #3, revisited: one transaction, four contexts, one rollback

`examples/00-monolith/SMELLS.md`'s smell #3 has been true from the start and
stayed true, unedited, all the way through ch.19: `place_order()`'s
synchronous path wraps the order row, the inventory reservation, the payment
charge, the shipping dispatch, and the outbox write inside one
`transaction.atomic()` block. ch.19 already showed what that buys automatically:
a `PaymentDeclined` three steps in unwinds the inventory decrement along
with everything else, because Postgres's own write-ahead log spans all of
it. It also showed what breaks the moment `Reserve` commits in a different
process's database. This chapter is about the other three contexts still left inside
that block in synchronous mode, and what happens to *all four* of ACID's
guarantees, not just the rollback, once payment and shipping leave too.

**Atomicity** is the "all or nothing" guarantee: every statement inside the
block commits together, or none of them do. **Consistency** is the
guarantee that a transaction moves the database from one valid state to
another: no order with items that reference a sku that was never reserved,
no payment recorded against an order that doesn't exist. **Isolation** is
the guarantee that a transaction's intermediate state is invisible to every
other transaction until it commits; nobody can see an order with a
reservation but no payment decision, because the database never exposes a
half-finished write. **Durability** is the guarantee that a committed
transaction survives a crash. `_place_order_local` gets all four for every
context it touches, and it gets them for the same reason every synchronous
monolith chapter in this book has gotten them: one process, one database,
one write-ahead log.

## The free rollback, proven, not asserted

ch.19 already measured this directly rather than asserting it: with
`INVENTORY_MODE=local`, a declined payment or a failed shipping dispatch
anywhere inside the atomic block rolls back the inventory decrement along
with the order row, and `GET /api/inventory/SKU-WIDGET-001` confirms
`quantityOnHand` never moved. That same direct-query discipline is what this chapter
reuses to prove the *opposite* claim for the choreographed path below. The
point of both measurements is the same: don't trust what a transaction
boundary promises until you've queried the actual state it's supposed to be
protecting.

## Why the free rollback cannot survive decomposition

The free rollback was never really "free"; it was Postgres doing
expensive, correct work (holding locks, maintaining a WAL, serializing
concurrent writers) that the monolith's architecture happened to make
invisible because every write stayed inside one database. The moment any
one of those writes needs to happen in a *different* process's database,
whether `Reserve` in inventory-service's own Postgres instance (ch.19), or a payment
capture in payment-service's own `payment` schema (this chapter), there is
no longer one write-ahead log spanning both writes, and nothing Postgres
does can undo a commit that already landed somewhere else. This is not a bug
in either service; it is what "service boundary" means at the data layer.
Every extraction in this book that moves a *write*, not just a read, pays
this cost exactly once, the moment that write starts landing in a schema the
original transaction doesn't own.

## ACD: what survives the cut, and what has to be rebuilt

`_place_order_choreographed` is where this book draws the line explicitly,
and the function's own docstring states the trade in one sentence: the
order, its items, and the outbox row stay inside one `transaction.atomic()`
block, per `"Deliberately NOT charging payment and NOT dispatching shipping"`,
and everything downstream of that commit happens outside this function and
this request entirely:

```python
# order/services.py -- _place_order_choreographed, the ACD-scoped transaction
def _place_order_choreographed(customer, items, payment_method, shipping_address):
    client = inventory_client.RemoteInventoryClient()
    try:
        line_snapshots, reserved = _reserve_lines_remote(client, items)
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    customer=customer, shipping_address=shipping_address,
                    status=Order.Status.PENDING,
                )
                for snapshot in line_snapshots:
                    OrderItem.objects.create(order=order, **snapshot_fields)
                order.total_cents = total_cents
                order.save(update_fields=["total_cents"])
                _write_order_placed_outbox_event(customer, order, payment_method=payment_method)
        except Exception:
            _release_reserved(client, reserved)
            raise
        return order
    finally:
        client.close()
```

Walk what each of ACID's four letters becomes once this function returns.
**Atomicity** survives for the smaller scope the `with transaction.atomic()`
block still covers: the order row, its items, and the outbox write commit
or roll back together, exactly as atomically as they always did.
**Consistency** survives too, in the sense that matters here: the committed
state (an order with valid, reserved line items and an outbox row recording
the fact) is a valid state, never a half-written one. **Durability**
survives unconditionally: once that `with` block exits normally, the
PENDING order is as durable as a CONFIRMED one ever was. What does *not*
survive is **Isolation**, and it does not survive by construction, not by
accident: the moment that smaller transaction commits, the PENDING order is
immediately visible to `GET /api/orders/{id}`, to every other transaction in
the database, to anything that queries it, hours before payment or
shipping have an opinion about whether that order will ever become
`CONFIRMED` at all. ACID's "I" becomes the gap ACD's name omits.

{% include excalidraw.html file="acid-to-acd-boundary" alt="What the single transaction.atomic() used to span versus what it spans now: Atomicity, Consistency, and Durability survive for a smaller scope; Isolation is gone for the gap outside it, where a PENDING order is visible and real before payment or shipping have resolved" caption="Figure 22.1: ACID → ACD: three letters kept, one traded for a window the saga has to manage explicitly" %}

**ACD** (Atomicity, Consistency, Durability, without Isolation) is not
this book inventing new vocabulary; it is the accurate name for what a saga
actually provides once no single transaction spans the whole business
operation. The isolation a shared transaction used to provide automatically has to be
replaced by something, and what replaces it is not a stronger lock or a
cleverer transaction. It's compensation: an explicit, code-level mechanism
that detects a bad outcome *after* the fact and undoes its visible effects,
rather than a database mechanism that prevents the bad outcome from ever
being observed in the first place. `order.services.handle_payment_declined`
and `handle_payment_captured`'s `ShippingFailed` branch, both covered in
full in ch.23, are that mechanism for this chapter's seam: there is no
longer a transaction boundary doing this work, only a listener reacting to
an event and a status-transition guard making sure it reacts exactly once.

## The isolation anomalies this book never had to name before

A reader who has only ever worked against a single-database, fully-ACID
system may never have had to name these anomalies, because a correctly
configured transaction isolation level in Postgres prevents every one of
them *inside* one database. They matter here precisely because
the saga reintroduces versions of all three across the service boundary,
and knowing which one you're looking at is what tells you whether a given
behavior is a bug or the documented cost of this chapter.

**A dirty read**, classically, is reading another transaction's uncommitted
write. The cross-service analog here is reading a PENDING order and
mistaking it for a settled fact: every `GET /api/orders/{id}` call made
during the window this chapter names is reading a row that is fully
committed (never literally dirty, in the database sense) but whose business
meaning is still unresolved. A caller that doesn't know to treat PENDING as
provisional is making the same mistake a dirty read protects against inside
one database, just one layer up the stack.

**A lost update** is two concurrent writers each overwriting the other's
change without either seeing the other's write. ch.19's `Reserve`
conditional `UPDATE` already closed this hole for the inventory decrement
itself (two concurrent `Reserve` calls for the last unit of stock never both
succeed, proven by the concurrency test cited in that chapter). The
anomaly this chapter's saga has to guard against instead is a *redelivered*
event causing a second, unwanted write: a `payment.declined` event consumed
twice driving `_release_order_lines` twice. That is why `_is_pending`'s
status-transition guard and inventory-service's `idempotency_key` ledger
both exist, and ch.23 proves both live.

**A non-repeatable read** is reading the same row twice in one transaction
and getting two different answers because another transaction committed a
change in between. There is no single transaction spanning the PENDING
window for this to happen *inside*, which is exactly the point: a client
that polls `GET /api/orders/{id}` twice, five seconds apart, during this
chapter's window can legitimately see `PENDING` and then `CONFIRMED`, and
that is not a bug to fix, it's the entire observable shape of the
consistency model this chapter names. The equivalence suite's bounded-wait
poll (ch.23) is built around exactly this fact: it expects the status to
change between polls, and treats a status that *never* changes within the
budget as the failure.

{% include excalidraw.html file="order-pending-to-terminal-lifecycle" alt="PENDING's three idempotent terminal exits (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) plus the documented stuck-PENDING failure mode a bounded-wait poll catches" caption="Figure 22.2: The state machine ACD introduces: three protected exits, and one clearly-named failure mode" %}

## CAP, PACELC, and what "correctness" means now

It is worth being precise about which well-known theorem this chapter is and
isn't invoking. CAP is a statement about a single replicated data store
under a network partition; it does not directly describe two *different*
services, each with its own database, coordinating a business process over
an asynchronous message broker. What the payment extraction actually
demonstrates is closer to the practical generalization PACELC makes
explicit: even *without* a partition, a system has to choose between
Latency and Consistency for every operation that could otherwise wait for a
remote answer. `PAYMENT_MODE=synchronous` chose consistency's stronger
form: a caller never sees an order until its truly final state is known,
at the cost of the entire request blocking on payment and shipping.
`PAYMENT_MODE=choreographed` chose the opposite: checkout returns in
milliseconds, after only the local work it can actually guarantee, and the
caller trades a synchronous terminal answer for a window of eventual
consistency it has to be told about explicitly, which is exactly why
ch.23's contract change moves the HTTP status code, not just an internal
implementation detail. "Correctness" under ACD does not mean "the database
never shows an inconsistent state"; it means "every state the database
does show is a state the system's own rules say is valid to be in,
including PENDING," and "every transition out of that state happens exactly
once, no matter how many times the event that triggers it is redelivered."

## Three extractions, three different answers

It is worth placing this chapter's trade next to the two extractions that
came before it, because the three together are the clearest evidence that
"give up isolation" is not a blanket policy this book applies everywhere;
it's a cost paid only where a synchronous answer is structurally impossible.
Review (ch.15) never touched a write at all; there was no transaction to
shrink. Notification (ch.17) moved a side effect that checkout's own
response never depended on: the outbox write happens inside the unchanged
transaction, and nothing about `201 Created`'s timing or meaning changed
when Notification left. Inventory (ch.19) moved a write checkout *does*
depend on, but kept the synchronous answer by compensating inline, inside
the same request, before responding; the caller still gets a terminal
`201`/`402`/`409`/`422` in one round trip, just reconstructed by explicit
compensation instead of a free rollback. Payment (this chapter, ch.23) is
the first extraction where the write structurally cannot resolve inside the
request at all, because the entity that has to decide, payment-service
reacting to a Kafka event it hasn't received yet, doesn't exist in this
process's call stack. That structural fact, not a preference for weaker
guarantees, is what forces the move from ACID to ACD.

## The real cost: the window, and the gap the choreographed path does not close

Two costs deserve naming directly rather than folded into the general
argument above, because both are measured facts about this iteration, not
hypothetical risks.

**The PENDING window itself** is real, observable latency, not a rounding
error. `tooling/newman/GOLDEN-BASELINE.md`'s cutover lane measured
Scenario 1's happy-path order resolving to `CONFIRMED` on the bounded-wait
poll's **attempt 2/20**: a real multi-hundred-millisecond round trip
through Kafka, payment-service, and back through the saga listener, not an
instant resolve a canned test might produce. A production deployment under
this mode has to design its UI, its caching, and its downstream integrations
for an order that is persisted and visible for a measurable span of
wall-clock time before its payment outcome is known.

**The stranded-payment gap is a named deferral, not a silent
bug.** `handle_payment_captured`'s `ShippingFailed` branch issues a
compensating gRPC `Release` for the reserved inventory and marks the order
`SHIPPING_FAILED`, but the payment that already captured is **not
refunded**, because payment-service exposes no Refund RPC or event yet.
The function's own docstring states this without hedging: "a payment that
captured and then hits `ShippingFailed` here is NOT refunded... That is
the orchestrated saga's job, once shipping itself is extracted." This is
precisely the kind of gap this book's scope discipline argues *for* naming
rather than quietly engineering around with speculative Refund
infrastructure a week before the chapter that would actually use it. It
is also the motivating example ch.24 needs: an orchestrated saga, with a
central coordinator that can issue a second compensation hop, is the shape
that closes this exact gap. ACD's real cost here is not just "isolation
is gone"; it's "a captured payment can, for now, outlive the order it paid
for," and the next part of this book exists to fix that.

> **ADLC in Action**: The decision to accept this gap rather than build a
> Refund mechanism ahead of schedule was made at the planning gate, not
> discovered mid-implementation: the build plan's user-gate
> named both options explicitly (ship a stranded payment and defer the fix,
> or keep shipping synchronous and dodge the problem for one more
> iteration) and the approved decision, Option A, is
> the one this chapter describes. Naming the deferral as a *decision*,
> with a reason and a target chapter, rather than letting it surface later
> as an unexplained TODO, is what the standing decisions ledger is for.

## What you learned

- ACID's four guarantees don't fail together when a transaction shrinks to
  cross a service boundary: Atomicity, Consistency, and Durability survive
  for whatever scope the remaining local transaction still covers; Isolation
  is the one that is structurally impossible to keep once two different
  services, each with their own database, both have to agree on an outcome.
- The free rollback ch.19 proved and then lost was never "free"; it was
  Postgres's own locking and WAL doing real work the monolith's single-process
  architecture made invisible; the moment a write lands in a different
  database, that invisible work has to be rebuilt by hand as explicit
  compensation.
- Classic isolation anomalies (dirty reads, lost updates, non-repeatable
  reads) reappear in cross-service form once the saga replaces the
  transaction: a PENDING order is a committed-but-provisional read; a
  redelivered event is the saga's version of a lost update; a status that
  legitimately changes between two polls is the saga's version of a
  non-repeatable read, and the equivalence suite is built to expect it.
- PACELC, not CAP, is the right lens for what the choreographed path actually traded: without
  any network partition, `PAYMENT_MODE=synchronous` chose consistency's
  stronger form at the cost of blocking the whole request; `choreographed`
  chose latency, at the cost of an explicitly-contracted eventual-consistency
  window the caller is told about via the HTTP status code itself.
- This book pays the ACID-to-ACD cost only where a synchronous answer is
  structurally impossible: Review and Notification never had to, Inventory
  kept the synchronous contract by compensating inline, and Payment is the
  first extraction where the deciding party doesn't exist yet in
  the request's own call stack.
- The stranded-payment-on-ship-fail gap is a named, ledgered deferral,
  not a silent defect; it is the exact motivating problem
  ch.24's orchestrated shipping saga exists to close.

Next: ch.23 builds the mechanism that lives inside the window this chapter
just named: the choreographed saga itself, the event topology that
replaces the transaction, and the proof that the equivalence suite stays
sound across a contract it can no longer verify in a single round trip.
