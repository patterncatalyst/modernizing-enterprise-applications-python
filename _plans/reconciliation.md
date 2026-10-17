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

## ch.18-19 — Inventory (r04, extraction 3 of 6)

### Proto-as-ACL + drift guard

**Source:** `_plans/r04-build-plan.md` (PROTO lane, DRQ-042) — a project-first
pattern, no external artifact reused; the design intent (author the contract
before either side's implementation) mirrors the Java sibling's gRPC seam but
the Python toolchain (`grpcio`/`grpcio-tools`/`protobuf`) is independently
authored.

**What shipped:** `inventory.proto` (`CheckStock`/`Reserve`/`Release`/
`GetStock`) authored first, with wire vocabulary deliberately distinct from
the domain model so the ACL earns its keep; `scripts/gen-proto.sh` generates
stubs for both `examples/04-inventory-service/` and a byte-identical vendored
copy under `examples/00-monolith/order/proto/`; `scripts/check-proto-drift.sh`
regenerates both copies and diffs them, failing loudly on any divergence.
Generated stubs are committed on both sides (not generated at build time),
so the drift guard has something concrete to check.

**Verdict:** CLEAN — the contract is the single source of truth, and the two
generated-stub copies (one per deployable) have an explicit, checkable
guarantee of staying identical rather than an implicit "they should match"
assumption.

### Reserve-outside-local-txn + compensating Release (the crux)

**Source:** `_plans/r04-build-plan.md` (MONOLITH-GRPC-CLIENT+SNAPSHOT lane,
DRQ-043) — a project-first design decision; no external precedent exists in
this project for compensating across a transaction boundary that spans two
separate databases.

**What shipped:** `place_order()` resolves the customer, then issues the
remote gRPC `Reserve` call **per line, before and outside**
`transaction.atomic()`, accumulating the set of already-reserved lines plus
the `StockReply` snapshot fields (sku/item name/unit price). Only once every
line reserves successfully does the flow enter `with atomic():` to create the
`Order`/`OrderItem`s (snapshotted)/payment/shipping/outbox rows. Any failure
*inside* the atomic block (a card decline → 402, a ship failure → 422) is
caught **outside** the block, after Django's own rollback has already run,
and triggers a compensating `Release` call for every line that was reserved
for this checkout — net-zero stock, proven by **directly querying the
inventory service's database** after a decline and after a ship-fail (not
inferred from HTTP status alone). `InventoryServiceUnavailable` (503) is kept
distinct from `InsufficientStock` (409) so a down dependency and a legitimate
stock conflict never share a status code.

**Rejected alternative (named, not silently avoided):** wrapping the remote
`Reserve` call inside the local `atomic()` block. Rejected because (a) it
holds a Postgres transaction open across a network round-trip for the
duration of the whole checkout, and (b) a local Django rollback cannot undo
an already-committed remote decrement in another service's database — the
"transaction" boundary would be cosmetic, not real. This is exactly the
crux the chapter teaches: once data crosses a process/database boundary,
ACID composition stops working and compensation becomes the only tool.

**Idempotency / over-restore — named limitation, not silently dropped.**
`Release` is not idempotent and does not guard against restoring more stock
than was actually reserved; this is documented in the inventory-service's
own module docs and recorded as DRQ-043's explicit deferral to the saga
chapters (ch.23/24), where idempotency keys and proper compensation
semantics are the chapter's actual subject matter. Not fixing it now is a
scope decision, not an oversight.

**Verdict:** CLEAN — the design is deliberate, the rejected alternative is
named with its concrete failure mode, the net-zero property is proven by
direct DB inspection rather than asserted, and the one real gap (idempotency)
is named and forward-referenced rather than hidden.

### CDC transition-only + NOT in CI (mirrors Java)

**Source:** `_plans/r04-build-plan.md` (CDC-BACKFILL lane, DRQ-044/045) —
confirmed against the Java sibling's own CDC/CI posture before building, per
the build plan's explicit note: "confirmed this is exactly how the Java gate
works."

**What shipped:** Debezium Connect (`quay.io/debezium/connect:3.7.0.Final`)
added to compose, Postgres switched to `wal_level=logical`, and
`infra/debezium/inventory-connector.json` configured for `pgoutput`
snapshot+stream off `public.inventory_items`. `scripts/register-debezium.sh`,
`scripts/verify-debezium.sh`, and `scripts/retire-debezium.sh` form a
register → verify → retire runbook, **live-verified**: register produced a
CDC event carrying a full before-image (REPLICA IDENTITY FULL) ahead of the
owned schema's own-seed taking over, and the idempotent retire left no
dangling connector or replication slot. The CI `inventory-equivalence-gate`
(`.github/workflows/code-ci.yml`) runs Postgres only, against the
**post-cutover end state** — inventory self-seeded via its own Alembic
migration, monolith `INVENTORY_MODE=grpc`, proxy flag ON — with **no Kafka,
no Connect, no Debezium container** anywhere in the job.

**Why this is not a gap:** CDC's entire job in this chapter is the one-time
migration of pre-existing shared-table data into the new owned schema during
a cutover window; once the service reaches its end state (own-seed or a
real backfill-then-retire), there is no remaining consumer of a live CDC
stream. Gating CI on a tool that by design doesn't run in steady state would
pay a real resource/time cost (standing up Kafka Connect) to test a
one-time migration aid, not the behavior-equivalence contract CI actually
needs to protect.

**Verdict:** CLEAN — CDC's scope (transition-only) and CI's scope (post-
cutover end state only) are both named explicitly and both confirmed to
match the Java sibling's precedent, not independently reinvented.

### FK→snapshot (DRQ-046)

**Source:** this project's own r02 price-snapshot precedent
(`unit_price_cents` was already snapshotted onto `OrderItem` at r01/r02),
extended to the full line-item identity now that inventory owns a separate
database.

**What shipped:** `order_items` drops its `inventory_item` ForeignKey and
gains `sku`/`item_name` snapshot columns, populated from the gRPC
`StockReply` at checkout time. A migration backfills the new columns from the
existing FK relationship *before* dropping it (so no data is lost in the
cutover), the DRF serializer maps `sku` via `source="sku"`, and the
`items__inventory_item` prefetch is removed. The public wire contract is
**unchanged** — this is purely an internal persistence change.

**Verdict:** CLEAN — the snapshot pattern already established for price is
extended consistently rather than inventing a second mechanism (e.g., a
second FK into the inventory service's database, which isn't even possible
across the schema boundary).

### Two cutover dimensions (DRQ-047)

**Source:** the r02/r03 precedent of a single strangler-proxy flag per
extraction (`STRANGLER_REVIEW_ENABLED`, `STRANGLER_NOTIFICATION_ENABLED`) —
inventory is the first extraction where one flag is not enough, because it
is also the first extraction with an internal (non-HTTP, non-proxied)
synchronous seam.

**Named divergence:** reads are still proxy-routed exactly like review and
notification (`STRANGLER_INVENTORY_ENABLED` on `/api/inventory*`), but the
monolith's reserve/release calls never go through the proxy at all — they
are an internal monolith→inventory-service gRPC call gated by its own
`INVENTORY_MODE=local|grpc` setting. The two flags are moved together in
practice (fully-local baseline, fully-gRPC cutover); a mixed state is
explicitly unsupported and documented as breaking Newman's stock-capture
assertions, so both the manual cutover runbook and the CI gate always flip
both together.

**Verdict:** CLEAN — the divergence from the one-flag-per-extraction
precedent is necessary (a second, genuinely different seam exists) and
named, not an accidental proliferation of flags.

### Concurrency-safe atomic Reserve (race-tested)

**Source:** no external artifact — a project-first requirement, since this
is the first mutation seam where two concurrent checkouts can race for the
same unit of stock.

**What shipped:** `Reserve` is implemented as a single conditional
`UPDATE inventory SET qty = qty - :q WHERE sku = :sku AND qty >= :q`, relying
on the row lock Postgres takes for the duration of the UPDATE rather than a
separate read-then-write check (which would race). A rowcount of 1 means
success, 0 means insufficient stock — both are distinguishable from the same
single statement. A dedicated concurrency test runs two racing reservations
against the last remaining unit of a SKU and asserts exactly one wins and
the other observes insufficient stock, never both succeeding (oversell) and
never both failing.

**Verdict:** CLEAN — concurrency safety is demonstrated by a race test, not
argued from the shape of the SQL alone.

### Newman: 71/71 green both configs, RED-then-green negative checks

**Source:** the r02/r03 equivalence-gate precedent
(`review-equivalence-gate`, `notification-equivalence-gate`), extended to a
contract with two independent cutover dimensions for the first time.

**What shipped:** the "Inventory Context Contract" Newman folder
(list/get/404, guarded by `--env-var inventoryContractEnabled=true`) plus the
existing Smoke + 4 checkout scenarios.

| Run | `STRANGLER_INVENTORY_ENABLED` | `INVENTORY_MODE` | Result |
|---|---|---|---|
| Fully-gRPC | ON | `grpc` | **71/71 green** |
| Fully-local (reversibility) | OFF | `local` | **71/71 green** |
| Negative — reads | ON | `grpc`, inventory service killed | reads **RED (502)**, then green again on restart |
| Negative — reserve | ON | `grpc`, inventory service killed | checkout **RED (503,** `InventoryServiceUnavailable`**)**, then green again on restart |

