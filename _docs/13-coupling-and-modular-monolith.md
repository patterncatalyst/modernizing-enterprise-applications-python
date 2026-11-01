---
title: "Coupling, the Modular Monolith & When Not to Split"
order: 13
part: "Finding the Seams"
description: "Khononov's three dimensions of coupling; the modular monolith and decomposed-DB monolith as legitimate destinations; the distributed-monolith trap."
---

## Learning objectives

By the end of this chapter you can:

- State Constantine's cohesion/coupling pairing and explain why coupling, not cohesion, is the dimension this book builds a sequencing strategy on.
- Place each of Chapter 9's remaining smells on the Constantine coupling ladder (content, common, control, stamp, data) with its concrete Python code example: the live `InventoryItem` handoff in `get_by_sku()`/`reserve()` (content and stamp), the shared Postgres schema (common), `paymentMethod` threaded into `payment.services.charge` (control), and the serializers' DTO output (data).
- Compute afferent (Ca) and efferent (Ce) coupling for a Django app from its import graph and foreign keys, and explain why low-Ca, low-Ce contexts should extract first.
- Reconstruct the six-context extraction ranking (review, notification, inventory, payment/shipping, order) purely from Ca/Ce scores, independent of narrative preference.
- Explain Khononov's strength/distance/volatility balancing-coupling model and why splitting strong, volatile coupling across a network produces a distributed monolith instead of a fix.
- Describe the three disciplines of a Python-native modular monolith (`import-linter`-enforced import-boundary isolation, no cross-module `ForeignKey` references in favor of a plain id field plus a published function, and module-owned tables named by `db_table`) and when that destination is preferable to further distribution.
- Recognize the distributed-monolith trap and state the precondition every extraction in this book satisfies before cutting a seam: an ACL, an outbox, a CDC pipeline, or a saga already in place.

## Why this matters

Chapter 11 gave you bounded contexts and aggregates as the *conceptual*
vocabulary for a seam, and Chapter 12 gave you event storming as a *process*
for discovering where those seams sit in a system that never shipped with a
map. Both chapters answer the question "where could this system be cut?" by
pointing at behavior: the verbs on the sticky notes, the domain language
that changes meaning as you cross a boundary. Neither chapter answers a
second, equally important question: given several legitimate candidate
seams, which one do you cut *first*, and (the question any decomposition
plan has to answer before a single extraction ships) is cutting any of them,
right now, the right call? This chapter supplies the metric that
answers both: **coupling**, measured precisely enough to rank candidates
rather than merely describe them, and precisely enough to reveal when the
correct answer is not to cut at all. Every smell Chapter 9 catalogued in
`examples/00-monolith/` is, at bottom, a coupling problem wearing a
different costume: a shared schema, a god function, a synchronous call, a
leaky entity reference. This chapter gives you the vocabulary to see that
they are the same problem, scored on the same scale, and the scale is what
turns an extraction order into a defensible sequence instead of an argument
settled by whoever spoke last in planning.

There is no new code in this chapter: `examples/00-monolith/` is unchanged
from Chapter 10, and the extraction order it motivates is realized starting
in Chapter 14. What this chapter adds is the measurement that makes the plan
*checkable*: given the real dependency graph of a real codebase, you can
compute which context has the smallest blast radius, and that computation,
not intuition, is why review went first and order goes last.

## Coupling and cohesion as the structural property, not a vibe

Larry Constantine's original formulation, from the structured-design
literature this book's whole vocabulary descends from, is a single sentence
worth keeping in exactly its plain form: **a structure is stable if cohesion
is high and coupling is low.** Cohesion measures how tightly the *elements
inside one module* belong together: do they share a single, nameable
purpose, or did they end up in the same file because that was convenient the
day someone wrote them. Coupling measures the opposite direction: how much
one module's internals leak into, or depend on, another module's internals.
The two are not independent axes you can optimize in isolation; in
practice they trade against each other, because the usual way to raise
cohesion inside a module is to pull in everything that module needs to do
its one job, which simultaneously *reduces* that module's coupling to its
neighbors, since it no longer needs to reach outside itself to get the job
done. `order.services.place_order` is the demonstration case run backwards:
its cohesion is low: "places an order by checking stock, persisting the
order, charging payment, and dispatching shipment" needs four verbs and
three "and"s to describe accurately, which Chapter 9 already pointed out as
the plain-English tell for a god function, and its coupling is
correspondingly high, because a function with no single purpose has no
natural boundary keeping it from reaching into everyone else's business.

