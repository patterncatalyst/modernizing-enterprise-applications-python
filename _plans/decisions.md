---
title: "Decision Log — Modernizing Enterprise Applications (Python)"
description: "Append-only decision log (DRQ-NNN), ported in format from the Java sibling's decisions.md. Seeds the r01 fixed/accepted decisions for the walking skeleton."
status: "r01 — walking skeleton"
mirror_of: "~/Dev/modernizing-enterprise-applications/_plans/decisions.md"
---

# Decision Log (DRQ-NNN)

Append-only. One row per decision: id, decision, rationale, status.
`status` ∈ {fixed (set by the user/brief, not relitigated), accepted
(synthesis decision, open to user override), proposed (recommended default
awaiting user confirmation)}.

## Version matrix (r01 — surveyed 2026-10-15, pin exactly)

| Component | Pin | Where | Notes |
|---|---|---|---|
| Python | **3.14** | `pyproject.toml` (uv) | paired with the Django 5.2 patch below (DRQ-003) |
| Django | **5.2.18** (LTS) | `examples/00-monolith/pyproject.toml` | verify this patch declares Python 3.14 support; fallback Python 3.13 if CI disagrees |
| djangorestframework | **3.18.3** | monolith | serializers + camelCase contract (DRQ-002) |
| psycopg[binary] | **3.3.6** | monolith | Postgres driver |
| gunicorn | **26.2.0** | monolith | WSGI front door, `:8000` (DRQ-005) |
| pytest | **9.1.1** | monolith, dev deps | |
| pytest-django | **4.14.0** | monolith, dev deps | |
| ruff | **0.17.1** | monolith, dev deps | lint/format gate |
| uv | **0.13.1** | toolchain | env/deps manager |
| drf-spectacular | survey current at r01 execution | monolith | seeds the Newman collection's OpenAPI reference |
| Postgres (image) | `18.6-alpine` | `.env.example`, compose, CI | reuse Java sibling's DRQ-077 pin, re-verify via `skopeo` |
| Kafka (image) | `apache/kafka:4.3.1` (JVM) | `.env.example`, compose, CI | off the r01 critical path (monolith needs only Postgres) |
| grafana/otel-lgtm (image) | `0.36.0` | `.env.example`, compose | reuse Java sibling's DRQ-077 pin, re-verify |
| UBI Python base | `ubi10/python-314-minimal` (exact tag via `skopeo`) | `Dockerfile` | fallback `ubi9/python-314` if the 3.14 UBI10 tag isn't published yet |
| Newman | **6.2.2** | CI (Node 20/22 LTS) | |
| Jekyll | `~> 4.3` + plugins | site, Ruby 3.3 in `pages.yml` | ported from the Java sibling's site toolchain |

