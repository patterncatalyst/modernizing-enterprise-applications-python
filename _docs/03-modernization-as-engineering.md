---
title: "Modernization as Engineering, Not Fashion"
order: 3
part: "Why Modernize"
description: "Modernization goals, the ten microservice traits, 'microservices are not the goal,' and when microservices are a bad idea."
---

Chapter 2 gave you the ledger you'll keep as you work through this book: the
decision log, the build plan, the reconciliation record. This chapter asks
the question every entry in that ledger ultimately has to answer: why do any
of this at all? Before a single line of the reference monolith exists, before
this book names a strategy or picks an extraction order, it owes you an
argument clear enough to survive a budget meeting: modernization is worth
doing when it solves a problem you can name and measure, and it has to be run
as a disciplined engineering activity with a safety net, not as a leap of
faith toward a fashionable architecture. That argument carries two
uncomfortable corollaries. First, microservices are not themselves the goal:
a project that treats them as one will end up with a distributed system that
has all of a monolith's coupling and none of its simplicity. Second, the
discipline this chapter argues for is exactly what separates a modernization
that ships value continuously from a rewrite that ships nothing until it
either ships everything or quietly dies. Both corollaries point at the same
destination every later chapter builds toward: incremental, strangler-based
extraction, with a behavior-equivalence suite standing guard at every step.

## Why modernize at all

Start from an uncomfortable truth: modernization has no value in the
abstract. A system that works, that nobody has to touch under duress, and
that the business can still staff and extend, does not need modernizing just
because its stack is unfashionable. What makes modernization worth the risk
is a problem you can point to and measure, not a preference for a newer
framework. Two categories of problem recur often enough to name
directly.

**Delivery problems** show up as symptoms in how fast a team can ship
anything. A single Django deployable means every change (a notification
template tweak, a payment-provider integration, a shipping-label format)
rides the same release train, waits on the same migration, and risks the
same regression surface as every other change in flight. Teams start to
avoid touching code they don't own because the blast radius of a mistake is
the whole system, not their corner of it. Release cadence slows from weekly
to monthly to "whenever we work up the nerve," and the slowdown is not a
discipline problem. It is the direct, structural consequence of one
deployable owning every concern at once.

**Operability problems** show up as symptoms in how the system behaves once
it's running. A payment-processing bug under load takes down checkout
*and* the ability to browse last month's reviews, because the processes
share a runtime, a database connection pool, and a failure domain, even
though nothing about reading reviews has anything to do with capturing a
payment. Scaling is similarly all-or-nothing: if order placement needs ten
times the capacity during a flash sale, the monolith's answer is to scale
everything ten times, including the notification worker that was already
comfortably idle.

Both categories share a measurable shape: time-to-ship for a
single-bounded-context change, blast radius of a single component's failure,
and the ratio between a service's actual load and the capacity it's forced to
share. Chapter 4's assessment rubric gives those measurements a framework;
this chapter's job is narrower: establishing that "I can name the metric and
it's bad" is the bar modernization has to clear, not "this looks old."

## The ten microservice traits

"Microservices" gets used as a synonym for "small HTTP services," which
flattens a specific, useful idea into something much weaker. The traits
below are the actual promise a microservices architecture makes, restated
for this book's own stack so nothing here leans on a Java-only idea.

{% include excalidraw.html file="microservice-traits" alt="A ten-cell grid of microservice traits: independently deployable; modeled around a business domain; communicate over the network; an opinionated form of service-oriented architecture; technology agnostic; a distributed system true of the set rather than one service; API-focused; decentralized governance; decentralized data management; designed for failure, each re-grounded in this project's FastAPI/Django stack rather than stated abstractly." caption="Figure 3.1: The ten traits 'microservices' is actually promising" %}

1. **Independently deployable.** A FastAPI service ships on its own
   schedule, not the Django monolith's shared release train.
2. **Modeled around a business domain.** A service boundary matches a
   bounded context (order, inventory, payment), not a technical layer like
   "data access" or "serialization."
3. **Communicate over the network.** HTTP, gRPC, or Kafka, not an in-process
   Django app import; what used to be a stack trace becomes a distributed
   trace.
4. **An opinionated form of service-oriented architecture.** The same
   integration ideas SOA introduced, with much stronger defaults about size
   and ownership than SOA ever enforced in practice.
5. **Technology agnostic.** One team's FastAPI service can run on a
   different language entirely than its neighbor's, without coordination.
6. **A distributed system, true of the set, not of one service.** Six
   services together form a distributed system, with everything that implies
   about partial failure and the loss of one shared transaction boundary.
7. **API-focused.** Internals hide behind the service's own API, rather than
   being exposed through a shared library or a shared table.
8. **Decentralized governance.** How a service is built is pushed to the
   team that owns it, not mandated from one shared `settings.py`.