What makes coupling the right word to build an entire decomposition strategy
around, rather than just one more code-smell synonym, is that it is
*measurable* in a way cohesion mostly isn't. You can count the edges in a
dependency graph. You cannot, in the same mechanical way, count how
"cohesive" a module feels: cohesion stays a judgment call applied to one
module at a time, while coupling is a relationship between two or more
modules that a static analysis tool, or a disciplined `grep`, can actually
enumerate. That asymmetry is why this chapter spends most of its time on
coupling: it is the dimension you can turn into a ranking, and a ranking is
what an extraction *order* requires. Conway's observation sits underneath
all of this as the organizational mirror of the same idea: "organizations
which design systems are constrained to produce designs which are copies of
the communication structures of these organizations," which is why a
coupling edge in the code is so often also, quietly, a coordination
requirement between two teams. A `ForeignKey` between `order` and
`customers` is not just a database constraint; it is a standing requirement
that whoever owns the shared schema's migration history coordinate with
whoever owns order's queries before touching it, whether or not an org chart
ever wrote that requirement down.

## The Constantine coupling taxonomy, applied to the monolith

Constantine and Yourdon's original structured-design work ranked module
coupling on a ladder from worst to best, and the ladder is worth walking in
full because every rung has a live example sitting in
`examples/00-monolith/` today: this is not a taxonomy imported from a
textbook and left abstract; it is a taxonomy that scores the actual code the
previous two chapters built on.

**Content coupling** is the worst rung: one module reaches inside another
and directly relies on its internals, bypassing whatever interface that
module exposes. The monolith's closest approach to content coupling is
`_place_order_local` receiving a live, queryset-managed `InventoryItem`
instance straight from `inventory_services.get_by_sku()`/`reserve()` and
reading its internal fields (`.sku`, `.name`, `.price_cents`) rather than a
contract type built for external consumption. It falls short of the
textbook definition only because nothing about Python's `InventoryItem`
class technically forbids the access: there is no ACL at the seam, and no
language feature standing in for one either, only Python's complete lack of
access modifiers to even pretend otherwise. Everything else about the
relationship (depending on the producer's exact internal representation,
with no translation layer absorbing change) is content coupling's spirit
if not its letter, which is exactly why Chapter 19's gRPC contract and
`RemoteInventoryClient` are the cure rather than a milder fix.

**Common coupling** is two or more modules sharing the same global or
widely-visible data store, where any of them can change state the others
depend on without the others knowing it happened. The monolith's single
Postgres schema is common coupling at the data-tier scale: `order`,
`inventory`, `payment`, `shipping`, `notification`, and `review` all read
and write tables in one schema that nothing enforces ownership boundaries
on. `customers`, in particular, has no single owner, joined directly by
`order`, `review`, and `notification` alike, so a migration that
`inventory` runs for its own reasons can silently break a query `order`
never knew it was leaning on. This is one of Chapter 9's smells, and it is
the smell this chapter treats as the single worst offender in the monolith;
the section after this one explains why.

**Control coupling** is one module passing another a flag or parameter
whose *value* dictates the receiving module's internal control flow: the
caller has to know something about the callee's internal branching logic to
use it correctly. The monolith's checkout flow brushes against this in a
narrow but real form: `OrderCreateSerializer`'s `paymentMethod` field is
threaded from the DRF view all the way into `payment.services.charge`,
where its value selects a code path (approve vs. decline, via the
`DECLINE_SENTINEL` check) that the order-placement flow's own success or
failure then depends on; the caller doesn't just pass data. It passes a
value whose meaning only makes sense in terms of payment's internal
decision logic.

**Stamp coupling** is passing a whole composite data structure across a
boundary when the receiver only needs part of it: the receiver becomes
implicitly dependent on the structure's full shape, including fields it
never touches, so any change to that shape is a potential breaking change
even to callers using a fraction of it. The same `get_by_sku()`/`reserve()`
handoff that produced content coupling above is also stamp coupling, viewed
from a different angle: `_place_order_local`'s loop gets back the entire
`InventoryItem` instance (five columns, a queryset-backed model with its
own manager and lifecycle) for the three fields it actually copies into
`OrderItem` (`sku`, `name`, `price_cents`). The problem isn't that either
rung is wrong in isolation; it's that the same one call site earns two
different rungs of the same ladder at once, because nobody drew the line
between "data this call needs a copy of" and "a reference to someone else's
whole aggregate."

