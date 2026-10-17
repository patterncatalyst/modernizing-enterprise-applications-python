# Front-Matter Build Plan — ch.00–13 (Parts 0–4, the on-ramp)

**Planner:** Opus (lgtm-relay Phase 1) · **Date:** 2026-10-17 · **Repo:** `modernizing-enterprise-applications-python` (public, patterncatalyst)
**Status:** awaiting user gate (DRQ-112 figures, DRQ-113 ch.08–10 footer).

**Mandate:** author the 14 remaining stub chapters `_docs/00`–`_docs/13` (Parts 0–4). The back half (`_docs/14`–`33`) is complete + merged. Re-author Python-native from the Java sibling's structure; never copy.

## Approach
- **Re-author, don't translate.** Read each Java sibling chapter `~/Dev/modernizing-enterprise-applications/_docs/0N` for scope/arc, then write fresh Python-native prose. The stacks diverge: Django 5.2 LTS + DRF (not Spring Boot); uv + Python 3.14 (not SDKMAN/JDK/Maven); FastAPI (not Quarkus); ASGI reverse-proxy strangler (not Camel); pytest/pytest-django + Newman; aiokafka/grpcio/Strawberry; frozen `@dataclass` `from_env()` config (NOT pydantic-settings, DRQ-083); the ADLC runs on the `lgtm-*` skills + `lgtm-relay` tiering (no Quarkus-Agent/Camel-MCP equivalent).
- **Front matter sets up what the back half delivers** — every forward ref matches as-built ch.14–33 + the ledger.
- **Ground ch.08–10 in real code:** `examples/00-monolith` (six Django apps order/inventory/payment/shipping/notification/review + `common` + `config`), `SMELLS.md` (7 tagged smells), `tests/` + `tooling/newman/`. Describe the pre-extraction "before" (all six contexts live); note the monolith is now frozen/break-glass (pristine state on branch `reference/monolith-before` + tag `v0-monolith`).
- **Voice:** `lgtm-professional-voice`, strict, 0 ban-tier; no confessional register; **no "capstone" (use "final project")**; FastAPI/Python-native (name Java/Quarkus/Camel/Maven/Spring only when deliberately pointing at the Java sibling).
- **Footer:** the compact badge. Conceptual chapters → `status--unverified` "conceptual chapter"; ch.08–10 → `status--verified` citing `examples/00-monolith` pytest/Newman (DRQ-113). ADLC-in-Action callout (`> **ADLC in Action** — …`) where it fits (esp. 05–07, 12).

### Rejected (one line each)
- Translating Java prose/figures 1:1 (residue: SDKMAN/mvn/@Transactional/native-image would be factually wrong).
- The Java ch.07 worked loop verbatim (its bugs are JVM/Spring-specific) → a real Python-shaped loop (DRQ-114).
- Full 30-figure parity by default → curated ~10 anchors (DRQ-112).
- `status--verified` on conceptual chapters (only 08–10 run code).
- Blanket ≥2000 padding → honest per-chapter targets (DRQ-116).

## Per-chapter table

| File | Part | Title | Scope | Java src | Figure (Option A) | Words | Footer |
|---|---|---|---|---|---|---|---|
| `00-introduction.md` | 0 | Introduction & How to Use This Book | Thesis (modernize *with* an agentic ADLC); shipping through-line; Django→6 FastAPI svcs before/after; reading paths; conventions; reference-book map. | 00 | monolith-to-microservices-outcome | 2,200 | unverified — conceptual |
| `01-prerequisites.md` | 0 | Prerequisites & the Toolchain | uv, Python 3.14, Django 5.2 + DRF, FastAPI; Docker + compose observability stack; minikube reserved for Parts 9–10; verify-your-setup gate. | 01 | toolchain-and-repo-layout | 2,600 | unverified — conceptual (setup commands reproducible) |
| `02-project-ledger.md` | 0 | The Project Ledger | The 3 ADLC artifacts as migration memory: decisions.md (DRQ convention), build-plan.md, reconciliation.md; the two human gates. | 02 | ledger-to-adlc-phases | 2,200 | unverified — conceptual |
| `03-modernization-as-engineering.md` | 1 | Modernization as Engineering, Not Fashion | Why modernize (delivery+operability metrics); ten microservice traits; "microservices aren't the goal"; when wrong; why big-bang fails; coupling compounds. | 03 | microservice-traits | 2,800 | unverified — conceptual |
| `04-strategies-and-assessment.md` | 1 | Strategies & Assessment | Lift&Shift / Modernize&Extend / Rip&Rewrite; value×change 2×2; ease-of-migration rubric; commit to incremental strangler; review-first ordering. | 04 | modernization-value-vs-change-2x2 | 3,000 | unverified — conceptual |
| `05-from-sdlc-to-adlc.md` | 2 | From SDLC to ADLC | Why SDLC breaks under agent-assisted work; ADLC phases (Frame→Map→Plan→Generate→Verify→Operate→Reconcile); agent/human split; gates. | 05 | sdlc-vs-adlc | 2,800 | unverified — conceptual |
| `06-agents-skills-mcp.md` | 2 | Agents, Skills & MCP Tools in the Loop | lgtm-relay tiering (Opus plan→Sonnet exec→Opus validate); MCP surface; skill map; no Quarkus-Agent/Camel-MCP + substitutes (DRQ-115). | 06 | plan-execute-validate-relay | 2,600 | unverified — conceptual |
| `07-adlc-safety-net.md` | 2 | The ADLC Safety Net (a worked loop) | Tests/contracts/reconciliation as guardrails; a full Frame→Reconcile loop on a trivial change; a real Python-shaped defect at a gate (DRQ-114). | 07 | adlc-safety-net-layers | 3,000 | unverified — conceptual (cited commands reproducible) |
| `08-designing-the-monolith.md` | 3 | Designing the Monolith | Six bounded contexts as one Django deployable: domain, 6 apps + common, shared Postgres schema, DRF edge, seed; seams visible. First running example. | 08 | monolith-architecture | 3,000 | **verified** — 00-monolith runs; pytest+Newman green (frozen/break-glass note) |
| `09-deliberate-smells.md` | 3 | The Deliberate Smells | 7 planted smells (god checkout, one ACID txn across 6 contexts, shared schema, cross-context FKs, sync notify, dual-write, review/auth coupling), each `# SMELL[ch.NN]:`-tagged. | 09 | smell-map | 3,000 | **verified** — smells grep-locatable; failure-injections exercised |
| `10-testing-the-monolith.md` | 3 | Testing the Monolith (the Equivalence Suite) | pytest/pytest-django tiers; the Newman contract collection that becomes the behavior-equivalence suite guarding every extraction; whitebox pyramid vs blackbox equivalence. | 10 | test-tiers-vs-equivalence | 2,800 | **verified** — tests/ + GOLDEN-BASELINE.md run |
| `11-ddd-and-hexagonal.md` | 4 | Strategic & Tactical DDD + Hexagonal | Subdomains, bounded contexts, context mapping; aggregates + domain events; ORM out of the domain core; why Review leaves first. | 11 | context-map | 2,800 | unverified — conceptual |
| `12-event-storming.md` | 4 | Event Storming the Monolith | Seams from behavior not schema; session grammar; storming checkout; the decomposition backlog, as an ADLC reconnaissance step. | 12 | event-storm-checkout | 2,600 | unverified — conceptual |
| `13-coupling-and-modular-monolith.md` | 4 | Coupling, the Modular Monolith & When *Not* to Split | Khononov's 3 coupling dimensions; Constantine taxonomy; afferent/efferent ranking; modular monolith + decomposed-DB as legit destinations; distributed-monolith trap; Part-4 consolidated extraction plan. | 13 | coupling-ladder | 3,000 | unverified — conceptual |

