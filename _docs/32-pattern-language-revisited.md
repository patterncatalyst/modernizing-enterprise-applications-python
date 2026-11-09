---
title: "The Pattern Language, Revisited"
order: 32
part: "Delivering & Reflection"
description: "The microservices pattern catalog re-walked against the finished migration: which patterns were earned, which adapted, which named and deferred, the over-decomposition trap, the chassis, and the ADLC retrospective."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Judge each adopted pattern (Strangler Fig, bounded contexts and Anti-Corruption Layer, database per service, Transactional Outbox, CQRS, choreographed and orchestrated Saga, GraphQL composition, schema registry, the chassis) against the pain it solved, and call it earned, adapted or deferred.
- Explain why full event sourcing, a `pybreaker` circuit breaker and a GitOps operator were deferred, and name the pain each would address.
- Recognize the distributed monolith and apply the rule that a bounded context splits further only when a real seam demands it.
- Trace the ADLC cycle (Frame, Plan, Generate, Verify, Reconcile) across the migration and say why the behavior-equivalence suite made agent-driven change safe to merge.
- Name the remaining horizons as a bounded list: durable sagas, trace propagation across Kafka, log aggregation, a delivery loop.

## Why this matters

The migration started from one Django monolith with six apps and five seeded smells. The last extraction left six independently deployable services plus a data-less GraphQL gateway behind one flagless router, with no monolith to fall back to. The cross-cutting concerns that no bounded context owns (chassis, contracts, deployment, mesh, delivery) came after. With the system finished, each row of the roughly 45-row pattern matrix the project set out to cover can be checked against running code instead of a plan.

The walk uses three verdicts, because that is what the matrix supports once its notes are read.

| Verdict | Meaning | Examples |
|---|---|---|
| **Earned** | Shipped in roughly the shape the literature describes, and the system is worse without it. | Strangler Fig, the outbox, both saga shapes |
| **Adapted** | Shipped in a narrower or differently scoped form. | A chassis that is a copied convention, a schema registry scoped to one demonstrator, tracing depth on three of eight services |
| **Named, deferred** | Never built, with the condition that would change the answer. | Full event sourcing, a circuit breaker, a GitOps operator |

A matrix with no deferred column would describe a different project than the one built.

## The pattern language, pattern by pattern

### Pattern: Strangler Fig (earned)

The ASGI reverse-proxy facade is the spine; every other extraction routed through it. `STRANGLER_*` flags toggled each bounded context and the facade never carried domain logic, only routing decisions. After the final extraction it is flagless: every `*_enabled` boolean and the monolith fallback are gone, an unmatched route returns 404, and the monolith sits frozen behind a `reference/monolith-before` branch and the `v0-monolith` and `stage/01..06` tags. One proxy written once beats six bespoke reverse-proxy configurations.

### Pattern: Content-Based Router and Anti-Corruption Layer (earned)

The two did different jobs at different seams. The router picked a backend by URL path, a one-dimensional decision. `inventory.proto` is the harder case: a wire contract distinct from both the monolith's vocabulary and inventory-service's, translated at both ends, with `scripts/check-proto-drift.sh` failing when the checked-in `.proto` and the generated stubs disagree. The Anti-Corruption Layer generalizes past a legacy translation layer to any synchronous seam where two services evolve their own vocabulary.

### Pattern: Database per Service, with Change Data Capture as the bridge (owned data earned, CDC adapted)

The Review extraction stayed on the monolith's shared schema, a named deferral. Inventory moved to an owned `inventory` schema fed during the transition window by a Debezium connector tailing the Postgres write-ahead log, then retired the connector once the owned schema was the only reader. The runbook (drain, delete the connector, drop the replication slot and publication, disable the flag) is why CDC is adapted: log tailing was never meant to be permanent, and no CI gate mentions Debezium today.

### Synchronous gRPC (earned, narrowly)

It is the only strongly typed, low-latency inter-service call. Order-service's `Reserve` into inventory-service is an atomic conditional `UPDATE`, race-tested under concurrent reservations, with a compensating `Release` issued outside any local transaction. Once a reservation crosses a process boundary the free rollback of a single database transaction is gone, and the sagas replace it.

### Pattern: Transactional Outbox (earned twice)

