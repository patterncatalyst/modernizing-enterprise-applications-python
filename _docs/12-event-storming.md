---
title: "Event Storming the Monolith"
order: 12
part: "Finding the Seams"
description: "Event storming finds seams from behavior instead of schema, and the finished wall becomes the decomposition backlog."
---

## Learning objectives

By the end of this chapter you can:

- Explain why event storming finds seams from a timeline of past-tense domain events instead of from schema, and what schema hides.
- Apply the color grammar (domain event, command, actor, aggregate, policy, read model, external system) in the order a session introduces it.
- Choose the right altitude (big-picture, process-level or design-level) for the question being asked.
- Run a process-level storm of checkout and produce its six-event timeline: `OrderPlaced`, `StockReserved`, `PaymentCaptured`/`PaymentDeclined`, `ShipmentDispatched`, `OrderConfirmed`, `NotificationSent`.
- Catch the gap a straight code read misses: the single `order.placed` outbox write at the end of checkout can carry the `OrderConfirmed` fact under the `OrderPlaced` name.
- Map each event boundary to the extraction that cuts it: inventory's gRPC anti-corruption layer, payment's choreographed saga, shipping's orchestrated saga, notification's outbox.
- Recognize that a finished wall answers where a seam is, not in what order to cut.

## Why this matters

Naming boundaries correctly makes extraction mechanical instead of archaeological, but it doesn't say how to find boundaries in a system that never wrote them down. Event storming does: it narrates what a system does, the facts it produces in the order it produces them, instead of reading its schema, model graph or app layout. Applied to `examples/00-monolith/`, it turns one paragraph ("a customer places an order, we check stock, charge the card, ship the box, and tell them") into a timeline of domain events whose gaps are the seams to cut along.

Each event name below is either a live constant in `config/settings.py` or the natural companion to one, and the calls come from `order/services.py::_place_order_local`.

{% include excalidraw.html file="event-storm-checkout" alt="Two stacked readings of the checkout flow: the top band shows today's _place_order_local as one synchronous call chain inside a single transaction.atomic() across inventory, payment, and shipping, ending in an outbox write already cured for notification; the bottom band shows the same business process re-read with the event-storming grammar: an actor and command producing an Order aggregate, a timeline of domain events (OrderPlaced, StockReserved, PaymentCaptured or PaymentDeclined, ShipmentDispatched, OrderConfirmed, NotificationSent) separated by policies and reactions, an external payment gateway, and an Order Status read model fed by the events." caption="Figure 12.1: The checkout flow, read two ways: one call chain today, a timeline of domain events once it's event-stormed" %}

## Why behavior beats schema for finding seams

A monolith carries an unofficial map of itself in its tables, foreign keys and import graph. It is concrete, queryable and easy to generate, and it is the wrong map for deciding where to cut. `order/models.py` shows that `OrderItem` once held a foreign key into `InventoryItem`. It doesn't say whether the business cared about that relationship or one developer found it the cheapest way to say "these rows are related." Schema encodes decisions without their reasons, and the reasons separate a critical boundary from an accidental one.

Event storming, introduced by Alberto Brandolini, asks instead what happened, in what order, and who or what made it happen. A session starts with a long roll of paper (or a shared document) and orange sticky notes. The first-pass rule is to write each domain event as a past-tense fact someone in the business would recognize: `OrderPlaced`, `StockReserved`, `PaymentDeclined`. Not `place_order()` and not `UPDATE orders SET status = ...`. Because naming what happened needs no knowledge of the code, domain experts and engineers can timeline a checkout in twenty minutes. You need to have used, sold or supported the system, not read `order/services.py`.

Seams surface from the outside in. A bounded-context boundary is where vocabulary changes: "reserve" stops meaning "decrement a quantity column" and starts meaning "authorize a charge," or "confirm" stops describing an order's status and starts describing a message reaching an inbox. In the timeline each shift is where one sticky hands off to a different actor, external system or team. The schema hides those shifts: a shared Postgres instance makes every app's tables look like equal neighbors, FK joins included.

> **ADLC in Action**: The wall is a Map-phase artifact, produced before an agent generates any extraction code. A human-facilitated session with sticky notes and an agent narrating a known code path onto a structured timeline are the same technique at two scales, and either yields a sequence of named facts handed to the Plan phase. Each extraction starts by re-reading its slice of the wall instead of re-deriving it from the code: reconnaissance done once and reused by every later phase.

The timeline needs no new tooling. It is prose and a diagram.

## The grammar of a session

Colors are added in a purposeful order; each answers a question the previous pass left open.

| Note | Color | Answers | In checkout |
|---|---|---|---|
| Domain event | Orange | What happened? | `OrderPlaced` |
| Command | Blue | What triggered it? | `PlaceOrder`, `CapturePayment` |
| Actor | Yellow figure | Who or what issued it? | Customer |
| Aggregate | Large yellow | Where is the invariant checked? | `Order`, `InventoryItem` |
| Policy | Lilac | Whenever X, then what? | Whenever `OrderPlaced`, issue `ReserveStock` |
| Read model | Green | What view do events feed? | `Order Status` |
| External system | Pink | What is outside our control? | Card network, carrier API |

