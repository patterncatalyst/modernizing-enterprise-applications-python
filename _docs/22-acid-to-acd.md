---
title: "ACID to ACD: Living Without Isolation"
order: 22
part: "Data Across the Seam"
description: "The consistency given up when a transaction shrinks: dirty reads, lost updates and non-repeatable reads across services, where they bite, and the real cost of checkout's 201 to 202 change."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- State SMELL #2 precisely: one `transaction.atomic()` block in `order/services.py::place_order` spans order, inventory, payment and shipping, and rolls back atomically only because Postgres does it for you.
- Explain why that rollback cannot survive decomposition once a write lands in another service's database.
- Define ACD (Atomic locally, Consistent, Durable, isolation dropped) and say what `_place_order_choreographed` keeps inside its smaller transaction and what it gives up.
- Explain a compensating action (`handle_payment_declined`, the `ShippingFailed` branch of `handle_payment_captured`) as a hand-written, forward-moving reaction, not a rollback.
- Recognize the dirty read, lost update and non-repeatable read in their cross-service forms, and say why inventory's reservation stays synchronous while payment gets a saga.
- Treat the stranded-payment gap as a ledgered deferral, not a silent defect.

## Why this matters

Earlier extractions cost something bounded and local: a slower cold start, a second schema, a proto contract to keep in sync. Moving inventory cost a free rollback, rebuilt by hand with an explicit compensating `Release`. Payment costs more: the consistency model checkout runs under changes, not just the mechanism behind it.

`PAYMENT_MODE=synchronous` still runs full ACID, unchanged. `PAYMENT_MODE=choreographed` runs on something weaker and more precise about what a distributed system can promise. The code is in `examples/00-monolith/order/services.py` (`_place_order_local` versus `_place_order_choreographed`) and `examples/00-monolith/order/models.py` (`Order.Status`). Nothing new runs for this idea; both dispatch paths are already exercised by the cutover lanes in `tooling/newman/GOLDEN-BASELINE.md`.

## SMELL #2: one transaction, four contexts, one rollback

Smell #2 in `examples/00-monolith/SMELLS.md` has stayed true from the start: the synchronous `place_order()` wraps the order row, the inventory reservation, the payment charge, the shipping dispatch and the outbox write in one `transaction.atomic()` block. A `PaymentDeclined` three steps in unwinds the inventory decrement with everything else, because Postgres's write-ahead log spans all of it. With `INVENTORY_MODE=local`, `GET /api/inventory/SKU-WIDGET-001` confirms `quantityOnHand` never moved after a decline or a failed dispatch.

Each letter of ACID is a separate promise:

| Letter | Guarantee |
|---|---|
| Atomicity | Every statement in the block commits together, or none do. |
| Consistency | The database moves from one valid state to another. No order references a SKU that was never reserved. |
| Isolation | Intermediate state is invisible to other transactions until commit. Nobody sees an order with a reservation and no payment decision. |
| Durability | A committed transaction survives a crash. |

`_place_order_local` gets all four for every context it touches, for one reason: one process, one database, one write-ahead log.

## Why the free rollback cannot survive decomposition

The rollback was never free. Postgres held locks, kept a log and serialized writers, and the monolith made that work invisible because every write stayed in one database. Once a write lands in a different process's database, whether `Reserve` in inventory-service or a capture in payment-service's `payment` schema, no single log spans both writes, and nothing Postgres does can undo a commit that already landed elsewhere. That is what a service boundary means at the data layer. Every extraction that moves a write pays this cost once, the moment the write leaves the schema the original transaction owns.

## ACD: what survives the cut

`_place_order_choreographed` draws the line explicitly. The order, its items and the outbox row stay in one `transaction.atomic()` block; the docstring says it does not charge payment or dispatch shipping, and everything downstream happens outside the function and the request.

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

Here is what each letter becomes:

- **Atomicity** survives for the smaller scope: order row, items and outbox write commit or roll back together.
- **Consistency** survives: the committed state, an order with valid reserved line items and an outbox row recording the fact, is never half-written.
- **Durability** survives unconditionally: once the `with` block exits, the `PENDING` order is as durable as a `CONFIRMED` one.
- **Isolation** does not survive, by construction. The moment the smaller transaction commits, the `PENDING` order is visible to `GET /api/orders/{id}` and every other transaction, before payment or shipping has an opinion about whether it will ever be `CONFIRMED`.

{% include excalidraw.html file="acid-to-acd-boundary" alt="What the single transaction.atomic() used to span versus what it spans now: Atomicity, Consistency, and Durability survive for a smaller scope; Isolation is gone for the gap outside it, where a PENDING order is visible and real before payment or shipping have resolved" caption="Figure 22.1: ACID to ACD, three letters kept and one traded for a window the saga has to manage" %}

**ACD** is the accurate name for what a saga provides once no single transaction spans the business operation. What replaces isolation is not a stronger lock but compensation: code that detects a bad outcome after the fact and undoes its visible effects, instead of a database mechanism that prevents the bad outcome from being observed. `order.services.handle_payment_declined` and the `ShippingFailed` branch of `handle_payment_captured` are that mechanism. No transaction boundary does this work any more, only a listener reacting to an event and a status-transition guard making it react exactly once.

## The isolation anomalies, across a service boundary

A correctly configured isolation level prevents all three inside one database. The saga reintroduces versions of each across services, and naming them tells you whether a behavior is a bug or the documented cost.