9. **Decentralized data management.** Each service owns its own schema, not
   the single shared Postgres schema the monolith started with.
10. **Designed for failure.** Built on the assumption that any one service
    can be unavailable at any moment, rather than the monolith's implicit
    assumption that if the process is up, every app inside it is reachable.

None of these ten traits is a goal on its own. A service that is
independently deployable but still writes to the monolith's shared schema
has traded one coupling axis for a harder-to-see one; a "service" that is
technology-agnostic but synchronously blocks on four others for every
request has become a distributed monolith with extra network hops. Together,
though, these ten traits are the destination the strangler-fig sequence in
Part 5 is built toward, extraction by extraction, and every chapter that
follows checks each extraction against as many of them as the step in
question actually earns.

## "Microservices are not the goal"

State the uncomfortable part directly: nobody's customer has ever asked for
microservices. They asked for the order page to load fast, for a payment
failure to not also break browsing, for a new notification channel to ship
in a sprint instead of a quarter. Microservices are a means some systems use
to get those outcomes; they are not the outcome. A team that adopts them
because a conference talk made them sound inevitable, without first
establishing which delivery or operability problem they're solving, is
optimizing the wrong variable, and will discover, usually around the third
service, that they have rebuilt the monolith's coupling problems with
network calls standing in for function calls, minus the monolith's one real
advantage: a transaction that actually commits atomically across everything
it touches.

That discovery has a name: the **distributed
monolith**. It looks like microservices on an architecture diagram (separate
repositories, separate deployables, separate databases even) but behaves
like the original monolith under the hood, because every service still has
to be deployed in lockstep with three others, or because a single logical
transaction still spans five service boundaries synchronously, or because
one shared library still gets vendored into every service and upgraded
everywhere at once. The diagram changed; the coupling didn't. Chapter 13
gives this failure mode its full vocabulary (afferent and efferent coupling,
Khononov's coupling dimensions, Constantine's taxonomy), but the trait list
above is enough to self-check against right now: a split that doesn't earn
most of those ten traits isn't a microservices migration, it's a
reorganization of file paths.

## When microservices are the wrong call

Three conditions, any one of which should slow a team down and make them
read Chapter 4's assessment rubric before committing to a split:

**The team is too small to own the operational surface a split creates.**
Each extracted service brings its own deployment pipeline, its own
on-call surface, its own schema migrations, its own dependency upgrades.
A two-person team splitting a monolith into eight services has not reduced
its workload: it has multiplied its operational surface area by eight
while keeping the same headcount to answer pages on all of them.

**The domain boundaries are actually unclear.** Event storming (Chapter 12)
and context mapping (Chapter 11) exist because drawing a service boundary in
the wrong place is expensive to undo: a database can be refactored in an
afternoon; an API contract a dozen clients already depend on cannot. Cutting
services along boundaries nobody has actually validated trades one kind of
technical debt for a worse kind: coupling that now requires a coordinated,
multi-team release to fix instead of a single pull request.

**The system's actual bottleneck is somewhere else entirely.** A slow query
plan, a missing index, or an N+1 query pattern will not get faster by moving
to microservices: it will get slower, because the same badly-shaped query
now also pays network latency and serialization overhead on top of the
database time it was already losing. Splitting a system before fixing its
actual hot path is a classic case of treating a symptom's address, not its
cause.

None of these three conditions describes this book's own monolith, which is
the point: Chapter 4's rubric runs this reference system through the same
assessment a reader should run their own system through, and the monolith
scores as a believable, unglamorous candidate for incremental
re-architecture, not a strawman built to make the "yes, split it" answer a
foregone conclusion.

## Why big-bang rewrites fail

The alternative to incremental extraction is the big-bang rewrite: freeze
the old system, build a new one from scratch, cut over on a single day. It
fails often enough, and in a specific enough pattern, that the pattern
deserves a name rather than taking it on faith.

{% include excalidraw.html file="rewrite-vs-strangler-risk" alt="A risk-shape contrast. Left: the big-bang rewrite concentrates three simultaneous bets (correctly understanding every piece of accumulated behavior, outbuilding the old system's decay, and the business tolerating a long stretch of no new value shipped) into one irreversible cutover at the end. Right: the strangler fig distributes the same risk across many small, independently reversible steps, starting with the review extraction live behind a flag before any other bounded context has been touched." caption="Figure 3.2: Why a big-bang rewrite concentrates risk a strangler fig distributes" %}

A big-bang rewrite makes three bets simultaneously, and every one of them
has to land before the first byte of new value reaches a user. It bets the
team correctly understood every piece of behavior the old system
accumulated, including the behavior nobody remembers choosing in the first place,
the edge case a support ticket from three years ago papered over, the
rounding rule a finance audit insisted on. It bets a rebuild of comparable
scope can be built faster than the old system decays underneath it: a race
the rewrite usually loses, because the old system keeps acquiring small
fixes and the new one keeps acquiring scope creep from stakeholders who
correctly notice the rewrite is their only chance to also get the features
they've wanted for years. And it bets the business can tolerate a long
stretch where almost no new value ships to users, because the team's
attention is split between keeping the old system alive and finishing the
new one. A rewrite that is ninety percent complete delivers zero percent of
its value; a monolith extracted one bounded context at a time delivers
value at every single cutover.

