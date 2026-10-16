---
title: "Reconciliation Log — Modernizing Enterprise Applications (Python)"
description: "Append-only artifact→source reconciliation log (build-plan.md §M, R4). Tracks every reused/adapted artifact against its source (the Java sibling, cloud-native-design-patterns, datamesh-reference-arch-quarkus) with a verdict, so reuse drift is always named, never silent."
status: "live — appended at each iteration's/extraction's reconcile step"
mirror_of: "~/Dev/modernizing-enterprise-applications/_plans/reconciliation.md"
---

# Reconciliation Log

Append-only. One section per iteration's or extraction's reconcile pass. For
each reused or adapted artifact: the source, what was reused, what diverges
(project-specific), and a verdict. `R4` (`build-plan.md` §M) requires **zero
unexplained drift** — divergence is fine as long as it is named here and
traceable to an accepted `DRQ-NNN`.

## How to use this file (per-extraction-reconcile instructions)

At the Verify/Reconcile phase (§F.1, phase 7) of each extraction or major
chapter, append a new `##` section here, named `ch.NN — <Service> (rNN,
extraction K of 6)`, following this shape:

1. **Source line(s).** For every artifact reused or adapted from another
   project (the Java sibling, `cloud-native-design-patterns`,
   `datamesh-reference-arch-quarkus`, or an earlier chapter in this same
   project), name the exact path reused.
2. **Reused as-is (shape).** What was carried over unchanged in intent, even
   if the syntax changed because the language changed.
3. **Named divergence.** Every place the Python artifact differs from its
   source, each traceable to an accepted `DRQ-NNN` — never an unexplained
   gap.
4. **Verdict.** One of: `CLEAN adaptation` (reused shape, all divergence
   named), `DRIFT` (an unnamed or unaccepted divergence was found — must be
   resolved before the extraction can be marked done), or `no drift to
   reconcile` (nothing external was reused for this chapter).

A **first-creation note** (like the one below) is only needed once, the first
time this file is created; subsequent sections follow the shape above
directly.

---

## First creation note (r01, LEDGERS lane)

This file is created at r01 alongside `build-plan.md` and `decisions.md`, all
three as a single ledger seed (mirroring the Java sibling's own ledger
creation, though the Java sibling's `reconciliation.md` wasn't actually
created until its r06/ch.23 reconcile pass — this project creates all three
`_plans/` artifacts together at r01 instead, since r01 here is a build
iteration, not a planning-only round). No extraction has happened yet (§E in
`build-plan.md` — all six rows are "not started"); this file has no
per-extraction sections until r02+. The section below records what the r01
**walking skeleton itself** reused.

## r01 — Walking skeleton (LEDGERS + SITE + MONOLITH + NEWMAN + INFRA + CI lanes)

### Site chrome

**Source:** `~/Dev/modernizing-enterprise-applications/_config.yml`,
`_layouts/{default,tutorial,part_index,plan}.html`, `_includes/*`,
`assets/css/site.css`, `assets/js/codetabs.js`, `index.html`.

**Reused as-is (shape):** the full Jekyll skeleton — collections
(`docs`/`plans`/`example_pages`/`parts`), the two-level Part→Chapter nav, the
card-grid homepage, the four layouts, the diagram embed convention, the
tabbed-codesample mechanism (`codetabs.html`/`codetabs.js`).

