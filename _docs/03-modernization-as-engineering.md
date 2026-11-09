---
title: "Modernization as Engineering, Not Fashion"
order: 3
part: "Why Modernize"
description: "Modernization goals, the ten microservice traits, 'microservices are not the goal,' and when microservices are a bad idea."
---

## Learning objectives

By the end of this chapter you can:

- Name the delivery or operability problem a modernization solves, with a metric.
- List the ten traits a microservices architecture actually promises and use them to spot a distributed monolith.
- Recognize the three conditions under which splitting a monolith is the wrong call.
- Explain why a big-bang rewrite concentrates risk that a strangler fig distributes.
- Read a migration metric that didn't move as evidence of where the payoff is.

## Why this matters

Modernize when it solves a problem you can name and measure, and it has to run as disciplined engineering with a safety net, not as a leap toward a fashionable architecture. Two corollaries follow. Microservices aren't the goal: a project that treats them as one ends up with a distributed system that has all of a monolith's coupling and none of its simplicity. And the discipline is what separates a modernization that ships value continuously from a rewrite that ships nothing until it ships everything or quietly dies. Both point at the same destination: incremental, strangler-based extraction, with a behavior-equivalence suite guarding every step.

## Why modernize at all

A system that works, that nobody touches under duress and that the business can still staff and extend, doesn't need modernizing because its stack is unfashionable. Two kinds of problem justify the risk.

**Delivery problems** show up in how fast a team ships. With a single Django deployable, a notification template tweak, a payment-provider integration and a shipping-label format ride the same release train, wait on the same migration and share one regression surface. Teams avoid code they don't own because a mistake's blast radius is the whole system. Release cadence slides from weekly to monthly to "whenever we work up the nerve." That isn't a discipline problem; it's the structural result of one deployable owning every concern.

**Operability problems** show up when the system runs. A payment bug under load takes down checkout and also the ability to browse last month's reviews, because both share a runtime, a connection pool and a failure domain. Scaling is all-or-nothing: if order placement needs ten times the capacity in a flash sale, the monolith scales everything ten times, including the notification worker that was idle.

Both have a measurable shape: time-to-ship for a change inside one bounded context, blast radius of one component's failure, and the ratio between a service's actual load and the capacity it's forced to share. The bar is "I can name the metric and it's bad," not "this looks old."

## The ten microservice traits

"Microservices" is often used as a synonym for "small HTTP services," which flattens a specific idea into a weak one. These traits are the actual promise, restated for the Django and FastAPI stack.

{% include excalidraw.html file="microservice-traits" alt="A ten-cell grid of microservice traits: independently deployable; modeled around a business domain; communicate over the network; an opinionated form of service-oriented architecture; technology agnostic; a distributed system true of the set rather than one service; API-focused; decentralized governance; decentralized data management; designed for failure, each re-grounded in the FastAPI and Django stack rather than stated abstractly." caption="Figure 3.1: The ten traits 'microservices' is actually promising" %}

1. **Independently deployable.** A FastAPI service ships on its own schedule, not the monolith's release train.
2. **Modeled around a business domain.** A boundary matches a bounded context (order, inventory, payment), not a technical layer like "data access."
3. **Communicate over the network.** HTTP, gRPC or Kafka, not an in-process Django app import; what was a stack trace becomes a distributed trace.
4. **An opinionated form of service-oriented architecture.** The integration ideas of SOA, with stronger defaults about size and ownership.
5. **Technology agnostic.** One team's service can run on a different language than its neighbor's without coordination.
6. **A distributed system, true of the set.** Six services together carry partial failure and the loss of one shared transaction boundary.
7. **API-focused.** Internals hide behind the service's API, not a shared library or shared table.
8. **Decentralized governance.** How a service is built is the owning team's call, not mandated from one shared `settings.py`.
9. **Decentralized data management.** Each service owns its schema, not the monolith's single shared Postgres schema.
10. **Designed for failure.** Any service can be unavailable at any moment, unlike the monolith's implicit assumption that if the process is up, every app in it is reachable.

No trait is a goal alone. A service that is independently deployable but still writes to the monolith's shared schema has swapped one coupling for a harder-to-see one. A technology-agnostic "service" that blocks synchronously on four others per request is a distributed monolith with extra network hops. Together the ten are the destination of the strangler sequence, and each extraction is checked against as many as that step earns.

## Microservices are not the goal

Nobody's customer has asked for microservices. They asked for the order page to load fast, a payment failure not to break browsing, and a new notification channel to ship in a sprint instead of a quarter. A team that adopts microservices because a talk made them sound inevitable, without naming the problem, optimizes the wrong variable. Around the third service it finds the monolith's coupling rebuilt with network calls for function calls, minus the monolith's one real advantage: a transaction that commits atomically across everything it touches.

That outcome is the **distributed monolith**. On a diagram it looks right: separate repositories, deployables, even databases. Underneath, every service still deploys in lockstep with three others, or one logical transaction still spans five service boundaries synchronously, or one shared library is vendored into every service and upgraded everywhere at once. The diagram changed; the coupling didn't. A split that doesn't earn most of the ten traits is a reorganization of file paths.

## When microservices are the wrong call

Any one of three conditions should slow a team down and send it to a strategy assessment before committing to a split.

| Condition | Why it hurts |
|---|---|
| The team is too small to own the operational surface | Each service brings its own pipeline, on-call surface, schema migrations and dependency upgrades. Two people splitting a monolith into eight services multiply the operational surface by eight with the same headcount answering pages |
| The domain boundaries are unclear | A database refactors in an afternoon; an API contract a dozen clients depend on doesn't. Cutting along unvalidated boundaries trades technical debt for coupling that needs a coordinated multi-team release to fix instead of one pull request |
| The real bottleneck is elsewhere | A slow query plan, a missing index or an N+1 pattern gets slower after a split, because the same query now pays network latency and serialization on top of the database time it was already losing |

