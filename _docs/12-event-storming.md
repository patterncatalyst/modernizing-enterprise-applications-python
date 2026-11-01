---
title: "Event Storming the Monolith"
order: 12
part: "Finding the Seams"
description: "Discovering seams from behavior, not schema; the decomposition backlog this produces, run as an ADLC reconnaissance step."
---

## Learning objectives

By the end of this chapter you can:

- Explain why event storming finds seams from behavior (a timeline of past-tense domain events) rather than from schema, and what schema hides that behavior reveals.
- Name and apply the event-storming color grammar (domain event, command, actor, aggregate, policy/reaction, read model, external system) in the order a real session introduces each one.
- Distinguish the three storming altitudes (big-picture, process-level, design-level) and explain why conflating them produces a wall that's either too shallow or too narrow to act on.
- Run a process-level storm of the checkout flow and produce its six-event timeline: `OrderPlaced`, `StockReserved`, `PaymentCaptured`/`PaymentDeclined`, `ShipmentDispatched`, `OrderConfirmed`, `NotificationSent`.
- Explain how storming catches a gap a straight code read misses: `_place_order_local`'s single `order.placed` outbox write, fired at the end of checkout, sometimes carries the `OrderConfirmed` fact under the `OrderPlaced` name.
- Map each event-boundary gap on the wall to the specific extraction chapter and mechanism that cuts it (inventory's gRPC anti-corruption layer in ch.19, payment's choreographed saga via an aiokafka consumer in ch.23, shipping's orchestrated saga in ch.24, notification's transactional outbox already cured).
- Explain why a finished wall only answers *where* a seam is, not *in what order* to cut it, setting up Chapter 13's coupling analysis.

## Why this matters

Chapter 11 gave you the vocabulary (subdomain, bounded context, aggregate,
ubiquitous language) and the promise that goes with it: if you can name the
boundaries correctly, extraction becomes mechanical instead of
archaeological. What it didn't give you is a *method* for finding those
boundaries in a system that never wrote them down. This chapter is that
method. Event storming is a facilitation technique for discovering bounded
contexts and aggregates by narrating what a system actually *does*, the
facts it produces, in the order it produces them, rather than by reading
its schema, its model graph, or its app layout. Applied to
`examples/00-monolith/`, it turns one paragraph of prose ("a customer places
an order, we check stock, charge the card, ship the box, and tell them")
into a timeline of domain events whose gaps are exactly the seams the next
chapters cut along.

The code is in `examples/00-monolith/`; nothing new has been scaffolded for
this chapter. Every event name below either already exists as a live
constant in `config/settings.py` or is the natural companion this chapter
adds to that set, and every call this chapter storms is quoted verbatim from
`order/services.py::_place_order_local`, the same function Chapter 9
tagged with most of its remaining smells.

{% include excalidraw.html file="event-storm-checkout" alt="Two stacked readings of the checkout flow: the top band shows today's _place_order_local as one synchronous call chain inside a single transaction.atomic() across inventory, payment, and shipping, ending in an outbox write already cured for notification; the bottom band shows the same business process re-read with the event-storming grammar: an actor and command producing an Order aggregate, a timeline of domain events (OrderPlaced, StockReserved, PaymentCaptured or PaymentDeclined, ShipmentDispatched, OrderConfirmed, NotificationSent) separated by policies and reactions, an external payment gateway, and an Order Status read model fed by the events." caption="Figure 12.1: The checkout flow, read two ways: one call chain today, a timeline of domain events once it's event-stormed" %}

## Why behavior beats schema for finding seams

Every monolith accumulates a second, unofficial map of itself: the one
implied by its tables, its foreign keys, and its import graph. That map is
seductive because it's concrete: you can query it, diagram it, even
generate it automatically, and it is also, reliably, the wrong map to use
when you're deciding where a system should be cut. `order/models.py` tells
you `OrderItem` once held a direct foreign key into `InventoryItem`. It does
not tell you *why* that relationship existed, whether it reflected something
the business actually cared about or just the cheapest way one developer
found to express "these rows are related," or whether it was one of this
book's deliberate smells rather than a real invariant. Schema is
implementation residue. It encodes decisions, but it doesn't encode the
decisions' reasons, and reasons are exactly what you need to tell a critical
boundary from an accidental one.

Event storming, a facilitation technique introduced by Alberto Brandolini,
inverts the question. Instead of "what tables exist and how are they
joined," it asks "what *happened*, in what order, and who or what made it
happen." A session starts with nothing but a long roll of paper (or, in an
ADLC context, a shared document) and a pile of orange sticky notes, and the
only rule for the first pass is: write down a domain event, a fact, named
in the past tense, that someone in the business would recognize and care
about, every time one occurs in the story you're narrating. `OrderPlaced`.
`StockReserved`. `PaymentDeclined`. Not `place_order()`, not `UPDATE orders
SET status = ...`, but the business fact those operations are trying to record.
That single discipline, past tense, business-recognizable, one note per
fact, is what makes the technique fast: a room full of domain experts and
engineers can timeline an entire checkout flow in twenty minutes, because
naming what happened requires no familiarity with how the code currently
implements it. You do not need to have read `order/services.py` to know that
a customer's order gets placed, their card gets charged, and their package
gets shipped. You need to have *used* the system, or sold it, or supported
it.