**Data coupling** is the best rung reachable while still passing anything at
all: modules communicate only through simple, well-defined parameters:
primitives or small, purpose-built value types with no incidental fields
riding along. The monolith already does this correctly a few lines away
from where it does the opposite: `InventoryItemSerializer`'s and
`OrderSerializer`'s read endpoints return serialized DTOs built for the
wire, never the raw Django model instances, which is exactly the discipline
`get_by_sku()`'s cross-context caller doesn't get. The contrast is
instructive on its own: the codebase already demonstrates both ends of the
same ladder, in sibling files, because the serializers were written for an
HTTP client's benefit while `get_by_sku()` was written for a Python caller's
convenience, and nobody applied the same discipline to both call sites.

Two of Constantine's rungs, **message coupling** (interaction only through
message passing, no shared state at all) and well-defined API/contract
coupling, don't have a live example in the monolith for the obvious reason:
they're what the *target* architecture looks like once Chapters 14 through
26 are done. `examples/02-review-service` through `examples/07-order-service`
already reach that rung for the edges each has cut: a FastAPI route and a
JSON body, a gRPC proto and a stub, an aiokafka consumer and an event
schema. That is exactly the point of walking the ladder now: you cannot
evaluate how far the extracted services have moved without knowing the full
span of the ladder you started on.

{% include excalidraw.html file="coupling-ladder" alt="The Constantine coupling ladder drawn as seven stacked rungs, worst to best, each paired with its monolith example. Content coupling: _place_order_local reading a live InventoryItem's sku/name/price_cents straight from get_by_sku()/reserve(), with no ACL at the seam and only Python's lack of access modifiers standing in for one. Common coupling: one shared Postgres schema across order, inventory, payment, shipping, notification, and customers, with no single owner. Control coupling: OrderCreateSerializer.paymentMethod threaded into payment.services.charge, where DECLINE_SENTINEL selects an approve-or-decline code path. Stamp coupling: the same get_by_sku()/reserve() handoff returning the full InventoryItem for the three fields OrderItem actually needs. Data coupling: InventoryItemSerializer and OrderSerializer returning serialized output, not raw models, already done right. Message coupling and API/data-structure coupling have no monolith example: they're what examples/02-07 already reach." caption="Figure 13.1: The Constantine coupling ladder, worst to best, each rung pinned to its monolith example" %}

## The two worst offenders, scored

Two of Chapter 9's smells dominate every other consideration in this book's
own extraction plan, and it's worth being explicit about *why* those two
specifically, using the taxonomy just built rather than gut feeling.