The strangler fig, this book's chosen strategy, takes the opposite bet:
distribute the same underlying risk across many small, independently
reversible steps instead of concentrating it into one irreversible moment.
This project's own concrete anchor is the first step: the review
extraction in Chapter 15 is a small slice of the system, live behind the
ASGI strangler proxy's flag, before any other bounded context has been
touched. Because the monolith and the new service run side by side behind
that flag until the new service is proven equivalent, the project can pause,
slow down, or reverse a single extraction without threatening anything else
in flight. Chapter 4 names the full strategy menu this choice is picked
from; this chapter's job is only to establish why the alternative, stop
everything, rewrite everything, cut over once, carries a risk shape no
amount of careful planning fully retires.

## Coupling compounds: it doesn't just add up

This book's own review extraction turned up a finding that needs stating
before the numbers, because the numbers would otherwise be read the wrong
way. Phase A, an illustrative sketch where FastAPI routes bridge onto the
Django ORM via `sync_to_async`, never actually shipped as running code, and
Phase B, the real, shipped service, idiomatic FastAPI with async
SQLAlchemy and its own queries, measure as **statistically
indistinguishable** on raw process-startup time and import-only memory.

{% include excalidraw.html file="migration-metrics-review" alt="A bar-style comparison of Phase A (illustrative, Django ORM bridged via sync_to_async) versus Phase B (shipped, idiomatic FastAPI plus async SQLAlchemy): import/startup time 0.32-0.35s versus 0.35-0.36s, import-only RSS about 73.5MB versus about 72.3MB: the two bars drawn nearly equal length because the near-equality is the finding, not a rendering quirk." caption="Figure 3.3: Phase A vs. Phase B: a structural win, not a startup-time number" %}

Import/startup time measured 0.32–0.35 seconds for Phase A against 0.35–0.36
seconds for Phase B; import-only resident memory measured about 73.5 MB
against about 72.3 MB. Those two bars are drawn nearly equal length in the
figure for exactly that reason: the near-equality *is* the finding, and both numbers
are dominated by FastAPI and Pydantic v2's own import graph, so swapping out
the ORM barely moves the needle at process-startup granularity. If this
chapter tried to sell you a dramatic speedup number here, it would be
selling you something the data doesn't say.

The real Phase A-to-Phase B payoff is structural, not a stopwatch reading:
Phase B has no synchronous ORM bridged into an async framework via
`sync_to_async` on every query, and no hard build-time dependency on the
entire monolith just to reach one model. That is coupling retired, not
milliseconds saved, and it is exactly the kind of result this book
commits to reporting in full throughout: a migration metric that doesn't
move is still worth measuring, because knowing it didn't move tells you
where the actual payoff is and isn't.

That distinction matters because coupling is the quantity this whole book
is actually optimizing, and coupling does not add: it compounds. Two
bounded contexts sharing one table is one coupling point; add a third
context reading that same table and the number of pairwise interactions
that can break each other doesn't grow by one, it grows combinatorially,
because now any change to the shape of that table has to be checked against
every context touching it, not just the two that were there first. The
monolith's own `SMELLS.md` catalogues exactly this shape of problem (cross-
app foreign keys, one ACID transaction spanning six contexts, a shared
schema no single team owns outright), and Chapter 9 walks each smell in the
actual source tree. The reason extraction order matters as much as it does
(Chapter 4's rubric, Chapter 13's coupling ladder) is a direct consequence
of this compounding: cutting the most tightly coupled context first, before
the mechanism for cutting it has been proven anywhere else, is strictly
harder than cutting the one bounded context that turns out to have no
synchronous calls in or out of it at all, which is exactly why Review goes
first, and exactly why Chapter 7's worked loop uses that extraction as its
evidence.

## What's next

This chapter made the case for modernizing at all, named the conditions
under which that case does not hold, and argued that incremental extraction
proven equivalent at every step, with measured properties as the payoff,
not an architecture diagram as the goal, is what separates a successful
modernization from a failed rewrite. It did not yet say *which* strategy
fits a given system, or how to score one rigorously against the
alternatives. **Chapter 4, "Strategies & Assessment,"** takes that question
head-on: the Lift and Shift / Modernize and Extend / Rip and Rewrite menu
this book's own monolith is run through, the strategic-value-versus-change-
frequency framing that turns "should we modernize this" into a defensible,
measured answer, and the specific strategy this book commits to for every
chapter that follows.