**Dirty read.** Classically, reading another transaction's uncommitted write. Here, `GET /api/orders/{id}` during the window returns a fully committed row whose business meaning is unresolved. A caller that treats `PENDING` as settled makes the mistake isolation used to prevent, one layer up.

**Lost update.** Two writers overwrite each other. The inventory `Reserve` conditional `UPDATE` already closes this for the decrement: two concurrent calls for the last unit never both succeed. The saga's version is a redelivered `payment.declined` event driving `_release_order_lines` twice. The `_is_pending` status-transition guard and inventory-service's `idempotency_key` ledger exist for this.

**Non-repeatable read.** The same row read twice returns two answers. No single transaction spans the window, so a client polling `GET /api/orders/{id}` five seconds apart can legitimately see `PENDING` and then `CONFIRMED`. That is the observable shape of the model, not a bug. A bounded-wait poll expects the status to change and treats a status that never changes within the budget as the failure.

{% include excalidraw.html file="order-pending-to-terminal-lifecycle" alt="PENDING's three idempotent terminal exits (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) plus the documented stuck-PENDING failure mode a bounded-wait poll catches" caption="Figure 22.2: The state machine ACD introduces, with three protected exits and one named failure mode" %}

## CAP, PACELC and what correctness means now

CAP describes one replicated store under a partition. It does not describe two services with their own databases coordinating over a broker. PACELC fits better: even without a partition, an operation that could wait for a remote answer must choose between latency and consistency.

- `PAYMENT_MODE=synchronous` chooses consistency. The caller never sees an order until its final state is known, and the request blocks on payment and shipping.
- `PAYMENT_MODE=choreographed` chooses latency. Checkout returns in milliseconds after only the local work it can guarantee, and the caller trades a terminal answer for an eventual-consistency window it is told about through the HTTP status code.

Correctness under ACD means every state the database shows is valid under the system's rules, including `PENDING`, and every transition out of it happens exactly once however often its triggering event is redelivered.

## Three extractions, three answers

Giving up isolation is not blanket policy. It is paid only where a synchronous answer is structurally impossible.

| Extraction | Write checkout depends on? | Outcome |
|---|---|---|
| Review | No write at all | No transaction to shrink. |
| Notification | Side effect only | The outbox write stays in the unchanged transaction; `201 Created` keeps its timing and meaning. |
| Inventory | Yes | Synchronous answer kept by compensating inline; the caller still gets a terminal `201`, `402`, `409` or `422` in one round trip. |
| Payment | Yes | The deciding party, payment-service reacting to a Kafka event it has not received yet, is not in this request's call stack, so the answer cannot be synchronous. |

## The real cost

**The `PENDING` window is real latency.** The cutover lane in `tooling/newman/GOLDEN-BASELINE.md` measured Scenario 1's happy-path order reaching `CONFIRMED` on poll **attempt 2/20**, a multi-hundred-millisecond round trip through Kafka, payment-service and the saga listener. A deployment in this mode must design its UI, caching and downstream integrations for an order that is persisted and visible for a measurable span before its payment outcome is known.

**The stranded-payment gap is a named deferral.** The `ShippingFailed` branch of `handle_payment_captured` issues a compensating gRPC `Release` and marks the order `SHIPPING_FAILED`, but a payment that already captured is not refunded, because payment-service has no Refund RPC or event yet. The docstring says so: refunding is "the orchestrated saga's job, once shipping itself is extracted." A captured payment can, for now, outlive the order it paid for. An orchestrated saga with a coordinator that can issue a second compensation hop is the shape that closes it.

> **ADLC in Action**: The gap was accepted at the planning gate, not discovered mid-build. The plan named both options, ship a stranded payment and defer the fix, or keep shipping synchronous and dodge the problem for one more iteration, and the approved decision was the first. Recording the deferral as a decision, with a reason and a target, rather than an unexplained TODO, is what the standing decisions ledger is for.

> **Decision**
>
> Give up isolation only where the answer cannot be synchronous. Keep the transaction (or inline compensation) when the deciding party is inside the request, and accept `PENDING` plus compensation when it is not. Every dropped guarantee needs a named window and a named gap.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith/order/services.py`, compare `_place_order_local` with `_place_order_choreographed`. List which of Atomicity, Consistency, Isolation and Durability each keeps, then find every place a client could observe a `PENDING` order and say whether it treats `PENDING` as provisional."
>
> Check: the reply names the `with transaction.atomic()` scope in `_place_order_choreographed`, and every `GET /api/orders/{id}` consumer it flags can be traced in `order/views.py`.

## Build, run, observe

Nothing new to start. Run `demos/demo-payment-cutover.sh` to bring up the full topology with the monolith in `PAYMENT_MODE=choreographed`, run the Newman suite through the strangler proxy, and tear everything down.

- Poll `GET /api/orders/{id}` right after checkout: the status moves from `PENDING` to `CONFIRMED`, and Scenario 1 resolves on attempt 2/20.
- Query `GET /api/inventory/SKU-WIDGET-001` after a decline in `INVENTORY_MODE=local`: `quantityOnHand` is unchanged, the free rollback at work.
- Check out with a `SHIP-FAIL` shipping address in the choreographed path: stock is released and the order is `SHIPPING_FAILED`, but the captured payment is not refunded.