**Domain events** come first, as chaotic exploration: every fact, out of order, duplicated, contradicted. The goal is coverage. Lining them into a timeline is the first modeling act, and disagreements about order surface the hidden assumptions a single ACID transaction has been enforcing unnoticed.

**Commands** come next, one per event. One command can produce either of two events: `CapturePayment` yields `PaymentCaptured` or `PaymentDeclined`, a branch invisible in the orange-only pass.

**Actors** may be a customer, a scheduled job, a gateway webhook or a policy reacting to an earlier event. The actor says which seam needs an authenticated human-facing route and which a background consumer on an internal topic.

**Aggregates** come from grouping each command and event pair: which cluster of data had to exist, enforce an invariant and decide whether the command was valid. `Order` decides whether `PlaceOrder` is well-formed; `InventoryItem` decides whether `ReserveStock` can succeed. The boundary found this way is a behavioral claim that can be checked independently of the tactical-DDD aggregate boundaries.

**Policies** chain events to the next command with no human in the loop. A policy sticky is the shape a message consumer takes once the system is distributed, and one step of a choreographed saga.

**Read models** are views projected from events. "What's the status of order #4412" needs an `Order Status` read model fed by several events, not a live join across apps on every question.

**External systems** are boxes outside the team's control. Naming them stops a session from assuming every collaborator is as fast and reliable as an in-process call, which is exactly what `_place_order_local` assumes today for inventory, payment and shipping.

{% include excalidraw.html file="event-storming-legend" alt="A seven-row legend card listing the event-storming note types in the order a session introduces them: domain event (orange sticky, a past-tense fact, e.g. OrderPlaced), command (blue sticky, the imperative that triggered it, e.g. Place Order), actor (small yellow figure left of its command, e.g. Customer), aggregate (large yellow sticky, the data cluster enforcing an invariant, e.g. Order), policy/reaction (lilac sticky, 'whenever X then issue command Y', no human actor), read model (green sticky, a view projected forward from events, e.g. Order Status), and external system (pink sticky, outside the team's control, e.g. the Payment Gateway stand-in). Each row also names the diagram box type that stands in for the sticky color." caption="Figure 12.2: The event-storming note types, in the order a session introduces them" %}

Three altitudes, and conflating them produces a wall too shallow to act on or too narrow to show the seams:

| Altitude | Scope | Output |
|---|---|---|
| Big-picture | A whole business, orange-only | Candidate bounded contexts; places where one word means two things |
| Process-level | One process end to end, full grammar | The decomposition backlog |
| Design-level | Inside one aggregate | Exact commands, validation rules and events, handing off to tactical DDD |

Checkout is a process-level storm.

## Storming checkout

The opening is the easiest sticky: a **Customer** issues **Place Order** with a customer id, a shipping address and line items, the payload `OrderCreateSerializer` validates for `POST /api/orders`. The **Order** aggregate accepts it and the first event goes up, **OrderPlaced**, already a live constant:

```python
# config/settings.py
ORDER_PLACED_TOPIC = "order.placed"
```

The next policy is *whenever OrderPlaced, then reserve stock*, and here a storm names what a code read blurs. `_place_order_local` persists the `Order` as `PENDING`, then reserves each line:

```python
# order/services.py::_place_order_local
order = Order.objects.create(customer=customer, shipping_address=shipping_address,
                              status=Order.Status.PENDING)
for line in items:
    inventory_item = inventory_services.get_by_sku(line["sku"])
    inventory_services.reserve(line["sku"], line["quantity"])  # InsufficientStock, no writes yet
    OrderItem.objects.create(order=order, sku=inventory_item.sku, ...)
```

The business order is right: the intent to buy is persisted before any reservation. But no event fires when the `Order` row commits. The only thing the function publishes is one `order.placed` outbox row, written at the end after payment has captured and shipping has dispatched, when the payload may already read "confirmed" (`_write_order_placed_outbox_event` sets `confirmed = order.status == Order.Status.CONFIRMED` and picks the verb from it). The wall needs two stickies where the code has one: **OrderPlaced** right after the `Order` row commits, and **OrderConfirmed** at checkout's real end. A code read in call-stack order papers over that.

**StockReserved** is named nowhere today; "stock reserved" is indistinguishable from "a function returned without raising." `InsufficientStock` is raised before any row is updated, so a failed reservation needs no rollback. Synchronous validation is standing in for an asynchronous reaction to a fact.

*Whenever StockReserved, then capture payment* is issued to an **external system**, the card network, drawn pink so "what if this is slow, down or ambiguous" gets asked out loud. One command, two events:

