---
title: "Strategies & Assessment"
order: 4
part: "Why Modernize"
description: "Lift & Shift, Modernize & Extend, Rip & Rewrite, the strategic-value x change-frequency 2x2, the ease-of-migration rubric, and the evolution arc reframed for 2026."
---

Chapter 3 made the case that modernization needs a reason before it needs a
plan — that microservices are never the goal, only sometimes the answer.
This chapter assumes you have a reason and asks the two questions that
follow from it, in order: *which* strategy fits the system you actually
have, and once you've picked one, *in what sequence* do you cut it apart
without breaking it. Those are different questions with different failure
modes. Pick the wrong strategy and you spend a year modernizing the wrong
thing the wrong way. Pick the right strategy but the wrong sequence and you
spend the first three months of the right project proving nothing except
that the hardest part of the system is, in fact, hard — a fact that was
true before you started and is expensive to relearn under deadline
pressure. This chapter answers both, and commits this book to a specific,
named strategy and a specific extraction order before Part 3 builds the
monolith that strategy runs against.

## The strategy menu: what each option actually buys

Every modernization effort, regardless of the vocabulary a given vendor
attaches to it, is choosing a point on the same spectrum: how much of the
existing system's *shape* survives the effort, versus how much of its
*behavior* has to survive it. At one end you touch almost nothing about the
system's internal shape and simply move where it runs. At the other you
discard the shape entirely and rebuild behavior from a blank editor. Naming
the full menu matters, because this chapter's strategy choice only makes
sense read against all of it.

- **Lift and Shift** — move the running system onto new infrastructure with
  its internal architecture essentially untouched: containerize the Django
  deployable as-is, deploy it on a modern platform, leave the code, the data
  model, and the integrations exactly as they were. The least complex
  option on the menu, and often the fastest route to a measurable cost
  benefit for a system that doesn't justify deeper investment — but it buys
  nothing about the system's actual architecture. The shared schema is
  still shared and the single deployable is still single; every structural
  reason the system was expensive to change before the move is expensive to
  change after it, just on newer hardware.
- **Modernize and Extend** — change the system's internal structure — its
  module boundaries, its data ownership, its deployment topology — while
  preserving its external behavior throughout the change. The legacy
  Django monolith stays intact while a new architectural layer is added
  alongside it, with new integration points connecting old and new, cut
  over incrementally rather than all at once. This is where the strangler
  fig lives, and it's the family this book commits to.
- **Rip and Rewrite** — discard most or all of the existing codebase and
  write new software against the same, or a changed, set of requirements.
  The cleanest result on paper, at the highest risk on the menu: a long,
  uninterrupted stretch where the new system doesn't yet do what the old
  one does, no way to verify partial progress against production behavior
  until the whole thing is finished, and the well-documented
  "second-system effect," where the rewrite quietly grows scope to fix
  everything wrong with the original instead of only modernizing it.

{% include excalidraw.html file="migration-strategy-spectrum" alt="Four migration strategies compared side by side: big-bang rewrite (highest risk, one long cutover), the strangler fig (this book's choice, incremental and independently verifiable), branch-by-abstraction (an in-process seam toggle), and parallel-run (a live shadow comparison of two running paths)." caption="Figure 4.1 — The migration-strategy spectrum, from big-bang rewrite to the strangler fig" %}

Each option trades the same two currencies against each other: how much
risk you take on at once, and how long you wait before the system is
measurably better. Lift and Shift is cheap and fast, and that's exactly its
appeal when a system's strategic value is modest and its change frequency
is low — a real win in weeks, without betting the project on understanding
a codebase nobody currently understands deeply. Rip and Rewrite is the
strategy of choice only when a system's required rate of change has
outgrown what incremental modernization can plausibly keep up with — a rare
enough condition that this book's own monolith, built from the start as a
believable, unglamorous candidate, does not meet it. Modernize and Extend
sits in the middle, and it's the family every remaining chapter in this
book commits to and builds.

