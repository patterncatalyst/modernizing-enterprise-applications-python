---
title: "Introduction & How to Use This Book"
order: 0
part: "Setting Up"
description: "The thesis: modernize with an agentic ADLC, the shipping through-line, the before/after, reading paths, conventions, and the reference-book map."
---

You learn to modernize a real system by modernizing one. The project builds a believable Django monolith (order, inventory, payment, shipping, notification, review: the shape of any shipping or e-commerce backend) and takes it apart one seam at a time. Every pattern arrives when the migration forces it. At the end the monolith is frozen and out of the running system, six independent FastAPI services and a GraphQL gateway stand in its place, and every step in between is checked in as runnable code, a passing test suite and a written record of why.

{% include excalidraw.html file="monolith-to-microservices-outcome" alt="Side-by-side before and after: one Django 5.2 LTS plus DRF deployable with six in-process bounded-context apps sharing a single Postgres schema and one transaction.atomic() checkout spanning order, inventory, payment, and notification, versus six independent FastAPI services plus a Strawberry GraphQL gateway, each owning its own schema, reached through one Starlette-based ASGI strangler proxy with a Kafka event backbone carrying the outbox and saga traffic." caption="Figure 0.1: The starting monolith and the six-service system it ends as" %}

## Who this is for

Engineers and architects accountable for a production system's behavior during a migration. You don't need an introduction to sagas or circuit breakers; both are explained, but they aren't the point. The hard problems are deciding where to cut a system nobody fully understands, proving the cut preserved behavior nobody wrote down, and doing it fast enough that the business case still holds.

Green-field instincts are often wrong against a decade of shortcuts, shared tables and implicit contracts. If you maintain a monolith you didn't write, the reference monolith will look familiar: it's ordinary, with planted smells, so the cures transfer to the system on your own machine. Tooling (uv, Python 3.14, Django, FastAPI, a local observability stack) is set up once in the next chapter.

## The thesis

One argument, made at two altitudes.

**Architecture.** A monolith becomes microservices by strangling it: cut one bounded context free at a time, behind a proxy, with a translation layer at the seam, instead of stopping the world to rewrite. The Strangler Fig is decades old, and the anti-corruption layer, the outbox, the saga and CQRS are documented in more depth elsewhere. What those sources rarely show is a complete, continuous run through all of them against one system, in the order a real migration forces, with code that proves each step. That's the gap: not a new catalog, but the catalog applied in sequence to a system you can run.

**Execution.** The work isn't done the way it was five years ago, with a requirements document, a design review, a sprint, a QA pass and a change board, each handed to a different role over weeks. It runs through an **Agentic Development Lifecycle** (the **ADLC**): a few coding agents inside a seven-phase loop with exactly two places where a human must stop and decide. An agent can read the legacy module, propose the seam, scaffold the service and write its tests in one sitting. What makes trusting that output responsible is a fast, automated, re-runnable check between every candidate change and anything called done.

That check is the **behavior-equivalence suite**. A contract collection is captured against the running monolith: every endpoint, status code and edge case it actually produces, including the ones nobody would have specified, because they were found by exercising a real system. The collection is never edited to make a service pass. It re-runs unchanged against every extracted service, and the **equivalence gate** built from it blocks a service from being trusted, and the matching monolith module from being decommissioned, until the service answers exactly as the monolith did. It caught real defects during the extractions. A passing suite is evidence that a change is safe, not proof, so you keep probing for what would make it pass by accident until you can't think of anything.

Stated once in full: take a Django monolith and modernize it into six FastAPI services and a GraphQL gateway, one pattern at a time, in the order the migration demands, driven by an agentic ADLC, with a behavior-equivalence gate proving at every step that the new code behaves like the old.

## The running example

One shipping and e-commerce platform runs through every chapter, built around six bounded contexts: **order**, **inventory**, **payment**, **shipping**, **notification** and **review**. It starts as a single Django deployable: one WSGI process, one shared Postgres schema, a DRF REST API for all six contexts, and an order-placement flow that reaches into inventory, payment, shipping and notification inside one `transaction.atomic()` block.

The design is ordinary, and its smells are planted: a god checkout service, one transaction spanning five contexts, a shared schema with cross-context foreign keys, a synchronous notification send inside checkout, and a dual-write hazard between a database commit and a provider call. Each smell is tagged to the extraction that cures it.

The monolith is strangled in order of rising difficulty, not domain importance:

| Order | Context | What it forces |
|---|---|---|
| 1 | Review | REST-only, no synchronous dependency: the cheapest proof that the extraction mechanism works end to end |
| 2 | Notification | An event backbone and the transactional outbox |
| 3 | Inventory | A decomposed database and Debezium change-data-capture behind a gRPC seam |
| 4 | Payment | A choreographed saga, since one database transaction is no longer available |
| 5 | Shipping | An orchestrated saga with crash-resume |
| 6 | Order, with a GraphQL gateway | The core aggregate and hardest coupling, saved for last; CQRS on the read side |