That is the property this chapter leans on hardest: event storming surfaces
seams from the *outside in*. A bounded-context boundary, properly found, is
a place where the vocabulary changes, where "reserve" stops meaning
"decrement a quantity column" and starts meaning "authorize a charge," or
where "confirm" stops being about an order's status and starts being about a
message reaching a customer's inbox. Those vocabulary shifts are visible in
the timeline of events almost immediately, because each shift is usually
where one orange sticky hands off to a different kind of actor, a different
external system, or a different part of the business that would staff a
different team if this were drawn as an org chart instead of a sequence
diagram. The schema, by contrast, actively hides those shifts: a shared
Postgres instance makes every app's tables look like equally valid
neighbors, FK joins and all, which is precisely one of Chapter 9's smells.
Event storming doesn't care what database a fact is persisted to. It only
cares whether the fact happened and what happened next.

This is also why event storming is the right reconnaissance tool for a book
built around an agentic development lifecycle rather than a liability unique
to in-person workshops. The ADLC's Map phase, introduced in Chapter 5,
exercised end to end in Chapter 7, is exactly the kind of investigative
pass a storm produces: before an agent generates a single line of extraction
code, something has to establish what the system actually does, in what
order, with what failure modes, independent of how the current
implementation happens to be wired.

> **ADLC in Action**: Treat this chapter's wall as a Map-phase artifact, not
> a workshop exercise you run once and file away. A human-facilitated
> session with sticky notes and an agent narrating a known code path onto a
> structured timeline are the same technique at two different scales; the
> artifact either way is a sequence of named facts, handed to the ADLC's
> Plan phase next. When this book's own extraction chapters opened, each one
> started by re-reading the relevant slice of this wall rather than
> re-deriving it from the code a second time: reconnaissance done once,
> reused by every later phase, instead of re-litigated at every step.

Nothing about this chapter asks you to adopt new tooling to get that
artifact; the timeline this chapter builds is written in prose and a
diagram, the same way the other chapters in this book record decisions.

## The grammar of a session

A real event-storming wall accumulates more than orange stickies, and the
order in which colors get added is purposeful: each new color answers a
question the previous pass left open.

**Domain events (orange)** come first, and only first. The initial pass is
*chaotic exploration*: write down every fact you can think of, out of order,
duplicated, contradicted: the goal is coverage, not correctness. Once the
events for a process exist, the group lines them up into a timeline, which
is itself the first real modeling act: disagreements about ordering are
where hidden assumptions surface, often the same assumptions a single ACID
transaction has been quietly enforcing without anyone noticing.

**Commands (blue)** come next, one per event: the imperative that triggered
the fact. `PlaceOrder` triggers `OrderPlaced`. `CapturePayment` triggers
`PaymentCaptured` or `PaymentDeclined`: note that one command can produce
either of two events, a branch that is invisible in the orange-only pass and
immediately obvious once you ask "what triggered this?" for every sticky on
the wall.

**Actors** (conventionally a small yellow figure, not a box) sit to the
left of each command: who or what issued it. A human customer issues
`PlaceOrder`. A scheduled job, a webhook from a payment gateway, or a policy
reacting to an earlier event can issue a command just as validly as a person
submitting a form, and naming the actor is what tells you later which seam
needs an authenticated human-facing route and which needs a background
consumer on an internal topic.

**Aggregates (yellow, large)** come from grouping: for each command/event
pair, which cluster of data had to exist, enforce an invariant, and decide
whether the command was even valid? `Order` is the aggregate that decides
whether `PlaceOrder` is well-formed; `InventoryItem` is the aggregate that
decides whether `ReserveStock` can succeed. An aggregate boundary found this
way is a *behavioral* claim, "this cluster of data is where this invariant
is checked," which lines up with, but is independently verifiable from, the
tactical-DDD aggregate boundaries Chapter 11 already named.