**Shared-schema coupling** is common coupling edging toward content
coupling at the same time, which is what makes it the worst single offender
in the system. It is common coupling because every context reads and writes
tables in one shared Postgres schema with no enforced ownership boundary:
`order`, `payment`, `shipping`, and `notification` each hold a direct
foreign key back into `orders`, and several apps join `customers` directly.
And it edges toward content coupling because a foreign key is not a
negotiated contract; it is the database enforcing a promise ("this row
cannot exist without that row") that neither context's own code declared
and neither context's own code can unilaterally relax. The reason this
smell outranks the others in sheer structural damage is that it is
invisible at the point of use: nothing in `order.services`' source code
says "I depend on inventory's schema," the database says it, silently,
which means the coupling only announces itself when someone tries to break
it: a migration three deploys later, owned by a different developer, that
drops a column inventory no longer needs and breaks a query `order` never
knew it was leaning on. Measured against Khononov's balancing-coupling
model, this is the textbook maximal-strength case: intrusive coupling, at
zero distance today, on data that changes constantly; every one of the
three dimensions (strength, distance, volatility) reads high, and the smell
only stays survivable because distance is currently zero. The instant any
one context gets its own database, distance jumps to its maximum while
strength stays exactly where it was, which is the distributed-monolith trap
arriving on schedule unless something changes strength *before* distance
changes.

**God-function orchestration coupling** is a different failure mode on the
same scale: it is primarily *control* coupling stacked across three separate
relationships at once, because `place_order` doesn't just call
`inventory_services`, `payment_services`, and `shipping_services`. It calls
them as a synchronous, in-process sequence where the entire checkout
operation's control flow is dictated by whether each call raises, and a
caller needing to know all three callees' internal exception behavior
(`InsufficientStock`, `PaymentDeclined`, `ShippingFailed`) to use any one of
them correctly is control coupling by definition, multiplied by three. It
also layers in instability in the Robert Martin sense: a function with three
remaining outbound dependencies on other contexts' services has an efferent
coupling (Ce) of three and, being a leaf of the checkout flow rather than
something other contexts call into, an afferent coupling (Ca) near zero: an
instability score `I = Ce/(Ca+Ce)` close to 1, meaning `place_order` depends
on everything and nothing depends back on it, which is exactly backwards
from where you want your most business-critical orchestration logic to sit
on the stability spectrum. Where shared-schema coupling is dangerous because
it's invisible, god-function coupling is dangerous because it's a single
point with maximum fan-out: every one of the three remaining services it
reaches into has to stay behavior-compatible with `place_order`'s
expectations forever, or checkout breaks, which is why Chapter 9 already
named it as the reason order has to be extracted *last*, not as a
narrative convenience but because each of the other extractions literally
cannot complete until it has removed one of `place_order`'s outbound edges,
shrinking its efferent coupling by one each time until there's finally
little enough left to cut.

## Afferent and efferent coupling: the metric that produces a ranking

The taxonomy above tells you *what kind* of coupling each smell embodies. It
does not, by itself, tell you *which context to cut first*: for that you
need a number, not a category: **afferent coupling (Ca)**, how many other
components depend on a given component, and **efferent coupling (Ce)**, how
many other components a given component depends on. Both are mechanically
countable from an import graph or a model's foreign keys, which is what
makes them useful for sequencing rather than merely descriptive; you can
compute them today, on the actual codebase, without waiting for an
architect's opinion.

The rule that falls out of these two numbers is: **extract low-Ca, low-Ce
contexts first, and save high-Ca, high-Ce contexts for last** because the
number of dependents you have to migrate alongside you (Ca) and the number
of dependencies you have to sever or bridge before you can leave (Ce) are
both, directly, the size of the extraction's blast radius. A context nobody
calls into and that calls into nothing else can be lifted out whole, in an
afternoon, with nothing left behind that notices. A context everyone calls
into, that itself calls into everyone, cannot move until both directions of
that traffic have been rerouted, which describes the god
function from the opposite direction.

Walk the six contexts with this lens and the extraction order stops looking
like a narrative choice and starts looking like a sorted list:

- **Review** has `Ca ≈ 0` (nothing in the monolith calls into review) and
  `Ce ≈ 0` (review has no runtime dependency on order, inventory, payment,
  shipping, or notification, per Chapter 11's own finding). That is the
  *lowest* possible business-coupling score a context in this system can
  have, which is exactly why it was extracted first, in Chapter 15.
- **Notification** has low `Ca` (one asynchronous consume off the outbox,
  no synchronous caller at all) and `Ce ≈ 0`. Its one inbound edge is
  already async, which is precisely why Chapter 12's storm found it already
  cured: its extraction (Chapter 17) only has to promote an existing
  consumer to its own deployable, not rewire a synchronous call first.
- **Inventory** has moderate `Ca` (one inbound call from `place_order`, plus
  the historical FK join Chapter 9 flagged) and `Ce ≈ 0` of its own. Its
  extraction (Chapter 19) is harder than notification's because severing
  the *call-site* coupling this chapter's content-and-stamp rungs both
  named requires a mechanism notification never needed: a gRPC
  contract and a client-side ACL, before the boundary can be
  trusted.
- **Payment** and **shipping** each have moderate `Ca` (one inbound call
  from `place_order` today), and `Ce ≈ 0` today, though payment gains a
  new inbound dependency the instant shipping is extracted: once Chapter 24
  ships, a `shipment.failed` event drives a refund reaction back into
  payment-service, a dependency that doesn't exist yet at this chapter's
  snapshot but is already visible on the dependency graph as a dashed,
  future edge. Both are read and written inside the same spanning
  transaction today, so splitting either one forces the question Chapter 22
  answers of what replaces the free rollback they currently get from
  sharing a database with the rest of checkout. Their extractions (Chapters
  23 and 24) are harder again because severing this edge means building a
  saga, not just a client-side contract: the compensating-action machinery
  neither review nor inventory needed.
- **Order** has the highest `Ca` of any context (it is the thing every other
  context's models point back to via foreign key: `Payment`, `Shipment`,
  and `Notification` all carry a direct `order` join) and by far the
  highest `Ce` (three remaining synchronous edges plus the one already-async
  edge into notification). That is the single worst coupling score on both
  axes simultaneously, which is exactly why it is extracted last, in
  Chapter 26, and exactly why Chapter 9 already told you the other
  extractions each have to remove one of this function's outbound edges
  before order's own extraction becomes tractable at all. An extraction
  order that put order first would have had to solve every other context's
  severance problem *at the same time*, with no smaller extraction's
  lessons to carry forward, which is precisely the "biggest cut first"
  failure mode a blast-radius ranking exists to prevent.

{% include excalidraw.html file="context-dependency-graph-cace" alt="A directed dependency graph of the six contexts. Order sits at the center with its remaining outbound edges -- place_order()'s calls into inventory, payment, and shipping (three synchronous) plus one already-async edge into notification -- its efferent coupling; and three inbound foreign-key edges from payment, shipment, and notification back to order, its afferent coupling. Inventory also carries a data-level edge from order via the historical FK Chapter 9 flagged. Review has no edges in or out. A dashed edge from shipping to payment marks the dependency payment only gains once shipping is extracted. Below, the same six contexts sorted into the resolved extraction order: review, notification, inventory, payment, shipping, then order, lowest Ca/Ce first." caption="Figure 13.2: The six contexts' dependency graph, scored by Ca/Ce, resolving into the extraction order" %}

That is the whole method: rank contexts by Ca and Ce, cut the lowest-scoring
context first, and let each completed extraction reduce the score of
whatever remains until the hardest context is also the smallest remaining
problem. It is the same discipline Part 1 argued for in the abstract (risk
distributed across many small, reversible steps instead of concentrated into
one large one), made concrete as an actual number you can compute from the
import graph sitting in front of you, and realized on git: `stage/01-review`
through `stage/06-order` tag the six extractions in exactly this order.

## The modular monolith: most of the benefit, none of the distribution tax

Everything so far has described coupling as a problem to reduce by splitting
a deployable into more deployables. That is not, on its own, license to
split everything; Khononov's balancing-coupling model already supplied
the reason why not, as a single formula: **distance is a cost multiplier,
and splitting strong, volatile coupling across a network adds distance
without removing strength**, which produces a *distributed* monolith: the
same tangle as before, now paying for network calls, partial failures, and
multi-service deploy coordination on top of coupling that was never
addressed. The underlying fact beneath that formula is that most of
coupling's damage (invisible cross-context writes, a function with
unbounded fan-out, a leaked internal model instance) is a property of
**module boundaries**, not of **process boundaries**, and module boundaries
can be enforced inside a single deployable just as rigorously as across a
network, for a fraction of the operational cost.

This book doesn't have to argue the modular monolith's payoff only in the
abstract, either: Chapter 12 already showed you one, in production inside
this very project. The notification edge was cured: the synchronous send
replaced with a transactional outbox, the dual-write hazard closed, before
notification was ever pulled into its own deployable. That cure happened
entirely inside the monolith: one new model (`common.models.OutboxEvent`),
one new management command (`outbox_relay`), one new consumer
(`notification.management.commands.order_placed_consumer`), all still
running in the same Django project, the same build, the same release train
as everything else. The behavioral seam was cut first, at module-boundary
cost; the deployable boundary came later, in Chapter 17, once there was a
real reason to pay for it. That ordering, fix the coupling inside the
monolith and distribute only once the fix is proven, is what makes the
**modular monolith** a legitimate destination in its own right, not merely a
waypoint everyone is assumed to outgrow.

A Python-native modular monolith, generalized past this one example, needs
three disciplines a distributed system gets automatically, enforced by
tooling and convention instead:

- **Import-boundary isolation**, where a tool like `import-linter` (or a
  convention enforced in CI) refuses to let code in one Django app import a
  class from another app's internal module. This turns the content-coupling
  rung this chapter scored (`get_by_sku()`/`reserve()` handing back a live
  `InventoryItem`) from a runtime discovery into a *build failure*: the
  moment `order` tries to import `inventory.models.InventoryItem` instead of
  a contract type `inventory` designates as its public interface, the build stops, which
  is strictly earlier and cheaper feedback than discovering the coupling
  during an incident three deploys later.
- **No cross-module model references**, meaning the `ForeignKey` pattern
  this chapter has spent its whole walkthrough pointing at (`Payment`,
  `Shipment`, and `Notification` all joining `Order` directly, several apps
  joining `Customer`) is disallowed across a module boundary, even
  though every module still lives in the same schema and the same database
  connection. Each module is only permitted to persist its own models and to
  reference other modules' data by a plain identifier (an `order_id` integer
  field, not a `ForeignKey`) plus a published, in-process function to
  resolve it, the same discipline Chapter 19's gRPC contract teaches for a
  *distributed* seam, enforced here for a boundary that hasn't crossed a
  network yet.