It cures two smells at once: a synchronous out-of-process call inside an HTTP request, and a dual-write race between a commit and a publish. The outbox row and the domain write land in one local transaction, so a declined or failed checkout leaves zero outbox rows. Payment-service's own outbox, publishing `payment.captured` and `payment.declined`, generalizes the shape: one transaction, an at-least-once relay, and an idempotent consumer (a check-then-insert, an upsert or a status-transition guard, whichever fits the write).

### Pattern: CQRS and ACID to ACD (earned)

Splitting one Postgres transaction that spanned order, payment and shipping into order-service's local transaction on its own `order_svc` schema makes a `PENDING` order real before payment or shipping has an opinion. `order_view`, a same-database read model updated by every write path, makes that state readable without querying write tables. `rebuild_order_view` rebuilds the projection from the write side, so it is a cache and not a second source of truth, and with projection disabled the read side does not fall back to write tables. The cost is an Isolation gap: a `PENDING` order is visible before its saga resolves.

### Pattern: Event Sourcing (adapted)

The outbox-as-event-log framing on order-service's `order.placed` outbox gives a durable, ordered, replayable record of what happened. It answers the question the project had, whether a reader can audit what happened to an order. Full event sourcing, rebuilding current state by folding every historical event, answers a harder question no extraction needed.

### Pattern: Saga, both shapes (earned)

The same problem, a multi-step operation across services that compensates on partial failure, solved two opposite ways. Payment's choreographed saga has no component that knows the sequence; it emerges from three independent event subscriptions reacting one hop at a time. Shipping's orchestrated saga reuses the DB-backed coordinator (`select(...).with_for_update()`, an idempotent `advance()`, a reverse-order `compensate()`) as one process that calls every step and owns the decision to undo. Its `resume_running_sagas()` resumes from the last persisted step after a crash, which an in-memory coordinator cannot do.