**Policies and reactions (lilac)** are the "whenever/then" rules that chain
events to the next command automatically, with no human actor in the loop:
*whenever* `OrderPlaced`, *then* issue `ReserveStock`; *whenever*
`StockReserved`, *then* issue `CapturePayment`. A policy sticky is the exact
shape a message consumer takes once the system is distributed. It is, not
coincidentally, also the exact shape of one step in a choreographed saga,
which is why this chapter's wall and Chapter 23's payment saga are the same
diagram read at two points in the book.

**Read models (green)** are the views built by projecting events forward for
some later question to be answered cheaply: "what's the status of order
#4412" needs an `Order Status` read model that several of this flow's
events feed, not a live join across several apps' tables each time someone
asks. **External systems (pink)** are the boxes outside the team's control
that a policy has to call through: a card network, a carrier's dispatch API.
Naming them explicitly is what stops a modeling session from quietly
assuming every collaborator is as reliable and as fast as an in-process
function call, which is exactly the assumption `_place_order_local` makes
today, for inventory, payment, and shipping, with no exception.

{% include excalidraw.html file="event-storming-legend" alt="A seven-row legend card listing the event-storming note types in the order a session introduces them: domain event (orange sticky, a past-tense fact, e.g. OrderPlaced), command (blue sticky, the imperative that triggered it, e.g. Place Order), actor (small yellow figure left of its command, e.g. Customer), aggregate (large yellow sticky, the data cluster enforcing an invariant, e.g. Order), policy/reaction (lilac sticky, 'whenever X then issue command Y', no human actor), read model (green sticky, a view projected forward from events, e.g. Order Status), and external system (pink sticky, outside the team's control, e.g. the Payment Gateway stand-in). Each row also names this book's house-style box type that stands in for the real sticky color." caption="Figure 12.2: The event-storming note-type legend: the wall's color grammar, named as the chapter calls it" %}

A session runs at three altitudes, and conflating them is the most common
way a storm produces a useless wall. **Big-picture** storming surveys an
entire business (weeks of activity across every process a company runs)
to find candidate bounded contexts and spot where two groups use the same
word to mean different things; it stays at the orange-only, no-detail level
because its job is breadth, not depth. **Process-level** storming picks one
process (checkout, in this chapter) and works it end to end with the full
grammar: events, commands, actors, policies, external systems, read models.
This is the altitude that produces a decomposition backlog, and
process-level storming is this chapter's focus. **Design-level** storming
goes one layer deeper still, inside a single aggregate, to work out the
exact commands, validation rules, and events needed to implement it; this
is where a storm hands off directly to the tactical DDD vocabulary Chapter
11 already gave you, and where the aggregate's own API gets drafted before a
line of extraction code exists.

## Storming checkout: the process-level pass

Run the process-level pass on checkout and the actor/command opening is the
easiest sticky on the wall: a **Customer** issues **Place Order**, carrying a
customer id, a shipping address, and a list of line items: this is exactly
the payload `OrderCreateSerializer` already validates for `POST
/api/orders`. The **Order** aggregate receives that command and, if it's
well-formed, the first domain event goes up: **OrderPlaced**. This is not a
sticky this book has to invent a name for: it is already a live constant:

```python
# config/settings.py
ORDER_PLACED_TOPIC = "order.placed"
```

The next policy on the wall is *whenever OrderPlaced, then reserve stock*,
and here storming pays off by naming something a straight code read
tends to blur past. `_place_order_local` persists the `Order` row as
`PENDING` first, then loops over the checkout lines reserving each one:

```python
# order/services.py::_place_order_local
order = Order.objects.create(customer=customer, shipping_address=shipping_address,
                              status=Order.Status.PENDING)
for line in items:
    inventory_item = inventory_services.get_by_sku(line["sku"])
    inventory_services.reserve(line["sku"], line["quantity"])  # InsufficientStock, no writes yet
    OrderItem.objects.create(order=order, sku=inventory_item.sku, ...)
```