Net-zero stock on the DECLINE (402) and SHIP-FAIL (422) scenarios is verified
by **directly querying the inventory database** for the SKU's quantity
before and after each scenario in fully-gRPC mode, not just by asserting the
HTTP status code — the same discipline the reserve-outside-local-txn design
depends on being true (see above).

**Verdict:** CLEAN — equivalence proven in both cutover configurations, with
two distinct RED-then-green negative checks (reads vs. reserve) rather than
one, since inventory is the first extraction with two independently
failing seams.

### No integration bug surfaced (contrast with r02)

Unlike r02's strangler-proxy chunked-body bug (DRQ-026 — a real production
bug only caught when the proxy was exercised against a real socket rather
than an in-process ASGI transport), **r04 surfaced no equivalent integration
bug.** The gRPC seam, the reserve-outside-atomic ordering, and the two-flag
cutover were all exercised against real running processes (inventory service,
monolith, proxy) from the start of the NEWMAN lane, which is the most likely
reason no "only shows up over a real socket" class of bug was hiding here —
there was no in-process mock transport in the loop to mask one. This is
recorded as an honest contrast, not a claim that r04's seam is inherently
less risky than r02's.

**Verdict:** CLEAN — no drift, no latent bug found and smoothed over; the
absence of a bug is reported as an observation, not manufactured as a
cleaner story than r02's.

### Verdicts summary

CLEAN across every artifact in this section. No DRQ gate was put to the user
for an A/B choice at r04 (contrast r02's auth-contract gate, DRQ-029, and
r03's monolith-self-consumer gate, DRQ-038) — every decision (DRQ-041 through
DRQ-048) was settled by the Phase-1 planner as a synthesis default, and the
user approved the plan as a whole ("go") rather than choosing between
alternatives. No unexplained drift for ch.18/19.

---

## ch.23 — Payment (r05, extraction 4 of 6)

### The sync→async 201→202 contract change, and how the suite stayed honest

**Source:** `_plans/r05-build-plan.md` (headline decision, DRQ-049) — a
project-first: every prior extraction (review, notification, inventory)
changed *who* served a request or *how* data was stored, never the wire
contract's response code for an existing endpoint. Payment is the first
extraction that deliberately changes `POST /api/orders`'s success response
from `201 CONFIRMED` to `202 PENDING`.

**What shipped:** in `PAYMENT_MODE=choreographed`, checkout reserves stock via
gRPC, persists the order as `PENDING`, writes the `order.placed` outbox row
(now carrying an additive optional `paymentMethod`, DRQ-050), and returns
**202** — no in-process capture, no in-process shipping dispatch, no
in-process confirm. The DRF view derives 202 vs. 201 purely from the
persisted `OrderStatus`, so there is one code path, not a forked one. In
`PAYMENT_MODE=synchronous`, checkout is **byte-for-byte unchanged**: 201
CONFIRMED, in-process capture, zero regression — proven by running the full
Newman suite against the unmodified synchronous monolith and getting the same
green result as before r05 touched anything.