**Named divergence:** `github_repo` → `modernizing-enterprise-applications-
python`; code-sample tabs relabeled Django ⇄ FastAPI instead of Spring Boot ⇄
Quarkus (DRQ-033 in the Java ledger's spirit, re-homed here); accent/emoji
**unchanged** (DRQ-001 — deliberately *not* a divergence; the two books share
a visual identity by design).

**Verdict:** CLEAN adaptation — ported near-verbatim per DRQ-021, divergence
limited to repo metadata and code-sample labels.

### Newman collection shape

**Source:** `~/Dev/modernizing-enterprise-applications/tooling/newman/`
(`mea.postman_collection.json`, `local.postman_environment.json`,
`GOLDEN-BASELINE.md`, `README.md`).

**Reused as-is (shape):** the Smoke + 4-scenario structure, the
`{{baseUrl}}`-templated request pattern, the environment-file-per-target
convention, the GOLDEN-BASELINE documentation format.

**Named divergence:** `baseUrl` → `http://localhost:8000` (DRQ-005, Django's
port vs the Java sibling's); payload field names preserved as camelCase
(DRQ-002) so request bodies are byte-for-byte comparable; scenario endpoints
point at DRF routes, not Spring MVC routes.

**Verdict:** CLEAN adaptation per DRQ-022 — shape reused, divergence limited
to port and route paths, payload contract intentionally unchanged.

### Ledger format

**Source:** `~/Dev/modernizing-enterprise-applications/_plans/build-plan.md`,
`decisions.md`, `reconciliation.md` (sections A–M, the DRQ table format, the
version-matrix convention, this file's own append-only template).

**Reused as-is (shape):** the DRQ-NNN decision-log convention and its status
vocabulary (fixed/accepted/proposed); the build-plan's lettered-section
structure (§A approach → §M risks); the per-extraction reconcile-section
template this file now carries forward.

**Named divergence:** section count trimmed to the sections `_plans/r01-
build-plan.md` actually asked for (§A, §B, §C, §D, §E, §F, §J, §K, §L, §M —
no §G/H/I testing/CI/deck sections at r01, since those would describe work
not yet scoped for this iteration); the §B.2 chapter list retitled per the
stack-substitution table (DRQ-019) rather than copied verbatim; the §J
iteration table is renumbered from the Java sibling's r01-planning/r02-
skeleton split to this project's r01-is-the-skeleton cadence (DRQ-018).

**Verdict:** CLEAN adaptation — format ported, content independently
authored for the Python stack; no unexplained drift (the section-count
trim and renumbering are both named DRQs, not silent omissions).

### Saga reuse (recorded now, not built until r06)

**Source:** `~/Dev/cloud-native-design-patterns/examples/17-sagas/python/`
(the `saga-orchestrator` DB-backed implementation) and its
`_docs/17-appendix-d-sagas.md`.

**Status at r01:** reuse decision recorded (DRQ-007) but **no code copied or
adapted yet** — the shipping extraction (ch.24) that will reuse this source
doesn't land until r06, per `build-plan.md` §E/§J. This entry exists so the
reuse intent is on record before the fact, not retrofitted at r06 the way the
Java sibling had to backfill its own first three extractions' reconciliation
retroactively (see the Java sibling's `reconciliation.md` "First creation
note").

**Verdict:** not yet applicable — tracked here as a forward reference only.

### Monolith design intent (in-project, not external reuse)

**Source:** this project's own `_plans/r01-build-plan.md` and
`build-plan.md` §D — not an external artifact, but worth recording because
the Java sibling's *current* `main` branch (fully decomposed, monolith
decommissioned) is explicitly **not** the mirror target (DRQ-023). The mirror
target is the Java monolith's *original design intent* (six live contexts,
six live smells, shared schema) as described in the Java sibling's own
`build-plan.md` §D, not its present committed state.

**Verdict:** no drift — the divergence from the Java repo's current `main`
is deliberate and named (DRQ-023), not an oversight.

---

## ch.14/15 — Strangler proxy + Review (r02, extraction 1 of 6)

### Strangler proxy

**Source:** no external artifact — a project-first implementation of the
façade role named in DRQ-019 (the Java sibling realizes the equivalent role
with a Camel strangler-fig route, which has no Python analogue; see DRQ-020's
tooling-asymmetry note). `_plans/r02-build-plan.md`'s "Approach" section is
the design source.

**Reused as-is (shape):** the strangler-fig cutover pattern itself —
content-based routing on a path prefix, a feature flag as the cutover
switch, monolith-as-fallback, reversibility as a design property (mirrors the
Java sibling's per-extraction flag-pair convention even though the mechanism
differs).

**Named divergence:** mechanism is a **Starlette + `httpx.AsyncClient`**
streaming ASGI reverse-proxy on `:8888`, not a Camel route (DRQ-026) — the
stack-substitution table (DRQ-019) names this mapping explicitly, so this is
not an unnamed gap.

**Reconciliation finding — the chunked-body proxy bug.** The in-process
routing tests (`tests/test_routing.py`, via `httpx.ASGITransport`) passed
clean, but a real defect hid underneath: the proxy forwarded the inbound
request body as an unread async stream, so `httpx` sent it upstream with
`Transfer-Encoding: chunked` and no `Content-Length`. The monolith is
Django/WSGI, which reads `CONTENT_LENGTH` and treats a missing one as an
empty body — so every `POST` routed through the proxy arrived at the
monolith **empty**. This was invisible to the in-process mock-transport
tests and surfaced only when the Newman suite ran against the real WSGI
server over a real socket during the live cutover. **Fixed** by buffering
the request body (`content = await request.body()`) so bounded requests
carry a correct `Content-Length`; a regression test now asserts the outbound
upstream request is non-chunked with the body intact (recorded as DRQ-026).
**Lesson:** equivalence must be proven against the real backend over a real
socket, not an in-process mock transport — the same principle the Java
sibling's own reconciliation practice leans on (R4, zero unexplained drift),
now reinforced by a concrete Python-side example.

**Verdict:** bug-found-and-fixed — caught by the cutover evidence trail
(`examples/01-strangler-proxy/CUTOVER.md`) before it reached the chapter,
not after.

### Review extraction (Phase A documented / Phase B shipped)

**Source:** `~/Dev/modernizing-enterprise-applications/examples/02-review-
service/` (Java/Quarkus sibling, same chapter role) for the two-phase
migration *policy* shape (DRQ-009); no code ported — this is an independent
implementation per the Python stack-substitution table (DRQ-019).

**Reused as-is (shape):** the two-phase bridge narrative (Phase A =
behavior-preserving lift; Phase B = idiomatic refactor, measured
before/after); the endpoint contract (camelCase JSON, no trailing slash,
uniform `{error,message,timestamp}` error body, `201` + `Location` on
create) carried over from the r01 monolith's own DRF contract, not from the
Java service directly.

**Named divergence — auth contract (the Java-sibling divergence and its
resolution).** The Java contract asserts `401` unauthenticated / `201`
authenticated on the review write endpoint (smell #6 in that project). The
Python r01 monolith, as actually built, wired **no auth** on that endpoint
(DRQ-025). `_plans/r02-build-plan.md` surfaced this gap explicitly as a
user decision point (Option A: match the unauthenticated r01 contract and
record the divergence vs. Java; Option B: add Basic auth to both monolith
and service, realizing the smell and matching Java). **The user chose
Option B** (2026-10-15): `POST /api/reviews` now requires HTTP Basic auth,
identically enforced on the monolith and the review service; reads stay
open. The monolith seeds `reviewer`/`review-pw-r02`; the service verifies
the same shared `auth_user` row via `passlib`'s `django_pbkdf2_sha256`
scheme (confirmed locally against a real Django `make_password()` hash:
verify-true on the right password, verify-false on the wrong one, and a
fixed dummy-hash comparison on username-miss to resist timing-based
enumeration). Recorded as DRQ-029, which supersedes the review-write portion
of DRQ-025. This is exactly the kind of divergence R4 requires to be named
rather than silent — it is now named, resolved by explicit user decision,
and traceable to an accepted DRQ.

**Named divergence — Phase A not shipped as code.** Unlike the Java
sibling, where Phase A was a real, previously-committed, measurable build
(`5479d49`), this project's Phase A (thin FastAPI over the monolith's
Django ORM via a `uv` path dependency + `django.setup()` in the lifespan) is
**documented in `MIGRATION.md` but never committed**. Two concrete problems
found while sketching it — a synchronous Django ORM bridged into FastAPI's
async loop via `sync_to_async` on every query, and a backwards build-time
dependency (the extraction gaining a hard dependency on the entire
monolith just to reach one model) — made shipping it purely to measure and
delete in the same iteration not worth the implementation/CI surface.
Before/after numbers are a faithful proxy (real `django.setup()` +
`import fastapi, uvicorn` cost on this machine), not a running server;
`MIGRATION.md` states this at every measurement, not glossed over.

**Honest finding — "structural not perf-fireworks."** Phase A→Phase B
import/startup time and import-RSS came back **statistically
indistinguishable** (within run-to-run noise): FastAPI + Pydantic v2's own
import graph dominates both columns, so swapping Django's ORM for
SQLAlchemy barely moves process-startup numbers — unlike the Java sibling's
dramatic native-image win, which has no Python equivalent. This is reported
as measured, not adjusted to tell a cleaner story. The real Phase A→Phase B
payoff ch.15 is built to teach is structural (no `sync_to_async` bridging,
no hard monolith build dependency), not a startup-time number.

**§E schema-column drift correction.** `build-plan.md` §E row 1 originally
read "Own schema from day one; no shared-txn entanglement" for the review
row — this was never actually true even at r01-planning time; the approved
`_plans/r02-build-plan.md` always intended review to stay on the **shared**
schema in r02, with DB ownership deferred to ch.18/19 (matching the Java
sibling's own precedent). This relay corrects the §E cell to "Shared schema
initially; DB decomposition deferred to ch.18/19" (DRQ-028) rather than
carrying the stale claim forward silently.

**Equivalence gate — green through the proxy in both flag states.** The
unedited Newman collection (`tooling/newman/mea.postman_collection.json`)
run through the proxy (`:8888`) against a live stack (Postgres, monolith
`:8000`, review-service `:8001`):

| # | Flag | Review served by | Result |
|---|---|---|---|
| 1 | `false` (baseline) | monolith | 19 req / 38 scripts / 58 assertions, 0 failed |
| 2 | `true` (cutover) | review-service | 19/38/58, 0 failed — byte-identical in shape to run 1 |
| 3 | `false` (reverted) | monolith | 19/38/58, 0 failed — reversibility confirmed |
| 4a | `true`, review-service **killed** | *(502, nothing)* | **RED, exit 1** (6/6 assertions failed) — the required negative check |
| 4b | `true`, review-service restarted | review-service | 16/16 green |

The RED-then-green negative check (4a→4b) confirms the equivalence gate
does not quietly pass when the extracted service is down — the gate fails
loudly, exactly as `_plans/r02-build-plan.md`'s risk section required. Full
detail in `examples/01-strangler-proxy/CUTOVER.md` and
`tooling/newman/GOLDEN-BASELINE.md`. The new `.github/workflows/code-ci.yml`
`review-equivalence-gate` runs the flag-ON case (3 services + proxy) in CI
and is wired into `code-ci-ok`; the pre-existing monolith gate remains
green.

**Verdict:** CLEAN adaptation (two-phase policy shape, endpoint contract) +
corrected drift (§E schema column) + bug-found-and-fixed (chunked-body
proxy bug) + a named, user-resolved divergence from the Java sibling (auth
contract, Option B). No unexplained drift remains for ch.14/15.

---

## ch.16-17 — Notification (r03, extraction 2 of 6)

### Transactional outbox + the dual-write cure

**Source:** no external artifact — a project-first implementation of the
Transactional Outbox pattern (§C) realized against `examples/00-monolith/`'s
own `place_order()` checkout flow. `_plans/r03-build-plan.md`'s
MONOLITH-OUTBOX lane is the design source.

**Reused as-is (shape):** the pattern's canonical shape — a transactional
`OutboxEvent` table (partial index on `published_at IS NULL`), written in the
**same database transaction** as the business write, with a separate relay
process polling and publishing asynchronously. This is the standard cure for
both SMELLS.md #5 (synchronous notification dispatch inside checkout) and
#6 (the dual-write of a `Notification` row + an external send, with no
atomicity between them).

**What shipped:** `place_order()` now writes a single `order.placed`
`OutboxEvent` row in-transaction instead of calling the notification
dispatcher; `manage.py outbox_relay` (an aiokafka-producer polling management
command, DRQ-032) picks up unpublished rows, publishes to Kafka keyed by
`orderId`, and stamps `published_at` on broker ack. **Verified atomic:** a
`CARD-DECLINE` or `SHIP-FAIL` checkout — which rolls back the whole
`transaction.atomic()` block — leaves **zero** new outbox rows; this was
exercised as a test, not just asserted. Checkout remains synchronous `201
CONFIRMED` with no Kafka on the request path (async `202` is out of scope
until r05/payment).

**Verdict:** CLEAN — the dual-write smell is cured atomically, proven by a
rollback test, not merely argued.

### The monolith becomes a consumer of its own event (DRQ-038)

**Source:** no external artifact — this is the pivotal design decision the
`_plans/r03-build-plan.md` gate posed directly to the user: once
`place_order()` stops writing a `Notification` row synchronously, something
has to repopulate the monolith's own `/api/notifications` read-model for the
flag-OFF state.

**Decision and why:** the user chose the **recommended** option over the
simpler fallback. The monolith gained a new `order_placed_consumer`
management command (consumer group `monolith-notification`, idempotent via
`record_order_placed`) that consumes the same `order.placed` topic the
notification-service consumes (in its own group, `notification-service`) and
writes the `Notification` row from the event rather than from the original
in-process call. The **rejected fallback** — keep an in-transaction
`Notification` write in checkout and drop only the external dispatch — was
recorded (DRQ-038) specifically because it would have kept the flag-OFF path
Kafka-free, which sounds safer but actually (a) leaves SMELLS.md #6 only
half-cured (the write is no longer dual, but it's also no longer the
event-driven thing ch.17 is teaching) and (b) would never exercise the
Newman async bounded-wait suite in the flag-OFF state, undermining the
chapter's own teaching point.

**Why this is the right pedagogy, not just the right code:** it makes the
monolith and the notification-service **true like-for-like replacements** —
both are now consumers of the identical `order.placed` event, differing only
in schema (shared vs. owned) and process (Django management command vs.
FastAPI lifespan task). The strangler flag now genuinely chooses *who serves
the read*, not *whether the system is event-driven at all*. This is recorded
in `build-plan.md` §C as the Decorating Collaborator pattern landing at
ch.16, and is the concrete proof-point for ch.17's "going event-driven"
narrative.

**Verdict:** CLEAN — a real architectural choice, made by the user at the
plan gate (not defaulted by the executor), traceable to DRQ-038 (status:
fixed), with a concrete narrative payoff in both ch.16 and ch.17.

### Notification-service: first owned schema (DRQ-035, contrast with DRQ-028)

**Source:** `examples/02-review-service/` (this project's own r02 work, not
an external project) for the *shape* of a FastAPI service with its own
Alembic-free, shared-schema posture — notification deliberately **diverges**
from that posture rather than repeating it.

**Named divergence:** review (r02) stayed on the monolith's shared schema,
DB ownership deferred to ch.18/19 (DRQ-028). Notification (r03) owns a
dedicated Postgres `notification` SCHEMA in the same instance, created and
migrated via **Alembic** — this project's first service to own its schema
from day one. The divergence is deliberate and named (DRQ-035): notification
is the right place to introduce owned-schema because its data (delivery
records keyed by `order_id`) has no legitimate reason to live in the
monolith's tables, unlike review's r02-scoped deferral.

**Reconciliation finding #1 — Alembic async `CREATE SCHEMA` needed an
explicit commit.** Alembic's async migration runner did not persist the
`CREATE SCHEMA IF NOT EXISTS notification` DDL until an explicit
`await connection.commit()` was added inside the migration's `run_sync`
path — without it, the schema silently failed to appear outside the
migration's own transaction scope in some run orders, which is the kind of
bug that only shows up when a second process (the service itself, started
after `alembic upgrade head`) tries to use the schema and finds it missing.
**Fixed** by adding the explicit commit. Found during the Verify phase, not
left latent.

**Reconciliation finding #2 — Testcontainers `KafkaContainer` needed
`.with_kraft()`.** The notification-service's own idempotency pytest, using
`testcontainers`'s `KafkaContainer`, failed to start a usable broker until
`.with_kraft()` was added — the default container mode did not match the
project's KRaft-only Kafka posture (no ZooKeeper anywhere in this project,
matching the `apache/kafka:4.3.1` CI service container). **Fixed** by
pinning the test fixture to KRaft mode, keeping the test environment
consistent with both CI and the dev-loop compose stack.

**Verdict:** CLEAN adaptation (owned-schema posture, named divergence from
DRQ-028) + two bugs found during Verify and fixed before merge, not
discovered later: the Alembic commit gap and the Testcontainers KRaft gap.
Both are recorded here per R4's "zero unexplained drift" bar — a bug found
and fixed during the same reconcile pass is not drift, but it is reported
honestly as a real defect rather than smoothed over.

### `order.placed` contract (DRQ-036)

**Source:** this project's own r02 camelCase JSON-contract convention
(DRQ-002), extended to an event payload rather than a REST response body.

**Reused as-is (shape):** camelCase field naming, applied consistently to an
event for the first time: `{orderId, customerId, customerEmail, totalCents,
confirmationMessage, placedAt}`, topic `order.placed`, key `orderId`.

**Named divergence:** hand-maintained (no schema registry) — Apicurio
registry governance is deferred to ch.28, named explicitly rather than
implied as already in place (DRQ-036).

**Verdict:** CLEAN — contract frozen before the three lanes (monolith-outbox,
notification-service, proxy-flag) built against it in parallel, per the
`_plans/r03-build-plan.md` dependency chain (STEP 0 froze the contract
first).

### Async equivalence gate — green through both flag states, plus the negative check

**Source:** the r02 synchronous equivalence-gate precedent
(`review-equivalence-gate`), extended to an async, eventually-consistent
contract for the first time — the shape is reused, the mechanism is new
(DRQ-039).

**What shipped:** an env-guarded "Notification Context Contract" Newman
folder — `POST /api/orders` → `201 CONFIRMED` capturing `customerId`/
`orderId`, then a busy-wait-on-retry poll of
`GET /api/notifications?customerId=` (self-`setNextRequest`, ≤20 attempts ×
750ms = a 15s budget) with a **strict terminal assertion** (not a soft
timeout) on camelCase fields + channel `EMAIL` + the confirmation message.
The folder is inert unless `--env-var notificationContractEnabled=true`
populates the environment-scope guard variable the pre-request script
checks — so the two pre-existing (Kafka-free) gates stay green and
untouched, and the new Kafka gate is the only one that turns it on.

| Run | Flag | Notifications served by | Result |
|---|---|---|---|
| Full suite, flag OFF | `STRANGLER_NOTIFICATION_ENABLED=false` | monolith (`order_placed_consumer` self-populates the read-model) | **66/66 green** |
| Full suite, flag ON | `STRANGLER_NOTIFICATION_ENABLED=true` | notification-service | **66/66 green — byte-identical in shape to the OFF run** |
| Bounded-wait margin | — | — | poll succeeded on attempt **2 of 20** (well inside the 15s budget — comfortable margin, not a near-miss) |
| Negative check (consumer down) | ON, notification-service consumer stopped | *(no row ever appears)* | **21 failed assertions, process exit 1** — the bounded-wait's strict terminal assert fires loudly, not a silent pass |
| Recovery | ON, consumer restarted | notification-service | green again |

The RED-then-green negative check mirrors the r02 precedent
(`CUTOVER.md`'s 502 negative check) for the async case: the gate does not
quietly pass when the extracted service's consumer is down, it fails loudly
with a nonzero exit code that a CI job can gate on.

**Kafka-in-CI:** `.github/workflows/code-ci.yml` gained a new
`notification-equivalence-gate` (Postgres + Kafka service containers +
monolith + relay + monolith self-consumer + notification-service + proxy,
run with the flag ON then OFF, plus the consumer-down negative check),
wired into the required `code-ci-ok` status. The two pre-existing gates
(monolith, review) remain Kafka-free and green, confirming the skip-guard
did not leak into gates that shouldn't pay the Kafka tax.

**Verdict:** CLEAN — async equivalence proven both directions, with margin,
plus a genuine negative check that fails loudly rather than silently.

### Verdicts summary

CLEAN across every artifact in this section, **plus two bugs found and fixed
during Verify** (not left latent, not discovered post-merge): the Alembic
async `CREATE SCHEMA` missing-commit bug, and the Testcontainers
`KafkaContainer` missing-`.with_kraft()` bug. One named user decision at the
plan gate (DRQ-038, monolith-self-consumer over the simpler fallback). No
unexplained drift for ch.16/17.

---

*Per `build-plan.md` §J, the Inventory extraction (ch.18–19, extraction 3 of
6) — Change Data Capture via Debezium, gRPC-first inventory on a decomposed
DB with CDC backfill — is scheduled for r04 in this project's renumbered
cadence. The next section appended to this file should be headed
`ch.18-19 — Inventory (r04, extraction 3 of 6)`, following the
per-extraction-reconcile shape above.*
