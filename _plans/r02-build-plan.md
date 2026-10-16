# r02 Build Plan — Strangler Proxy (ch.14) + Review Extraction (ch.15)

**Branch:** `feat/r02-strangler-review` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval before execution.

## Approach

- **Strangler proxy** = a thin **Starlette ASGI app + `httpx.AsyncClient`** streaming reverse-proxy on **:8888**. One catch-all route forwards method/path/query/headers/body verbatim and returns upstream status/body/headers verbatim (never raising on 4xx/5xx — the httpx analogue of Camel's `bridgeEndpoint=true&throwExceptionOnFailure=false`). Content-based routing on the **full** path prefix `/api/reviews`, env flags, monolith fallback. *Rejected:* a proxy library (less header/stream control, hides the taught pattern); FastAPI (pydantic/OpenAPI dead weight for pass-through).
- **Review Phase-A bridge (DRQ-009)** = **thin FastAPI reusing the monolith's Django ORM** (uv path dep on `../00-monolith`, `django.setup()` in lifespan against the same shared Postgres). Byte-identical behavior → fast gate pass; honest analogue of the Java Spring-compat lift. **Phase B** refactors to idiomatic FastAPI + Pydantic v2 + async SQLAlchemy/asyncpg, with measured before/after as the ch.15 payoff. *Rejected for Phase A:* direct SQLAlchemy re-map (second mapping of shared tables risks contract drift; it's the Phase-B tool).
- **Schema posture** = **keep Review on the SHARED schema** in r02; defer DB ownership to ch.18/19 (as the Java sibling did). The shared schema is also what makes the cutover's false-positive routing bug teachable.
- **Ports:** monolith :8000, proxy :8888, review-service :8001.