This matrix is reproduced verbatim from `_plans/r01-build-plan.md`'s
"Suggested version pins" section (the Phase-1 planner's survey); the
executor re-verifies image tags with `skopeo list-tags` before building.

## Decisions

| ID | Decision | Rationale | Status |
|---|---|---|---|
| DRQ-001 | **Accent color = "migration green" `--accent: #3d7a4e`; `brand_emoji` = 🏗️** — unchanged from the Java sibling. | User-fixed: reads as a matched set with the Java book rather than a distinct brand; no value in a second accent for the same narrative arc. | fixed |
| DRQ-002 | **JSON field naming = camelCase**, matching the Java sibling's contract, delivered via DRF serializer `source=` mappings and/or a shared camelCase renderer (not DRF's snake_case default). | User-fixed: lets the Newman collection port from the Java sibling with minimal edits instead of forking the collection to snake_case. | fixed |
| DRQ-003 | **Django 5.2 LTS on Python 3.14**; pin the 5.2 patch that declares 3.14 support (surveyed as 5.2.18); **fallback to Python 3.13** if CI shows incompatibility. | User-fixed. Django 5.x × Python 3.14 support timing is a known risk (§M R6 in `build-plan.md`); the fallback is named up front so a red CI run has a pre-agreed escape hatch, not an ad hoc one. | fixed |
| DRQ-004 | **Compose engine = docker-primary, podman-compatible** (the project's own choice, independent of the Java sibling's DRQ-077 "Docker Engine replaces Podman" — this project never had a Podman-first phase to supersede). | User-fixed. Matches the Java sibling's current engine (Docker) so dev-loop instructions transfer; "podman-compatible" is stated as a constraint (no Docker-only compose syntax) rather than a second maintained compose file. | fixed |
| DRQ-005 | **Monolith front-door port = `:8000`** (Django's conventional dev-server port; distinct from the Java sibling's `:8080`-family ports). | User-fixed. Python-idiomatic; the Newman `local.postman_environment.json`'s `baseUrl` matches. | fixed |
| DRQ-006 | **Shared single Postgres schema across all six Django apps (with cross-app FKs) is the r01 smell; per-service owned schema is the decomposition target**, realized incrementally as each extraction lands (mirrors the Java sibling's DRQ-002/§D smell #1 and §E's owned-data roadmap). | Accepted — the coupling *is* the smell the whole decomposition roadmap (§E) cures one seam at a time; building owned schemas now would remove the smell before the book teaches curing it. | accepted |
| DRQ-007 | **Saga reuse (orchestrated): the shipping extraction (ch.24, r06) reuses `~/Dev/cloud-native-design-patterns/examples/17-sagas/python/` (the DB-backed saga orchestrator) and its `_docs/17-appendix-d-sagas.md`**, adapted rather than re-authored. | Accepted — a working, already-documented Python DB-backed saga orchestrator exists in the catalog; re-authoring one from scratch would duplicate effort the reuse-map discourages (mirrors the Java sibling's DRQ-015 "reuse ≈ 60%" posture). **Not built in r01** — recorded here for the r06 relay to execute against. | accepted |
| DRQ-008 | **Saga reuse (choreographed): the payment extraction (ch.23, r05) uses aiokafka choreography** (`order.placed`→`payment.captured`/`payment.declined`), the Python analogue of the Java sibling's SmallRye Reactive Messaging choreography (DRQ-048 in the Java ledger). | Accepted — aiokafka is the idiomatic async Kafka client for FastAPI; no framework-level choreography engine is needed for a producer/consumer pair. **Not built in r01.** | accepted |
| DRQ-009 | **Two-phase Django→FastAPI migration policy, stated honestly as having no Spring-compatibility-extension equivalent.** Phase A = a behavior-preserving FastAPI lift, either (a) a thin FastAPI layer still calling the Django ORM, or (b) a direct SQLAlchemy re-map of the same tables — whichever the seam calls for; Phase B = fully idiomatic FastAPI + Pydantic + async SQLAlchemy, measured before/after. Each extraction chapter must say plainly which Phase-A bridge it used. | Accepted — the Java sibling's two-phase policy (DRQ-029 in the Java ledger) leans on Quarkiverse Spring-compatibility extensions that have no Django/FastAPI analogue; silently reusing the Java framing would overclaim a drop-in bridge that doesn't exist in the Python ecosystem. | accepted |
| DRQ-010 | **The Newman behavior-equivalence suite is the CI equivalence gate** for every future extraction (unchanged in spirit from the Java sibling's DRQ-014/031), captured against the monolith at r01 and re-run unchanged against each extracted service. | Accepted — makes "preserves behavior" checkable; the single acceptance gate this whole roadmap hangs off. | accepted |
| DRQ-011 | **The monolith is kept permanently in-repo at `examples/00-monolith/`**, mirroring the Java sibling's DRQ-024, as the living "before" and the equivalence suite's referent — even after every context is eventually extracted. | Accepted — the equivalence suite needs a running/frozen referent; cross-references stay valid across the book's life. | accepted |
| DRQ-012 | **12 parts (Part 0–11, including a numbered Appendices part) / 34 chapters (ch.00–33)**, retitling only where the Java title named a Java-specific technology (Quarkus/Camel/SmallRye). | Accepted — mirrors the Java sibling's 11 parts + an informal "A+" appendix grouping, but makes the Python site's Appendices a first-class numbered Part (`_parts/11-appendices.md`) so the 12-part/34-chapter count is exact and the SITE lane's stub generation has an unambiguous target. | accepted |
| DRQ-013 | **Extraction order = rising difficulty: review → notification → inventory → payment → shipping → order+gateway** — unchanged from the Java sibling's DRQ-013. | Accepted — each step forces exactly the next pattern; no reason to reorder for a stack substitution alone. | accepted |
| DRQ-014 | **Review service remains the walking-skeleton / first extraction** (not inventory) — unchanged from the Java sibling's DRQ-012. | Accepted — REST-only, no sync dependency; least surface to prove the full loop end-to-end. | accepted |
| DRQ-015 | **ADLC = dedicated Part (Part 2) AND a woven "ADLC in Action" per-chapter callout** — unchanged from the Java sibling's DRQ-006. | Accepted — same requirement (ADLC *replaces* the SDLC) needs the same explicit-instruction-plus-demonstration treatment regardless of target stack. | accepted |
| DRQ-016 | **This project's own `_plans/` ledger IS the worked ADLC example** — unchanged from the Java sibling's DRQ-007. | Accepted — zero-gold-plating proof; these are artifacts the project produces anyway. | accepted |
| DRQ-017 | **Narrative = chronological migration timeline**, patterns introduced at the moment the migration forces each — unchanged from the Java sibling's DRQ-008. | Accepted — preserves "why this pattern, why now" regardless of language. | accepted |
| DRQ-018 | **r01 = the walking skeleton itself** (monolith + site shell + Newman + CI, all green), not a planning-only round like the Java sibling's r01. Total iteration count stays at **10** (r01–r10) by adding a dedicated r10 for the OpenShift/CRC appendix + a cross-sibling reconciliation pass. | Accepted — this relay was explicitly scoped to build, not merely plan (per `_plans/r01-build-plan.md`); the Java sibling's r01-planning/r02-skeleton split doesn't apply here because approval to build r01 was already given. | accepted |
| DRQ-019 | **Stack-substitution table is fixed for the whole project:** Spring Boot→Django 5.2 LTS+DRF; Quarkus+Camel→FastAPI; Maven/JDK→uv/Python 3.14; JUnit/Testcontainers→pytest/pytest-django; Camel strangler proxy→a thin ASGI reverse-proxy façade; SmallRye Reactive Messaging→aiokafka; quarkus-grpc→grpcio; Camel Saga EIP (orchestrated)→the reused CNDP Python DB-backed saga orchestrator (DRQ-007); SmallRye GraphQL→Strawberry; Apicurio stays unchanged (language-agnostic). | Accepted — stated once so every later chapter/extraction applies the same mapping consistently instead of re-deciding per chapter. | accepted |
| DRQ-020 | **No Camel MCP / Quarkus Agent MCP equivalent exists for this project's stack.** The ADLC's Map and Generate phases substitute manual reconnaissance plus the `lgtm-python` skill's scaffold conventions; this gap is stated explicitly in ch.06 rather than implied away. | Accepted — honesty about tooling asymmetry between the two sibling books; a reader following along in Python should not expect a live MCP-driven migration tool that doesn't exist. | accepted |
| DRQ-021 | **Site chrome (`_config.yml`, layouts, `assets/css/site.css`, `codetabs.js`) is ported near-verbatim from the Java sibling and re-skinned only for `github_repo`/nav labels** — the accent/emoji are unchanged (DRQ-001), so "re-skin" here means repo metadata and copy, not color. | Accepted — the site shell is language-agnostic Jekyll; re-authoring it from scratch would be pure busywork against the project's reuse posture. | accepted |
| DRQ-022 | **Newman collection shape (Smoke + 4 scenarios, `{{baseUrl}}` templating, environment-file pattern) is adapted from the Java sibling's `tooling/newman/`**, with payload field names preserved as camelCase (DRQ-002) so the collection ports with edits limited to endpoint paths/ports, not payload shape. | Accepted — the behavior-equivalence suite's entire value is in being comparable across the two books' tooling conventions. | accepted |
| DRQ-023 | **The r01 monolith is captured at its pristine "before" state** — all six Django apps live, all six smells live, nothing extracted — explicitly **not** a mirror of the Java sibling's frozen/decommissioned `main` end-state (where every context has already been extracted and the monolith survives only as a frozen referent). | Accepted — building the Python monolith from the Java repo's *current* state would scaffold six already-decommissioned apps instead of a believable, smell-bearing "before"; the Java repo's *original* (pre-extraction) monolith design is the correct mirror target, not its present `main`. | accepted |
| DRQ-024 | **Scenario 4 (Shipping-Failure) is meaningful at r01**: the synchronous checkout wraps everything in one `transaction.atomic()`, so a `SHIP-FAIL` sentinel rolls the whole checkout back (stock net-zero) — this is possible *because* the transaction boundary hasn't been split yet, setting up the ACID→ACD narrative (ch.22) from day one. | Accepted — gives the r01 monolith a genuine failure-mode teaching hook instead of deferring all failure semantics to later extractions. | accepted |

## Open questions (none outstanding at r01 close)

All five questions the Phase-1 planner flagged in `_plans/r01-build-plan.md`
("Open decisions for the user") were resolved by the user before this relay
began and are recorded above as fixed DRQ-001 through DRQ-005. No open
questions remain blocking r01.
