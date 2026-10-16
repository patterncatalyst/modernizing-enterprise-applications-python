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

*Per `build-plan.md` §J, the Review extraction (ch.15, extraction 1 of 6) is
scheduled for r02 in this project's renumbered cadence. The next section
appended to this file should be headed `ch.15 — Review (r02, extraction 1 of
6)`, following the per-extraction-reconcile shape above.*