## DECISION REQUIRED AT GATE — Review auth contract
The Java contract asserts 401 unauthenticated / 201 authenticated writes (smell #6). The **actual Python r01 monolith review endpoint enforces NO auth** (DRQ-025 wired none). The equivalence suite must be green against both monolith (flag OFF) and service (flag ON), so it can only assert shared behavior.
- **Option A (recommended):** match the monolith's current **unauthenticated** contract (200 reads / 201 writes / 400 validation). No monolith edit, no re-baseline; record the divergence from Java as a DRQ; ch.15 still teaches independence.
- **Option B (faithful to Java):** add DRF BasicAuth + IsAuthenticated to the review write endpoint in **both** monolith and service, re-capture the r01 baseline, assert 401/201 (realizes smell #6). Higher touch (edits the monolith, re-baselines r01).
Plan written for Option A; Option B adds only a scoped monolith auth edit + baseline recapture + 2 extra Review requests.

## Lanes / dependency chain
monolith review endpoints (done r01) → [PROXY ∥ REVIEW-SVC] → NEWMAN-CUTOVER → CI → CHAPTERS → LEDGERS.

### PROXY — `examples/01-strangler-proxy/`
pyproject+uv.lock (starlette 1.8.0, uvicorn[standard] 0.54.0, httpx 0.28.1; dev pytest/pytest-asyncio/ruff) · `app/config.py` (env: port 8888, `STRANGLER_REVIEW_ENABLED` default false, monolith/review base URLs; operator-configured targets only) · `app/main.py` (Starlette factory, shared httpx client in lifespan, catch-all route, **full-path** `/api/reviews` match, verbatim pass-through, real 5xx on upstream down) · `tests/test_routing.py` (two in-process stub backends; flag OFF/ON routing; pass-through fidelity; upstream-down→5xx) · README · CUTOVER.md (flag-OFF/ON/flip-back/negative-check evidence) · Containerfile (UBI10 python-314-minimal).

### REVIEW-SVC — `examples/02-review-service/`
pyproject+uv.lock (Phase A: fastapi 0.143.2, uvicorn 0.54.0, path dep `../00-monolith` → django 5.2.18/DRF/psycopg; Phase B: sqlalchemy[asyncio] 2.1.4, asyncpg 0.32.0, pydantic 2.14.1) · `settings_bridge.py` (Phase A Django settings) · `main.py` (FastAPI, `django.setup()` lifespan, `redirect_slashes=False`) · `routes.py` (GET /api/reviews[?sku], GET /api/reviews/{id}, POST→201+Location; no trailing slash) · `schemas.py` (Pydantic v2 camelCase aliases, byte-match serializers) · `repository.py` (Phase A Django ORM; Phase B async SQLAlchemy) · `errors.py` (uniform {error,message,timestamp}: 404 NOT_FOUND, 400 VALIDATION_FAILED) · `db.py` (Phase B async engine, no own migrations) · tests · README (Phase-A bridge stated plainly) · MIGRATION.md (A→B table + real before/after: CPython startup, RSS, latency) · AGENTS/CLAUDE/Containerfile.

### NEWMAN-CUTOVER — `tooling/newman/` (single-writer)
Add **"Review Context Contract"** folder (Option A: 200 list?sku / 200 get / 201 POST+Location / 400 invalid-rating), all `{{baseUrl}}`; DO NOT edit existing folders · `proxy.postman_environment.json` (baseUrl :8888); keep local (:8000) · README + GOLDEN-BASELINE updated (OFF green / ON green / flip-back / negative-check).

### CI — `.github/workflows/code-ci.yml`
Extend `changes` filter (+01-strangler-proxy, +02-review-service) · add `review-equivalence-gate` (Postgres service + monolith :8000 + review :8001 + proxy :8888 with flag ON; Newman through :8888; dump 3 logs on fail; stop all in always()) · add it to `code-ci-ok` needs; keep monolith gate.

### CHAPTERS — `_docs/14-*.md`, `_docs/15-*.md`
**Port `scripts/generate_diagram.py`** (missing from this repo — copy from lgtm-diagram-generator) + seed `assets/diagrams/` · generate ~3–4 paired SVG+Excalidraw figures (strangler 3-steps; proxy routing with flag; cutover timeline; Phase-A vs Phase-B bridge) · rewrite ch.14 (~400+ lines) and ch.15 (~600 lines), re-authored for Python, cite real MIGRATION/CUTOVER numbers · run lgtm-professional-voice + lgtm-idiomatic-review scans clean; jekyll build clean.

### LEDGERS — `_plans/`
Append r02 DRQs (proxy=Starlette+httpx; Review Phase-A bridge + Phase-B plan; shared-schema posture; **auth-contract decision**; ports; new pins + version-matrix rows) · **correct build-plan §E row 1 "Own schema from day one" → shared-schema-initially (deferred to ch.18/19)** · update §E rows 0/1 status → done, §J r02 scope · add r02 reconciliation section.

## Acceptance criteria (per lane)
- **PROXY:** pytest green; flag OFF→all paths to monolith; ON→/api/reviews* to :8001, else :8000; pass-through fidelity; upstream-down→real 5xx; ruff clean.
- **REVIEW-SVC:** pytest green; endpoints byte-match monolith contract (camelCase, no trailing slash, 201+Location, 400/404 uniform error); README states Phase-A bridge; MIGRATION.md has real numbers; ruff clean.
- **NEWMAN-CUTOVER:** full suite green through :8888 with flag OFF **and** ON (collection byte-identical across runs); flip-back restores monolith routing; review-service-down negative check goes RED then recovers.
- **CI:** review-equivalence-gate green (3 services + proxy flag ON); wired into changes + code-ci-ok; monolith gate still green.
- **CHAPTERS:** ch.14/15 replace stubs at ≥ site depth with ≥3–4 figures; jekyll clean; voice + idiomatic scans clean.
- **LEDGERS:** DRQs appended; §E rows flipped + schema row corrected; §J updated; r02 reconciliation present.

## Risks (+ Phase-3 detection)
- Two processes on one shared schema (pool/txn/stale) → flag-ON Newman + CI exercise both live.
- **False-positive routing bug** (shared schema masks a wrong prefix) → the **negative check** (service down, flag ON → Review folder MUST go RED) + full-path unit test.
- Header/stream fidelity (Host/Content-Length/Location, buffering) → pass-through unit test + Scenario folders assert Location + exact error JSON.
- Sync parity 201 vs 202 → Review-folder 201 + immediate get-by-id.
- Flag-flip reversibility (flag cached in client/route) → documented flip-back run + both-states unit test.
- Phase-A Django bridge (django.setup() settings/app resolution; path-dep drift) → lifespan-boot test + `uv sync --locked`.
- Pydantic v2 camelCase/`redirect_slashes` regressions → field-name + no-trailing-slash assertions.
- (CDC read-after-write races are NOT this iteration — ch.18/19.)

## New dependency pins (survey 2026-10-15; executor re-verifies at uv lock)
starlette 1.8.0 · uvicorn[standard] 0.54.0 · httpx 0.28.1 · fastapi 0.143.2 · sqlalchemy[asyncio] 2.1.4 · asyncpg 0.32.0 · pydantic 2.14.1 · pytest-asyncio 1.4.0. (Reused: django 5.2.18, DRF 3.18.3, psycopg 3.3.6, pytest 9.1.1, ruff 0.17.1, uv 0.13.1, Postgres 18.6-alpine, Newman 6.2.2, UBI10 python-314-minimal.) **Double-check `starlette 1.8.0`** resolves with fastapi 0.143.2 at lock time (historically 0.x); fall back to the fastapi-pinned Starlette range on conflict.
