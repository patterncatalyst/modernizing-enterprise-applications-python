---
title: "Introduction & How to Use This Book"
order: 0
part: "Setting Up"
description: "The thesis — modernize with an agentic ADLC — the shipping through-line, the before/after, reading paths, conventions, and the reference-book map."
---

This book teaches you to modernize a real system by modernizing one. It does
not describe microservices patterns in the abstract and leave you to work out
how they apply to the tangle of code your organization actually runs. It
builds a believable Django monolith — order, inventory, payment, shipping,
notification, review, the shape of any shipping or e-commerce backend you
have ever worked on or inherited — and then takes it apart, one seam at a
time, in front of you. Every pattern in this book arrives at the moment the
migration forces it, not at the moment a chapter outline says it is time to
introduce it. By the last page, the monolith is frozen and no longer part of
the running system, six independent FastAPI services and a GraphQL gateway
stand in its place, and every step in between is checked into this repository
as runnable code, a passing test suite, and a written record of why it was
done the way it was done.

{% include excalidraw.html file="monolith-to-microservices-outcome" alt="Side-by-side before/after: one Django 5.2 LTS plus DRF deployable with six in-process bounded-context apps sharing a single Postgres schema and one transaction.atomic() checkout spanning order, inventory, payment, and notification, versus six independent FastAPI services plus a Strawberry GraphQL gateway, each owning its own schema, reached through one Starlette-based ASGI strangler proxy with a Kafka event backbone carrying the outbox and saga traffic." caption="Figure 0.1 — The monolith this book starts with, and the six-service system it ends as" %}

## Who this book is for

This is a book for people who already know how to write software and have
been asked, or will be asked, to take an existing production system apart
without breaking it. You do not need this book to learn what a saga is or
what a circuit breaker does — those explanations are here, but they are not
the point. The point is the harder problem underneath them: deciding *where*
to cut a system that nobody fully understands anymore, proving that the cut
preserved behavior nobody wrote down as a specification, and doing all of
that fast enough that the business case for modernizing still holds by the
time you finish.

If your experience is building new systems from a blank editor, parts of this
book will feel unfamiliar in a useful way — green-field instincts are often
exactly wrong against a decade of accumulated shortcuts, shared tables, and
implicit contracts between modules that nobody remembers making explicit. If
your experience is maintaining a monolith you did not write, large stretches
of this book will feel uncomfortably familiar, because the monolith built in
Part 3 is ordinary, with the same planted smells, so that the techniques that
cure them transfer directly to the unglamorous system on your own machine.
Either way, the assumed reader is an engineer or architect accountable for a
production system's behavior during a migration, not someone encountering
distributed systems for the first time. Prerequisite material — uv, Python
3.14, Django and FastAPI, a local observability stack — is handled once,
directly, in the next chapter, so this one can stay focused on what the book
argues and why.

## The central thesis

Strip away the specific technologies and this book makes one argument twice,
at two different altitudes. At the architecture altitude: a monolith becomes
a set of microservices by strangling it — cutting one bounded context free at
a time, behind a proxy, with a translation layer at the seam — rather than by
stopping the world and rewriting it. That argument is not new; Martin
Fowler's Strangler Fig pattern is decades old, and most of this book's
individual patterns — the anti-corruption layer, the outbox, the saga, CQRS —
are documented elsewhere in more depth than any one book could cover. What
those sources rarely show is a *complete, continuous* run through all of them
against one system, in the order a real migration actually forces, with the
code to prove each step actually worked. That is the gap this book fills: not
a new pattern catalog, but the catalog applied, in sequence, to a system you
can run.

At the execution altitude, the argument is less familiar and more critical
for how fast any of this can responsibly happen: the work in this book is not
done the way a modernization project was done five years ago, with a
requirements document, a design review, an implementation sprint, a QA pass,
and a change-advisory board, each stage handed off to a different role over
weeks. It is done through an **AI Development Lifecycle** — the **ADLC** —
built around a small number of coding agents working inside a disciplined,
seven-phase loop with exactly two places a human has to stop and decide. Part
2 names that lifecycle in full; the short version is that an agent can read
the legacy module, propose the seam, scaffold the extracted service, and
write its tests, all inside one sitting, and the thing that makes trusting
that output responsible rather than reckless is not a human rereading every
line — it is a fast, automated, re-runnable check standing between every
candidate change and anything that gets called "done."