```python
# payment/services.py
DECLINE_SENTINEL = "DECLINE"

def charge(order, amount_cents: int, method: str) -> Payment:
    """SMELL[ch.22]/[ch.26]: called synchronously, in-process, from
    order.services.place_order(), inside the SAME transaction.atomic() as
    the inventory reservation. A decline raised here rolls back everything
    written so far in that same local transaction."""
    if DECLINE_SENTINEL in method.upper():
        raise PaymentDeclined(f"Payment method '{method}' was declined")
```

**PaymentCaptured** and **PaymentDeclined** are separate orange stickies off one blue command. The facilitator's question at this point is "when payment is declined, what undoes the stock reservation?" The monolith's answer is "nothing has to; `transaction.atomic()` rolls back by default." The wall states that smell out loud, and it finds the question whose answer, "the database handles it," stops being true once either side of a seam has its own database. Every remaining extraction depends on that premise.

A captured payment triggers dispatch, which `shipping.services.dispatch` performs synchronously and in-transaction, producing **ShipmentDispatched** (`SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"`). The last policy, *whenever ShipmentDispatched, then notify customer*, differs from the rest because the code already matches the wall. `order/services.py` writes one `OutboxEvent` row and returns; nothing notification-shaped runs in the checkout path. **NotificationSent**, the event of a message leaving the system, happens later and independently, driven by `notification.management.commands.order_placed_consumer` once a relay publishes the outbox row. Storming this policy surfaces no gap, only a cure already shipped: the behavioral seam was cut inside the monolith, where being wrong was cheapest, before notification became deployable.

The wall's one green sticky, **Order Status**, is fed by `OrderPlaced`, `PaymentCaptured`, `ShipmentDispatched` and `OrderConfirmed`: the projection a "where's my order" screen needs, built by folding events forward.

## From the wall to the backlog

Read left to right, a finished process-level wall is the decomposition backlog. Each place where a policy's reaction crosses into another context's module as a Python function call is a synchronous call today and a published event once the boundary is cut.

| Event boundary | Seam | Mechanism |
|---|---|---|
| `OrderPlaced` to `StockReserved` | Inventory | gRPC contract and the `RemoteInventoryClient` anti-corruption layer, plus a CDC backfill |
| `StockReserved` to `PaymentCaptured`/`PaymentDeclined` | Payment | Choreographed saga: the policy sticky becomes, almost unchanged, an aiokafka consumer reacting to `order.placed` |
| `PaymentCaptured` to `ShipmentDispatched` | Shipping | Orchestrated saga: one FastAPI coordinator sequences the steps |
| `ShipmentDispatched` to `OrderConfirmed`/`NotificationSent` | Notification | Transactional outbox, already cut behaviorally, completed as a standalone service |

{% include excalidraw.html file="storm-wall-to-backlog" alt="A four-row table mapping each event boundary the storm found to its extraction mechanism: OrderPlaced to StockReserved (inventory) uses a gRPC proto as anti-corruption layer plus a CDC backfill; StockReserved to PaymentCaptured or PaymentDeclined (payment) uses a choreographed saga via an aiokafka consumer; PaymentCaptured to ShipmentDispatched (shipping) uses an orchestrated saga with a single FastAPI coordinator; ShipmentDispatched to OrderConfirmed and NotificationSent (notification, cut first behaviorally) uses a transactional outbox. A footnote says order/services.py::place_order() is cut last, after all four boundaries already fire events." caption="Figure 12.3: From the storm wall to the extraction backlog, with each boundary and its mechanism" %}

`place_order()` is not one box on the wall. It issues the triggering command of every policy in the flow, calling reserve, capture and dispatch directly and synchronously, all but one edge inside one transaction. A function in that many command-issuing positions can't be extracted until each has been rewired to fire an event instead of a direct call. That is why order is extracted last, after each of the other boundaries is cut.

The wall says where a boundary exists, not which order is safest. Notification jumped the queue on behavior but is still extracted second as a service, which the wall can't explain, because "where" and "in what order" are measured by different things. Ordering needs coupling analysis: of several candidate seams, which has the least coupling pulling against it, and which has a blast radius small enough to cut first. Each cut is then gated the same way: the behavior-equivalence suite runs against both the monolith and the extracted service before the old code path stops seeing live traffic.

> **Decision**
>
> Find seams from behavior, not schema: storm the process, put one sticky per business fact, and treat every place a policy calls another context's module directly as a candidate seam. Use the wall to decide where to cut and coupling analysis to decide when.

> **🤖 Explore with your agent**
>
> "Read `_place_order_local` in `examples/00-monolith/order/services.py` and produce an event-storming timeline of checkout as a table of event, triggering command, actor, aggregate and the policy that follows. Mark every direct cross-context call as a candidate seam, and say whether the `order.placed` outbox row is written at the OrderPlaced or the OrderConfirmed moment."
>
> Check: the reply should name six events, flag that the outbox row is written at checkout's end and can carry the `OrderConfirmed` fact under the `order.placed` name, and list inventory, payment and shipping as synchronous seams with notification already cured.