## The value-versus-change 2x2

Deciding among the three strategies starts with a plot: a candidate
system's **strategic value** against its **change frequency**. The quadrant
a system lands in suggests which strategy fits.

{% include excalidraw.html file="modernization-value-vs-change-2x2" alt="A four-quadrant plot of strategic value against change frequency. High value, high change frequency favors incremental re-architecture. Low value, low change frequency favors Lift and Shift or Retain. This book's own monolith is plotted high on strategic value — the order-taking and fulfillment path for a shipping business — and, on the ease-of-migration rubric, difficult on data (one shared schema with cross-app foreign keys) and moderate everywhere else." caption="Figure 4.2 — Where this book's monolith lands on the value-versus-change quadrant" %}

High strategic value and high change frequency — a system the business is
actively investing in and iterating on — is exactly where incremental
re-architecture earns its cost, because every future feature lands faster
once the architecture stops fighting the team that maintains it. Low
strategic value and low change frequency is Lift and Shift territory, or
simply leaving the system alone; there's no return on a deeper investment.
A second, orthogonal axis matters just as much: an **ease-of-migration
rubric**, scored across code, configuration, data, secrets, network
topology, and system type, rated easy, moderate, or difficult — because a
system can be strategically critical *and* difficult to touch at the same
time, and that combination is precisely where sequencing, not strategy
choice, becomes the hard problem.

This book's monolith sits in exactly that combination by design: high
strategic value — it's the order-taking and fulfillment path for a shipping
business — and, on the ease-of-migration rubric, difficult on data (one
shared Postgres schema with cross-app foreign keys, catalogued in full in
`examples/00-monolith/SMELLS.md`) and moderate everywhere else. That's not
an accident of narrative convenience; it's an unglamorous candidate chosen
to make that point, scored the same way a reader's own system should be scored,
rather than a strawman built to make "yes, split it" a foregone conclusion.

## Why this book commits to incremental strangler-fig re-architecture

Given that plot, the commitment made at the end of Chapter 3 follows
directly: incremental, strangler-fig re-architecture, gated at every step
by a behavior-equivalence suite, executed within the Modernize and Extend
family. Three properties make that the right fit for a high-value,
difficult-to-touch system specifically, rather than a default preference
for "incremental is always better."

**Reversibility, held open as long as possible.** A strangler-fig cutover
is a feature flag, not a deployment. `STRANGLER_REVIEW_ENABLED`, read from
the environment, decides whether `/api/reviews` traffic reaches the
monolith or the extracted service; flipping it back is a config change and
a restart, right up until the monolith's own module is decommissioned.
That window — explored in full with real evidence in Chapter 7 — is the
single biggest reason incremental extraction survives contact with a
production system that a big-bang rewrite does not: a bad bet costs a flag
flip, not a rollback of months of work.

**Continuous delivery of value.** Each extraction ships something real —
Review live on its own service, Notification moved to event-driven delivery
— the moment its equivalence gate goes green, not after the whole
modernization finishes. A rewrite that is ninety percent complete delivers
zero percent of its value to a user; a monolith extracted one bounded
context at a time delivers value at every single cutover.

**Proof before commitment.** The equivalence suite — the same Newman
collection, unedited, run against the monolith and then against every
extracted service in turn — is what makes "proven equivalent" a checkable
claim rather than an assertion. Chapter 10 builds that suite; every
extraction chapter from Chapter 15 onward treats a green run as the gate
that has to pass before the next flag gets flipped.

## Assessing the monolith: how do you choose an order

A strategy answers "how do we cut." It doesn't answer "what do we cut
first, and in what order after that." Getting that second question wrong
doesn't show up as a failed migration — it shows up as a migration that
technically succeeds while teaching the team the wrong lessons in the wrong
order, because the hardest seam got tackled before anyone had practiced on
an easy one. Four criteria, applied together rather than separately, turn
"where do we start" from a guess into a defensible answer.