Read as code, that sequence already gets the business order right: the
`Order` row, the fact of a customer's intent to buy, is persisted
*before* any reservation is attempted. What the code doesn't do is *name*
that moment as a fact anything else could react to. No event fires when the
`Order` row commits; the only thing this function ever publishes is a single
`order.placed` outbox row, written at the very end of the function, after
payment has captured and shipping has dispatched, by which point the
event's own payload may already read `"confirmed"` rather than `"placed"`
(`order/services.py::_write_order_placed_outbox_event` sets `confirmed =
order.status == Order.Status.CONFIRMED` and picks the verb from that). The
wall needs two separate stickies where the code has one: **OrderPlaced**,
the fact belonging right after the `Order` row commits, and
**OrderConfirmed**, the fact belonging at checkout's actual end, and
naming that gap is exactly the kind of thing a storm catches that a code
read, following call-stack order, tends to paper over.

**StockReserved** is the event this system doesn't currently name anywhere:
today, "stock got reserved" is indistinguishable from "a function returned
without raising." `inventory_services.reserve()`'s own
`InsufficientStock` is raised before any row is updated, so a failed
reservation needs no rollback, a tell that synchronous validation is
standing in for what should be an
asynchronous reaction to a fact that already happened.

**StockReserved** feeds the next policy: *whenever StockReserved, then
capture payment*, issued to an **external system**, the card network
sitting outside this codebase's control, modeled on the wall as a pink box
specifically so the question "what if this is slow, or down, or ambiguous"
gets asked out loud instead of assumed away. The command produces one of two
events, and the branch is where `payment/services.py::charge` names the
mechanism this book is retiring:

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

On the wall, **PaymentCaptured** and **PaymentDeclined** are two separate
orange stickies coming off one blue command, and the question the
facilitator asks at exactly this point, "when payment is declined, what
undoes the stock reservation?", is the question this monolith currently
answers with "nothing has to; `transaction.atomic()`'s rollback does it by
default." That answer is one of Chapter 9's smells stated out loud, by the
wall itself, before Chapter 22 ever names ACID versus ACD. A storm doesn't
just find seams; it finds the exact question whose current answer, "the
database handles it," stops being true the instant either side of the seam
gets its own database, which is the premise every remaining extraction in
this book depends on.

Successfully captured payment triggers *dispatch shipment*, which
`shipping.services.dispatch` performs (its own doc comment already flags
the call as synchronous and in-transaction), producing **ShipmentDispatched**,
the event name already reserved in `config/settings.py`
(`SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"`). The final policy,
*whenever ShipmentDispatched, then notify customer*, is where this chapter's
wall diverges from every other row on it, because here the current code
already matches the wall's own prescription rather than falling short of
it: `order/services.py` writes a single `OutboxEvent` row and returns,
nothing notification-shaped runs synchronously in the checkout path at all.
**NotificationSent**, the narrower fact that a message actually left the
system, happens later, independently, driven by
`notification.management.commands.order_placed_consumer` reacting to that
same outbox row once a separate relay process has published it. Storming
this policy doesn't surface a gap to close. It surfaces a cure already
shipped, which proves the method:
this book didn't have to wait for notification to become its own deployable
(Chapter 17) before cutting the behavioral seam first, inside the monolith,
where the cost of being wrong was cheapest. An **Order Status** read model,
the wall's one green sticky for this process, is fed by `OrderPlaced`,
`PaymentCaptured`, `ShipmentDispatched`, and `OrderConfirmed`, the
projection a customer-facing "where's my order" screen actually needs,
built by folding events forward instead of joining several apps' live
tables on every page load.

## From the wall to the backlog

A finished process-level wall is not decoration; read left to right, it *is*
the decomposition backlog, and the mapping from event boundary to extraction
chapter is close to direct. Every place on the timeline where one policy's
reaction currently crosses into another context's module as a plain Python
function call is a synchronous call today and a published event once that
boundary is cut. The wall built in this chapter maps onto the decomposition
roadmap as follows: the `OrderPlaced` → `StockReserved` boundary is
inventory's seam, cut with a gRPC contract and the `RemoteInventoryClient`
anti-corruption layer in Chapter 19; the `StockReserved` →
`PaymentCaptured`/`PaymentDeclined` boundary is payment's seam, cut as a
choreographed saga in Chapter 23, where the lilac policy sticky *whenever
StockReserved, then capture payment* becomes, almost unchanged, an aiokafka
consumer reacting to `order.placed`; the `PaymentCaptured` →
`ShipmentDispatched` boundary is shipping's seam, cut in Chapter 24 as an
orchestrated saga with a single FastAPI coordinator sequencing the steps
instead of each service discovering the next event for itself; and the
`ShipmentDispatched` → `OrderConfirmed`/`NotificationSent` boundary is
notification's seam, already cut behaviorally by the transactional outbox
this chapter found, and completed as an independently deployable service in
Chapter 17.

