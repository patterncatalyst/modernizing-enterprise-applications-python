# r01 "Walking Skeleton" — Build Plan

**Project:** modernizing-enterprise-applications-python
**Branch:** `docs/r01-walking-skeleton`
**Mirror target:** `~/Dev/modernizing-enterprise-applications` (Java sibling)
**Phase-1 planner:** Opus (lgtm-relay). Status: awaiting user approval before execution.

---

## Approach

Build the **empty book frame + the running "before" system + the gates that prove it**, as
six parallel lanes mirroring the Java project's directory layout 1:1 so the two books are
navigable side-by-side. Chapters are **stubs** (front-matter + "coming in rNN"); the Django
monolith, the Newman baseline, the compose stack, and CI **must run/build green**.

Stack substitution (mechanical, consistent): Spring Boot → **Django 5.2 LTS + DRF**;
Quarkus + Camel → **FastAPI** (services are r02+, not r01); Maven/JDK → **uv / Python 3.14**;
JUnit/Testcontainers → **pytest / pytest-django**. Site shell, `_plans/` ledger format, Newman
collection shape, compose topology, and the CI summary-job gate are ported near-verbatim
(language-agnostic) and re-skinned for the Python narrative.

Baked-in decisions:
- Monolith captured at its **pristine "before" state** — all six apps live, all six smells live,
  nothing extracted (mirror the Java monolith's *original* schema/seed/smell intent, NOT its
  frozen decommissioned `main` end-state).
- Shared single Postgres schema across all six Django apps, cross-app FKs — the coupling *is* the smell.
- Scenario 4 (Shipping-Failure) is meaningful at r01: the synchronous checkout wraps everything in
  one `transaction.atomic()`, so a `SHIP-FAIL` sentinel rolls the whole checkout back (stock
  net-zero) — sets up the ACID→ACD narrative from day one.

**Rejected:** mirror Java `main` (frozen) state; build FastAPI services/strangler now; uv workspace
root; per-app separate schema now; author chapter prose.

---

## Steps (parallel lanes)

LEDGERS and SITE start immediately, fully parallel. MONOLITH → NEWMAN → CI is the one real
dependency chain. INFRA is independent but the monolith run + Newman green-check consume it.

### Lane SITE — Jekyll shell
- **S-SITE-1** Site chrome: `_config.yml`, `Gemfile`, `_layouts/{default,tutorial,part_index,plan}.html`, `_includes/*`, `assets/css/site.css`, `assets/js/codetabs.js`, `index.html`. Port from Java, re-skin for Django/FastAPI. *(no deps)*
- **S-SITE-2** Part stubs `_parts/00..11-*.md` (12 files). *(deps S-SITE-1)*
- **S-SITE-3** Chapter stubs `_docs/00..33-*.md` (34 files), front-matter + "Coming in rNN" one-liner. *(deps S-SITE-1)*

### Lane LEDGERS — `_plans/`
- **S-LEDG-1** `build-plan.md` (§A approach, §B 12-part/34-ch list, §C pattern matrix re-homed to Python, §D monolith, §E six-extraction Django→FastAPI roadmap, §F 7-phase ADLC, §J r01–r10 iterations). *(no deps)*
- **S-LEDG-2** `decisions.md` (DRQ format + version matrix; seed DRQs — version pins, two-phase Django→FastAPI policy, shared vs owned schema, saga reuse decision, equivalence gating, accent/emoji, monolith port). *(no deps)*
- **S-LEDG-3** `reconciliation.md` (template + r01 reuse section). *(no deps)*

### Lane MONOLITH — `examples/00-monolith/` (Django 5.2 + DRF)
- **S-MONO-1** Project scaffold + toolchain: `pyproject.toml` (uv), `uv.lock`, `manage.py`, `config/` (settings/urls/wsgi/asgi), pytest/ruff config, `.env.example`, `AGENTS.md`, README. *(no deps to start)*
- **S-MONO-2** Six apps (order/inventory/payment/shipping/notification/review) + shared schema + cross-app FKs + checkout REST flow + deterministic failure injection (DECLINE→402, over-order→409, SHIP-FAIL→rollback) + seed data + the **six smells tagged `# SMELL[ch.NN]:`** + `SMELLS.md`. *(deps S-MONO-1)*
- **S-MONO-3** Dockerfile (UBI, non-root), smoke tests (all six contexts), run docs. *(deps S-MONO-2)*

### Lane NEWMAN — `tooling/newman/`
- **S-NEWM-1** `mea.postman_collection.json` (Smoke + 4 scenarios at the synchronous-monolith baseline) + `local.postman_environment.json` (`baseUrl=http://localhost:8000`) + README + `GOLDEN-BASELINE.md`; green against the running monolith. *(deps S-MONO-2 + INFRA Postgres)*

### Lane INFRA — compose stack
- **S-INFRA-1** `compose.yaml` (Postgres + Kafka KRaft + grafana/otel-lgtm, podman/docker-portable), `infra/db/init`, `infra/grafana`, `infra/otelcol`, `.env.example` (pinned tags). No Debezium/Apicurio yet (scope). *(no deps)*
- **S-INFRA-2** `scripts/stack-up.sh`, `stack-down.sh`, db helper. *(deps S-INFRA-1)*