Idempotent compensation closes the gap `Reserve` and `Release` opened. A compensating `Release` survives redelivery at the Kafka layer (a status-transition guard in the saga listener) and at the RPC layer (inventory-service's `idempotency_key` ledger), and stock stays constant across forced redelivery on both paths.

### Circuit breakers, discovery and health (adapted)

The resilience this system has is spread across existing mechanisms: a gRPC deadline, the outbox's at-least-once delivery with two-layer idempotency, the proxy's 502 fail-safe when a backend is unreachable, and the orchestrator's crash resume. The one new mechanism is a `tenacity` retry with timeout around the shipping saga's single outbound HTTP call (`enrich`). A `pybreaker` breaker and a bulkhead were named in planning and never built, because no second failure mode in eight services has forced the question.

### The Microservices Chassis (adapted)

Config (a frozen `@dataclass` with `from_env()`, 7 of 8 services) and logging (stdlib `RotatingFileHandler`, 8 of 8) are copied into each service by hand, not imported from a shared package. `/health` and `errors.py` sit at 6 of 8, each gap with a structural reason. The chassis exists and every service runs on it, as eight near-identical files and not one versioned dependency.

### Deployment (earned)

Kustomize `base` plus one `overlays/minikube` tree: 8 app Deployments, a shared `postgres` StatefulSet with schema selected in each service's own code (not a per-service connection string, an assumption the build caught), and probes that match each service's health surface: `tcpSocket` for the two services with no `/health` route, `httpGet /health` for the other six. The base renders under `kubectl kustomize` and passes `kubeconform -strict` with 23 of 23 resources valid; the minikube overlay, which also composes the mesh and observability trees, passes with `-ignore-missing-schemas`, its Istio resources reported Skipped. Offline rendering is not a live cluster admitting and scheduling the manifests, and the verdict carries that limit.

### Contracts and the schema registry (adapted)

`examples/09-schema-registry-demo/` registers one Avro schema with Apicurio and resolves it through a hand-rolled global-id wire envelope (no Confluent serde in the pure-Python lane). A field addition with a default is accepted and a field retype is rejected with a 400. Every other event still ships as a hand-authored JSON contract with no registry behind it. The mechanism is real, but it answers "can this project use a registry", not "does every event go through one".

### Service mesh, observability and tracing (adapted)

`deploy/k8s/istio/` makes `mea` a mesh: `PeerAuthentication` STRICT mesh-wide, enforced by the receiving Envoy sidecar, with one PERMISSIVE override at the plaintext NodePort edge where outside traffic enters. Injection is opted into by a pod-template label, not an annotation, because the injection webhook's object selector matches labels and an annotation injects nothing in an unlabeled namespace. `deploy/k8s/observability/` runs a `grafana/otel-lgtm` backend in-cluster over OTLP, fed partly by a Prometheus scrape of every Envoy sidecar's stats.

The mesh gives all eight services spans, mTLS state and a service graph with no application code changed. It cannot see a database query or a business-logic branch. App-level OpenTelemetry on three of eight (strangler-proxy, order-service, inventory-service) adds that depth, rooted at the synchronous `POST /api/orders` to gRPC `Reserve` path, which crosses no outbox and needs no extra context plumbing to stay one trace. Kafka saga hops stay visible at the mesh layer only; connecting them needs a `traceparent` persisted through the outbox and restored by the relay before publish.

### REST, gRPC and GraphQL side by side (earned)

One additive, data-less Strawberry gateway fans a single `order(id)` query out to five sources (three REST, one gRPC, one REST-per-item). Each field resolves lazily and is nullable, so a failing source degrades a field to `null` with an `errors` entry and does not fail the query. Each protocol stays on the seam it fits: REST for each service's own surface, gRPC for the hot synchronous path, GraphQL for bounded aggregation.

### CI/CD and supply chain (earned)

Scanning order-service and the frozen monolith with syft and grype found 35 High findings in both images, all in the shared UBI base layer, all `fix-state: not-fixed`, with no patched tag to re-pin onto (confirmed with `skopeo`). The supply-chain gate fails on fixable findings only and still lists all 35 in `ignoredMatches`. It narrows what the bar holds a merge responsible for; it doesn't lower it.

{% include excalidraw.html file="pattern-language-map" alt="Two chained rows of patterns colored by verdict. Row one: Strangler Fig, ACL plus gRPC seam, Transactional Outbox, CQRS, Saga Choreographed and Saga Orchestrated, all earned. Row two: Contracts and Schema Registry and Microservices Chassis adapted, Deployment earned, Service Mesh plus Observability adapted (mesh earned, OpenTelemetry on 3 of 8), CI/CD plus Supply Chain earned. A ghost row below names five further horizons connected by dashed arrows from the pattern each would extend: full event sourcing from CQRS, pybreaker and bulkhead from the chassis, a GitOps operator plus canary from deployment, Loki log aggregation and Kafka saga-hop tracing both from service mesh plus observability." caption="Figure 32.1: The pattern language as one connected flow, colored by verdict" %}

## The anti-pattern of over-decomposition

Given roughly 45 patterns to reach for, why eight services and not twenty? Every one of the six extractions was triggered by a named smell the monolith already had (a sync-send inside a transaction, a shared-table race, a God object doing five jobs), not by a target service count or a textbook boundary.

A **distributed monolith** is what you get by splitting a database along service lines before splitting the code that owns it, or the code before anything forces a database split. It has multiple schemas and deployables, but everything still changes in lockstep. It is worse than the monolith: it loses the single transaction's atomic consistency and gains independence in exchange for nothing, because the services still can't deploy, migrate or fail independently. No extraction here split a schema first and found a reason afterward. Notification's event-driven seam needed no shared schema from day one, inventory's CDC backfill bridged a live cutover window before retiring, and order's CQRS projection gave it a read path that never touches another service's write tables.

A nanoservice design for the same domain (a `create-order-id` service, a `validate-sku` service, a `send-confirmation-email` service) has the same catalog available and reaches for most of it for the wrong reason: more network calls per request, more places a business rule can drift, and no gain in independent deployability, since services that only make sense called together aren't independent.

## The chassis in 2026

| Concern | Coverage | Mechanism |
|---|---|---|
| Config | 7 of 8 | frozen `@dataclass` with `from_env()` |
| Logging | 8 of 8 | stdlib `RotatingFileHandler` |
| `/health` | 6 of 8 | each gap structural |
| `errors.py` | 6 of 8 | each gap structural |
| `tenacity` retry | 1 of 8 | only where a call needed it |
| OpenTelemetry | 3 of 8 | one connected trace, up from zero |

{% include excalidraw.html file="book-pattern-scorecard" alt="Three stacked bands of the pattern scorecard. Earned (8 cards): Strangler Fig, Content-Based Routing plus ACL, Shared to Owned Data plus sync gRPC, Transactional Outbox plus event-driven, CQRS plus ACID to ACD, Saga Choreographed plus Orchestrated, Deployment via kustomize, CI/CD plus Supply Chain. Adapted (5 cards): Microservices Chassis, Contracts and Schema Registry, Service Mesh plus Observability (mesh earned, OpenTelemetry on 3 of 8), CDC and Transaction Log Tailing (transition-only, retired), Event Sourcing (light, outbox-as-log framing). Named, deferred (6 ghost cards): full event sourcing, pybreaker and bulkhead, a GitOps operator plus canary, Loki log aggregation, Kafka saga-hop tracing, and Caching." caption="Figure 32.2: The pattern scorecard" %}

Eight copies of a fifteen-line `_configure_logging()` were not collapsed into one shared package. A library versioned independently of eight services is a second dependency each must bump, test and roll out on its own schedule, and these services evolve and redeploy without coordinating a release. Collapse them when drift across the copies causes a real, observed bug, the same trigger a circuit breaker waits for. None has appeared. The chassis here is eight files that agree, re-checkable with the same `grep` commands, not a ninth artifact underneath them.

## The ADLC retrospective

The system was built by an agentic development lifecycle: a planner drafts an approach and names every open design question as a numbered decision before any code exists, a builder implements against the plan one iteration at a time, and a validator checks the result against the plan's acceptance criteria and writes down what it found. The plan was rarely right the first time. What mattered is that every disagreement between plan and code was recorded in the pass that found it.

Three corrections show it:

- The plan said every service's configuration ran on `pydantic-settings`. Grepping every `app/config.py` (seven services; review-service has none) found a plain `dataclasses.dataclass` in each and no `pydantic_settings` import anywhere.
- The plan described the deployment ConfigMap as one connection string per service. Building `app-config.yaml` against the real modules showed one shared `DATABASE_URL`, with schema chosen in each service's code. The manifest shipped correct.
- The supply-chain gate's risk section expected a transient CVE a base-image re-pin could clear. The real scan found 35 unfixable Highs with no newer tag, and the fixable-only policy shipped against that finding instead.

None is a planning failure; a plan written before the code can't know what the code will be. They show the validation pass reading the files, not the plan's description of them. The per-iteration reconciliation record states what shipped, names any divergence from the plan, and renders a CLEAN or DRIFT verdict with reasoning, which is what lets a reader check any claim against the code that backs it.

> **ADLC in Action**: The service mesh and observability row of the matrix sat with an empty note through nine iterations, because the work that would fill it was built last. Filling it meant reading `deploy/k8s/istio/` and `deploy/k8s/observability/` directly: `PeerAuthentication` STRICT, the injection label mechanism, and which three services carry an `opentelemetry-distro` dependency in their `pyproject.toml`. It did not mean inferring the row from the plan that proposed it, the same check run against the `config.py` files and the ConfigMap's real shape. A matrix whose last row was filled by paraphrasing the plan would be the drift this retrospective argues against.

## Further horizons

Each of the five extensions has a checkable trigger.

| Extension | Build it when |
|---|---|
| `pybreaker` circuit breaker and `asyncio` bulkhead | Two of the eight services fail in a way the gRPC deadline, at-least-once outbox and 502 fail-safe don't catch. |
| Full event sourcing | A reader needs point-in-time reconstruction (an order as it looked three saga steps ago), not just an ordered record. |
| GitOps operator with canary rollout (Argo CD or Flux) | A second cluster or staged rollout target exists to promote into; it extends the flag-gated delivery the `STRANGLER_*` and `*_MODE` flags already practice. |
| Loki log aggregation | A reader needs to correlate a log line with its span; Tempo carries traces today and the stack already ships Loki. |
| Tracing across a Kafka saga hop | The saga's event chain must be one connected trace; it needs only the `traceparent` plumbing through the outbox row and relay. |

## Build, run, observe

Nothing new runs here. The claims above are re-checkable against the tree:

```bash
grep -rn "pydantic_settings" examples/*/app/config.py
grep -rln "opentelemetry-distro" examples/*/pyproject.toml
kubectl kustomize deploy/k8s/base | kubeconform -strict -summary
```

- Config: the first command prints nothing, since every `app/config.py` uses a plain dataclass.
- Tracing footprint: the second lists exactly strangler-proxy, order-service and inventory-service.
- Deployment: the third reports 23 resources valid and none invalid.