That check is this book's second central idea, and it has a specific name
used consistently from here forward: the **behavior-equivalence suite**. Part
3 captures a contract test collection against the running monolith — every
endpoint, every status code, every edge case the monolith actually produces,
including the ones nobody would have thought to specify from scratch, because
they were discovered by exercising a real system rather than by imagining
one. That collection is never edited to make a later service pass. It is
re-run, unchanged, against every extracted service, and the **equivalence
gate** built from it blocks a service from being trusted — and blocks the
corresponding monolith module from being decommissioned — until the service
answers exactly as the monolith did. A behavior-equivalence suite is a
specific, checkable artifact with a specific job, not a mystical arbiter of
truth, and this book is deliberate about naming it precisely rather than
reaching for a vaguer shorthand. Chapter 7 shows this gate catching real
defects during this project's own extraction work, and the lesson is the one
this book repeats whenever the stakes are high enough to deserve it: a
passing suite is evidence that a change is safe, not proof, and the
discipline the ADLC asks for is to keep probing what would make the suite
pass by accident until the answer is nothing you can think of.

So the thesis, stated once in full: take a believable Django monolith and
modernize it into six FastAPI services and a GraphQL gateway, one pattern at
a time, in the order the migration itself demands, driven by an agentic ADLC
instead of a traditional SDLC, with a behavior-equivalence gate proving at
every step that the new code behaves like the old code did. Everything else
in this book — the parts, the chapters, the running example — exists to make
that one sentence concrete enough to execute against your own system.

## The running example

One system runs through every chapter: a shipping and e-commerce platform
built around six bounded contexts — **order**, **inventory**, **payment**,
**shipping**, **notification**, and **review**. It starts, in Part 3, as a
single Django deployable: one WSGI process, one shared Postgres schema, a DRF
REST API for all six contexts, and an order-placement flow that reaches into
inventory, payment, shipping, and notification inside one
`transaction.atomic()` block. That design is ordinary, built the way a team
under a real deadline five years ago would actually have built it, with
smells planted rather than accidental: a god checkout service, a single
database transaction spanning five contexts, a shared schema with
cross-context foreign keys, a synchronous notification send wedged inside
checkout, and a dual-write hazard between a database commit and an external
provider call. Each smell is tagged, in Part 3, to the exact later chapter
that cures it, so nothing about the monolith's design is incidental to the
argument this book is making.

From there, the monolith gets strangled one seam at a time, in order of
rising difficulty rather than domain importance: **review** first, because it
is REST-only with no synchronous dependency on anything else and therefore
the cheapest way to prove the entire extraction mechanism works end to end
before anything harder is asked of it; then **notification**, which
introduces an event backbone and the transactional outbox pattern; then
**inventory**, which requires a decomposed database and Debezium
change-data-capture to migrate state safely behind a gRPC seam; then
**payment** and **shipping**, which force a choreographed and then an
orchestrated saga because a single database transaction is no longer
available once those contexts live in separate services; and finally
**order** itself, together with a GraphQL gateway, because the core aggregate
and the hardest coupling are saved for last rather than tackled first. Every
one of those six extractions is executed through the full migration process
this book teaches, not a single worked example followed by five summaries —
each gets its own chapter, its own equivalence-gate run, and its own "ADLC in
Action" callout showing the real trace that produced it.

{% include excalidraw.html file="extraction-sequence-ladder" alt="The six extractions in the order this book executes them, rising in difficulty left to right: review (ch.15, REST leaf on a shared schema), notification (ch.17, async transactional outbox), inventory (ch.19, Debezium CDC plus a gRPC seam), payment (ch.23, choreographed saga), shipping (ch.24, orchestrated saga with crash-resume), and order with its Strawberry GraphQL gateway (ch.26, CQRS)." caption="Figure 0.2 — The extraction order: rising difficulty, not rising domain importance" %}

By the final chapter of the extraction sequence, the monolith's modules have
all been decommissioned from the running system, and what remains is the six
services, communicating over REST, gRPC, and GraphQL as each relationship
actually calls for, deployed to a Kubernetes substrate, observed through
distributed tracing, and delivered through a CI pipeline that runs the
equivalence gate on every change. That end state is close enough to
production practice that the "after" picture in this book is a system you
could actually run, not a diagram you have to take on faith.