### Lane CI — `.github/workflows/`
- **S-CI-1** `pages.yml` (Ruby 3.3, build any branch, deploy only on main). *(deps SITE)*
- **S-CI-2** `code-ci.yml` summary-job pattern: `changes` → `monolith-equivalence-gate` (Postgres service, uv sync, migrate+seed, gunicorn :8000, run Newman) → `code-ci-ok` (always reports). No `paths:` on `on:`. *(deps NEWMAN + MONOLITH + INFRA)*

### Lane DELIVERY
- **S-DELIV-1** Verify all acceptance criteria, commit per-lane (Conventional Commits, no attribution trailers), open PR for squash-merge. **Requires explicit user go-ahead before push.**

---

## Acceptance criteria (per lane)

- **SITE** — `jekyll build` exits 0; `_site/` has 34 chapter + 12 part pages; home card grid of 12 Part cards; accent `#3d7a4e` in compiled CSS; stubs are front-matter + one-liner only.
- **LEDGERS** — build-plan has §A/§B/§C/§D/§E/§F/§J; decisions seeds the named DRQs + version matrix; reconciliation has template + r01 section; `plans` collection `output:false` (no `/plans/*` rendered).
- **MONOLITH** — `migrate && seed && check` succeed; `pytest` green (six-context smoke); `ruff check` clean; `grep 'SMELL\[ch\.'` finds all six; all `/api/*` surfaces + four failure paths behave; Docker image builds + runs non-root.
- **NEWMAN** — `newman run` passes Smoke + 4 scenarios (0 failures); every request uses `{{baseUrl}}`; GOLDEN-BASELINE documented.
- **INFRA** — `docker compose config` + `podman compose config` validate; stack-up reaches healthy (Kafka KRaft no cluster-ID mismatch); stack-down tears down; no `latest` tags.
- **CI** — `pages.yml` build green on branch; `code-ci.yml` gate green on a code change; on a **docs-only** change the heavy job skips and `code-ci-ok` still reports success; a documented red-then-green proves the gate gates.

---

## Risks (and Phase-3 detection)

- **Django 5.x × Python 3.14** — 3.14 support landed in a Django 5.2 patch (~5.2.7+) / fully in 6.0. Detect via `manage.py check` + pytest on 3.14 in CI; escalate DRQ (pin ≥5.2.7, raise to 6.0, or drop to 3.13).
- **JSON field-name contract (camelCase vs snake_case)** — DRF defaults snake_case; ported collection may assert camelCase. Detect via Newman green-check; record the chosen convention as a DRQ.
- **Scenario 4 semantics** — SHIP-FAIL must roll back the whole `atomic()` (net-zero stock); Newman asserts net-zero.
- **Version drift / unpinned images** — grep for `latest`/unpinned; CI re-resolves `uv.lock`.
- **Kafka KRaft health** — cluster-ID mismatch on reused volume; stack-up health-wait + `stack-down -v` recovery; Kafka is off the r01 critical path (monolith needs only Postgres).
- **Summary-job misconfig** — a `paths:` filter or wrong required-check name blocks docs-only PRs; verify with a docs-only run.
- **UBI 3.14 image availability** — verify tag via `skopeo list-tags`; documented fallback `ubi9/python-314`.
- **Wrong monolith state** — ensure six live apps/smells, not six 404s.
- **Cross-lane chapter-list divergence** — site stubs (34) must match build-plan §B.2.

---

## Suggested version pins (surveyed 2026-10-15; pin exactly; executor re-verifies image tags with skopeo)

- Python 3.14; **Django 5.2.18** (LTS; verify the 5.2 patch declaring 3.14 support); **djangorestframework 3.18.3**; **psycopg[binary] 3.3.6**; **gunicorn 26.2.0**; **pytest 9.1.1** + **pytest-django 4.14.0**; **ruff 0.17.1**; **uv 0.13.1**; drf-spectacular (survey current).
- Images (reuse Java DRQ-077 pins, re-verify): Postgres `18.6-alpine`; Kafka `apache/kafka:4.3.1` (JVM); `grafana/otel-lgtm:0.36.0`; UBI `ubi10/python-314-minimal` (exact tag via skopeo; fallback `ubi9/python-314`).
- Newman 6.2.2 (Node 20/22 LTS in CI); Jekyll `~> 4.3` + plugins, Ruby 3.3 in pages.yml.

---

## Open decisions for the user (DRQ-flagged)

1. **Accent + emoji** — keep the Java sibling's migration-green `#3d7a4e` + 🏗️ (reads as a matched set) or give the Python book a distinct accent?
2. **JSON field naming** — match the Java camelCase contract (collection ports with minimal edits) or go snake_case idiomatic Python (fork the collection)?
3. **Django/Python version** — Django 5.2.x on Python 3.14 (verify patch) vs raise to Django 6.0 vs drop to Python 3.13.
4. **Compose engine primary** — docker-primary/podman-compatible (Java landed docker at DRQ-077) or podman-primary.
5. **Monolith front-door port** — `:8000` (Python-idiomatic; Newman `local` env matches).