Each extraction gets its own chapter, its own equivalence-gate run and its own "ADLC in Action" callout showing the trace that produced it.

{% include excalidraw.html file="extraction-sequence-ladder" alt="The six extractions in execution order, rising in difficulty left to right: review (REST leaf on a shared schema), notification (async transactional outbox), inventory (Debezium CDC plus a gRPC seam), payment (choreographed saga), shipping (orchestrated saga with crash-resume), and order with its Strawberry GraphQL gateway (CQRS)." caption="Figure 0.2: The extraction order: rising difficulty, not rising domain importance" %}

At the end the monolith's modules are all decommissioned. Six services communicate over REST, gRPC and GraphQL as each relationship calls for, run on Kubernetes, are observed through distributed tracing and ship through a CI pipeline that runs the equivalence gate on every change.

## How the material is organized

Eleven parts, in the chronology of a real migration rather than a textbook's logical order.

| Part | Covers |
|---|---|
| Setting Up (you are here) | Toolchain, the project ledger, how to run every example |
| Why Modernize | The business and engineering case, including when microservices are the wrong answer |
| The ADLC | The seven phases, the two human gates, the agents and tooling, and a worked run of the loop on a trivial change |
| The Reference Monolith | The "before" system and the contract tests that become the behavior-equivalence suite |
| Finding the Seams | Domain-driven design, event storming and coupling theory as the method for choosing the six boundaries |
| The Strangler Fig in Practice | The strangler proxy, the review and notification extractions, the anti-corruption layer and content-based routing |
| Data Across the Seam | Shared database to service-owned data: change-data-capture, the outbox done correctly, the CQRS read side, and what eventual consistency gives up |
| Coordinating Across Services | The payment and shipping sagas and the resilience toolkit for failures a single process never had |
| Communication & Contracts | The order extraction and GraphQL gateway, the FastAPI chassis conventions and a schema and contract registry |
| Operating the Modernized System | Deployment patterns, a service mesh and distributed tracing on a Kubernetes substrate |
| Delivering & Reflection | The CI pipelines, the job that runs the equivalence gate on every extraction, the supply-chain scan, and the finished migration walked back against the pattern language, including what was left out |

## How the chapters work

Every hands-on chapter has the same shape: the one new idea, the real code and why each call is there, a build-and-run section with the actual commands, and, where an independent check exists, a cross-check against it. Conceptual chapters, this one included, say so instead of inventing a toy example.

The code is most of the argument. The monolith lives permanently at `examples/00-monolith/`, the ASGI strangler proxy at `examples/01-strangler-proxy/`, each extracted service in its own directory beside them, and `examples/08-graphql-gateway/` is the service the last extraction adds rather than replaces. Each directory has a `README.md` with the build, start and exercise commands. The behavior-equivalence suite lives under `tooling/newman/`, versioned with the monolith it was captured from, and it's the same collection re-run unchanged after every extraction.

Some quoted code exists only at a particular point along the way:

- `main` is the finished system: six services, the GraphQL gateway and the flagless strangler proxy. Its `examples/00-monolith/` is the frozen deployable the monolith was reduced to.
- The complete, runnable monolith from before any extraction is on the `reference/monolith-before` branch, tagged `v0-monolith`.
- The repository right after each extraction is tagged `stage/01-review` through `stage/06-order`.

When a listing shows code that a later extraction moved or removed, check out the matching branch or tag to run it as it was.

## The reference-book map

One outside source is reused by name: **`cloud-native-design-patterns`**, a pattern catalog. The shipping extraction adapts its database-backed saga orchestrator onto this project's own persistence stack instead of re-authoring the mechanism. The reuse is recorded where it happens, because a project that argues for an auditable decision trail should keep one for its borrowed code too.

## What you can do at the end

- **Find the seams** in a real monolith, using strategic and tactical domain-driven design, event storming and coupling analysis as decision tools, so the order of the cuts is reasoned rather than accidental.
- **Execute an extraction** with the behavior-equivalence suite as the acceptance gate: capture a contract suite against the system as it stands, build the strangler seam, migrate in phases, and prove with a re-runnable check that nothing observable changed before you retire the old code.
- **Run the process through an agentic ADLC:** frame intent precisely enough for an agent to act on, know which two moments need your judgment, and keep a ledger good enough that the next person, or you in six months, can trust the record of what was done and why.

## Where to go next

The next chapter gets your machine ready: uv, Python 3.14, Django and FastAPI, Docker and the compose observability stack, and a check you can run to confirm the setup works. After it, the project ledger: the decision log, the build plan and the reconciliation record the ADLC's final phase produces, as a template for the ledger on your own migration. Then the case for why any of this is justified, and when it isn't.