- **Module-owned tables**, named here and detailed in Chapter 18's actual
  migration mechanics: each app gets a table-naming convention that makes
  ownership explicit: `inventory_items` owned and migrated only by
  `inventory`, never written to by a cross-app query, so a foreign key
  *physically cannot* cross module boundaries even by accident, while the
  operational cost of a second database, a second connection pool, and a
  second set of credentials to rotate is deferred until a real
  decomposition need justifies paying it. This is "own your data" practiced
  at the lightest weight the idea supports. The full shared-data-to-owned-data
  story, including CDC, is Chapter 18's and 19's subject, not this one's;
  this chapter's job is only to name the decomposed-database monolith as the
  midpoint between "one undifferentiated schema" and "one database per
  service."

The pedagogical payoff of doing all three inside a monolith first, before
distributing anything, is that it isolates two problems that a premature
microservices migration conflates. "Are these module boundaries correct: do
they track real bounded contexts, or did we guess wrong about where the
seams are?" is a question you can answer and *cheaply fix* inside
a single deployable, where moving a function between apps is a refactor,
not a cross-service migration. "Is this coupling now low enough, and this
context's operational profile different enough from its neighbors', to
justify the cost of a second deployable, a second database, and a network
between them?" is an entirely separate question, and it should only be
asked, per this book's own Chapter 3 argument that microservices are not
themselves the goal, once the first question already has a confident
answer.