**Coupling and cohesion.** A direct, measurable question for each candidate
bounded context: how many other contexts does this one call synchronously,
and how many call into it? A context with zero synchronous collaborators in
either direction can be extracted and verified in isolation; a context
wired into four others' internals cannot be extracted without first
untangling, or at minimum proxying, every one of those four relationships.
Coupling is the single strongest predictor of how much *other* work an
extraction drags behind it.

**Change frequency.** The same signal from the 2x2 applies again at the
per-context level: a context the business rarely touches is a low-stakes
place to validate a new mechanism, because nobody is actively shipping
features against it that a migration could collide with. A context under
constant feature development is exactly where the payoff of modernizing is
highest — but also where a botched extraction does the most damage to
delivery velocity, which argues for tackling it once the mechanism has
already been proven elsewhere, not first.

**Risk and blast radius.** Independent of coupling: what breaks, and for
whom, if this extraction goes wrong? Does it sit on the revenue path, does
a failure cascade into contexts not yet touched, and can the cutover be
reversed cheaply if the equivalence gate catches a regression after
rollout has already begun? A context that fails loudly and in isolation is
a far safer first bet than one that fails silently and spreads.

**Data entanglement.** Shared schema and cross-context foreign keys are a
distinct axis from code coupling — two contexts can be decoupled in their
service layer while still welded together at the database. A context with
its own schema, or one that can plausibly get one without a data migration,
is cheaper to extract than one that shares tables with everything else in
the system.

None of these four criteria is sufficient alone. A context can be
low-coupling and still high-risk if it sits on the revenue path; a context
can be rarely changed and still deeply data-entangled. A defensible
extraction sequence scores every candidate against all four together and
orders from lowest combined score to highest — strategic importance decides
*whether* to modernize a system at all; it's the wrong signal for deciding
*which seam to cut first* inside a system you've already committed to
modernizing, because the most important context is almost never the least
risky one to practice on.

## This book's own answer: review first, and why

The preceding criteria aren't abstract here — they're exactly the ones
this project's own build plan applies to its six bounded contexts, and the
resulting sequence is the one every extraction chapter that follows executes: **review,
then notification, then inventory, then payment, then shipping, then order
together with its GraphQL gateway.** Walking that sequence against the
criteria above is worked evidence of the assessment method, not just a plan
to take on faith.

**Review goes first**, and the reasoning is a direct application of
coupling and risk, not an arbitrary starting point. Review is a REST-only
leaf: nothing in order, inventory, payment, shipping, or notification calls
into review synchronously, and review calls nothing in any of those five
contexts either. Its only entanglement with the rest of the monolith was
never architectural — it shares the monolith's authentication setup with
every other endpoint despite having no runtime dependency on anything that
authentication actually protects. That's about as close to zero coupling as
a bounded context inside a real system gets, and it means Review can be
extracted, stood up behind the strangler proxy, and verified against the
equivalence suite with nothing else in the system able to confound the
result. If the extraction fails, the cause is the extraction mechanism
itself — the proxy, the equivalence gate, the cutover flag — not some
tangled dependency on a context not yet touched. That's exactly what a
first extraction needs to be worth: the full mechanism proven once, end to
end, against the lowest-risk possible subject, before it's asked to carry
any real domain complexity. It's an anticlimactic first win by design —
nobody is impressed that reviews moved to their own service — and that's
the point: the second extraction is where the mechanism starts paying for
itself, because by then it already works.

**Notification comes second** because it's the next-lowest-coupling
context, but it isn't risk-free in quite the same way Review was: nothing
calls Notification's output synchronously, but Notification previously sat
*inside* the checkout code path, invoked directly from order placement.
That difference is why Notification's extraction forces the next new
mechanism rather than repeating Review's: a transactional outbox in the
monolith publishes the event reliably, and Notification becomes this
project's first event-driven, Kafka-consuming service rather than another
REST leaf. Rising difficulty, not rising domain importance, is the
ordering principle.

