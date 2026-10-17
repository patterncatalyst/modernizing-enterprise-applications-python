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
28. **27 The FastAPI Chassis** — config via a frozen `@dataclass`'s
    `from_env()` classmethod (**DRQ-083 corrects this blurb's earlier
    pydantic-settings claim** — no service ever adopted pydantic-settings;
    7/8 services follow the `Settings.from_env()` shape), dependency
    injection, structured health/metrics, OpenAPI, async lifespans — "what
    you migrated *to*," the Python analogue of the Quarkus/MicroProfile
    chassis chapter. **Landed r08** — authored as an honest per-service
    used/partial/deferred scorecard (`/health` 6/8, `errors.py` 6/8,
    `tenacity` 1/8, OTel/metrics 0/8 deferred to ch.30), not a claim of a
    uniform shared chassis library (DRQ-082, deferred by choice).
29. **28 Contracts & the Service Registry** — schema/API/shared-data-type
    registry use cases; Apicurio with Avro/Protobuf/JSONSchema/OpenAPI/
    AsyncAPI (unchanged — language-agnostic). **Landed r08** —
    `examples/09-schema-registry-demo/` realizes the Avro path on pure-Python
    fastavro + aiokafka + the Apicurio v3 REST API (honoring DRQ-033's
    standing rejection of confluent-kafka), with a hand-rolled global-id wire
    envelope; schema evolution verified live (v2 optional-with-default
    ACCEPTED 200, v3 retype REJECTED 400 `RuleViolationException`) against
    Apicurio 3.3.3 via Testcontainers (DRQ-084).

**Part 9 — Operating the Modernized System**
30. **29 Deployment Patterns** — rolling, breaking-schema-change, blue-green
    tied to the cutover; which fits synchronous vs event-driven services.
    **Landed r09** — `deploy/k8s/` (kustomize `base` + a single
    `overlays/minikube` overlay) for all 8 services, probes matching each
    service's real `/health` posture (`tcpSocket` for the strangler proxy +
    review-service, `httpGet /health` for the other six, DRQ-089), one
    shared `DATABASE_URL` Secret with schema-per-service-in-code; renders
    clean (`kubectl kustomize` → 23 resources per tree, `kubeconform -strict`
    23/23 Valid); the headless-render limit (no server dry-run/admission
    without a live cluster) is stated explicitly, deferred to the user's
    minikube run at ch.30/r10.
31. **30 Mesh, Observability & Distributed Tracing** — Istio, Kiali,
    OpenTelemetry + the LGTM stack — on minikube; Python auto-instrumentation.