None of this contradicts this book's own strangler-fig sequence. This
book's reference monolith is not taken to the full modular-monolith stage as
an intermediate step before Chapter 14; its extraction sequence goes
mostly straight from "one undifferentiated shared schema" to "owned service
with its own database," with notification's outbox as the one deliberate
exception, because the book's pedagogical goal is demonstrating the full
strangler-to-microservices journey end to end on a system with a measured
before/after. A reader applying this chapter to their *own* system, however,
should read the modular-monolith option as a live, frequently-correct
destination: if your organization's actual problem is lead time and
change-failure rate inside a single team's release train, and not
independent scaling or independent team ownership across multiple teams,
enforcing import boundaries, banning cross-module model references, and
naming table ownership can retire most of this chapter's coupling damage
without ever standing up a second deployable, a message broker, or a
service mesh. Distribute only where the business case, a named, measured
need for independent scaling, independent deployment cadence, or
independent team ownership, justifies the operational tax a
network boundary imposes.

## The distributed-monolith trap, named precisely

This chapter closes the loop on the failure mode it has gestured
at twice already, because it is the single most common outcome of getting
this chapter's lesson backwards: a team sees coupling, concludes
"microservices fix coupling," and distributes a system whose coupling they
never reduced. The result has every operational cost of a
distributed system: network latency, partial failure, independent deploys
that still have to be coordinated because nothing was decoupled,
distributed tracing standing in for what used to be a stack trace, and
none of a monolith's redeeming simplicity, because the calls that used to be
in-process function invocations are now network calls making exactly the
same synchronous, tightly-coupled demands of each other that they always
did. Khononov's formula names the mechanism precisely: distance went up,
strength did not go down, and volatility on the core domain was already
high: all three dimensions landed high at once, which is the model's own
definition of maximum coupling pain. A hypothetical version of this
monolith that split into six services *without* first addressing the shared
schema and the god function is the distributed monolith this chapter warns
against by name: six deployables, each reaching across the network into
tables and services it does not own, paying every operational cost of
distribution while keeping every coupling problem Chapter 9 catalogued,
which is exactly why this book's actual extraction sequence does not do
that. Each chapter from 15 onward only cuts a context once the specific
coupling standing in its way has an answer (an ACL, an outbox, a CDC
pipeline, a saga), and the equivalence gate exists precisely to prove that
answer held, rather than discovering in production that it didn't.