**Inventory comes third** because order needs it synchronously at checkout
time, which Review and Notification did not require of anything, and
because Inventory's data lives in the same shared schema the rest of the
monolith uses — the data-entanglement axis, not the coupling axis, is what
makes Inventory harder than Notification. Extracting it forces a
change-data-capture backfill into a newly owned database before cutting
writes over, the first time this sequence solves a data-ownership problem
rather than only a code-boundary problem.

**Payment and shipping come fourth and fifth** because extracting either
one removes a piece of the monolith's single transaction spanning checkout,
which is the point where the system can no longer get distributed-
transaction safety without writing any extra code — payment forces a choreographed saga over
Kafka, shipping the same underlying problem solved by a reused,
database-backed orchestrator, so the two extractions teach both
coordination styles back to back on one codebase rather than in the
abstract.

**Order, together with its GraphQL gateway, comes last** because it's, by a
wide margin, the highest-coupling, highest-risk context in the whole
system: the monolith's order-placement path reaches directly into
inventory's, payment's, shipping's, and notification's code, and every one
of the five extractions before it exists in part to remove one of those
direct dependencies before order itself has to move. By the time order's
turn comes, the strangler proxy, the equivalence gate, and the whole ADLC
loop that produces each extraction have all been exercised five times
already — which is precisely why the hardest, highest-value seam is saved
for when the mechanism extracting it is the most proven, not the newest.

{% include excalidraw.html file="strangler-evolution-arc" alt="Four left-to-right snapshots of the system's topology over the course of the book: one Django deployable with six in-process apps and one shared schema; the same monolith with the ASGI strangler proxy standing in front, every call still passing through unchanged; review and notification live as FastAPI services behind the proxy while four contexts still answer from the shrinking monolith; and the fully extracted end state, a flagless edge router in front of all six services plus the GraphQL gateway, with the monolith decommissioned from the running topology and kept frozen as the 'before' referent." caption="Figure 4.3 — The evolution arc this book actually executes, snapshot by snapshot" %}

## Review-first ordering as a discipline, not a one-time choice

The sequence above is specific to this book's monolith, but the discipline
behind it generalizes, and it's worth separating the two before moving on.
The discipline is: score every remaining candidate against coupling, change
frequency, risk, and data entanglement *again* after each extraction,
rather than committing to the full six-context order up front and executing
it blindly. Inventory's data-entanglement problem wasn't visible with the
same clarity before Review and Notification had already proven the
mechanism works on simpler subjects — the assessment runs are themselves a
kind of reconnaissance into how the next seam actually behaves, which is
exactly the role Chapter 12's event storming plays in finding seams the
assessment criteria alone can miss. A reader applying this chapter's method
to their own system should expect the same thing: the order you can
confidently name for contexts one and two will look obvious in hindsight,
and the order for contexts five and six will depend on what the first four
extractions actually taught you about where this particular system's real
coupling lives.

## What's next

This chapter picked a strategy — incremental, strangler-fig re-architecture,
gated on behavioral equivalence — and the method for ordering the cuts
inside it, and showed both applied to this book's own system as worked
evidence rather than assertion. Two things still have to happen before any
of that method can run: the lifecycle that will actually *execute* each
step, and the system the method will be run against. **Part 2, "The AI
Development Lifecycle (ADLC),"** names that lifecycle in full, starting
with **Chapter 5, "From SDLC to ADLC."** **Part 3, "The Reference
Monolith,"** then builds the six-context system this chapter has been
describing in the abstract, including the deliberate smells each extraction
above is designed to cure, and the test suite that becomes the
behavior-equivalence suite every later chapter depends on.

---

*Verification status: <span class="status status--unverified">unverified</span> —
conceptual chapter, no runnable example under `examples/`. Its claims about
extraction order are checkable against `examples/00-monolith/SMELLS.md`
(the coupling this chapter's "review first, order last" argument depends
on). The strategy and strangler-fig mechanics named here are built out,
with running code, in Part 3 and Part 5.*