**Total ≈ 38,200 words across 14 files.**

### Figure policy
No existing `assets/diagrams/*` fits (all 46 are ch.14+ back-half assets). **Option A (recommended): 10 new Python-native anchor figures** (table), one per load-bearing chapter, authored via `lgtm-diagram-generator` (paired .svg/.excalidraw/.py, light-box style). **Option B:** full ~30-figure Java parity (3× effort, over-illustrates the on-ramp) — not recommended. Orchestrator owns `assets/diagrams/README.md` (register new figures).

## Build waves
14 disjoint files → parallel-safe. **Wave 1: 4 Sonnet executors** (one per Part): A = Part 0 (00/01/02); B = Parts 1+2 (03/04/05/06/07); C = Part 3 (08/09/10, reads 00-monolith code — the verified chapters); D = Part 4 (11/12/13). Figure authoring (10 Option-A figures) runs in parallel; orchestrator registers them in the catalogue. **Wave 2: Opus validation** — voice 0 ban-tier/no-capstone/FastAPI-native, compact footers, jekyll exit 0, full nav 00→…→14 intact, figures resolve, forward-consistency vs ch.14–33 + ledger. Fix-in-place + re-scan.

## Acceptance criteria
- All `_docs/00`–`13` authored to target, no stubs left; compact footer each (08–10 verified citing 00-monolith, rest unverified/conceptual).
- Voice 0 ban-tier; no "capstone"; FastAPI/Python-native (Java terms only for deliberate sibling contrast).
- `bundle exec jekyll build` exit 0; nav 00→…→13→14 contiguous; parts match `_parts/00`–`04`.
- Every figure include resolves + registered in `assets/diagrams/README.md`.
- Forward refs (extraction order, saga, CQRS, chassis, registry, mesh, OpenShift) match as-built ch.14–33 + decisions.md/reconciliation.md.
- ch.08–10 match `examples/00-monolith` (apps, 7 smells, tests/newman) — no invented behavior.

## Risks + detection
- R1 Java residue → voice scan + `grep -riE 'sdkman|jdk|maven|spring|quarkus|camel|pom\.xml|@Transactional|native.image|mvn '` over `_docs/0[0-9],1[0-3]`; allow only deliberate sibling mentions.
- R2 Front/back inconsistency (e.g. pydantic-settings, 2PC, shared chassis) → cross-check every forward claim vs ch.14–33 + DRQ-082/083.
- R3 Over-long on-ramp → honest per-chapter targets (DRQ-116).
- R4 Figure drift (wrong app names/order) → author against 00-monolith + as-built topology; validation resolves each `file=`.
- R5 "before" vs frozen reality → describe pre-extraction state; cite reference/monolith-before + v0-monolith; footer frozen note.
- R6 ch.07 loop invention → real Python ADLC loop vs 00-monolith (DRQ-114).

## DRQ allocations (next free = DRQ-112)
- **DRQ-112 — Figure strategy (A/B, user gate):** A = ~10 new anchor figures (rec); B = ~30-figure parity.
- **DRQ-113 — ch.08–10 footer:** verified citing runnable 00-monolith (rec) vs unverified conceptual.
- **DRQ-114 — ch.07 worked loop:** a real Python-shaped ADLC loop vs the Java native-image/Spring bug narration.
- **DRQ-115 — ch.06 MCP substitution:** record no Quarkus-Agent/Camel-MCP equiv; substitutes = lgtm-python + lgtm-relay tiering + generic MCP surface.
- **DRQ-116 — on-ramp word band:** allow conceptual chapters below the ~2000 floor where warranted (00/02 ≈2,200), reference/seams at full depth.