## Part 4, consolidated: the extraction plan

Part 4 has now supplied three lenses, in this order, and here is how they
combine into the one plan the extraction chapters that follow carry out. Chapter 11's
domain-driven design gave you *where the conceptual boundaries are*: the
bounded contexts, the aggregates, the rule that keeps the ORM out of the
domain core so a later extraction is mechanical rather than a rewrite.
Chapter 12's event storming gave you *how to find those boundaries from
behavior* when no one has drawn them for you: watching where domain events
cluster, where one team's vocabulary stops making sense to the next,
producing the decomposition backlog as a reconnaissance artifact rather than
an architect's guess. This chapter has given you *the order to cut them in*:
coupling, scored precisely enough by the Constantine taxonomy and the Ca/Ce
metric to rank six already-identified candidate boundaries from cheapest to
most expensive to extract, and precise enough to also say when the right
answer for a given boundary is a modular monolith rather than a network
call.

Put the three together and Part 4's output is a single artifact, not three
separate ones: a list of bounded contexts (Chapter 11), each annotated with
the behavioral evidence that the boundary is real (Chapter 12), each scored
for coupling and ranked by blast radius (this chapter). The result is review
first because its score is the floor, order last because its score is the
ceiling, with notification, inventory, payment, and shipping sorted in
between by exactly how much coupling each one's extraction has to sever.
Every chapter from here forward executes one row of that ranked list. **Part
5, "The Strangler Fig in Practice,"** opens immediately after this chapter
with the mechanism that makes a ranked list executable one row at a time
without ever requiring a big-bang cutover: Fowler's strangler fig pattern,
a proxy that lets old and new code serve traffic side by side, and the first
extraction, review, run end to end exactly where this chapter's coupling
score said it belonged: first, because there was nothing in its way.

## What you learned

- Coupling and cohesion are Constantine's structural pair: "a structure is
  stable if cohesion is high and coupling is low." Coupling is the
  dimension this book builds a sequencing strategy on because it is
  measurable, while cohesion stays a per-module judgment call.
- The Constantine taxonomy (content → common → control → stamp → data,
  worst to best) scores the monolith's remaining smells on the same scale:
  the inventory seam reads as both content and stamp coupling at once, the
  shared schema reads as common coupling, the checkout flow's
  `paymentMethod` threading reads as control coupling, and the read
  endpoints' serialized output is the data coupling the rest of the
  codebase should match.
- Shared-schema coupling and god-function orchestration coupling are the two
  worst offenders because they combine multiple rungs of the ladder at
  once: common-plus-content for the schema, control coupling multiplied
  across three outbound edges for the function. Khononov's
  strength/distance/volatility model explains precisely why distributing
  either one without first weakening it produces a distributed monolith
  rather than a fix.
- Afferent coupling (Ca, who depends on you) and efferent coupling (Ce,
  what you depend on) turn "which seam first?" into a number: review's
  near-zero Ca and Ce put it first in Chapter 15; order's maximal Ca and Ce
  (every other context's foreign key points at it, and it still calls three
  others directly) put it last in Chapter 26, with the middle extractions
  sorted by how much coupling each one's cut has to sever.
- The modular monolith (import-boundary isolation, no cross-module model
  references, module-owned tables) captures most of coupling's fix inside
  a single deployable, at a fraction of a network boundary's operational
  cost, and this book has already proven the payoff once: notification's
  transactional outbox shipped inside the monolith, before notification
  was ever its own deployable. Distributing further is justified only by a
  named business case for independent scaling, deployment cadence, or team
  ownership, per Chapter 3's "microservices are not the goal."

Part 5, "The Strangler Fig in Practice," begins immediately after this
chapter with the mechanism: Fowler's strangler fig, the proxy, and the
flag-gated cutover, that turns this ranked extraction plan into six real,
individually reversible migrations, starting with the context this
chapter's own scoring already named as the obvious first cut.
