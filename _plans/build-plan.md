---
title: "Build Plan — Modernizing Enterprise Applications (Python)"
description: "Django 5.2 LTS monolith strangled to FastAPI microservices, driven by the same ADLC the Java sibling book teaches. Ported in structure from the Java sibling's canonical build-plan.md, rewritten for the Python/Django/FastAPI stack."
status: "r01 walking skeleton — site shell + running 'before' monolith + the gates that prove it"
mirror_of: "~/Dev/modernizing-enterprise-applications/_plans/build-plan.md"
---

# Modernizing Enterprise Applications (Python) — Build Plan

> **r01 IS A WALKING SKELETON, not a planning-only round.** Unlike the Java
> sibling (whose r01 produced planning artifacts only, with the monolith and
> walking-skeleton extraction arriving at r02), this project's r01 builds the
> empty book frame **and** the running Django monolith **and** the Newman/CI
> gates that prove it — in parallel lanes, as laid out in
> `_plans/r01-build-plan.md`. Chapters are stubs; no FastAPI service is built
> yet (that starts at r02, mirroring the Java sibling's own first extraction).

---

## A. Approach

### A.1 Chosen approach

The same **single continuous shipping/e-commerce narrative** as the Java
sibling, strangled the same six seams in the same order, teaching the same
ADLC — but every stack decision is re-made for Python rather than translated
line-by-line:

- **Monolith "before":** Django 5.2 LTS + DRF, not Spring Boot. One
  deployable, one shared Postgres schema, six Django apps, the same six
  deliberate smells (§D).
- **Microservices "after":** FastAPI, not Quarkus + Camel. No Python
  framework plays the role Camel plays for Spring (a full integration/EIP
  framework with routing, sagas, and content-based transformation built in),
  so each Camel-shaped mechanism is re-homed to the nearest idiomatic Python
  tool rather than forced into a single framework — **pattern-when-forced**,
  not pattern-for-its-own-sake (§C).
- **Toolchain:** uv + Python 3.14 in place of Maven/JDK; pytest +
  pytest-django in place of JUnit/Testcontainers; the same Newman behavior-
  equivalence suite (DRQ-010) as the CI equivalence gate, ported with payload
  shapes preserved (camelCase, DRQ-002) so the collection reads as the same
  contract in both books.
- **ADLC-driven:** same seven phases (§F), same two human gates (Plan
  approval, Verify sign-off), same three-ledger worked example (this
  `build-plan.md` / `decisions.md` / `reconciliation.md`) — **DRQ-016**. The
  one structural difference: there is no Quarkus Agent MCP / Camel MCP
  equivalent for Python, so the Map/Generate phases substitute manual
  reconnaissance plus the `lgtm-python` skill (DRQ-020).

**Rejected (r01):** mirroring the Java `main` branch's frozen/decommissioned
monolith end-state (DRQ-023 — the Java repo's `examples/00-monolith/` is
*permanently* kept but *decommissioned from the running topology*; this
project's r01 monolith must be the **pristine "before"**, all six apps and
smells live, nothing extracted yet); building FastAPI services or the
strangler façade now (that is r02+ work, mirroring the Java sibling's own
cadence of "monolith first, walking-skeleton extraction second"); a uv
workspace root (premature — no second Python package exists yet); per-app
separate schema now (that is the *target*, not the r01 "before," per DRQ-006);
authoring chapter prose (r01 chapters are stubs only, per the SITE lane).

### A.2 Stack-substitution table (mechanical, consistent — DRQ-019)

| Java sibling | Python sibling | Where it shows up |
|---|---|---|
| Spring Boot 4.x | **Django 5.2 LTS + DRF** | the monolith, §D |
| Quarkus + Camel | **FastAPI** | every extracted service, §E |
| Maven / JDK 25 | **uv / Python 3.14** | toolchain, §F, §J |
| JUnit + Testcontainers | **pytest + pytest-django (+ Testcontainers-python later)** | §D, §F |
| Camel strangler proxy | **a thin ASGI reverse-proxy façade** (httpx-based, path/content routing) | ch.14, §E row 0 |
| SmallRye Reactive Messaging (Kafka) | **aiokafka** | notification (ch.17), payment choreography (ch.23) |
| quarkus-grpc | **grpcio** | inventory (ch.19) |
| Camel Saga EIP (orchestrated) | **the reused CNDP Python DB-backed saga orchestrator** (`cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator`) | shipping (ch.24), DRQ-007 |
| SmallRye GraphQL | **Strawberry** | order + gateway (ch.26) |
| Apicurio Schema Registry | **Apicurio (unchanged — language-agnostic)** | ch.28 |
| Quarkus Agent MCP / Camel MCP | **no equivalent — manual reconnaissance + `lgtm-python` skill** | §F.1, DRQ-020 |

### A.3 Standing constraints honored

Scope discipline (no speculative infrastructure — no uv workspace, no
services before r02; §M R1), conceptual coherence (one abstraction level per
lane; the monolith is deliberately the simple "before," not where FastAPI's
strengths are shown — mirrors the Java sibling's own DRQ-032 framing),
security-by-design (OWASP Top 10 / CIS woven into the ADLC Verify gate, §F.4),
and never push upstream without explicit permission (this relay writes files
only; branch/PR/push is a separate, explicitly-gated step per standing
memory).

---

## B. Site architecture

Jekyll/GitHub Pages, ported from the Java sibling's `_config.yml` / layouts /
CSS and re-skinned for this book's accent and emoji (DRQ-001). Collections:
`docs`, `plans` (`output: false` — never rendered), `example_pages`, `parts`.
Chapters are stubs at r01 (front-matter + "Coming in rNN" one-liner); full
authoring begins r02+.

- **Accent:** `--accent: #3d7a4e` ("migration green," unchanged from the Java
  sibling — **DRQ-001, fixed**, reads as a matched set with the Java book).
- **`brand_emoji`:** 🏗️ (**DRQ-001, fixed**).
- **`github_repo`:** `modernizing-enterprise-applications-python`;
  **`github_username`:** `patterncatalyst`.

### B.1 Parts (ordered — 12 parts, `_parts/00..11-*.md`)

Retitled only where the Java title named a Java-specific technology; every
other Part title is unchanged, since the narrative arc (why → ADLC → monolith
→ seams → strangle → data → coordinate → communicate → operate → deliver →
appendices) does not depend on the language.

| # | Part | Blurb (Python-specific delta from the Java sibling) |
|---|---|---|
| 0 | Setting Up | Toolchain is uv/Python 3.14/Django+DRF/FastAPI CLI, not SDKMAN/JDK/Maven/Quarkus+Camel CLI; the observability stack is `lgtm-docker-stack` (docker-primary, podman-compatible, DRQ-004), not `lgtm-podman-stack`. |
| 1 | Why Modernize | Unchanged narrative; same strategy framing, same 2×2, same evolution arc. |
| 2 | The AI Development Lifecycle (ADLC) | Same phase model (§F); the Map/Generate tooling column differs (no Camel/Quarkus MCP, DRQ-020). |
| 3 | The Reference Monolith | Django 5.2 LTS + DRF "before," not Spring Boot; same shared-schema smell, same equivalence-suite approach. |
| 4 | Finding the Seams | Unchanged — DDD/hexagonal/event-storming/coupling theory is language-agnostic. |
| 5 | The Strangler Fig in Practice | The façade is a thin ASGI reverse proxy, not a Camel strangler proxy; same first-two-extractions sequencing. |
| 6 | Data Across the Seam | Unchanged narrative (shared→CDC→outbox→CQRS→ACID→ACD); CDC still Debezium (language-agnostic, reads Postgres WAL). |
| 7 | Coordinating Across Services | Choreography via aiokafka, orchestration via the reused CNDP Python saga orchestrator, not Camel Saga EIP. |
| 8 | Communication & Contracts | REST/gRPC/GraphQL via FastAPI/grpcio/Strawberry, not Quarkus/quarkus-grpc/SmallRye GraphQL; chassis chapter retitled (ch.27). |
| 9 | Operating the Modernized System | Same mesh/observability narrative on minikube; images are FastAPI/Django UBI-Python images, not Quarkus JVM/native images. |
| 10 | Delivering & Reflection | Same GitHub Actions / GitOps / supply-chain narrative; Code CI pipeline runs uv + pytest + Newman, not Maven + JUnit + Newman. |
| 11 | Appendices | Same appendix posture (reuse-as-is / adapt / reference); the OpenShift-on-CRC appendix (ch.33) is still the terminal chapter — the project's **OpenShift/CRC Appendix Standard** memory applies here too. |

### B.2 Ordered chapter list (34 chapters, `_docs/00..33-*.md`)

Titles ported verbatim from the Java `_docs/*` front-matter where the title
names no Java-specific technology; retitled where it did (ch.19 generalized
to "Change Data Capture," ch.23/24 relabeled to name the Python saga
mechanism, ch.27 renamed from the Quarkus/MicroProfile chassis to the FastAPI
chassis). Filenames are unchanged so the two books' `_docs/` directories line
up 1:1.

**Part 0 — Setting Up**
1. **00 Introduction & How to Use This Book** — the thesis (modernize *with*
   an agentic ADLC), the shipping through-line, reading paths, the
   reference-book map. *(no code)*
2. **01 Prerequisites & the Toolchain** — uv, Python 3.14, Django 5.2 LTS +
   DRF, FastAPI; `lgtm-docker-stack` (docker-primary, podman-compatible);
   minikube reserved for Part 9–10; verify-your-setup gate.
3. **02 The Project Ledger** — the three ADLC artifacts (`decisions.md` with
   the `DRQ-NNN` convention, `build-plan.md`, `reconciliation.md`) as the
   reader's own migration memory.

**Part 1 — Why Modernize**
4. **03 Modernization as Engineering, Not Fashion** — goals, the microservice
   traits, when microservices are a bad idea.
5. **04 Strategies & Assessment** — Lift&Shift / Modernize&Extend / Rip&Rewrite;
   the strategic-value × change-frequency 2×2; the evolution arc.

**Part 2 — The ADLC**
6. **05 From SDLC to ADLC** — why the traditional lifecycle breaks under
   agent-assisted work; the phases; human gates.
7. **06 Agents, Skills & MCP Tools in the Loop** — the lgtm-relay tiering; why
   there is no Python Quarkus-Agent/Camel-MCP equivalent and what substitutes
   for it (`lgtm-python`, manual reconnaissance).
8. **07 The ADLC Safety Net (a worked loop)** — a full Frame→Reconcile loop on
   a trivial change, establishing the "ADLC in Action" callout format.

**Part 3 — The Reference Monolith**
9. **08 Designing the Monolith** — the six bounded contexts as one Django
   deployable: domain model, six Django apps, single shared schema, DRF REST
   API, seed data. *First running example.*
10. **09 The Deliberate Smells** — the six smells planted on purpose (§D), each
    tagged `# SMELL[ch.NN]:` to the chapter that later cures it.
11. **10 Testing the Monolith (the Equivalence Suite)** — pytest/pytest-django
    unit + integration tests, plus the Newman contract collection that becomes
    the behavior-equivalence suite.

**Part 4 — Finding the Seams**
12. **11 Strategic & Tactical DDD + Hexagonal** — subdomains, bounded contexts,
    aggregates; keeping Django's ORM out of the domain core so extraction is
    mechanical.
13. **12 Event Storming the Monolith** — discovering seams from behavior, not
    schema.
14. **13 Coupling, the Modular Monolith & When *Not* to Split** — Khononov's
    three dimensions; legitimate non-split destinations; the distributed-
    monolith trap.

**Part 5 — The Strangler Fig in Practice**
15. **14 The Strangler Fig Pattern** — Fowler's pattern; the ASGI reverse-proxy
    façade used for cutover (the Python stand-in for the Camel strangler proxy).
16. **15 Extraction 1 — Review Service (the walking skeleton)** — REST-only, no
    sync dependency; the full loop proven once. *Authored first, r02.*
17. **16 Content-Based Routing & the Anti-Corruption Layer** — path/content
    routing at the façade; the ACL translation layer at the seam.
18. **17 Extraction 2 — Notification Service (Going Event-Driven)** — the Kafka
    backbone via aiokafka; the outbox in the monolith; first taste of eventual
    consistency.

**Part 6 — Data Across the Seam**
19. **18 From Shared Data to Owned Data** — the shared-schema pattern and its
    limits; planning the split.
20. **19 Change Data Capture & Extraction 3 — Inventory** — Debezium CDC/log-
    tailing to bridge the monolith's tables; gRPC-first inventory (grpcio) with
    a decomposed DB and CDC backfill.
21. **20 The Outbox Pattern, Done Right** — transactional outbox vs dual-write;
    idempotent consumers; ordering and deduplication.
22. **21 Event Sourcing & CQRS** — CQRS read/write split (load-bearing for the
    gateway read side); event sourcing covered but kept light/optional.
23. **22 ACID → ACD: Living Without Isolation** — the consistency given up;
    where it bites and how to bound it.

**Part 7 — Coordinating Across Services**
24. **23 Distributed Transactions, the Saga & Extraction 4 — Payment
    (choreographed, aiokafka)** — why 2PC is off the table; compensating
    transactions; event choreography (`order.placed`→`payment.captured`).
25. **24 Orchestrated Sagas & Extraction 5 — Shipping** — the same outcome via
    the reused CNDP Python DB-backed saga orchestrator; choreography vs
    orchestration made concrete on one codebase.
26. **25 Failure Modes & the Resilience Chassis** — partial-failure taxonomy;
    timeouts, retry+jitter, circuit breaker, bulkhead — the Python resilience
    toolkit (e.g. `tenacity`/`circuitbreaker`) in place of SmallRye Fault
    Tolerance.

**Part 8 — Communication & Contracts**
27. **26 Communication Styles & Extraction 6 — Order + GraphQL Gateway** —
    REST/gRPC/GraphQL and when each fits; the core aggregate extracted last;
    the Strawberry GraphQL gateway as the CQRS read-aggregation surface; the
    strangler completes and the monolith's order app is decommissioned.
28. **27 The FastAPI Chassis** — pydantic-settings, dependency injection,
    structured health/metrics, OpenAPI, async lifespans — "what you migrated
    *to*," the Python analogue of the Quarkus/MicroProfile chassis chapter.
29. **28 Contracts & the Service Registry** — schema/API/shared-data-type
    registry use cases; Apicurio with Avro/Protobuf/JSONSchema/OpenAPI/
    AsyncAPI (unchanged — language-agnostic).

**Part 9 — Operating the Modernized System**
30. **29 Deployment Patterns** — rolling, breaking-schema-change, blue-green
    tied to the cutover; which fits synchronous vs event-driven services.
31. **30 Mesh, Observability & Distributed Tracing** — Istio, Kiali,
    OpenTelemetry + the LGTM stack — on minikube; Python auto-instrumentation.

**Part 10 — Delivering & Reflection**
32. **31 CI/CD, GitOps, Progressive Delivery & Supply Chain** — the actual
    GitHub Actions workflows (`code-ci.yml` and friends), the equivalence-gate
    job, UBI Python image builds, GitOps, feature-flag/canary cutover, SBOM +
    CVE scan + policy-as-code.
33. **32 The Pattern Language, Revisited** — the pattern map re-walked with the
    completed migration; anti-patterns of over-decomposition; honestly-scoped
    "further horizons."

**Part 11 — Appendices**
34. **33 Appendix A: Deploying to OpenShift** — the finished system on
    OpenShift Local (CRC): a Helm chart, Routes, Security Context Constraints,
    the internal registry — per the project's standing OpenShift/CRC Appendix
    Standard.

**Count check:** 12 parts × chapters above = **34 chapters (00–33)**,
matching the SITE lane's `_docs/00..33-*.md` stub count exactly.

### B.3 Appendix posture

Same posture as the Java sibling (DRQ-016/B.3): appendices are reuse-as-is /
adapt / reference, zero net-new appendix prose before the late iterations.
Two appendices are **reused directly from Python-native sources** rather than
translated from the Java sibling's Java/Quarkus appendices:

| Appendix | Source | Verdict |
|---|---|---|
| Sagas — DB-backed orchestrator | `cloud-native-design-patterns/examples/17-sagas/python/` + `_docs/17-appendix-d-sagas.md` | reuse-as-is (pairs with ch.24; **DRQ-007**, not built in r01) |
| OpenShift on CRC | new, Python-native (Django/FastAPI UBI images) | new (companion to ch.33, per standing OpenShift/CRC Appendix Standard memory) |
| All other appendices (DDD/hexagonal, coupling, failure modes, feature flags, testing strategy, Newman-as-contracts, Kafka fundamentals, Quarkus-vs-Spring-style comparison reframed as Django-vs-FastAPI, AI/MCP, k8s deploy, observability economics, glossary) | Java sibling's appendices, ported/retitled | adapt — deferred past r01; tracked in the Java sibling's own §B.3 and re-homed chapter-by-chapter as each Part is authored |

---

## C. Pattern-coverage matrix (re-homed from the Java sibling's §C)

Same ~45 deck patterns, same homes (chapter numbers are unchanged 1:1), only
the "Runnable via" column changes to name the Python mechanism.

| Deck pattern (category) | Home | Runnable via (Python) | Note |
|---|---|---|---|
| Lift&Shift / Modernize&Extend / Rip&Rewrite (A) | ch.04 | conceptual | book executes Modernize&Extend → strangler |
| Repurchase/Retire/Retain; Container-Native Virtualization (A) | ch.04 | demoted | non-targets; a paragraph |
| Monolith (B) | ch.08 | Django 5.2 LTS + DRF | the "before" |
| Modular Monolith (B) | ch.13 | Django apps as modules | legit destination |
| Modular Monolith w/ decomposed DBs (B) | ch.13, ch.18 | per-app `DATABASES` routing | distributed-monolith trap |
| Strangler Fig + proxy/redirection/shared-DB variants (B) | ch.14 | ASGI reverse-proxy façade | the spine |
| Content-based Routing (B) | ch.16, ch.17 | façade path/header routing | cutover + event routing |
| Decorating Collaborator (B) | ch.16, ch.19 | FastAPI client wrapper | proxy-side + inventory retire |
| Shared Data (C) | ch.18 | shared Postgres schema | and its limits |
| Transaction Log Tailing (C) | ch.19 | Debezium (unchanged) | folded into CDC |
| Simple CDC (C) | ch.19 | Debezium Postgres connector | inventory backfill |
| Outbox (C) | ch.17 (intro), ch.20 | Django outbox table + relay (Celery/cron or asyncio task) | reliable-publish workhorse |
| Event Sourcing (C) | ch.21 | light/optional | demoted-light: high cost, not required |
| CQRS (C) | ch.21, ch.26 | Django write model + denormalized read model | load-bearing via gateway read side |
| Distributed Transactions ACID→ACD (C) | ch.22 | conceptual | framing for sagas |
| Saga — general (D) | ch.23 | compensations | |
| Saga — Choreographed (D) | ch.23 | aiokafka consumer/producer | + payment extraction |
| Saga — Orchestrated (D) | ch.24 | CNDP Python DB-backed saga orchestrator | + shipping extraction, DRQ-007 |
| Circuit Breaker / Discovery / Health (E) | ch.25, ch.27, ch.30 | `tenacity`/`circuitbreaker` + FastAPI health routes | reframed off Netflix OSS, same as Java sibling |
| Microservices Chassis (E) | ch.27, ch.32 | FastAPI + pydantic-settings | |
| Fixed / Rolling / Breaking-Schema / Blue-Green (F) | ch.29 | manifests (unchanged) | Fixed demoted to a paragraph |
| Service/Schema/API registry + requirements (G) | ch.28 | Apicurio (unchanged) | |
| Service Mesh / Observability / Tracing (H) | ch.30 | Istio + OTel Python auto-instrumentation (minikube) | |
| Caching (H) | App. H (Java-sourced, adapted) | demoted → appendix | generic; no migration driver |
| API Gateway + Service Discovery evolution (H) | ch.26, ch.28 | FastAPI gateway + Apicurio | |
| REST / gRPC / GraphQL (H) | ch.26 | FastAPI / grpcio / Strawberry | |
| Unit / E2E / Testing-Data (I) | ch.10 + woven | pytest/pytest-django + Newman | testing throughout |

**Demotions, rationale unchanged from the Java sibling:** Container-Native
Virtualization + Repurchase/Retire/Retain (non-migration targets); Event
Sourcing (high build cost, not required); Caching (generic, appendix);
Fixed deployment (a paragraph); Netflix OSS (historical framing).

**New topics beyond the deck, Python-specific:** the Agentic ADLC (unchanged
from the Java sibling, Part 2); the FastAPI chassis as the concrete runtime
(ch.27); the **Python two-phase Django→FastAPI migration policy** (§E, no
Spring-compatibility-extension equivalent exists, so this is named honestly
as its own topic rather than silently assumed); OpenTelemetry + LGTM (ch.30);
GitOps + progressive delivery (ch.31); supply-chain/SBOM/CVE/policy-as-code
(ch.31); explicit DDD + event storming (Part 4); a measured Django-vs-FastAPI
comparison (the book's premise, analogous to the Java sibling's Quarkus-vs-
Spring appendix).

---

## D. Reference monolith design

A **fresh Django 5.2 LTS + DRF monolith (Python 3.14)** — one deployable, one
database — the Python sibling's believable common ancestor, built to the same
design as the Java monolith but idiomatically Django-shaped.

- **Domain (six bounded contexts as Django apps):** `order`, `inventory`,
  `payment`, `shipping`, `notification`, `review`. Reuse the shared field
  vocabulary (`OrderDto`→`Order` serializer, `OrderStatus`, `StockDto`,
  `ReviewDto`, `NotificationDto`, `Topics`) so extracted services line up 1:1
  with the Java sibling and with `datamesh-reference-arch-quarkus`.
- **Architecture:** classic Django MTV/DRF layering (view → serializer →
  model → queryset), DRF serializers for the REST API, Django's built-in auth
  for review endpoints — deliberately **not** hexagonal at first (a smell,
  mirroring the Java monolith's deliberately-not-hexagonal framing).
- **Persistence:** one PostgreSQL schema shared across all six Django apps,
  with cross-app `ForeignKey`s (the data-coupling smell). Django migrations;
  deterministic seed data via a management command / fixtures.
- **API surface:** DRF REST for all six contexts; an in-process checkout flow
  touching inventory → payment → shipping → notification wrapped in **one
  `transaction.atomic()`** (the distributed-transaction smell cured by saga).
  `drf-spectacular` seeds the Newman behavior-equivalence suite.
- **JSON contract:** DRF serializer fields exposed in **camelCase** via
  `source=`/a shared camelCase renderer (not DRF's default snake_case) so the
  Newman collection ports from the Java sibling with minimal edits
  (**DRQ-002**).
- **Deliberate smells (each tagged `# SMELL[ch.NN]:`, each cured by a later
  chapter):**
  1. Shared schema / cross-app FKs → owned data + CDC (ch.18/19).
  2. God `OrderService`/order view reaching into other apps → hardest/last
     extraction (ch.26) + motivates sagas.
  3. One in-process ACID transaction across contexts → saga (ch.23/24),
     ACID→ACD (ch.22).
  4. Synchronous notification inside the checkout transaction → outbox +
     event-driven extraction (ch.17).
  5. No ACL / leaky domain model → ACL at the seam (ch.16).
  6. Review tangled into shared auth but genuinely independent → easy first
     strand (ch.15, the walking skeleton).
- **Deterministic failure injection (r01, per `_plans/r01-build-plan.md`):**
  `CARD-DECLINE` → `402`; over-order → `409`; `SHIP-FAIL` → the whole
  `transaction.atomic()` rolls back, stock net-zero (Scenario 4 — meaningful
  *because* the checkout is still one ACID transaction at r01, setting up the
  ACID→ACD narrative from day one).
- **Testing (the equivalence suite):** pytest unit tests per app;
  pytest-django integration tests over real Postgres; the Newman contract
  collection (Smoke + 4 scenarios) re-run unchanged against each extracted
  service.
- **Scale discipline:** match the Java sibling's "3–9 files per module" bar.

---

## E. Decomposition roadmap (strangler-fig sequence → chapters)

Same rising-difficulty order as the Java sibling (DRQ-013): review →
notification → inventory → payment → shipping → order+gateway. Each step is a
chapter, a `DRQ-NNN`, a `build-plan.md` row, a flag-gated cutover behind the
ASGI strangler façade, and an equivalence-gate check before the monolith's
Django app is decommissioned. **None of rows 1–6 are built in r01** (r01 is
the monolith + site + gates only, per `_plans/r01-build-plan.md`); they are
recorded here as the roadmap future relays execute against.

| # | Service | Seam / mechanism | Data & transaction handling | Target runtime | Chapters | Status |
|---|---|---|---|---|---|---|
| 0 | — | Insert the ASGI strangler façade in front of the monolith | n/a | — | ch.14 | not started |
| 1 | **review** | REST leaf, no sync deps; façade redirect by path; ACL | Own schema from day one; no shared-txn entanglement | FastAPI | ch.15 *(walking skeleton)* | not started |
| 2 | **notification** | Event consumer; content-based routing; decorating collaborator | Outbox in monolith → Kafka; idempotent consumer | FastAPI + **aiokafka** | ch.16–17 | not started |
| 3 | **inventory** | Synchronous gRPC; decomposed DB; decorating collaborator | CDC (Debezium) backfill from shared schema → owned DB, then cut writes | FastAPI + **grpcio** server | ch.19 | not started |
| 4 | **payment** | Event choreography (`order.placed`→`payment.captured`) | Choreographed saga via **aiokafka**; compensations; ACID→ACD realized | FastAPI + aiokafka | ch.23 | not started |
| 5 | **shipping** | Completes the chain; alternative orchestration | **Orchestrated saga** via the reused CNDP Python DB-backed saga orchestrator | FastAPI + saga orchestrator | ch.24 | not started |
| 6 | **order** (+ gateway) | Core aggregate, extracted last; GraphQL read side | CQRS read model; event-sourcing optional; monolith decommissioned | FastAPI REST/aiokafka + **Strawberry** GraphQL gateway | ch.26 | not started |

**Seam toolkit (consistent across all six):** an ASGI reverse-proxy façade
routing by path/content; an ACL (a thin FastAPI translation layer) at each
boundary; feature flags (environment-variable-gated, or OpenFeature/flagd if
a Python SDK proves out) as the cutover mechanism; the Newman equivalence
gate as the go/no-go checkpoint. Reversibility is a design property, mirroring
the Java sibling's per-extraction flag pairs (e.g. `notification.mode`,
`strangler.notification.enabled`).

### Two-phase Django→FastAPI migration policy (DRQ-009)

The Java sibling's two-phase policy (Phase A: lift onto Quarkus via
Quarkiverse Spring-compatibility extensions; Phase B: refactor to idiomatic
Quarkus) has **no direct Python analogue** — there is no Django-compatibility
shim for FastAPI the way `quarkus-spring-web`/`-data-jpa`/`-security` exist
for Quarkus. The honest Python framing is therefore stated as its own policy,
not a translation of the Java one:

- **Phase A — behavior-preserving FastAPI lift.** The service's Django-app
  surface (views, serializers, models) is re-expressed on FastAPI as directly
  as the two frameworks allow: either (a) a **thin FastAPI layer that
  continues to call into the Django ORM** for persistence (via
  `django.setup()` in an ASGI lifespan, accepting the Django dependency as a
  deliberate, temporary bridge), or (b) a **direct SQLAlchemy re-map** of the
  same tables with equivalent models, whichever the chapter's seam calls for.
  Either way, this phase's goal is identical to the Java sibling's Phase A:
  pass the Newman equivalence gate fast, with no idiom rewrite blocking the
  gate.
- **Phase B — fully idiomatic FastAPI.** The service is refactored off the
  Phase-A bridge to idiomatic FastAPI + Pydantic models + SQLAlchemy (async),
  with a measured before/after (startup time, memory, request latency)
  captured as the teaching payoff — the Python analogue of the Java sibling's
  native-image/startup-time measurement.
- **Why stated explicitly:** glossing this as "the same two-phase policy,
  just reworded" would be dishonest — Python has no equivalent of a
  compatibility-extension bridge, so Phase A is sometimes a thin wrapper and
  sometimes a rewrite, and each extraction chapter must say plainly which one
  it is, rather than implying a drop-in shim exists where none does.

---

## F. ADLC / agentic-workflow design

Same seven-phase ADLC the Java sibling teaches and demonstrates (Part 2); the
tooling column differs where no Python MCP server exists.

### F.1 Phases

| ADLC phase | What happens | Human gate? | Agents / tools / skills (Python) | Replaces |
|---|---|---|---|---|
| **1. Frame** | Human states the step's outcome + acceptance criteria into a PRD + `decisions.md` entry | author intent | human | requirements |
| **2. Map** | Agent reconnaissance: classify the legacy Django app, map dependencies, find the seam | — | **manual reconnaissance + `lgtm-python` skill** (no Camel/Quarkus-MCP equivalent, DRQ-020); Explore subagent | design/analysis |
| **3. Plan** | Opus produces the step plan, `DRQ-NNN`, and `build-plan.md` rows | **GATE: human approves plan before any code** | `lgtm-relay` (Opus plan) | design + task breakdown |
| **4. Generate** | Sonnet scaffolds + writes code + tests | — | `lgtm-relay` (Sonnet); `lgtm-python` (FastAPI/aiokafka/grpcio/Strawberry service shapes) | implementation |
| **5. Verify** | Opus validates: run pytest/Newman, check the equivalence gate, security scan; write `reconciliation.md` | **GATE: human signs off on equivalence** | `lgtm-relay` (Opus validate); Newman | code review + QA + security |
| **6. Operate** | Deploy behind a flag, observe via LGTM, shift traffic | human controls rollout % | `lgtm-docker-stack` / `lgtm-minikube-stack`; feature flags | deploy |
| **7. Reconcile** | Append decision outcomes, update build-plan status, record drift | — | the three ledger artifacts | change log / traceability |

### F.2 What's structurally different from the Java sibling

The Java sibling's Map and Generate phases lean on **MCP servers**
(`quarkus-agent`, `camel-mcp`) that give the agent live, version-matched
ground truth about the target framework and can even scaffold/run the
service. **No Python equivalent exists** for this project's stack (there is
no "FastAPI Agent MCP" or "aiokafka MCP"). This is named explicitly rather
than papered over: the Map phase substitutes careful manual reading of the
Django app plus the `lgtm-python` skill's scaffold conventions, and the
Generate phase has no live dev-mode reload loop as tight as Quarkus's — the
ADLC chapter (ch.06) must say this plainly as a real, not cosmetic,
difference between the two books' agentic workflows.

### F.3 Security in the ADLC

Unchanged from the Java sibling: the Verify gate includes dependency/CVE scan
(`pip-audit`/`uv`'s lock-based resolution), secrets hygiene, and (once
services exist) FastAPI secure-by-default validation — security-by-design is
part of the loop (OWASP/CIS).

---

## J. Iteration / release plan

Unlike the Java sibling — whose r01 was planning-only and whose r02 was the
first walking-skeleton build — **this project's r01 IS the walking skeleton**
(site shell + the pristine "before" monolith + Newman + CI, all running
green). The remaining cadence mirrors the Java sibling's r03–r10 themes,
shifted down by one iteration, for the same total of **10 iterations**.

| Iter | Theme | Deliverable | Mirrors (Java sibling) |
|---|---|---|---|
| **r01** | **Walking skeleton (this relay)** | site scaffold + Django monolith (pristine "before," all six apps/smells live) + Newman baseline + minimal Code-CI green; chapters are stubs | Java r01 (planning) **+** r02 (skeleton), combined |
| **r02** | Front matter + ADLC | Part 0 (00–02), Part 1 (03–04), Part 2 (05–07), finish Part 3 prose (08–10) | Java r03 |
| **r03** | Seams + first event-driven | Part 4 (11–13), ch.14, ch.16, **Notification extraction (ch.17)** + outbox intro | Java r04 |
| **r04** | Data patterns | Part 6 (18–22) incl. **Inventory extraction (ch.19)** + CDC, outbox-done-right, CQRS, ACID→ACD | Java r05 |
| **r05** | Sagas — choreographed | Part 7 ch.23 incl. **Payment extraction (ch.23, aiokafka choreography)** | Java r06 |
| **r06** | Sagas — orchestrated + resilience | Part 7 ch.24–25 incl. **Shipping extraction (ch.24, CNDP Python saga orchestrator)** | Java r07 |
| **r07** | Comms + contracts | Part 8 (26–28) incl. **Order extraction + GraphQL gateway (strangler completes)** | Java r08 |
| **r08** | Operate + deliver + appendices | Part 9 (29–30), ch.31; minikube substrate; port/adapt remaining reuse appendices | Java r09 |
| **r09** | Deck + close | ch.32 conclusion; rebuild the companion deck (`lgtm-presentation`); cross-linking; final validation | Java r10 |
| **r10** | OpenShift/CRC appendix + cross-sibling reconciliation | ch.33 built live on CRC (per standing OpenShift/CRC Appendix Standard); a dedicated drift sweep against the Java sibling's `reconciliation.md` | new — not present in the Java sibling's table; added so the 10-iteration count matches while giving the OpenShift appendix and a final reconciliation pass their own iteration rather than crowding r08 |

**r01 boundary:** r01 ends at a green site build + green monolith + green
Newman + green Code-CI, all on branch `docs/r01-walking-skeleton`. No FastAPI
service exists yet. Branch/PR/push requires explicit user go-ahead (lane
DELIVERY in `_plans/r01-build-plan.md`), per standing memory — this relay
writes files only.

---

## K. Execution mapping

All work runs through `lgtm-relay` (Opus plan → Sonnet execute → Opus
validate), gated on user review of each iteration's plan before any code.

| Work stream | Primary skill(s) | Executor tier | Parallel? | Collision risk |
|---|---|---|---|---|
| Site scaffold | `lgtm-jekyll` | Sonnet | sequential first (owns `_config.yml`, CSS) | **high** — must land before chapters |
| Chapter authoring | `lgtm-tutorial` | Sonnet / Opus validate | parallel across `_docs/NN-*.md` once scaffold exists | low per-file; **serialize `_config.yml`/`_parts/`/nav** |
| Monolith code | Django (manual) + `lgtm-python` (scaffold conventions) | Sonnet | sequential (shared `pyproject.toml`/`config/`) | **high** — one writer for the project root |
| Service extraction (r02+) | `lgtm-python` (FastAPI/aiokafka/grpcio/Strawberry shapes) | Sonnet | one service at a time (walking skeleton first) | med — isolate per-service dirs |
| Infra (dev loop + CI) | `lgtm-docker-stack` (docker-primary, podman-compatible) | Sonnet | parallel with authoring | **high** — single compose source; do not mix in `lgtm-podman-stack`'s compose as a second source |
| k8s substrate | `lgtm-minikube-stack` | Sonnet | after services exist (r08) | med — one writer for `k8s/` overlays |
| Testing harness | pytest/pytest-django + Newman (reuse shape from the Java sibling's `tooling/newman/`) | Sonnet | parallel per example | low |
| Diagrams | `lgtm-diagram-generator` | Sonnet | parallel | low; serialize `assets/diagrams/README.md` catalogue |
| Deck | `lgtm-presentation` | Sonnet | last (r09) | low (own `presentation/`) |
| Repo / release | `lgtm-github` | Sonnet / Opus validate | **gated** | **gate** — never without explicit user permission |

**Single-writer (serialize) files:** `_config.yml`, `assets/css/site.css`,
`_parts/*`, nav, `pyproject.toml`/`uv.lock` (the monolith's, until a second
Python package exists), `compose.yaml`, `assets/diagrams/README.md`, and the
three `_plans/*` ledgers. **Safe to parallelize:** independent
`_docs/NN-*.md`, independent diagram SVG pairs, per-example dirs, and (once
r02+ begins) independent new FastAPI service directories.

---

## L. Acceptance criteria

### L.1 r01 (this build) — checkable now

Mirrors the per-lane acceptance criteria already stated in
`_plans/r01-build-plan.md` §Acceptance criteria; restated here for the
ledger's own self-containment:

- [ ] `build-plan.md` (this file) covers §A/§B(12-part/34-chapter list)/§C/§D/
      §E(six-extraction roadmap)/§F(7-phase ADLC)/§J(r01–r10)/§K/§L/§M.
- [ ] `decisions.md` seeds the named DRQs (accent/emoji, camelCase, Django/
      Python version, compose engine, monolith port, shared-vs-owned schema,
      saga reuse, two-phase policy, Newman gate, monolith permanence) with
      statuses, plus a version matrix matching `r01-build-plan.md`'s pins.
- [ ] `reconciliation.md` has the append-only template plus an r01 section.
- [ ] The §B.2 chapter list is exactly 34 ordered chapters, titles derived
      from the Java sibling's `_docs/*` front-matter, matching the SITE
      lane's stub count.
- [ ] The monolith, Newman, infra, and CI lanes meet their own acceptance
      bars as stated in `_plans/r01-build-plan.md` (not restated here to
      avoid two sources of truth drifting).

### L.2 Eventual build — acceptance bar (post-r01)

- [ ] Every chapter ≥ 2000 words excluding code/diagrams, with a runnable
      example and a verification-status footer.
- [ ] The monolith runs; the equivalence gate is green in CI.
- [ ] Every extracted service passes the monolith's Newman collection
      unchanged before its Django app is decommissioned.
- [ ] Every one of the six extractions states explicitly which Phase-A
      bridge it used (thin-FastAPI-over-Django-ORM vs direct SQLAlchemy
      re-map) — no extraction may imply a compatibility shim that doesn't
      exist (§E).
- [ ] Every migration chapter carries a real "ADLC in Action" callout with
      traceable Frame/Plan/Generate/Verify/Reconcile evidence, naming the
      manual-reconnaissance substitution where it applies (§F.2).
- [ ] Site CI + Code CI (uv sync + pytest + Newman equivalence gate) green;
      security-by-design evidence (SBOM/CVE-scan via `pip-audit`) in CI.
- [ ] Reconciliation log shows zero unexplained drift from reused sources
      (the Java sibling's site chrome, the CNDP saga orchestrator, the
      Newman collection shape).
- [ ] Full system runs on minikube and, per the OpenShift/CRC Appendix
      Standard, on OpenShift Local (CRC) at ch.33.

---

## M. Risks + detection

| ID | Risk | How it silently goes wrong | Detection / mitigation |
|---|---|---|---|
| **R1** | Scope explosion | 34 ch × 2k × running code balloons; services built before r02 | r01 caps scope at monolith+site+gates; `build-plan.md` is the only backlog |
| **R2** | Wrong monolith state | Monolith built as the Java sibling's frozen/decommissioned end-state instead of the pristine "before" | DRQ-023; grep for six live `# SMELL[ch.` tags + six live apps, not six 404s |
| **R3** | ADLC is hand-wavy | Described in Part 2, never shown; the "no MCP equivalent" gap glossed over | per-chapter "ADLC in Action" callout is an acceptance gate; F.2 states the gap explicitly rather than hiding it |
| **R4** | Reuse drift | Site chrome / Newman shape / saga orchestrator diverge from source without being named | `reconciliation.md` tracks every artifact→source; r01 section seeds this |
| **R5** | Docker/podman conflict | Someone pulls `lgtm-podman-stack`'s compose as a second source; image-tag mismatch | single `lgtm-docker-stack` compose source (docker-primary, podman-compatible, DRQ-004); pin tags once in `.env` |
| **R6** | Django 5.x × Python 3.14 incompatibility | Django 5.2 patch lands 3.14 support late, or not at all | `manage.py check` + pytest on 3.14 in CI; escalate DRQ to fallback Python 3.13 (named in DRQ-003) |
| **R7** | JSON contract drift | DRF's snake_case default leaks through despite DRQ-002 | Newman green-check asserts camelCase keys; serializer-level test |
| **R8** | Two-phase policy dishonesty | A chapter implies a Spring-compat-style drop-in shim exists for Django→FastAPI | DRQ-009 names the honest two-phase framing; each extraction chapter must state which Phase-A bridge it used |
| **R9** | Pattern-coverage gaps | A deck pattern quietly never lands in the Python retelling | §C matrix is the checklist; validate phase cross-checks matrix vs shipped chapters each relay |
| **R10** | Equivalence suite rots | Newman collection drifts from the API as chapters are authored | collection versioned with the monolith; CI runs it against every service; failure blocks "done" |
| **R11** | Shared-root collisions | Two executors edit `pyproject.toml`/`_config.yml`/`compose.yaml` at once | §K single-writer rule; per-module isolation otherwise |
| **R12** | Premature push / repo creation | Agent creates a repo or pushes without approval | standing memory gate; this relay writes files only, no git commands run |
| **R13** | Cross-sibling chapter-list divergence | SITE lane's 34 stub titles/filenames don't match this §B.2 list exactly | r10's dedicated cross-sibling reconciliation pass; both lanes derive titles from the same Java front-matter source in this same relay |

---

*Python sibling of `modernizing-enterprise-applications`. r01 is a walking
skeleton — the monolith, site shell, and gates ship now; FastAPI services and
chapter prose begin at r02.*