**Part 10 — Delivering & Reflection**
32. **31 CI/CD, GitOps, Progressive Delivery & Supply Chain** — the actual
    GitHub Actions workflows (`code-ci.yml` and friends), the equivalence-gate
    job, UBI Python image builds, GitOps, feature-flag/canary cutover, SBOM +
    CVE scan + policy-as-code. **Landed r09** — `examples/10-supply-chain/`
    (syft→grype→policy, scanning container IMAGES, DRQ-090) scans
    order-service "after" (hard-gated) and the frozen `00-monolith` "before"
    (non-gating/reported, A/B-4=B, DRQ-088); the real finding was 35 High
    CVEs on BOTH images, all `fix-state: not-fixed` in the shared UBI base
    layer with **no patched tag to re-pin onto** (confirmed via `skopeo`) —
    the chapter gates on **fixable findings only** (DRQ-094), surfacing the
    35 unfixable Highs rather than hiding them; order-service = 0 fixable
    Highs = a real PASS. New additive `supply-chain.yml` CI gate corrects the
    Java sibling's `paths:`-filtered, `*-ok`-less shape (DRQ-092).
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
| OpenShift on CRC | new, Python-native (Django/FastAPI UBI images) | **landed r11** (companion to ch.33, per standing OpenShift/CRC Appendix Standard memory) — Helm chart + Routes-as-edge + 3 SCC postures + podman→internal-registry delivery + an opt-in OSSM3/Kiali/RHBOTel platform tier; headless-verified (`helm lint` + `helm template \| kubeconform -strict -ignore-missing-schemas`), live CRC run pending (DRQ-104) |
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
| Strangler Fig + proxy/redirection/shared-DB variants (B) | ch.14 | ASGI reverse-proxy façade | the spine; **Decommission COMPLETE r07** — all six extractions done, the proxy is now flagless (every `*_enabled` boolean + the monolith fallback removed, unmatched→404), the monolith is frozen-not-deleted in-repo plus a `reference/monolith-before` branch + `v0-monolith`/`stage/01..06` tags (DRQ-075), reached via a pre-cutover reversibility proof before the one deliberate irreversible move (DRQ-077) |
| Content-based Routing (B) | ch.16, ch.17 | façade path/header routing | **landed r03** — `STRANGLER_NOTIFICATION_ENABLED` routes `/api/notifications*` |
| Anti-Corruption Layer (B) | ch.16, ch.19 | FastAPI translation layer at the seam | **ch.16 landed r03** at the notification seam; **ch.19 landed r04** — `inventory.proto` is the ACL for the gRPC seam, deliberately wire-vocab-distinct from the domain, with a byte-identical drift guard (`scripts/check-proto-drift.sh`, DRQ-042) |
| Decorating Collaborator (B) | ch.16, ch.19 | FastAPI client wrapper | **ch.16 landed r03** — the monolith's `order_placed_consumer` decorates the monolith's own read-model from the same event the service consumes (DRQ-038); **ch.19 inventory retire landed r04** — the monolith's `RemoteInventoryClient` wraps the gRPC seam, and the CDC backfill connector is retired per its runbook once the owned schema is reached (DRQ-044) |
| Shared Data (C) | ch.18 | shared Postgres schema | and its limits |
| Owned Data / Database-per-Service (C) | ch.18, ch.19 | own Postgres schema per service (Alembic) | **landed r04** — inventory's CDC-backfilled, Alembic-migrated `inventory` schema completes the shared→owned narrative begun with notification's day-one owned schema (DRQ-035); own-migration + own-seed is the steady-state path, CDC is transition-only (DRQ-041) |
| Synchronous gRPC (C) | ch.19 | `grpc.aio` server + grpcio client (`CheckStock`/`Reserve`/`Release`/`GetStock`) | **landed r04** — the project's first synchronous inter-service RPC seam; atomic conditional-UPDATE `Reserve` (concurrency-safe, race-tested) + compensating `Release` issued outside the monolith's local `transaction.atomic()` (DRQ-043) |
| Transaction Log Tailing (C) | ch.19 | Debezium (unchanged) | folded into CDC; **landed r04**, transition-only (DRQ-044) |
| Simple CDC (C) | ch.19 | Debezium Postgres connector | **landed r04** — inventory backfill (snapshot + pgoutput stream from `public.inventory_items`), then retired; confirmed NOT in CI, mirrors the Java sibling's gate (DRQ-044/045) |
| Transactional Outbox (C) | ch.17 (intro), ch.20 | Django `OutboxEvent` model (partial index) + `outbox_relay` management-command poller (aiokafka producer); payment-service's own outbox (`examples/05-payment-service/`) | **landed r03** (monolith instance) — cures SMELLS #5/#6 (sync-send + dual-write); a DECLINE/SHIP-FAIL checkout leaves zero outbox rows (tested); **ch.20 (outbox-done-right deep dive) landed r05** — authored against a *second*, now-mature outbox instance (payment-service's own transactional outbox publishing `payment.captured`/`payment.declined`) |
| Event-Driven (C) | ch.17 | aiokafka producer (relay) → aiokafka consumers (monolith self-consumer + notification-service) | **landed r03** — first event-driven extraction; `order.placed` hand-maintained contract (DRQ-036) |
| Idempotent Consumer (C) | ch.17 | DB partial-unique backstop, deduped by `order_id`/`customerId` | **landed r03** — both the monolith's `order_placed_consumer` and the notification-service's consumer are idempotent on redelivery |
| Event Sourcing (C) | ch.21 | light/optional | demoted-light: high cost, not required; **landed r07** — the outbox-as-event-log framing is taught against order-service's own outbox (`order.placed`), not full event-sourced replay |
| CQRS (C) | ch.21, ch.26 | FastAPI write aggregate + denormalized `order_view` read model, same-DB, same-transaction projection | **landed r07 (ch.21)** — the order extraction's `order_view` is the first load-bearing CQRS read model (deferred from r05, DRQ-057); every write path upserts it in the SAME local transaction (DRQ-072), reads are served exclusively from it, `rebuild_order_view` proves it's rebuildable, and a dedicated projection-disabled negative proves the read side isn't silently falling back to the write tables (DRQ-079) |
| Distributed Transactions ACID→ACD (C) | ch.22 | conceptual | **landed r05**, extended r07 — the `POST /api/orders` 201→202 PENDING flip (DRQ-049) is the concrete break of the one-ACID-transaction checkout into a choreographed saga, realized and taught in ch.22; **r07 completes it for all six contexts** — SMELL #1/#2 (god checkout service, one shared ACID transaction) are STRUCK, since order-service's own local transaction now spans only its own `order_svc` schema (DRQ-080) |
| Saga — general (D) | ch.23 | compensations | **landed r05** — the payment extraction's saga reaction (`order_saga_listener`) and its compensating gRPC `Release` are the first concrete saga in the project |
| Saga — Choreographed (D) | ch.23 | aiokafka consumer/producer | **landed r05** — payment extraction (`order.placed`→`payment.captured`/`payment.declined`); deliberate contrast with r06's orchestrated shipping saga |
| Saga — Orchestrated (D) | ch.24 | CNDP Python DB-backed saga orchestrator | **landed r06** — shipping extraction adapts + embeds the CNDP orchestrator (`select(Saga).with_for_update()`, idempotent `advance()`, reverse-order `compensate()`, DRQ-059); crash-resumable (`resume_running_sagas()`), a durability upgrade over the Java sibling's `InMemorySagaService` (DRQ-060); deliberate orchestration-vs-choreography contrast with r05's payment saga |
| Idempotent Compensation (D) | ch.23 | inventory-service `idempotency_key` + `inventory.compensations` ledger (`ON CONFLICT DO NOTHING`), plus a client-side status-transition guard in `order_saga_listener` | **landed r05** — closes DRQ-043's explicit deferral; double-delivery proven at both layers (saga-listener guard + ledger), stock net-zero (94→94) under forced redelivery |
| Circuit Breaker / Discovery / Health (E) | ch.25, ch.27, ch.30 | `tenacity`/`circuitbreaker` + FastAPI health routes | reframed off Netflix OSS, same as Java sibling; **ch.25 landed r06** — the gRPC deadline, compensating `Release`, outbox at-least-once + two-layer idempotency, and the orchestrator's own timeout/crash-resume are documented as the existing chassis, plus one new concrete mechanism (a `tenacity` retry-with-timeout on the shipping saga's `enrich` HTTP call, DRQ-068/069); `pybreaker` circuit breaker + bulkhead are named but deferred (no second failure mode yet forces them) |
| Microservices Chassis (E) | ch.27, ch.32 | FastAPI + frozen `@dataclass`/`from_env()` config (**DRQ-083 corrects this row's earlier "pydantic-settings" claim** — no service ever adopted it) | **landed r08 (ch.27)** — honest per-service used/partial/deferred scorecard across all 8 services (config 7/8, schemas-via-pydantic 6/8, `/health` 6/8, `errors.py` 6/8, `tenacity` 1/8, OTel/metrics 0/8 deferred to ch.30); a shared chassis library is DEFERRED BY CHOICE, not built (DRQ-082) |
| Fixed / Rolling / Breaking-Schema / Blue-Green (F) | ch.29 | manifests (unchanged) | Fixed demoted to a paragraph; **landed r09** — `deploy/k8s/` kustomize `base` + `overlays/minikube`, real per-service probes (`tcpSocket` proxy+review, `httpGet /health` the other six, DRQ-089), one shared `DATABASE_URL` Secret; renders clean, `kubeconform -strict` 23/23 Valid both trees; server-side admission/rolling-update behavior itself needs a live cluster, deferred to the user's minikube run at ch.30/r10 |
| Service/Schema/API registry + requirements (G) | ch.28 | Apicurio (unchanged) | **landed r08** — `examples/09-schema-registry-demo/` on pure-Python fastavro + aiokafka + Apicurio v3 REST (no confluent-kafka, honoring DRQ-033), hand-rolled global-id envelope; v2 optional-field evolution ACCEPTED (200), v3 field-retype REJECTED (400 `RuleViolationException`), both verified live via Testcontainers against Apicurio 3.3.3; Apicurio added to `compose.yaml`/`.env.example` additively (`:8095`), scoped to this one demo (DRQ-084/DRQ-085); separate additive `schema-registry.yml` CI gate (DRQ-086) |
| Service Mesh / Observability / Tracing (H) | ch.30 | Istio + OTel Python auto-instrumentation (minikube) | **landed r10** — `deploy/k8s/istio/` (`PeerAuthentication` STRICT mesh-wide in `mea`, with a PERMISSIVE edge exception for the plaintext NodePort → strangler-proxy hop; the `sidecar.istio.io/inject` pod-template LABEL on the 8 app Deployments, DRQ-097; postgres/kafka kept unmeshed, matching the Java sibling and datamesh precedent) plus `deploy/k8s/observability/` (a single `grafana/otel-lgtm:0.36.0` all-in-one Deployment, OTLP ingest, and a Prometheus-SD scrape of each Envoy sidecar's stats, DRQ-099); app-level OpenTelemetry auto-instrumentation added to exactly 3 of 8 services — strangler-proxy, order-service, inventory-service (DRQ-096 = the synchronous checkout→reserve trio, avoiding the outbox trace-context hazard the async trio would have required) — naming the property the mesh and app-level OTel split between them: the mesh gives every hop breadth with zero app-code changes, OTel on 3 services adds in-process depth; the Kafka saga hops stay mesh-visible only, named as app-level-deferred (the same posture the Java sibling took). Verification state (`verified-live (user-run)` or a named `deferred` fallback) is carried in ch.30's own footer, not restated here. |
| Caching (H) | App. H (Java-sourced, adapted) | demoted → appendix | generic; no migration driver |
| API Gateway + Service Discovery evolution (H) | ch.26, ch.28 | FastAPI gateway + Apicurio | **GraphQL/Aggregation Gateway landed r07 (ch.26)** — see the row below |
| REST / gRPC / GraphQL (H) | ch.26 | FastAPI / grpcio / Strawberry | **landed r07** — `examples/08-graphql-gateway/` (:8090) is an additive, data-less Strawberry gateway with its own front door, federating order/payment/shipment/review over REST and per-item stock over gRPC behind one query, depth/token-bounded, partial-failure = per-field null + `errors[]` not a 500 (DRQ-074) |
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
(ch.31 — **landed r09**: `examples/10-supply-chain/` scans container images
with syft→grype→policy, order-service hard-gated + the frozen monolith
non-gating per DRQ-088; the gate blocks on fixable findings only after a
re-pin was confirmed impossible against the shared UBI base layer's 35
not-fixed Highs, DRQ-094; a separate additive `supply-chain.yml` corrects the
Java sibling's `paths:`-filtered/`*-ok`-less shape, DRQ-092); explicit DDD +
event storming (Part 4); a measured Django-vs-FastAPI
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
recorded here as the roadmap future relays execute against. **Rows 0 and 1
are now done, built in r02** (`_plans/r02-build-plan.md`): the ASGI strangler
façade (`examples/01-strangler-proxy/`) and the review extraction
(`examples/02-review-service/`), behind `STRANGLER_REVIEW_ENABLED`, gated
green by the Newman `review-equivalence-gate`. **Row 2 is now done, built in
r03** (`_plans/r03-build-plan.md`): the notification extraction
(`examples/03-notification-service/`), behind
`STRANGLER_NOTIFICATION_ENABLED`, gated green by the new
`notification-equivalence-gate`. **Row 3 is now done, built in r04**
(`_plans/r04-build-plan.md`): the inventory extraction
(`examples/04-inventory-service/`) — the project's first synchronous gRPC
seam and first CDC (Debezium) use, own `inventory` Postgres schema reached
via own-migration + own-seed with a transition-only CDC backfill, behind the
two independent cutover flags `STRANGLER_INVENTORY_ENABLED` (reads) and
`INVENTORY_MODE=local|grpc` (reserve/release), gated green by the new
`inventory-equivalence-gate`. **Row 4 is now done, built in r05**
(`_plans/r05-build-plan.md`): the payment extraction
(`examples/05-payment-service/`) — the project's first **choreographed saga**
and first deliberate change to a previously-stable response contract
(`POST /api/orders` 201 CONFIRMED → 202 PENDING in `PAYMENT_MODE=choreographed`,
byte-for-byte 201 unchanged in `PAYMENT_MODE=synchronous`). Payment-service
reacts to `order.placed`, captures/declines, and publishes its own
`payment.captured`/`payment.declined` events from its own `payment` schema +
own transactional outbox (no grpcio — compensation is issued by the
monolith); the monolith's new `order_saga_listener` management command reacts
to those events, dispatching shipping in-process and compensating via an
idempotent gRPC `Release` (closing DRQ-043) on decline or on the new
`SHIPPING_FAILED` terminal (shipping-fail Option A, DRQ-054). Behind the two
independent cutover flags `STRANGLER_PAYMENT_ENABLED` (reads) and
`PAYMENT_MODE=synchronous|choreographed` (capture), gated green by the new
`payment-equivalence-gate` (including a stuck-PENDING honesty negative).
**Row 5 is now done, built in r06** (`_plans/r06-build-plan.md`): the
shipping extraction (`examples/06-shipping-service/`, :8087) — the project's
first **orchestrated saga**, adapting the CNDP Example-17 DB-backed saga
orchestrator (`cloud-native-design-patterns/examples/17-sagas/python/`,
DRQ-007/DRQ-059) onto this repo's async SQLAlchemy+asyncpg+Alembic stack
(`select(Saga).with_for_update()`, idempotent `advance()`, reverse-order
`compensate()`, its own `shipping` schema for sagas/saga_log/shipments/
outbox). A **durability upgrade over the Java sibling's in-memory
orchestrator**: `resume_running_sagas()` crash-resumes from the persisted
`step_index` at startup, proven live (kill mid-saga → restart → resume
without re-invoking `enrich`, DRQ-060). Shipping-service consumes
`payment.captured`, runs enrich (REST, httpx+tenacity)→dispatch→
book_carrier (SHIP-FAIL sentinel in the address)→emit, and publishes
`shipment.dispatched`/`shipment.failed` from its own outbox; the monolith's
new `OrderStatus.AWAITING_SHIPMENT` sits between `payment.captured` and a
terminal status, and `CONFIRMED` now requires a `shipment.dispatched` event
(DRQ-061/DRQ-063). **Payment-service gains a refund hop** — it consumes
`shipment.failed` and, if it holds a CAPTURED payment for that order,
transitions to a new `REFUNDED` status and emits `payment.refunded`,
**closing the stranded-payment gap DRQ-054 named and deferred** (DRQ-064).
Behind the two independent cutover flags `STRANGLER_SHIPPING_ENABLED`
(reads, a transparent pass-through) and `SHIPPING_MODE=inprocess|
orchestrated` (dispatch), gated green by the new
`shipping-equivalence-gate` (including the stuck-AWAITING_SHIPMENT honesty
negative). **Row 6 is now done, built in r07** (`_plans/r07-build-plan.md`)
— **THE FINALE, and with it the strangler fig is COMPLETE: all six
extractions are done, the monolith is decommissioned.** The order extraction
(`examples/07-order-service/`, :8088) is CQRS from day one: a normalized
write aggregate (`orders`/`order_items`) plus a denormalized `order_view`
read table, upserted in the SAME local transaction as every write
(DRQ-072); every `GET` is served exclusively from `order_view`. It lifts the
monolith's four saga reactions (`payment.captured`/`payment.declined`/
`shipment.dispatched`/`shipment.failed`) into its own idempotent consumer,
owns its own forward-filled `customers` table (`order_svc` schema,
customer FK→snapshot, DRQ-073), and produces `order.placed` from its own
transactional outbox (DRQ-078). A new, additive **Strawberry GraphQL
gateway** (`examples/08-graphql-gateway/`, :8090) federates order/payment/
shipment/review (REST) and per-item stock (gRPC) behind one data-less
aggregation query, with its own front door — never routed through the
strangler proxy (DRQ-074). The decommission itself: a pre-cutover
reversibility proof (full extracted topology vs. bare-monolith, both green)
was captured immediately before the one deliberate, system-wide
**irreversible** move (DRQ-077) — the monolith is frozen-not-deleted
in-repo (a `reference/monolith-before` branch + `v0-monolith`/`stage/01..06`
tags preserve the learner-facing "before," DRQ-075), the strangler proxy
becomes **flagless** (every `*_enabled` boolean and the monolith fallback
removed; unmatched paths 404; `test_routing.py` rewritten, 29/29 green), and
shipping-service's `enrich` call is re-pointed from the monolith to
order-service. **SMELL #1 (god checkout service) and #2 (one ACID
transaction) are STRUCK** — ACID→ACD is now realized for all six contexts,
not just payment/shipping (DRQ-080). The Newman equivalence suite converts
to a contract/acceptance suite (no more monolith to compare against,
DRQ-076), proven green ≥2× against the fully monolith-free mesh plus three
honesty negatives (consumer-down, compensation-disabled, and a
CQRS-specific **projection-disabled → stale-read** negative, DRQ-079) — one
real integration bug (a staged GraphQL query that didn't match the as-built
schema) was found and fixed along the way.

| # | Service | Seam / mechanism | Data & transaction handling | Target runtime | Chapters | Status |
|---|---|---|---|---|---|---|
| 0 | — | Insert the ASGI strangler façade in front of the monolith | n/a | — | ch.14 | done |
| 1 | **review** | REST leaf, no sync deps; façade redirect by path; ACL | Shared schema initially; DB decomposition deferred to ch.18/19 | FastAPI | ch.15 *(walking skeleton)* | done |
| 2 | **notification** | Event consumer; content-based routing; decorating collaborator | Outbox in monolith → Kafka; idempotent consumer; **own schema from day one** (`notification`, Alembic-migrated — first owned schema, DRQ-035); the monolith's own notification read-model survives as a decorating collaborator (`order_placed_consumer`, DRQ-038) | FastAPI + **aiokafka** | ch.16–17 | done |
| 3 | **inventory** | Synchronous gRPC; decomposed DB; decorating collaborator | CDC (Debezium) backfill from shared schema → owned DB (transition-only, then retired), then cut writes; own `inventory` schema (Alembic, own-seed); `order_items` FK→snapshot | FastAPI + **grpcio** server (`grpc.aio`, :9004) | ch.18–19 | **done** |
| 4 | **payment** | Event choreography (`order.placed`→`payment.captured`) | Choreographed saga via **aiokafka**; idempotent compensations (closes DRQ-043); ACID→ACD realized via the 201→202 flip | FastAPI + aiokafka | ch.20, ch.22, ch.23 | **done** |
| 5 | **shipping** | Completes the chain; alternative orchestration | **Orchestrated saga** via the reused CNDP Python DB-backed saga orchestrator; crash-resumable; refund hop closes DRQ-054 | FastAPI + saga orchestrator | ch.24–25 | **done (r06)** |
| 6 | **order** (+ gateway) | Core aggregate, extracted last; GraphQL read side | CQRS read model (same-DB, same-tx projection); monolith decommissioned | FastAPI REST/aiokafka + **Strawberry** GraphQL gateway | ch.21, ch.26 | **done (r07) — strangler fig COMPLETE** |

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
| **r01** | **Walking skeleton** | site scaffold + Django monolith (pristine "before," all six apps/smells live) + Newman baseline + minimal Code-CI green; chapters are stubs — **done** | Java r01 (planning) **+** r02 (skeleton), combined |
| **r02** | **Strangler proxy + review extraction — done** | ASGI strangler façade (`examples/01-strangler-proxy/`, ch.14) + Review extraction Phase A (documented) / Phase B (shipped) (`examples/02-review-service/`, ch.15), auth contract realized (Option B), Newman `review-equivalence-gate` green through the proxy flag OFF and ON | Java r03 (re-themed: this project's r02 is the first extraction, not front matter) |
| **r03** | **Notification extraction — event-driven, outbox + aiokafka, own schema — done** | `OutboxEvent` transactional outbox cures SMELLS #5/#6 (`examples/00-monolith/`); notification extraction (`examples/03-notification-service/`, ch.16–17) on aiokafka with its own Alembic-migrated `notification` schema; the monolith becomes a consumer of its own event (DRQ-038); `STRANGLER_NOTIFICATION_ENABLED` cutover; Newman async bounded-wait suite + `notification-equivalence-gate` green both flag states | Java r04 |
| **r04** | **Inventory extraction — gRPC seam + CDC backfill + FK→snapshot — done** | Part 6 (18–19): `inventory.proto` (gRPC ACL) + drift guard; inventory extraction (`examples/04-inventory-service/`, ch.18–19) with own `inventory` Alembic schema + own-seed, atomic conditional-UPDATE Reserve (concurrency-safe, race-tested) + compensating Release issued outside the monolith's local transaction; transition-only Debezium CDC backfill (retired, NOT in CI); `order_items` FK→snapshot; two cutover flags (`STRANGLER_INVENTORY_ENABLED` + `INVENTORY_MODE`); Newman `inventory-equivalence-gate` green fully-gRPC and fully-local, plus RED-then-green negative checks | Java r05 |
| **r05** | **Sagas — choreographed — done** | Part 7 ch.20/22/23 (ch.21 deferred to r07): **Payment extraction (`examples/05-payment-service/`, aiokafka choreography)** — `POST /api/orders` 201→202 PENDING in choreographed mode (zero-regression synchronous mode unchanged); `order_saga_listener` reacts to `payment.captured`/`payment.declined`; idempotent inventory `Release` (ledger + `idempotency_key`) closes DRQ-043; shipping-fail Option A (new `SHIPPING_FAILED` terminal, refund-on-ship-fail deferred to r06); `STRANGLER_PAYMENT_ENABLED` + `PAYMENT_MODE` two-dimension cutover; Newman converted to async bounded-wait + stuck-PENDING negative; `payment-equivalence-gate` green | Java r06 |
| **r06** | **Sagas — orchestrated + resilience — done** | Part 7 ch.24–25: **Shipping extraction (`examples/06-shipping-service/`, :8087) via the reused CNDP Python DB-backed saga orchestrator** (ch.24), crash-resumable (durability upgrade over the Java sibling's in-memory orchestrator), `AWAITING_SHIPMENT` lifecycle, orchestrated-vs-choreographed contrast with r05; **payment-service refund hop closes DRQ-054** (ship-fail now refunds a captured payment); ch.25 (failure-mode taxonomy + the one new `tenacity` enrich-retry mechanism, pybreaker/bulkhead deferred); two cutover flags (`STRANGLER_SHIPPING_ENABLED` + `SHIPPING_MODE`); Newman `shipping-equivalence-gate` green both ways + stuck-AWAITING_SHIPMENT negative (and a poll-script bug the live cutover caught and fixed — retry through `AWAITING_SHIPMENT`, not just `PENDING`) | Java r07 |
| **r07** | **Order + GraphQL gateway — THE FINALE, strangler fig COMPLETE — done** | Part 8 ch.21/26: **Order extraction (`examples/07-order-service/`, :8088, CQRS from day one — same-DB two-table read model, same-tx projection, DRQ-072) + the additive Strawberry GraphQL gateway (`examples/08-graphql-gateway/`, :8090, own front door, DRQ-074)**; lifts the four saga reactions, own outbox → `order.placed`, customer FK→snapshot (owns `customers`, DRQ-073); monolith **decommissioned** — pre-cutover reversibility proof, then the one irreversible move (DRQ-077): flagless strangler proxy, monolith frozen-not-deleted + `reference/monolith-before` branch + `v0-monolith`/`stage/01..06` tags (DRQ-075); shipping's `enrich` re-pointed to order-service; **SMELL #1/#2 STRUCK, ACID→ACD for all six contexts** (DRQ-080); equivalence suite converted to a contract/acceptance suite, green ≥2× monolith-free plus 3 negatives incl. the CQRS projection-disabled check (DRQ-076/DRQ-079); ch.21 (Event Sourcing & CQRS, deferred from r05) + ch.26 authored | Java r08 |
| **r08** | **Part 8: FastAPI chassis + contracts/registry — done** | ch.27 (FastAPI Chassis) authored as an honest per-service used/partial/deferred scorecard, correcting the plan's earlier pydantic-settings claim to the as-built frozen `@dataclass`/`from_env()` shape (DRQ-082/DRQ-083); ch.28 (Contracts & Service Registry) authored + `examples/09-schema-registry-demo/` built (pure-Python fastavro + aiokafka + Apicurio v3 REST, hand-rolled global-id envelope, honoring DRQ-033's rejection of confluent-kafka, DRQ-084); round-trip + schema-evolution compatibility (v2 ACCEPT-200 / v3 REJECT-400) verified live via Testcontainers; Apicurio added to `compose.yaml`/`.env.example` additively (`:8095`, DRQ-085), live JSON event flows untouched; new separate `schema-registry.yml` CI gate, `code-ci.yml`/`contract-gate`/`code-ci-ok` untouched (DRQ-086); new pins fastavro 1.13.1 + apicurio-registry 3.3.3 (DRQ-087). **Part 8 (ch.27–28) is now complete; ch.29–33 remain.** Per the approved `_plans/backmatter-track-plan.md` (which diverges from this table's original r08/r09/r10 grouping, as that plan itself notes), the remaining back-matter work is sequenced r09 = ch.29 (Deployment Patterns, `deploy/k8s/`) + ch.31 (CI/CD & Supply Chain, `examples/10-supply-chain/`), r10 = ch.30 (Mesh/Observability, live/user-run) + ch.32 (the final project). | Java r09 (regrouped per the back-matter track plan) |
| **r09** | **Part 9 (ch.29) + Part 10 (ch.31): Deployment Patterns + CI/CD & Supply Chain — done** | ch.29 (Deployment Patterns) authored + `deploy/k8s/` built — kustomize `base` + a single `overlays/minikube` overlay for all 8 services, probes matching each service's real `/health` posture (`tcpSocket` for proxy+review, `httpGet /health` the other six, DRQ-089), one shared `DATABASE_URL` Secret with schema-per-service-in-code, renders clean (`kubectl kustomize` 23/23 resources, `kubeconform -strict` Valid both trees), headless-render limit stated and deferred to r10's live minikube run; ch.31 (CI/CD & Supply Chain) authored + `examples/10-supply-chain/` built — syft→grype→policy on container IMAGES, A/B-4 resolved **B** (order-service hard-gated + frozen `00-monolith` non-gating, DRQ-088); the grype gate was red on both images (35 High, 0 Critical, all `fix-state: not-fixed` in the shared UBI base layer, no patched tag to re-pin onto per a `skopeo` check) — **gate on fixable findings only** (DRQ-094, correcting this plan's own "re-pin" risk-mitigation assumption), order-service = 0 fixable Highs = PASS; two new additive CI gates (`deploy-manifests.yml`, `supply-chain.yml` — the latter correcting the Java sibling's `paths:`-filtered/`*-ok`-less shape, DRQ-092); new pins DRQ-093. Per the approved `_plans/backmatter-track-plan.md` resequencing noted at the r08 row above, ch.30 (live minikube/Istio) + ch.32 (the final project) remain, grouped at r10. | Java r09 (Part 9/10 content, regrouped per the back-matter track plan — see r08 row) |
| **r10** | **Part 9 (ch.30) + Part 10 (ch.32): Mesh/Observability/Tracing + the final project — done (ch.30 live-cluster verification pending the user's run)** | ch.30 (Mesh, Observability & Tracing) authored + `deploy/k8s/istio/` built (`PeerAuthentication` STRICT mesh-wide with a PERMISSIVE edge exception for the plaintext NodePort → strangler-proxy hop, a `Telemetry` resource, an istioctl-installed `IstioOperator`, DRQ-098) + `deploy/k8s/observability/` built (a single `grafana/otel-lgtm:0.36.0` all-in-one Deployment, unmeshed, with an `otelcol` ConfigMap carrying an istio-mesh Prometheus-SD scrape receiver, DRQ-099) + the minikube overlay activated with 8 per-Deployment `sidecar.istio.io/inject` label patches (postgres/kafka excluded, namespace unlabelled, DRQ-097) + `install-istio.sh`; headless render clean (activated overlay 31 resources Valid + 3 Istio CRs skipped-missing-schema, observability overlay 8/8 Valid). OTel wired on exactly 3 services — strangler-proxy, order-service, inventory-service (the synchronous gRPC hero trace, A/B gate resolved **A**, DRQ-096) — via `opentelemetry-distro` 0.66b1 + `opentelemetry-exporter-otlp-proto-grpc` 1.45.0, no-op by default (`OTEL_SDK_DISABLED=true` in `.env.example`, flipped in the k8s ConfigMap); additive, all existing suites green unchanged (29/20/24); noted caveat: `opentelemetry-instrumentation-sqlalchemy` 0.66b1 needs `sqlalchemy<2.1.0` but these services pin 2.1.4, so DB spans come from the `asyncpg` instrumentor, not the ORM one. **A/B-2 (ch.30 verification mode) resolved A** — the user runs the live minikube+Istio+LGTM sequence once and hands back trace/metrics/mTLS evidence, closing the track plan's last open A/B gate (DRQ-095); ch.30's footer is **`verified-live (user-run)` — evidence capture pending** until that run lands, everything else in this row is already built and committed. One new additive CI gate, `mesh-manifests.yml` (headless `kubeconform` on the istio+observability overlays, `mesh-manifests-ok` summary, no `paths:`, cluster-free, DRQ-101); `code-ci.yml`/`contract-gate`/`code-ci-ok`/`schema-registry.yml`/`deploy-manifests.yml`/`supply-chain.yml` untouched. ch.32 (the book's final project, not a capped summary chapter) authored + §C reconciliation (Mesh/Observability/Tracing (H) row filled, every "landed rNN" cell re-confirmed, scorecard figure == §C, DRQ-102). New pins: Istio/istioctl 1.31.2, `opentelemetry-distro`/`-instrumentation` 0.66b1, `opentelemetry-exporter-otlp-proto-grpc` 1.45.0 (DRQ-100); driver switched to docker+containerd only (podman minikube-driver opt-in removed); the old "capping-off chapter" label was swept to "final project" across `_plans/` + this table. DRQ-095 through DRQ-102 recorded; DRQ-103 (conditional outbox trace-propagation) not triggered since DRQ-096 resolved A. | Java r09 (Part 9/10 content, regrouped per the back-matter track plan — see r08 row) |
| **r11** | **Part 11 (ch.33): the OpenShift-on-CRC appendix — THE FINAL CHAPTER — done (headless; live CRC run pending)** | ch.33 (`_docs/33-appendix-openshift.md`) + the new `openshift/` tree: Helm chart `openshift/helm/mea` (the 8 services from a data-driven `services:` map, DRQ-105), Routes replacing NodePort on strangler-proxy + graphql-gateway — OSSM provisions no ingress gateway, the Route is the edge (DRQ-106); three SCC postures — restricted-v2 (the 8 app Deployments), nonroot-v2 (postgres/kafka under a dedicated `mea-infra` SA), anyuid + `runAsUser: 0`-only (`grafana/otel-lgtm`) (DRQ-107); podman build → internal-registry image delivery for all 8 services plus the frozen monolith image, with a `--mirror-infra` path for the egress-less CRC VM (DRQ-108); an opt-in platform tier — OSSM 3 via the Sail operator, `Istio` CR `spec.version: v1.30.5`, sidecar injection by the `istio.io/rev: default` pod-template label (not the minikube path's annotation), namespace-wide STRICT mTLS with a PERMISSIVE carve-out for the two Route-facing services, Kiali pointed at the redeployed otel-lgtm, RHBOTel (DRQ-109); and an in-cluster idempotent bootstrap Job seeding review-service's shared schema in place of the minikube path's host port-forward (DRQ-111). `deploy/k8s`, app code, Containerfiles, and the 8 service images are unchanged — the A.0 separation discipline keeps OpenShift/CRC/OSSM/Routes/SCC confined to `openshift/` + ch.33 alone, and the existing UBI10-1001 images already satisfy restricted-v2 with no rebuild. Headless-validated: `helm lint` clean; `helm template \| kubeconform -strict -ignore-missing-schemas` → 25 Valid, Routes/PeerAuthentication skipped on missing schema (not invalid), under both the default and the mesh-on/observability-on flag combinations. One new additive, cluster-free `openshift-chart.yml` gate (DRQ-110); every existing CI workflow untouched. New pins: CRC 2.64.0/OpenShift 4.22.14/k8s 1.35.6, OSSM3 v3.4.3/Istio v1.30.5, Kiali v2.27.5, RHBOTel v0.158.0-2, Helm v4.2.2 (a build-time correction of the plan's v4.3.1 survey), reusing `grafana/otel-lgtm` 0.36.0 and kubeconform v0.8.0. **ch.33 verification: `verified-if-automated-tests-pass; headless CRC run pending`** — the orchestrator's live CRC run (DRQ-104) sets the footer to `verified` only if `openshift/project-checks.sh` plus the mesh/mTLS/trace checks pass against that real run, else `unverified`; nothing is set ahead of the run. DRQ-104 through DRQ-111 recorded. This closes the book's last chapter — remaining scope is the front-matter chapters (ch.00–13), the three decks, and landing ch.30's + ch.33's live-cluster evidence. | Java sibling's own OpenShift/CRC appendix chapter, per the standing cross-project OpenShift/CRC Appendix Standard |

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