{% include excalidraw.html file="storm-wall-to-backlog" alt="A four-row table mapping each event boundary this chapter's storm found to its extraction chapter and mechanism: OrderPlaced to StockReserved (inventory's seam) to Chapter 19, a gRPC proto-as-ACL plus CDC backfill; StockReserved to PaymentCaptured/PaymentDeclined (payment's seam) to Chapter 23, a choreographed saga via an aiokafka consumer; PaymentCaptured to ShipmentDispatched (shipping's seam) to Chapter 24, an orchestrated saga with a single FastAPI coordinator; and ShipmentDispatched to OrderConfirmed/NotificationSent (notification's seam, cut first behaviorally) to Chapter 17, a transactional outbox. A footnote box notes order/services.py::place_order() itself is cut last in Chapter 26, after all four boundaries already fire events." caption="Figure 12.3: From the storm wall to the extraction backlog: each boundary, its chapter, and its mechanism" %}

Notice what the wall does *not* tell you: it tells you *where* a boundary
exists, not *which order is safest to cut them in*. Notification already
jumped the queue on behavior, but it's still extracted as a standalone
service second, not first, a question this chapter's wall has no way to
settle, because "where" and "in what order" are measured by two different
things. That ordering question, given several candidate seams, which one
has the least coupling pulling against it, which one's distance from the
others bounds the blast radius of getting it wrong, is a different kind of
analysis, and it's the subject of the next chapter. Every cut the roadmap
makes from Chapter 14 onward is also gated the same way: an equivalence gate
runs the behavior-equivalence suite against both the monolith and the newly
extracted service before that service's old code path stops seeing live
traffic, which is the same discipline Chapter 7 demonstrated and Chapter 9
named as this method's existence proof.

The god `place_order()` function itself deserves one more look through the
wall's lens, because it explains something Chapter 9 stated as a roadmap
fact without fully justifying it: why order is extracted last. On the wall,
`place_order()` isn't one box. It's the function that issues *every*
policy's triggering command in this flow: it is the thing that calls
reserve, calls capture, calls dispatch, all directly, all synchronously,
all (except the one already-cured edge) inside one transaction. A function
occupying that many command-issuing positions on one timeline cannot be
extracted until each of those positions has already been rewired to fire an
event instead of a direct call, which is precisely what Chapters 19, 23,
and 24 each do, one boundary at a time, before Chapter 26 ever touches
`place_order()` itself.

## What you learned

- Event storming finds bounded-context seams by narrating what a system
  *does*: a timeline of past-tense domain events, each with a triggering
  command and actor, grouped into aggregates, chained by policies/reactions,
  projected into read models, and bounded by external systems, instead of
  inspecting its schema, which encodes implementation accidents rather than
  business meaning.
- A session runs at three altitudes: big-picture (breadth, across a whole
  business), process-level (depth, one process end to end, the
  backlog-producing altitude), and design-level (depth inside one aggregate,
  handing off to tactical DDD). Conflating them produces a wall that's
  either too shallow to act on or too narrow to show the seams.
- Storming checkout surfaced six events this chapter needed: `OrderPlaced`,
  `StockReserved`, `PaymentCaptured`/`PaymentDeclined`, `ShipmentDispatched`,
  `OrderConfirmed`, `NotificationSent`, and caught a real gap: the code's
  one `order.placed` outbox row is written at the *end* of checkout, so it
  sometimes carries the `OrderConfirmed` fact under the `OrderPlaced` name.
- One boundary on this wall, `ShipmentDispatched` → `NotificationSent`, was
  already cured behaviorally inside the still-single-deployable monolith,
  proof that a seam can be cut before a service boundary is, and that
  "where" (this chapter) and "in what order to cut" (the next one) are
  separate questions, not restatements of each other.
- Each remaining event boundary maps directly onto a later chapter's
  extraction seam: inventory (ch.19), payment's choreographed saga (ch.23),
  shipping's orchestrated saga (ch.24). But the wall only answers *where*
  to cut; *in what order* is Chapter 13's question.

Chapter 13 takes this wall and asks the question left open here: given
several candidate seams, which is safest to cut first, measured
by how strongly coupled it is to everything around it, and which, measured
the same way, might be better left uncut.