## How this book is organized

The book runs in eleven parts, numbered 0 through 10, and the ordering is
itself part of the argument: it follows the chronology of an actual
migration, not the logical order a textbook might choose. You are reading
**Part 0, Setting Up**, which handles the toolchain, the project ledger, and
the mechanics of running every example before anything else is asked of you.
**Part 1, Why Modernize**, steps back from code entirely to make the business
and engineering case for modernizing at all — including when microservices
are the wrong answer — before committing a single line to a specific
strategy. **Part 2, The ADLC**, is where the lifecycle this book runs on gets
named in full: its seven phases, its two human gates, the agents and tooling
that carry each phase out, and a complete worked run of the loop on a trivial
change, so that the model is demonstrated once at low stakes before it is
trusted at high stakes.

**Part 3, The Reference Monolith**, builds the "before" picture described
above in full, including the test suite that becomes the behavior-equivalence
suite used in every later chapter. **Part 4, Finding the Seams**, is where
domain-driven design, event storming, and coupling theory earn their keep —
not as theory for its own sake, but as the actual method used to decide where
the six extraction boundaries in this book's monolith actually are. **Part
5, The Strangler Fig in Practice**, introduces the strangler proxy itself and
walks the first two extractions, review and notification, including the
anti-corruption layer and content-based routing that make every later
extraction mechanical rather than improvised.

**Part 6, Data Across the Seam**, is where the migration's hardest and most
underestimated problem gets the space it needs: moving from one shared
database to data each service owns, by way of change-data-capture, the
outbox pattern done correctly, and the CQRS read side a later gateway
depends on — ending with what is actually given up when ACID consistency
becomes eventual consistency. **Part 7, Coordinating Across Services**, is
where the payment and shipping extractions force the distributed-transaction
question that a shared database had been quietly answering by default,
resolved through a choreographed and an orchestrated saga and a resilience
toolkit for the failure modes a single process never had to think about.
**Part 8, Communication & Contracts**, completes the strangler with the order
extraction and its GraphQL gateway, and then turns to what the system was
migrated *to*: the FastAPI chassis conventions underneath every service, and
a schema and contract registry that keeps eight independently deployed
services accountable for the shapes they exchange.

**Part 9, Operating the Modernized System**, moves from building the services
to running them in production — deployment patterns, a service mesh, and
distributed tracing, on a Kubernetes substrate reserved for exactly the
chapters that need it rather than introduced on day one. **Part 10,
Delivering & Reflection**, names the actual CI pipelines this project runs —
the specific workflow files, the specific job that runs the equivalence gate
on every extraction, the specific supply-chain scan — and then closes by
walking the completed migration back against the pattern language it started
from, naming what this book left out and why, so the map it leaves you with
states its edges rather than pretending to be exhaustive.

## How to read this book

Every chapter from Part 3 onward that touches code follows the same shape on
purpose, so that once you have worked through one, you know how to work
through all of them: a short section naming the one new idea the chapter
introduces, a walkthrough of the real code explaining each meaningful call
and why it is there — written so that you could retype it yourself, not just
run it — a build-and-run section with the actual commands, and, where an
independent check exists, a cross-check against it. Chapters that are
conceptual rather than hands-on, including this one, are marked as such
rather than padded with a token example to look consistent; a chapter that
has nothing real to run says so instead of manufacturing a toy. Every
chapter, hands-on or not, ends with a verification-status note naming exactly
what was and was not confirmed by a real run, because a claim this book
cannot check is a claim it does not make silently.

The code is not a supplement to this book; it is most of the argument. Every
extraction chapter points at a corresponding directory under `examples/` —
the monolith itself lives permanently at `examples/00-monolith/`, the ASGI
strangler proxy at `examples/01-strangler-proxy/`, and each extracted service
in its own directory alongside it, with `examples/08-graphql-gateway/` as the
service this book's last extraction adds rather than replaces. Each of those
directories has a `README.md` explaining what you are watching happen and the
commands to build, start, and exercise it. The behavior-equivalence suite
itself lives under `tooling/newman/`, versioned alongside the monolith it was
captured from, and it is the same collection you will see re-run, unchanged,
in every later chapter's equivalence-gate result.