**How the equivalence suite stayed honest across the change (DRQ-056):**
every checkout-scenario POST became tolerant of `201|402|202`, and the
load-bearing assertion moved from "the POST response says X" to a
**bounded-wait poll of `GET /api/orders/{id}` to a strict terminal status**
(reusing the notification folder's `setNextRequest` retry idiom from r03),
plus strict side-effect assertions (stock delta / net-zero) verified by
direct DB query, not inferred from HTTP status. Two things keep this
honest rather than vacuous: (1) the suite was baselined **green against the
unmodified synchronous monolith first** — the bounded-wait polls resolve on
their very first attempt there, proving the mechanism isn't just "always
eventually passes"; (2) a **stuck-PENDING negative** — payment-service/its
consumer taken down, so an order can never leave `PENDING` — drives the
bounded wait to exhaustion and fails **RED, exit 1, in ~15.1s**, not a hang
and not a false green. A bounded-wait suite that cannot fail isn't actually
asserting anything; this is the concrete proof that it can.

**Verdict:** CLEAN — the contract change is named and user-approved (fixed,
DRQ-049), the suite's shape change is deliberate and documented (DRQ-056),
and both the positive baseline and the negative failure mode are
demonstrated, not asserted.

### Choreographed topology (contrast with r06's planned orchestration)

**Source:** `_plans/r05-build-plan.md` (DRQ-050, DRQ-008) — the choreographed
half of the project's saga stack-substitution mapping; `_plans/decisions.md`
DRQ-007 names the *other* half (r06's orchestrated shipping saga, reusing the
CNDP Python DB-backed orchestrator) as the deliberate contrast point.

**What shipped:** no orchestration engine, no central saga coordinator —
`examples/05-payment-service/` (:8085) is an aiokafka consumer of
`order.placed` that captures/declines and publishes `payment.captured`/
`payment.declined` from its own outbox; the monolith's new
`order_saga_listener` management command (group `monolith-order-saga`,
DRQ-053) is a second, independent aiokafka consumer that reacts to those
events with its own local state-transition logic. Each side only knows the
event contract, not the other side's internal state — the defining property
of choreography versus orchestration.

**Named divergence (none from plan):** the topology shipped exactly as
designed in `_plans/r05-build-plan.md`'s S5/S3 lanes — no deviation surfaced
during the build that required a new decision.

**Verdict:** CLEAN — the choreographed shape is real (two independent
reactive consumers, no coordinator), and its deliberate contrast with r06's
upcoming orchestrated shipping saga is named up front rather than discovered
after the fact.

### Idempotent compensation, closing DRQ-043

**Source:** `_plans/decisions.md` DRQ-043 (r04) explicitly deferred
"idempotency of `Release` and over-restore protection" to "the saga chapters
(ch.23/24)" — this section is where that deferred debt is paid off, recorded
now as DRQ-052.

**What shipped:** an `idempotency_key` field added to `inventory.proto`'s
`ReleaseRequest` (stubs regenerated both sides, `scripts/check-proto-drift.sh`
still green), checked against a new `inventory.compensations` ledger
(`UNIQUE` constraint, `ON CONFLICT DO NOTHING`) inside the inventory-service's
`Release` handler — a repeated `Release` with the same key is a database-level
no-op, not a second increment. A **client-side status-transition guard** was
added to `order_saga_listener` as defense-in-depth (it won't reprocess an
order already past the relevant status), but the **server-side ledger is the
real correctness guarantee** for the crash window the client guard cannot
see: `Release` succeeds, the status commit fails, redelivery retries. This
was proven, not just argued — a forced double-delivery test showed the saga
listener's guard catching the common case *and* the ledger catching the
crash-window case, with stock observed net-zero (**94→94**) after the
replay.

**Verdict:** CLEAN — closes an explicitly-named prior deferral (DRQ-043) at
the exact chapter the deferral pointed to, double-delivery is demonstrated at
both layers rather than asserted at one, and the over-restore protection
DRQ-043 flagged as missing is now mechanically impossible (ledger-enforced),
not just less likely.

### Shipping-fail Option A, and the honestly-deferred refund gap

**Source:** `_plans/r05-build-plan.md`'s USER-GATE DECISION (DRQ-054) — the
one A/B choice put to the user this iteration.

**What shipped:** shipping dispatch moved into the `payment.captured` saga
reaction (dispatched *after* capture, not before, avoiding a ship-before-pay
ordering smell); a shipping failure triggers a compensating gRPC `Release`
(idempotency-key-bearing, see above) and a new terminal `OrderStatus.
SHIPPING_FAILED` (a `TextChoices` addition, no DB migration). Scenario 4
converts to async: checkout POST tolerant of 202 (no longer 422 at checkout
time), bounded-wait to `SHIPPING_FAILED`, net-zero stock verified by direct
DB query.

**Named, un-silenced gap:** the payment that was already captured before
shipping failed is **not refunded** — a second compensation hop (a payment
refund, not just an inventory release) that this iteration deliberately does
not build. This is recorded here exactly as `_plans/r05-build-plan.md` framed
it: Option A was chosen *because* it turns shipping into a real saga step
that r06's orchestrated saga can extend to include the refund hop, rather
than solving the whole compensation chain in one iteration. Option B (reject­
ed) would have kept shipping synchronous and byte-for-byte, but would have
reintroduced a ship-before-pay smell inside the very chapter curing checkout's
ACID coupling, and would never have made shipping a saga step at all.

**Verdict:** CLEAN — the gap is named, scoped, and forward-referenced to a
specific future iteration with a specific mechanism (r06's orchestrator) to
close it, not left as an implicit todo.

### Two cutover dimensions, zero-regression synchronous mode

**Source:** the r04 precedent of two independent cutover flags
(`STRANGLER_INVENTORY_ENABLED` + `INVENTORY_MODE`, DRQ-047) extended to
payment (DRQ-055): proxy `STRANGLER_PAYMENT_ENABLED` routes `/api/payments`
reads to `:8085`; monolith `PAYMENT_MODE=synchronous|choreographed` selects
checkout's capture behavior. As with inventory, the two flags are moved
together in the cutover runbook and in CI; a mixed state is unsupported.

**Zero-regression claim, verified not asserted:** with `PAYMENT_MODE=
synchronous`, the full Newman suite runs byte-for-byte green against the
unmodified checkout path — the new choreographed machinery (payment-service,
`order_saga_listener`, the idempotent `Release` path) sits entirely dormant
when the flag is off, so introducing it carries no regression risk for
readers who haven't cut over yet.

**Verdict:** CLEAN — extends an established two-flag pattern consistently
rather than inventing a third flag shape; the zero-regression claim is
demonstrated by a full green suite run in the pre-cutover configuration, not
merely argued from the code's structure.

### Green evidence summary

| Check | Result |
|---|---|
| Scenario 1 (happy path), choreographed | 202 → bounded-wait → CONFIRMED, attempt 2 of 20 |
| Scenario 3 (card decline), choreographed | 202 → bounded-wait → PAYMENT_DECLINED, stock net-zero |
| Scenario 4 (ship-fail), choreographed, Option A | 202 → bounded-wait → SHIPPING_FAILED, stock net-zero |
| Reversibility (`PAYMENT_MODE=synchronous`) | full suite green, byte-for-byte |
| Stuck-PENDING negative (consumer down) | RED, exit 1, ~15.1s — not a hang |
| Double-delivery idempotency (forced redelivery) | saga-listener guard + inventory ledger both catch it; stock 94→94 |
| `payment-equivalence-gate` (CI) | green, wired into `code-ci-ok` |

### Verdicts summary

CLEAN across every artifact in this section. One DRQ gate was put to the user
at r05 — shipping-fail Option A vs. Option B (DRQ-054) — resolved in favor of
the planner's recommended Option A; every other r05 decision (the 201→202
contract change itself, DRQ-049; the choreographed topology, DRQ-050; the
payment-service shape, DRQ-051; idempotent compensation, DRQ-052; the saga
reaction location, DRQ-053; the two cutover dimensions, DRQ-055; the suite
conversion, DRQ-056; the chapter scope, DRQ-057; no new pins, DRQ-058) was
settled by the Phase-1 planner as a synthesis default or as the plan's own
stated headline. No unexplained drift for ch.20/22/23.

---

## ch.24-25 — Shipping (r06, extraction 5 of 6)

### Orchestrated saga: the CNDP Example-17 adaptation

**Source:** `~/Dev/cloud-native-design-patterns/examples/17-sagas/python/
saga-orchestrator/` and its `_docs/17-appendix-d-sagas.md` — recorded as a
forward reference at r01 (DRQ-007) and in this file's own first-creation
note, built for the first time this iteration (DRQ-059).

**Reused as-is (shape):** the orchestrator's core logic — a STEPS/
COMPENSATIONS table, `advance()` guarded by a row lock and an idempotent
"already past this step" check, reverse-order `compensate()` over only the
steps that actually completed, and persisted `sagas`/`saga_log` state as the
source of truth for where a saga is.

**What shipped (adapted, not ported verbatim):** the source's raw-asyncpg
persistence is re-homed onto this repo's async SQLAlchemy[asyncio] +
asyncpg + Alembic stack — the row lock is `select(Saga).with_for_update()`,
not a hand-rolled `SELECT ... FOR UPDATE` string — and the orchestrator is
embedded inside `examples/06-shipping-service/` (:8087) rather than kept as
a standalone service, triggered by a `payment.captured` Kafka consumer
instead of the source's own trigger. The service owns its own `shipping`
Postgres schema (sagas, saga_log, shipments, outbox), mirroring the owned-
schema posture every prior service-with-its-own-data has used since
notification (DRQ-035). Steps: `enrich` (REST `GET` to the monolith for the
shipping address, `httpx`+`tenacity`) then `dispatch` then `book_carrier`
(the `SHIP-FAIL` sentinel lives in the address, checked here, DRQ-065) then
`emit` (writes `shipment.dispatched`/`shipment.failed` to the service's own
outbox, atomically with the saga's terminal state change).

**Named divergence:** persistence engine (raw asyncpg to SQLAlchemy[asyncio]/
asyncpg), embedding (standalone service to embedded in shipping-service),
and trigger (the source's own driver to a Kafka consumer) — all three named
and traced to DRQ-059, not silent.

**Verdict:** CLEAN adaptation — logic reused, persistence and integration
re-homed deliberately and named.

### The durability upgrade: crash-resume, proven live

**Source:** the Java sibling's `InMemorySagaService` (the orchestrator's
analogue in that book) is the explicit comparison point named in
`_plans/r06-build-plan.md` and recorded as DRQ-060 — not a reused artifact,
but the contrast this adaptation is built to demonstrate.

**What shipped:** because saga state (`sagas`+`saga_log`) is persisted, not
held in a process's memory, a crash mid-saga does not lose progress.
`resume_running_sagas()` runs at shipping-service startup, scans for
`RUNNING` sagas, and resumes each from its persisted `step_index`. **Proven
live**, not just argued from the schema: the process was killed mid-saga and
restarted, and the health/startup log reported `resumedSagaCount=1` — the
saga picked up from its last completed step without re-invoking `enrich`
(the already-fetched shipping address was not re-fetched).

**Why this matters for ch.24's pedagogy:** the Java sibling's in-memory
orchestrator loses all in-flight saga state on a crash or restart — there is
nothing to resume from. The Python sibling's DB-backed adaptation is a real,
measured improvement over that, not a parity port dressed up as one; ch.24
teaches crash-resume as a concrete property with a before/after demo, not a
claim.

**Verdict:** CLEAN — a genuine durability upgrade, demonstrated by a kill-
and-restart test, not merely asserted from the orchestrator's design.

### Orchestrated vs. choreographed, side by side on one codebase

**Source:** r05's payment saga (`examples/05-payment-service/`,
`reconciliation.md`'s own "ch.23 — Payment" section above) is the direct
comparison point, by design (DRQ-050/DRQ-061).

**The contrast, concretely:** r05's payment-service and the monolith's
`order_saga_listener` are two independent Kafka consumers, each reacting to
events with no shared coordinator and no knowledge of the other's internal
state — choreography. r06's shipping-service is one named coordinator
(`app/orchestrator.py`) that owns the entire fulfilment sequence
(enrich then dispatch then book_carrier then emit) and the compensation
decision top-to-bottom — orchestration. The two topologies sit in the same
codebase, reacting to adjacent events in the same saga (`payment.captured`
triggers shipping; `shipment.failed` triggers the payment refund, see
below), making the contrast concrete rather than textbook.

**A structural consequence, not just a style difference:**
`OrderStatus.CONFIRMED` now *requires* a `shipment.dispatched` event — the
monolith's saga listener no longer sets CONFIRMED as a side effect of
`payment.captured` in orchestrated mode, it waits for shipping-service's own
event (DRQ-061). This is what makes shipping-service a true saga
*participant* rather than a relocated function call.

**Verdict:** CLEAN — the contrast is real and structural (different
coordination topologies with a visible consequence on the order lifecycle),
not a relabeling of the same mechanism.

### The refund hop, closing DRQ-054

**Source:** `_plans/decisions.md` DRQ-054 (r05) named the gap explicitly:
"the already-captured payment is not refunded on ship-fail... this iteration
explicitly defers to r06's orchestrated shipping saga, which is positioned
to close it." This section is where that deferred debt is paid off,
recorded now as DRQ-064.

**What shipped:** payment-service gained a second Kafka consumer —
`shipment.failed` — alongside its existing `order.placed` consumer. On
receipt, if it holds a `CAPTURED` payment for that `order_id`, it
transitions to a new `REFUNDED` status and emits `payment.refunded` via its
own outbox; a status guard means an uncaptured order is never refunded and
a redelivered `shipment.failed` refunds at most once. This is the concrete
correctness win `_plans/r06-build-plan.md` calls out as "the r06 correctness
win the Java sibling never built."

**Why payment-service, not shipping-service, owns this:** the refund
mutates payment data that only payment-service's schema holds; having the
shipping orchestrator reach into another service's database to write a
refund would violate the owned-data boundary every extraction since
notification's DRQ-035 has respected. Modeling it as payment-service
reacting to a fact about shipping (`shipment.failed`) keeps the pattern
identical to every other saga reaction in the project.

**Verdict:** CLEAN — **closes DRQ-054**'s named deferral at exactly the
iteration it pointed to, with the refund proven idempotent (status guard)
and correctly scoped (never fires for an uncaptured order).

### The `AWAITING_SHIPMENT` lifecycle

**Source:** `_plans/r06-build-plan.md` (DRQ-063) — a project-first addition
to the order state machine, the first new terminal-adjacent status since
`SHIPPING_FAILED` at r05.

**What shipped:** `PENDING` then (`payment.captured`) then
`AWAITING_SHIPMENT` then (`shipment.dispatched`) then `CONFIRMED`, or
(`shipment.failed`) then `SHIPPING_FAILED` plus a compensating `Release`. A
`TextChoices` addition only, no DB migration; `SHIPPING_MODE=inprocess`
leaves the r05 PENDING-to-CONFIRMED path untouched (zero regression,
verified by a full green Newman run in `inprocess` mode).

**Reconciliation finding — the poll-script bug the live cutover caught.**
The Newman bounded-wait poll script (the `setNextRequest` retry idiom used
since the notification folder, DRQ-039) had hard-coded its "keep polling"
condition to `status === "PENDING"`. Once orchestrated mode introduced a
second non-terminal status, a poll issued while an order legitimately sat in
`AWAITING_SHIPMENT` exited the retry loop early — a **false negative**, not
a false positive: the suite reported failure on an order that was still
correctly in flight. This surfaced during the live cutover run, not in a
unit test. **Fixed** by changing the retry condition to check against the
full set of known non-terminal statuses (`PENDING`, `AWAITING_SHIPMENT`)
rather than a single hard-coded value; the same narrow-retry assumption was
latent in Scenario 4's negative (N1b) and was fixed at the same time. The
suite is **6/6 stable** after the fix, re-run against both `inprocess` and
`orchestrated` modes.

**Lesson:** a bounded-wait suite's retry condition is itself a claim about
how many non-terminal statuses exist — that claim silently stopped being
true the moment this iteration added a second one. The fix generalizes the
retry condition instead of special-casing `AWAITING_SHIPMENT`, so a future
third non-terminal status won't repeat the same bug (recorded in
`_plans/decisions.md` DRQ-063 as a suite-design lesson, not just a one-line
patch).

**Verdict:** bug-found-and-fixed — caught by the live cutover evidence
trail before it reached CI, consistent with this project's precedent
(DRQ-026's chunked-body bug at r02, the Alembic-commit and Testcontainers-
KRaft bugs at r03).

### The stuck-AWAITING_SHIPMENT negative

**Source:** the established RED-then-green negative-check precedent
(the r02 502 proxy-down check, the r03 stuck-notification check, the r05
stuck-PENDING check) extended to shipping's new intermediate status.

**What shipped:** with shipping-service (or its consumer) taken down, an
order that reaches `AWAITING_SHIPMENT` can never leave it; the bounded-wait
poll exhausts its budget and the suite fails **RED, exit 1** — not a hang,
not a silent pass. Restarting shipping-service and re-running recovers to
green. This is the honesty guarantee for the new intermediate status, the
same role DRQ-056's stuck-PENDING negative played for payment at r05.

**Verdict:** CLEAN — a genuine negative, not merely a positive-only suite
with an assumed failure mode.

### Zero-regression `inprocess` mode

**Source:** the established zero-regression precedent for every prior
extraction's "off" flag state (review, notification, inventory's `local`
mode, payment's `synchronous` mode).

**What shipped:** with `SHIPPING_MODE=inprocess`, the full Newman suite runs
byte-for-byte green against the r05 checkout path — the new orchestrator,
the `AWAITING_SHIPMENT` status, and the refund hop all sit entirely dormant.

**Verdict:** CLEAN — demonstrated by a full green suite run in the
pre-cutover configuration, not merely argued from the code's structure.

### Green evidence summary

| Check | Result |
|---|---|
| Orchestrated saga, happy path | AWAITING_SHIPMENT then bounded-wait then CONFIRMED, one `shipment.dispatched`, one Shipment DISPATCHED |
| Orchestrated saga, SHIP-FAIL | AWAITING_SHIPMENT then bounded-wait then SHIPPING_FAILED, compensating Release (net-zero stock), one `shipment.failed`, no `shipment.dispatched` |
| Refund hop | SHIP-FAIL order gets payment REFUNDED exactly once plus `payment.refunded`; decline-then-no-ship path asserts no refund fires |
| Crash-resume | kill mid-saga, restart, `resumedSagaCount=1`, resumed from persisted `step_index`, `enrich` not re-invoked |
| Reversibility (`SHIPPING_MODE=inprocess`) | full suite green, byte-for-byte vs. r05 |
| Stuck-AWAITING_SHIPMENT negative | RED, exit 1 — not a hang |
| Poll-script fix | 6/6 stable after retrying through `AWAITING_SHIPMENT`, not just `PENDING` |
| `shipping-equivalence-gate` (CI) | green, wired into `code-ci-ok` (6 gates) |

### Verdicts summary

CLEAN across every artifact in this section, **plus one bug found and fixed
during the live cutover** (the poll-script's narrow `PENDING`-only retry
condition) — consistent with this project's established practice of
reporting defects found during Verify honestly rather than smoothing them
over. No A/B gate was put to the user at r06 (DRQ-059 through DRQ-070 were
all settled by the Phase-1 planner as synthesis defaults, and the user
approved the plan as a whole with "go" — the same no-A/B posture as r04).
No unexplained drift for ch.24/25.

---

## ch.21/26 — Order + GraphQL Gateway (r07, extraction 6 of 6) — THE FINALE

### CQRS: same-DB read model, same-transaction projection

**Source:** `_plans/r07-build-plan.md`'s user-approved recommendations #1
and #2 (DRQ-072), authoring ch.21 (Event Sourcing & CQRS) deferred from r05
specifically to have a load-bearing anchor (DRQ-057).

**What shipped:** `examples/07-order-service/` (:8088) is CQRS from day
one — a normalized write aggregate (`orders`/`order_items`, plus `outbox`
and the owned `customers` table) and a denormalized `order_view` read
table. Every write path (`create_order_with_outbox_and_view`,
`transition_order_status_with_view`) upserts `order_view` inside the SAME
local transaction as the aggregate mutation it pairs with — never a second,
asynchronously-lagging source of truth. `app/routes.py`'s `GET` handlers
read `order_view` exclusively; the write tables are never queried for a
response. `rebuild_order_view` proves the projection is mechanically
rebuildable from the aggregate, not an independently-maintained shadow
copy.

**Reconciliation finding — the projection-disabled negative.** The suite's
honesty requirement (established at DRQ-056/DRQ-063's stuck-status
negatives) needed a CQRS-specific failure mode: a stale read model, not a
stuck write-side status. Commenting out the `order_view` upsert call in
`transition_order_status_with_view` (aggregate still transitions correctly;
only the read-side projection stops syncing) and re-running Scenario 1
alone produced a clean, bounded-wait RED: `GET /api/orders/{id}` exhausted
its full 40-attempt budget still reporting `PENDING` while the aggregate had
genuinely reached `CONFIRMED` — 1/53 assertions failed, newman exit 1.
Restoring the line and re-running returned a clean 0-failed pass. This is
the proof that `order_view` has no fallback path to the write tables; a
bounded-wait suite that can't catch a stale read isn't actually testing the
CQRS contract.

**Verdict:** CLEAN — the same-transaction design choice is demonstrated, not
merely argued: the projection-disabled negative is the concrete evidence
that read-your-writes depends on the projection actually running.

### Lifting the four saga reactions (preserving r05/r06 behavior)

**Source:** the monolith's `order/management/commands/order_saga_listener.py`
(DRQ-053/DRQ-061/DRQ-063), the project's own prior artifact — not an
external reuse.

**What shipped:** `app/consumer.py` lifts the same four-stage reaction table
(`payment.captured`→`AWAITING_SHIPMENT`, `payment.declined`→
`PAYMENT_DECLINED` + compensating Release, `shipment.dispatched`→
`CONFIRMED`, `shipment.failed`→`SHIPPING_FAILED` + compensating Release)
into order-service's own `aiokafka` consumer (group `order-service`), with
every transition an atomic conditional `UPDATE ... WHERE status = <expected>`
(idempotent, extending the DRQ-066 status-guard pattern) and every
compensating `Release` carrying a stable `{order_id}:{sku}:release`
idempotency key (extending DRQ-052's ledger-based guarantee to this side of
the gRPC seam). The refund-on-ship-fail behavior closed at DRQ-064 is
**preserved unchanged** — order-service's own `handle_shipment_failed` only
releases inventory and transitions status (by design, documented in its own
docstring as a "KNOWN DEFERRAL"); the refund itself still fires from
`05-payment-service`'s independent `shipment.failed` consumer, reacting to
the identical event. No regression: a captured-then-failed order is still
refunded exactly once, by the same service that always owned that
responsibility.

**Named divergence:** none structural — this is a same-project relocation
(monolith Django management command → order-service's own FastAPI/aiokafka
consumer), not an external adaptation; the reaction table, guards, and
compensation targets are unchanged.

**Verdict:** CLEAN — unit-level guard re-assertion plus the live contract
suite (Scenario 3/4 and the forced-redelivery negatives below) confirm the
lift regressed nothing.

### Customer FK → snapshot, and the order-service-seeds-customers divergence from Java

**Source:** `00-monolith/order/models.py::Order.customer` (a hard FK into
the shared `common.Customer` table, SMELL[ch.18]) and the inventory
extraction's own FK→snapshot precedent (DRQ-046).

**What shipped:** order-service owns a forward-filled copy of the
customer table (`order_svc.customers`, migrated and seeded via
`migrations/versions/0002_seed_customers.py` with the same Ada/Grace rows
the monolith's seed creates); `orders.customer_id` is a real FK into this
OWNED table, never a live cross-service reference, and `orders.customer_email`
is additionally captured as its own point-in-time snapshot so a later email
change never rewrites a historical order's outbox payload (DRQ-073).

**Named divergence from the Java sibling, recorded deliberately:** the
Python order-service **seeds** its own customer rows; the Java sibling's
`08-order-service` ships **no demo seed** of its own, because in the Java
book customer data remained monolith-shared-schema even after
decommission. The Python sibling instead makes order-service the genuine
owner of customer master data once the monolith is frozen off — a
from-scratch Python order-service has to be able to stand up and seed
itself with no live monolith left to read from, which the Java topology
never required of its own order-service. This is a real behavioral
difference between the two sibling books' end states, not an oversight —
recorded at DRQ-073.

**Verdict:** CLEAN adaptation, with the seed divergence named and traced to
DRQ-073 rather than left as a silent gap against the Java sibling.

### The data-less GraphQL gateway, and partial-failure handling

**Source:** the house Strawberry aggregation style in
`~/Dev/datamesh-reference-arch-python/examples/lgtm-datamesh/services/
graphql-gateway` and the role played by the Java/Quarkus sibling's own
`examples/08-graphql-gateway` (SmallRye GraphQL) — re-authored on
Strawberry, not ported line-for-line (DRQ-074, user rec #3).

**What shipped:** `examples/08-graphql-gateway/` (:8090) owns no data; it
answers `Query.order(id)` by federating order-service (REST), payment-
service (REST), shipping-service (REST), review-service (REST), and
inventory-service (gRPC `GetStock`) — each field resolved by calling the
service that owns it, the same protocol that service's other consumers use.
It sits alongside every other service's own REST surface and the strangler
proxy, with its own front door, never routed through either. Query depth
(`strawberry.extensions.QueryDepthLimiter`) and total-token
(`MaxTokensLimiter`) bounds are wired in, both in-package — no new
dependency beyond `strawberry-graphql` itself needed for the bound. A
downstream failure on a federated field (`payments`, `shipments`, `stock`,
`reviews`) raises `DownstreamUnavailable`, left uncaught on purpose;
Strawberry's own null-propagation nulls just that field and appends an
entry to the response's top-level `errors[]` — siblings still resolve, the
whole query never crashes into a 500. An unknown order id returns a plain
`data.order: null` with **no** `errors[]` entry (a missing order is a
legitimate answer, not a downstream failure).

**Named divergence:** re-authored on Strawberry rather than SmallRye
GraphQL (the project's standing stack-substitution mapping, DRQ-019); no
federation router or schema-stitching framework introduced — a single
data-less resolver module is sufficient at this scale (rejected alternative
named at DRQ-074).

**Verdict:** CLEAN adaptation — the aggregation role is reused, the
implementation is idiomatically Python-native, and partial-failure
behavior is proven (see the bug below), not just asserted.

### A real integration bug found and fixed: the GraphQL contract query didn't match the live schema

**Source:** the GraphQL Gateway Contract folder (G1) was authored STAGED,
inert-by-default, in an earlier lane (`tooling/newman/GOLDEN-BASELINE-r07.md`)
*before* `08-graphql-gateway` existed — a speculative guess at the schema
shape.

**What broke:** the staged query guessed `stock { quantityOnHand }` (the
real field, per `app/schema.py::StockView`, is `onHandQty`) and a top-level
`order.reviews` (reviews are federated PER-ITEM —
`OrderItemView.reviews` — not a top-level `OrderView` field, because a
review is posted against a sku, not an order). Running the staged query for
real, for the first time, against the live gateway produced `data.order:
null` with two `errors[]` entries (`Cannot query field 'quantityOnHand' on
type 'StockView'`, `Cannot query field 'reviews' on type 'OrderView'`),
confirmed by hand with a direct `curl` against `:8090/graphql`.

**Root cause:** the query was authored speculatively against a schema that
didn't exist yet; it was never run against a live gateway until the
decommission lane's contract-suite conversion pass.

**Fix:** corrected the query to the real, per-item-nested shape
(`items { sku stock { onHandQty } reviews { rating } } }`), rewrote the
test-script assertions to match it, and added an explicit "No GraphQL
errors" assertion so a future schema drift fails loudly instead of
producing a confusing `TypeError` on `order.items`. Verified by hand against
the live gateway post-fix (order id 29: real nested stock + 5 reviews + 1
payment + 1 shipment, zero errors) before re-running the suite, which then
passed green (see the stability table below).

**Lesson:** a STAGED, never-executed contract request is not a verified
contract — it's a hypothesis. This is the same lesson this project's
earlier bug catches (DRQ-026's chunked-body bug, the r06 poll-script's
narrow retry condition) keep teaching: equivalence/contract claims are only
real once proven against the live system, not an in-process mock or an
authored-but-unrun guess.

**Verdict:** bug-found-and-fixed — caught during the decommission lane's
contract-suite conversion, before it reached CI, consistent with this
project's established practice of reporting defects found during Verify
honestly.

### The decommission: reversibility proven, then the one irreversible move

**Source:** `_plans/r07-build-plan.md`'s user rec #4 (monolith end state,
the plan's explicitly highest-stakes question, DRQ-075) and rec #5
(reversibility, DRQ-077).

**What shipped, in order:** (1) `STRANGLER_ORDER_ENABLED` was added to the
proxy and shipping-service's `enrich` call was re-pointed from
`MONOLITH_BASE_URL` to order-service's `ORDER_BASE_URL` — both reversible
changes. (2) **The last reversible proof in this project's strangler-fig
history** was captured: full extracted topology with every strangler flag
on (no monolith process running at all) — 44 requests/117 assertions, 0
failed; vs. every flag off, only the bare monolith running — 33
requests/105 assertions, 0 failed. Both configurations produced a correct
answer; turning `STRANGLER_ORDER_ENABLED` off and restarting still worked,
right up to this point. (3) **The irreversible step:** the strangler proxy
was rewritten flagless — every `*_enabled` boolean and `monolith_base_url`
removed from `Settings`; `_select_backend()` became an unconditional
six-way lookup (review/notification/inventory/payment/shipping/order),
returning `None` (→ a real `404`) for anything else; `test_routing.py` was
rewritten from scratch (29/29 green, `ruff check` clean) — a parametrized
all-12-path-variants test, an all-six-coexist test, an unmatched-path test
(including near-miss prefixes like `/api/order` that must NOT match
`/api/orders`), and six independent backend-down tests. (4) The monolith
itself was frozen, not deleted: `README.md`/`AGENTS.md` gained a "FROZEN
STATUS (r07)" section; `compose.yaml`/`scripts/`/`demos/` no longer start
it or its `outbox_relay`/`order_placed_consumer`/`order_saga_listener`
management commands. (5) Learner-reference preservation: a
`reference/monolith-before` branch plus `v0-monolith` and `stage/01..06`
tags (`stage/06-order` cut at merge) — a re-bootable break-glass path, not
a deleted-and-gone history. (6) The proto-drift guard was extended from 2
to 4 vendored copies (monolith, order-service, graphql-gateway, plus the
canonical inventory-service original) — verified live, including a
deliberate drift injection that correctly failed.

**Verdict:** CLEAN — the one deliberate, system-wide irreversible move in
this project's history was de-risked exactly as planned: proven reversible
right up to the moment before it wasn't, with a frozen, re-bootable
break-glass path recorded rather than destroyed.

### SMELL #1/#2 struck — ACID→ACD for all six contexts

**Source:** `examples/00-monolith/SMELLS.md`, the project's own standing
smell ledger, created at r01 and updated at every extraction since.

**What shipped:** SMELL #1 (the god checkout service, `order/services.py::
place_order()`) and SMELL #2 (one in-process ACID transaction spanning six
contexts) are both marked **STRUCK (r07)** in `SMELLS.md` (DRQ-080). The
monolith's own `place_order()` is now frozen, decommissioned code with a
real replacement: `07-order-service/app/service.py::place_order` reaches
inventory only over a versioned gRPC contract and never touches payment/
shipping/notification's code or tables directly. Its own local transaction
spans ONLY the `order_svc` schema (aggregate + `order_view` + the
`order.placed` outbox row); the four downstream reactions are each their
own local transaction in their own service's own schema, coordinated purely
through Kafka events and idempotent status guards. This completes the
ACID→ACD arc that began at r05 (payment's 201→202 flip) and continued at
r06 (shipping's AWAITING_SHIPMENT handoff) — **every one of the six
contexts** now reaches its terminal state through a real saga with real
compensating actions, never a shared-transaction rollback. SMELL #3/#4
(shared schema / cross-context FKs) and SMELL #7 (review auth coupling)
remain `open` in the ledger — they describe the frozen monolith's own
code, which is out of scope for this extraction.

**Verdict:** CLEAN — the two smells SMELLS.md named at r01 as the specific
motivation for making order the hardest/last extraction are struck with
concrete evidence (a frozen function, a real replacement, a transaction
boundary that now spans one schema), not a label change.

### Equivalence → contract suite, monolith-free

**Source:** DRQ-010's standing requirement (the Newman suite is the one
equivalence gate every extraction is re-measured against) and DRQ-076's
reframing of it for the post-decommission state.

**What shipped:** with no live monolith left to compare against,
`tooling/newman/proxy.postman_environment.json` now bakes in every
context's contract flag as always-on (review/notification/inventory/
payment/shipping/order/graphql); the collection's own default `{{baseUrl}}`
re-points from the monolith (`:8000`) to the proxy edge (`:8888`);
`local.postman_environment.json` (bare monolith) is kept, unchanged, for
break-glass use only. The suite's assertions now mean "does the live system
satisfy its contract," not "does it match the monolith."

**Green evidence summary**

| Check | Result |
|---|---|
| Final monolith-anchored baseline (pre-cutover) | `tooling/newman/GOLDEN-BASELINE-r07.md`, Order Context Contract O1–O4 green against the live monolith |
| Reversibility proof | extracted-topology ON: 44 req/117 assertions, 0 failed; monolith-only OFF: 33 req/105 assertions, 0 failed |
| Flagless proxy routing | 29/29 tests green, `ruff check` clean |
| Proto-drift guard (4 copies) | `OK`, byte-identical; drift injection correctly detected and reverted |
| Contract suite, monolith-free, post-fix | 50 req/133 assertions, 0 failed (×2 stable) |
| Contract suite, post negative-check restores | 45 req/128 assertions, 0 failed (×2 stable) |
| Negative 1 — consumer-down (order-service killed) | 59/111 assertions failed, exit 1; recovered 0 failed on restart |
| Negative 2 — compensation-disabled | 1/30 assertions failed (stock non-net-zero), exit 1; recovered 0 failed on restore |
| Negative 3 — projection-disabled → stale read | 1/53 assertions failed (stuck PENDING past the bounded-wait budget), exit 1; recovered 0 failed on restore |
| `demos/demo-final-topology.sh` | standalone from-scratch run, 50 req/133 assertions, 0 failed, clean teardown |
| GraphQL gateway, live | `order(id)` stitches order+payment+shipment+per-item-stock+per-item-reviews, zero errors post-fix |

**Verdict:** CLEAN — contract suite green ≥2× against the fully
monolith-free mesh (four total clean runs, two before and two after the
three negative-check interventions), all three required negatives
independently proven RED when broken and GREEN when restored, one real
integration bug found and fixed along the way.

### Verdicts summary

CLEAN across every artifact in this section, **plus one bug found and
fixed** (the staged GraphQL contract query not matching the real, as-built
schema) — consistent with this project's established practice of reporting
defects found during Verify honestly rather than smoothing them over. Five
A/B gates were put to the user at r07's header — CQRS shape, projection
timing, the gateway's shape, the monolith's end state (the plan's
explicitly highest-stakes question), and reversibility — and all five were
resolved in favor of the planner's recommended option (DRQ-072, DRQ-074,
DRQ-075, DRQ-077); every other r07 decision was a synthesis default. No
unexplained drift for ch.21/26.

---

## FINAL PROJECT

**The strangler-fig is complete — the Django monolith is decommissioned;
six FastAPI services plus a GraphQL gateway sit behind a flagless edge
router; ACID→ACD everywhere.** Review, notification, inventory, payment,
shipping, and order have each been extracted in rising order of difficulty
(DRQ-013), each behind its own reversible cutover flag, each gated green by
its own equivalence check before the next extraction began. The monolith
that was once the single point of truth for all six contexts — one shared
Postgres schema, one god checkout function, one ACID transaction spanning
everything — is now frozen, in-repo, unreachable from the running topology,
its own `SMELLS.md` crossed out line by line as each cure landed (#5/#6 at
r03, #1/#2 at r07; #3/#4/#7 remain, by design, describing only the frozen
code). What runs today is seven independently deployable services —
review, notification, inventory, payment, shipping, order, and the GraphQL
gateway — coordinated through Kafka sagas (choreographed at r05, orchestrated
at r06, both lifted into order-service's own reactions at r07) and gRPC
contracts, fronted by one flagless edge router with no monolith fallback
left to fall back to. This is the payoff the whole roadmap (§E) was built
toward from r01's walking skeleton onward.

**What remains, non-extraction:** Part 8–10 chapters (ch.27–32: the FastAPI
microservices chassis, deployment strategies, registries, service mesh/
observability, GitOps/supply-chain, and the closing chapter); the
OpenShift/CRC appendix (ch.33, per the standing OpenShift/CRC Appendix
Standard); and the three companion decks. None of these are extractions —
the decomposition roadmap itself (§E) is finished as of this section.

---

## ch.27-28 — FastAPI Chassis + Contracts & Service Registry (r08, Part 8, non-extraction)

### The chassis scorecard, and the pydantic-settings correction

**Source:** `build-plan.md` §B.2's ch.27 blurb and §C's "Microservices
Chassis" row — both asserted, at planning time, that the chassis chapter
would document **pydantic-settings** as the configuration mechanism. This is
the first doc-vs-code drift this project's reconciliation practice has found
in its own planning artifacts (every prior reconcile section found drift
only between a reused *external* source and its adaptation, e.g. the
chunked-body proxy bug or the GraphQL staged-query bug — this one is a plan
describing something the as-built code never did).

**What the code actually does, verified by reading every service's own
config module, not by re-trusting the plan:** 7 of 8 services (strangler
proxy excepted; see below) use a **frozen `@dataclass` with a `from_env()`
classmethod** reading `os.environ` — `pydantic-settings` is not a dependency
of any `pyproject.toml` in this repo. The strangler proxy uses a
module-level singleton instead of a `Settings` dataclass instance; the
review-service makes bare `os.environ` calls with no `Settings` object at
all. **No service ever adopted pydantic-settings** — the plan's claim was
aspirational, written before any extraction shipped a config module, and
never revisited against the as-built code until this reconcile pass.

**What shipped (the correction, recorded as DRQ-083):** ch.27 is authored
against the real shape, not the planned one; `build-plan.md` §B.2/§C are
corrected in place (not silently rewritten — the correction itself is named
and cross-referenced to DRQ-083, so a reader of the ledger's history can see
what was claimed, when it was caught, and what replaced it). The chapter's
full scorecard, each cell independently verified against the actual
service code rather than assumed from the pattern established by the first
service checked:

| Mechanism | Coverage | Detail |
|---|---|---|
| Config = frozen `@dataclass Settings.from_env()` | 7/8 | proxy = module singleton; review = bare `os.environ`, no `Settings` object |
| pydantic models for request/response schemas | 6/8 | |
| stdlib logging → `logs/` | 8/8 | |
| Containerfile | 8/8 | |
| `/health` route | 6/8 | absent in proxy + review |
| `errors.py` (uniform error body) | 6/8 | absent in proxy + gateway |
| `tenacity` retry/timeout | 1/8 | shipping only (DRQ-068/069) |
| OTel traces/metrics | 0/8 | DEFERRED — ch.30 adds OTel to 3 services |
| pybreaker (circuit breaker) / bulkhead | 0/8 | DEFERRED — named at DRQ-068, still true at r08 |
| Shared chassis library (one package, 8 importers) | not built | DEFERRED BY CHOICE (DRQ-082) — each service's chassis bits are independently written, not extracted into a common dependency |

**Named divergence:** the shared-chassis-library framing implied by the
chapter's working title ("the FastAPI chassis") does not exist as a single
artifact — DRQ-082 names this explicitly: convention, not library. The
chapter's honesty is the point — a chassis chapter that claimed uniform
coverage across 8 independently-built services, or implied a shared package
that was never written, would be exactly the kind of silent drift this
ledger's R4 standard exists to catch.

**Verdict:** CLEAN — a real doc-vs-code drift (the pydantic-settings claim)
was found during this reconcile pass, named, corrected at its source
(`build-plan.md` §B.2/§C), and traced to an accepted DRQ (DRQ-083) rather
than quietly rewritten without a trail; the chassis chapter itself is
authored as a scorecard, not an inflated uniformity claim.

### Contracts & Service Registry: the schema-registry demo

**Source:** `_plans/decisions.md` DRQ-036 (r03) named the gap explicitly —
"a schema registry (Apicurio, Avro/Protobuf/JSONSchema) is deferred to
ch.28" — and `_plans/decisions.md` DRQ-033 (r03) rejected `confluent-kafka`
for the project's Kafka client, a constraint this chapter's registry client
choice has to honor too, not just the original consumer/producer seam.
`_plans/backmatter-track-plan.md`'s USER DECISION A/B-1 is the direct design
source: **(A) fastavro + aiokafka + Apicurio v3 REST** (pure-Python,
consistent with DRQ-033) was recommended and chosen over **(B)**
`confluent-kafka[avro]` (which would have pulled librdkafka back in,
contradicting DRQ-033 for the sake of one demo).

**What shipped:** `examples/09-schema-registry-demo/` — a producer/consumer
pair exchanging Avro-encoded messages through Kafka, with the schema itself
registered in and resolved from a live Apicurio v3 instance over its REST
API (no confluent-kafka, no librdkafka). Because fastavro has no built-in
Confluent-wire-format framing the way `confluent-kafka`'s `AvroSerializer`
does, the demo **hand-rolls the wire envelope**: `[1-byte magic][8-byte
big-endian global id][Avro binary payload]` (`struct ">BQ"`), encode and decode both
implemented in the example itself (DRQ-084) — a named
consequence of the pure-Python client choice, not an oversight.

**Round-trip and compatibility, verified live, not asserted:** a
Testcontainers-backed integration test spins up real Kafka + a real
Apicurio 3.3.3 instance and proves (1) a message encoded against a
registered schema round-trips byte-for-byte through the hand-rolled
envelope and back to the original record, and (2) Apicurio's own
compatibility rule enforcement is real, not a client-side illusion:
registering a **v2** schema (an optional field with a default — backward-
compatible) against the same subject **succeeds, HTTP 200**; registering a
**v3** schema (retyping an existing field — backward-incompatible) against
the same subject **fails, HTTP 400 `RuleViolationException`**. The track
plan's own risk note flagged that the Java sibling observed a 409→400
status drift across Apicurio versions for this exact kind of check — the
**actual observed status (400, not assumed)** against the pinned
`apicurio-registry:3.3.3` image is what's recorded here, not the status the
planner guessed before the image was pulled.

**Verdict:** CLEAN — the client-library choice honors a standing rejection
(DRQ-033) rather than quietly reintroducing the dependency it rejected, the
wire-envelope gap created by that choice is named and implemented rather
than hidden, and the compatibility-rule claim (accept-compatible,
reject-incompatible) is demonstrated against a live, pinned registry
instance with the actual HTTP status recorded, not inferred from Apicurio's
documentation.

### Additive posture: compose, CI, and the live JSON flows left untouched

**Source:** `_plans/backmatter-track-plan.md`'s "compose has NO Apicurio
yet" reconnaissance note and its CI-discipline note ("new gates = SEPARATE
additive workflows... never touch `code-ci.yml`/`contract-gate`/
`code-ci-ok`").

**What shipped:** Apicurio (`quay.io/apicurio/apicurio-registry:3.3.3`)
added to `compose.yaml` as a new `apicurio` service on `:8095`, and
`APICURIO_IMAGE_TAG=3.3.3` added to `.env.example` — both scoped,
by inspection, to `examples/09-schema-registry-demo/`'s own use; no existing
service's `order.placed`/`payment.captured`/`payment.declined`/
`shipment.dispatched`/`shipment.failed` hand-maintained JSON event contract
(DRQ-036 and its descendants through r07) references Apicurio, is validated
against a registered schema, or has its producer/consumer code touched in
any way (DRQ-085). CI gained a **separate** `.github/workflows/
schema-registry.yml` with its own summary job (Testcontainers-backed Kafka
+ Apicurio) and no `paths:` filter; `code-ci.yml`'s `contract-gate` and the
required `code-ci-ok` summary status are unmodified and remain the gate
every prior extraction's equivalence check still reports to (DRQ-086).
`demos/demo-schema-registry.sh` runs the round-trip + compatibility
scenario standalone, green.

**Verdict:** CLEAN — the registry's blast radius is exactly the one new
demo it was built to teach, verified by checking that no live event
contract's producer or consumer code changed, not merely by asserting the
new compose service is "additive" from its position in the file.

### The real per-service JSON drift ch.28 documents (not a replayed Java anecdote)

**Source:** `_plans/backmatter-track-plan.md`'s reconnaissance note: "Python's
real per-service drift ≠ Java's 'notification missing paymentMethod' — read
the actual order-service producer payload + payment/notification `schemas.py`
and tell Python's true story." This is a reconciliation finding in its own
right — a borrowed anecdote from the Java sibling would have been exactly
the kind of unexamined cross-project assumption R4 is built to catch.

**What was actually found, read from the live producer/consumer code rather
than assumed from the Java sibling's analogous chapter:** order-service's
`order.placed` outbox payload (DRQ-036/DRQ-078) carries the full frozen
contract (`orderId`, `customerId`, `customerEmail`, `totalCents`,
`confirmationMessage`, `placedAt`, plus the additive optional
`paymentMethod` field from DRQ-050) — every downstream consumer
(payment-service, the monolith's frozen `order_placed_consumer`) tolerates
unknown/absent fields by construction (the additive-field discipline
established at DRQ-050/DRQ-062 for exactly this reason), so there is no
analogous "a consumer silently drops a field it needs" drift instance to
report for this project's real event contracts. ch.28 names this plainly —
the project's hand-maintained-JSON contracts have, in practice, stayed
forward-compatible by discipline (every new field addition since r05 has
been additive-and-optional, DRQ-050/DRQ-062), not by registry enforcement —
which is itself the honest motivating case for ch.28's registry demo: a
registry makes that discipline *checkable*, where today it is only
*practiced*.

**Verdict:** CLEAN — the chapter's drift anecdote is independently
re-derived from this project's own producer/consumer code, not carried over
from the Java sibling's unrelated (and inapplicable) "notification missing
paymentMethod" story.

### Verdicts summary

CLEAN across every artifact in this section, **plus one real doc-vs-code
drift found and fixed during this reconcile pass**: the build-plan's
pydantic-settings claim for the chassis config mechanism, corrected in
place and traced to DRQ-083. Two USER DECISIONS from
`_plans/backmatter-track-plan.md` applied to this iteration's scope — A/B-1
(Avro client = fastavro+aiokafka+Apicurio-REST, DRQ-084) and A/B-3 (build
the runnable demo + its CI gate, not prose-only, DRQ-086/087) — both
resolved in favor of the planner's recommended option. The schema-registry
demo's compatibility claim (accept-compatible, reject-incompatible) was
verified live against a real, pinned Apicurio instance with the actual
observed HTTP status recorded (400), not assumed from the Java sibling's
different-version behavior (409). The additive posture (compose, CI, and
every live JSON event contract) was verified by inspection, not merely
asserted. No unexplained drift for ch.27/28.

---

## ch.29/31 — Deployment Patterns + CI/CD & Supply Chain (r09, Part 9 + Part 10, non-extraction)

### The deploy tree, and the config-model divergence caught during build

**Source:** `_plans/r09-build-plan.md`'s "Grounded reconnaissance" section
(the plan's own binding-facts recon of the 8 services' real ports, probes,
and config) and DRQ-083 (r08's config-mechanism correction: a frozen
`@dataclass Settings.from_env()`, not pydantic-settings).

**What shipped:** `deploy/k8s/` — a kustomize `base` (namespace `mea`,
`app-config.yaml` ConfigMap, `app-secret.yaml`, eight per-service
Deployment+Service manifests, `infra/` Postgres + Kafka StatefulSets) plus a
single `overlays/minikube` overlay (image retagging, `imagePullPolicy:
Never`, NodePort 30888 on the strangler-proxy edge only, the ch.30
Istio/observability seam left commented so the overlay renders clean now).
Probes are honored per-service rather than copied uniformly: `tcpSocket` for
`01-strangler-proxy` and `02-review-service` (the two services with no
`/health` route, per DRQ-082's chassis scorecard), `httpGet /health` for the
other six (DRQ-089). Both trees render with `kubectl kustomize` (23
resources each) and pass `kubeconform -strict` (23/23 Valid).

**The real config-model divergence, caught during the W1-a self-check, not
assumed from the plan's wording:** `_plans/r09-build-plan.md`'s own
"Approach" section described the ConfigMap as carrying "per-service
`*_DATABASE_URL`/schema" entries — read literally, that implies one
connection-string variable per service. Building `app-config.yaml` against
the actual services' `config.py`/`Settings.from_env()` modules (the same
source DRQ-083 corrected at r08) showed the real shape is simpler and
different: **one shared `DATABASE_URL`** (all eight services point at the
same Postgres instance and the same env var name), with schema selection
happening **in each service's own code** (SQLAlchemy `schema=` /
Django `search_path`), not via a per-service connection-string variable.
Building `app-config.yaml` to the plan's literal wording would have shipped
eight ConfigMap keys that no service actually reads. **Corrected in the
manifest itself** (one `DATABASE_URL` key, schema-per-service-in-code
documented in ch.29 and the ConfigMap's own comments), not shipped as
written and footnoted later.

**Why this is the same class of finding as DRQ-083, not a new kind of bug:**
r08's reconcile pass found a build-plan blurb asserting a config mechanism
(pydantic-settings) the code never adopted; this is the same
doc(-plan)-vs-code drift, one layer removed — a plan clause describing a
ConfigMap shape the as-built services' config modules don't support. Caught
the same way: by reading the actual `config.py` of each service before
writing the manifest, not by trusting the plan's prose.

**Verdict:** CLEAN — a real plan-vs-code divergence was found during build
(not after), corrected in the shipped manifest rather than carried forward,
and named here per R4 rather than silently fixed with no trail.

### The headless-render limit

**Source:** `_plans/r09-build-plan.md` §M's own named risk ("Renders-but-
wouldn't-apply").

**What's actually verified vs. what isn't:** `kubectl kustomize` (offline
render) and `kubeconform -strict` (offline schema validation) both passed
clean on `base` and `overlays/minikube`. `kubectl apply --dry-run=client`
is also offline and structural. None of these reach cluster admission —
defaults, webhooks, RBAC, PVC binding, and whether the manifests would
actually schedule and come up healthy all require a live apiserver, which
r09 does not have. ch.29 and `deploy/k8s/README.md` both state this limit
in the same terms, scoped to exactly what offline validation covers, rather
than implying the headless checks are equivalent to a live deploy. The live
minikube path is written and user-runnable (`deploy/k8s/scripts/`) but
deferred to ch.30/r10, not claimed as CI-verified here.

**Verdict:** CLEAN — the limit is named in the same chapter that could be
read as implying more, not left for a reader to discover the hard way.

### Supply-chain: the fixable-only result, told accurately

**Source:** `_plans/r09-build-plan.md` §M's "grype DB drift / point-in-time"
risk, and the A/B-4 user gate (resolved **B**, recorded as DRQ-088).

**What was actually found, not what the plan expected:** the plan's risk
section anticipated a *transient* High appearing after the evidence was
committed, mitigated by "pin/triage via a documented grype ignore... never
by silently lowering `fail-on`," and separately assumed (in its own
drafting) that a red gate on the UBI base layer could be cleared by
re-pinning to a newer, patched tag. Running the real scan surfaced a
different and harder fact: **both** scanned images — order-service (after)
and the frozen `00-monolith` (before) — came back with **35 High CVEs, 0
Critical, every one `fix-state: not-fixed`**, all in the shared UBI10
`python-314-minimal:10.2-1791928506` base layer, none in either image's
application dependencies. **Re-pinning was checked and found impossible**:
`skopeo` confirmed the pinned tag is already the newest `10.2-` build
published, and "not-fixed" means no vendor patch exists yet to re-pin onto
— the plan's re-pin assumption does not hold against this image, and ch.31
says so plainly rather than silently dropping the idea.

**The decision, and why it's not the same as lowering the bar:** the user
chose to **gate on fixable findings only** — `examples/10-supply-chain/
.grype.yaml` sets `ignore: fix-state: not-fixed`, consumed identically by
`demo.sh` and `.github/workflows/supply-chain.yml` (DRQ-094). This is
different from raising `fail-on` or dropping the check: every one of the 35
unfixable Highs is still visible — in grype's `ignoredMatches` field for
order-service's scan output, and in the monolith's full, unfiltered raw
report (which is non-gating per A/B-4=B anyway) — the gate just stops
blocking merges on CVEs no action in this repo can fix. With the ignore rule
applied, **order-service has 0 fixable Highs and PASSes for real**; the
monolith (non-gating) reports its findings including all 35. Both images
sharing the identical base-layer finding is itself evidence the result is a
base-image fact, not an order-service-specific regression.

**Named limitation, not silently dropped:** this result is point-in-time
(grype DB built 2026-10-16, per the plan's own drift risk); a future grype
DB update could reclassify a finding as fixed (tightening the gate, which is
fine) or a new High could appear outside the `not-fixed` ignore (also fine —
that's the gate doing its job). README + ch.31's verification footer state
this explicitly.

**Verdict:** CLEAN — the actual (harder) finding is reported instead of the
plan's anticipated (milder) one, the re-pin assumption's failure is named
rather than quietly abandoned, and the fixable-only decision is shown to
still surface the full 35, not hide them.

### Two new additive gates, one explicit correction of the Java sibling

**Source:** `_plans/r09-build-plan.md`'s CI-discipline note (citing
DRQ-086's precedent) and its explicit call-out that "the Java `supply-
chain.yml` violates both rules (has `paths:`, no `*-ok`)."

**What shipped:** `deploy-manifests.yml` (`changes` → `render` → `deploy-
manifests-ok`) and `supply-chain.yml` (`changes` → `sbom-scan` → `supply-
chain-ok`), both with no `paths:` filter and both ending in an `if: always()`
summary job — the same shape as `schema-registry.yml` (DRQ-086) and every
`*-equivalence-gate` before it. `supply-chain.yml` **explicitly corrects**
the Java sibling's shape, which has a `paths:` filter (risking a wedged
required check on unrelated PRs) and no `*-ok` summary at all (DRQ-092).
`code-ci.yml`, `contract-gate`, `code-ci-ok`, `pages.yml`, and
`schema-registry.yml` are confirmed untouched.

**Verdict:** CLEAN — the one-new-additive-gate-per-seam pattern is extended
twice more without exception, and the Java-sibling correction is named as a
correction, not a silent divergence.

### Verdicts summary

CLEAN across every artifact in this section, **plus one plan-vs-code
divergence found and fixed during build** (the ConfigMap's per-service-
DATABASE_URL wording vs. the real single-shared-`DATABASE_URL`-plus-
schema-in-code shape, corrected in the shipped manifest and named here, the
same class of finding as DRQ-083's config-mechanism correction at r08) and
**one finding harder than the plan anticipated** (35 not-fixed, un-re-pinnable
base-layer Highs shared by both scanned images, resolved by the user's
gate-on-fixable-only decision, DRQ-094, rather than the plan's own
re-pin-to-a-patched-tag assumption, which did not hold). The track-plan A/B-4
gate (order-service only vs. order-service + the frozen monolith) was
resolved by the user in favor of **B**, recorded as DRQ-088. The
headless-render limit is named in the same chapter it could be mistaken as
exceeding. No unexplained drift for ch.29/31.

**Forward reference:** the next sub-iteration, **r10**, covers **ch.30
(Mesh, Observability & Distributed Tracing — Istio, Kiali, OpenTelemetry +
the LGTM stack, live on minikube, user-run, per track-plan USER DECISION
A/B-2 still open at r09 close) and ch.32 (The Pattern Language, Revisited —
the final project)**, per `_plans/backmatter-track-plan.md`'s grouping.

## ch.30/32 — Mesh, Observability & Tracing + The Pattern Language, Revisited (r10, Part 9 + Part 10, non-extraction)

**What shipped (headless, merged):** ch.30 (4,395 words, 2 figures) activates the
ch.29 Istio seam — `deploy/k8s/istio/` (PeerAuthentication STRICT mesh-wide + a
PERMISSIVE edge exception scoped to strangler-proxy, Telemetry → the `otel`
provider, and an `IstioOperator` applied via `istioctl install -f`, kept out of
every kustomization as a cluster-only object) and `deploy/k8s/observability/`
(one `grafana/otel-lgtm:0.36.0` all-in-one, unmeshed, with an `otelcol` config
that adds a Kubernetes-pod-SD scrape of the Envoy sidecars' `:15090` stats).
The minikube overlay activates sidecar injection as a pod-template **label**
(not an annotation — the datamesh webhook-objectSelector gotcha) on exactly the
8 app Deployments; postgres, kafka, and lgtm stay unmeshed. OpenTelemetry is
added additively to exactly 3 services (strangler-proxy, order-service,
inventory-service — the synchronous hero-trace path, DRQ-096=A) via
`opentelemetry-distro`, no-op by default (`OTEL_SDK_DISABLED=true`) and active
only through the k8s ConfigMap. ch.32 (5,326 words, 2 figures) re-walks the
whole pattern language as the book's final project and reconciles build-plan §C.
A new headless `mesh-manifests.yml` gate validates the istio + observability
overlays with `kubeconform -strict -ignore-missing-schemas`.

**Decisions:** A/B-2 resolved **A** (ch.30 verified by a user-run live capture,
DRQ-095); OTel trio **A** (DRQ-096, so the conditional outbox-traceparent work
DRQ-103 never triggered); label injection (DRQ-097); STRICT + edge-PERMISSIVE
mTLS (DRQ-098); the LGTM overlay shape (DRQ-099); r10 pins (DRQ-100 — Istio/
istioctl 1.31.2, opentelemetry-distro 0.66b1, exporter-otlp-proto-grpc 1.45.0,
reusing grafana/otel-lgtm 0.36.0 / k8s v1.37.1 / kubeconform v0.8.0); the mesh
gate (DRQ-101); §C reconciliation + final-project framing (DRQ-102).

**Drift found and corrected (CLEAN after fix):**
1. *Instrumentor version skew (named, not worked around).* `opentelemetry-
   instrumentation-sqlalchemy==0.66b1` requires `sqlalchemy<2.1.0`, but
   order/inventory pin `sqlalchemy[asyncio]==2.1.4`; the ORM instrumentor
   declines to patch. sqlalchemy stays at 2.1.4 (prefer-newer-versions); DB
   spans come from the compatible `asyncpg` instrumentor. Named in ch.30, not
   presented as full coverage.
2. *The activated seam broke the r09 `deploy-manifests` gate.* Adding the Istio
   CRs to the minikube overlay made that gate's `kubeconform -strict` (no
   `-ignore-missing-schemas`) error on the 3 schemaless CRs. Caught on live CI
   on PR #10, fixed by giving the overlay render `-ignore-missing-schemas` (base
   stays strict). This is the render-vs-cluster gap ch.29/30 describe, surfacing
   as a real cross-gate interaction rather than a hypothetical.

**Terminology + driver sweeps:** "capstone" → "final project" across `_plans`
(and the `lgtm-professional-voice` skill's preferred replacement updated from the
interim "complete project"); the podman minikube-driver opt-in removed from
`deploy/k8s` so docker + containerd is the only documented driver (`CONTAINER_
ENGINE=podman` remains a separate image-build knob).

**Live verification — DEFERRED (user-run, post-merge).** The maintainer chose to
merge the headless-complete tree and run the live minikube+Istio+LGTM capture
separately. ch.30's footer therefore reads `headless-verified; live mesh capture
DEFERRED (user-run, scheduled post-merge)` with three named, not-yet-present
evidence files (`deploy/k8s/observability/evidence/ch30-{hero-trace.json,
istioctl-mtls.txt,metrics.txt}`) produced by `capture-ch30-evidence.sh`. Every
trace ID, span count, mTLS line, and metric value is left for the captured
evidence; none is drawn from an uncaptured file. When the capture lands, the
evidence is committed and the footer flips to `verified-live (user-run)`.

**Verdict:** CLEAN on the headless tree (10/10 adversarial-validation criteria
met; all required CI gates green on PR #10 after the deploy-manifests fix). The
one outstanding item is ch.30's live-cluster evidence, named and deferred to the
maintainer's separate run.

**Forward reference:** no further back-matter chapters remain. Future work
(not A/B gates): front-matter ch.00-13, the 3 decks (101/201/201-fastapi), and
ch.33 (OpenShift/CRC appendix); plus landing ch.30's live evidence when the
maintainer's run completes.
