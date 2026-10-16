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

*Per `build-plan.md` §J, the Order + GraphQL Gateway extraction (ch.26,
extraction 6 of 6) is scheduled for r07 in this project's renumbered
cadence — the **last and hardest extraction**: the core aggregate, extracted
last, decommissions the monolith (the strangler fig completes) and
introduces the Strawberry GraphQL gateway as the CQRS read-aggregation
surface over the now-fully-decomposed services. r07 also authors **ch.21
(Event Sourcing & CQRS)**, deferred from r05 (DRQ-057) specifically because
the order/gateway extraction is the first place a CQRS read model is
load-bearing (per the §C matrix) rather than merely illustrative. The next
section appended to this file should be headed `ch.21/26 — Order + GraphQL
Gateway (r07, extraction 6 of 6)`, following the per-extraction-reconcile
shape above.*