Because the book is a sequence of extractions, some of the code it quotes
exists only at a particular point along the way. `main` is the finished
system — the six extracted services, the GraphQL gateway, and the flagless
strangler proxy — and the `examples/00-monolith/` you find there is the
frozen deployable the monolith was reduced to once its last context left. The
complete, runnable monolith as it stood *before* any extraction lives on the
`reference/monolith-before` branch, tagged `v0-monolith`, and the repository
as it stood right after each individual extraction is tagged
`stage/01-review-extracted` through `stage/06-order-extracted`. So when a
chapter quotes code that a later extraction moved or removed, you will find
it on `reference/monolith-before`, or on the matching `stage/NN` tag, even
where `main`'s frozen monolith no longer carries it. Each citation's
`examples/…` path is the directory the code lived in at the point the
chapter describes; these branches and tags are how you check it out and run
it as it was then.

## The reference-book map

This book draws, by name and with every reuse recorded in
`_plans/reconciliation.md`, on two other projects rather than inventing
everything from scratch. The closer of the two is its own **Java sibling**,
*Modernizing Enterprise Applications* — the same shipping-and-e-commerce
domain, the same six extractions in the same order, a Spring Boot monolith
strangled into Quarkus and Apache Camel services instead of a Django monolith
strangled into FastAPI. Where this book's prose or a decision log row says
"unchanged from the Java sibling," that means the architectural argument
transfers even though not one line of code does; every stack-specific
mechanism — the proxy, the saga, the chassis — is re-authored for Python
rather than translated, and Chapter 6 names the one real capability gap
between the two books directly: there is no Python equivalent of the Java
sibling's Quarkus Agent and Camel MCP tooling, and this book says so instead
of quietly working around it. The second source is
**`cloud-native-design-patterns`**, a pattern catalog this project reuses
code from exactly once: the shipping extraction's orchestrated saga in
Chapter 24 adapts that catalog's already-documented, database-backed saga
orchestrator onto this project's own persistence stack rather than
re-authoring the same mechanism from a blank file. Both reuses are named
where they happen, not folded in silently, because a book that argues for an
auditable decision trail should keep one for its own borrowed code too.

## What you will be able to do by the end

Finishing this book should leave you able to do three concrete things you
could not reliably do before. First, given a real monolith, find the seams in
it — using strategic and tactical domain-driven design, event storming, and
coupling analysis as actual decision tools, not as vocabulary, so that the
order you cut things in is deliberate rather than accidental. Second, execute
an extraction end to end with a behavior-equivalence suite as the acceptance
gate: capture a contract suite against the system as it stands today, build
the strangler seam, migrate the code in disciplined phases, and prove with a
re-runnable check — not a feeling — that nothing observable changed before
you retire the old code. Third, run that entire process through an agentic
ADLC rather than a traditional SDLC: frame intent precisely enough for an
agent to act on, know which two moments require your judgment and which do
not, and keep a ledger disciplined enough that the next person — or the next
version of yourself, six months later — can trust the record of what was
done and why, without having to reconstruct it from memory.

## Where to go next

**Chapter 1, "Prerequisites & the Toolchain,"** gets your machine ready — uv,
Python 3.14, Django and FastAPI, Docker and the compose observability
stack — and ends with a gate you can run yourself to confirm the setup
actually works before you depend on it for anything else. **Chapter 2, "The
Project Ledger,"** introduces the project ledger in detail — the decision
log, the build plan, and the reconciliation record the ADLC's final phase
produces — as a template for the ledger you will want to keep on your own
migration, starting with the first decision you make. From there, Part 1
makes the case for why any of this modernization work is worth doing in the
first place — and when it is not.

---
*Verification status: <span class="status status--unverified">unverified</span>. Conceptual chapter — no runnable example lives under `examples/` for this chapter itself; its factual claims point at artifacts the `examples/` directories make checkable elsewhere in this book, including the six-context monolith and its deliberate smells (Part 3), the behavior-equivalence suite and the equivalence gate (Chapter 10 and Chapter 7), and the extraction history recorded in `_plans/reconciliation.md`.*