None of the three describes the reference monolith, which is the point: it's a believable, unglamorous candidate for incremental re-architecture, not a strawman built to make "yes, split it" a foregone conclusion.

## Why big-bang rewrites fail

A big-bang rewrite freezes the old system, builds a new one from scratch and cuts over on one day. It fails in a specific pattern.

{% include excalidraw.html file="rewrite-vs-strangler-risk" alt="A risk-shape contrast. Left: the big-bang rewrite concentrates three simultaneous bets (correctly understanding every piece of accumulated behavior, outbuilding the old system's decay, and the business tolerating a long stretch of no new value shipped) into one irreversible cutover at the end. Right: the strangler fig distributes the same risk across many small, independently reversible steps, starting with the review extraction live behind a flag before any other bounded context has been touched." caption="Figure 3.2: Why a big-bang rewrite concentrates risk a strangler fig distributes" %}

It makes three bets at once, and all must land before the first byte of new value reaches a user:

- **It understood every behavior the old system accumulated**, including what nobody remembers choosing: the edge case a three-year-old support ticket papered over, the rounding rule a finance audit insisted on.
- **A comparable rebuild outruns the old system's decay.** The old system keeps collecting small fixes while the new one collects scope creep from stakeholders who rightly see the rewrite as their only chance at features they've wanted for years.
- **The business tolerates a long stretch with almost no new value shipped**, because attention is split between keeping the old system alive and finishing the new one.

A rewrite that is ninety percent complete delivers zero percent of its value. A monolith extracted one bounded context at a time delivers value at every cutover.

The strangler fig distributes the same risk across many small, reversible steps. The first, the review extraction, is a small slice of the system live behind the ASGI strangler proxy's flag before any other context is touched. The monolith and the new service run side by side behind that flag until the service is proven equivalent, so one extraction can pause, slow or reverse without threatening anything else in flight.

## Pattern: Strangler Fig

Route traffic through a proxy, move one bounded context at a time to a new service behind it, and retire the old module only after the new service has answered identically.

| | Big-bang rewrite | Strangler Fig |
|---|---|---|
| Cutover | One, irreversible | One per context, each reversible |
| Value shipped before the end | None | At every cutover |
| Understanding of old behavior | Must be complete up front | Verified per extraction by the equivalence suite |
| Failure scope | Everything | One context |

## Coupling compounds

The review extraction turned up a finding to state before the numbers, because they're easy to misread. Phase A, an illustrative sketch that bridges FastAPI routes onto the Django ORM with `sync_to_async`, never shipped as running code. Phase B, the shipped service, is idiomatic FastAPI with async SQLAlchemy and its own queries. The two measure as statistically indistinguishable on process-startup time and import-only memory.

{% include excalidraw.html file="migration-metrics-review" alt="A bar-style comparison of Phase A (illustrative, Django ORM bridged via sync_to_async) versus Phase B (shipped, idiomatic FastAPI plus async SQLAlchemy): import and startup time 0.32 to 0.35 seconds versus 0.35 to 0.36 seconds, import-only RSS about 73.5MB versus about 72.3MB. The two bars are drawn nearly equal length because the near-equality is the finding." caption="Figure 3.3: Phase A vs. Phase B: a structural win, not a startup-time number" %}

| Measure | Phase A (illustrative) | Phase B (shipped) |
|---|---|---|
| Import and startup time | 0.32 to 0.35 s | 0.35 to 0.36 s |
| Import-only resident memory | about 73.5 MB | about 72.3 MB |

Both numbers are dominated by FastAPI's and Pydantic v2's own import graph, so swapping the ORM barely moves them. The Phase A to Phase B payoff is structural: Phase B has no synchronous ORM bridged into an async framework via `sync_to_async` on every query, and no hard build-time dependency on the whole monolith to reach one model. That's coupling retired, not milliseconds saved. A metric that doesn't move is still worth measuring because it tells you where the payoff is and isn't.

Coupling is the quantity being optimized, and it compounds instead of adding. Two contexts sharing one table is one coupling point. A third context reading the same table doesn't add one interaction; the pairwise interactions that can break each other grow combinatorially, because any change to the table's shape must be checked against every context touching it. The monolith's `SMELLS.md` catalogues this shape: cross-app foreign keys, one ACID transaction spanning six contexts, a shared schema no team owns outright. It's why extraction order matters. Cutting the most tightly coupled context first, before the mechanism is proven anywhere, is strictly harder than cutting the one with no synchronous calls in or out, which is why Review goes first.

> **Decision**
>
> Modernize only against a delivery or operability metric you can name and that is currently bad. Extract incrementally behind a proxy, least-coupled context first. If a proposed split earns few of the ten traits, or hits one of the three wrong-call conditions, fix the real bottleneck first.

> **🤖 Explore with your agent**
>
> "Check out the `v0-monolith` tag and read `examples/00-monolith/SMELLS.md` and the six app directories under `examples/00-monolith/`. For each planted smell, name the delivery or operability metric it hurts (time-to-ship for a one-context change, blast radius, load-to-capacity ratio). Then check the monolith against the three wrong-call conditions and rank the six contexts by how many synchronous calls cross their boundary, least coupled first. Change no code."
>
> Check: the reply cites a metric for every smell in `SMELLS.md`, concludes the monolith meets none of the three wrong-call conditions, and ranks `review` first: `order/services.py` calls four other contexts' services, `review` calls none and nothing calls it.
