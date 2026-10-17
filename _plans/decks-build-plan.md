# Decks Build Plan — Modernizing Enterprise Applications (Python)

**Phase-1 plan (lgtm-relay / lgtm-presentation), user-gated + corrected.** Three
Red Hat-branded decks (101 / 201 / 201-fastapi), re-authored FastAPI-native from
the AUTHORED chapters `_docs/14`–`_docs/33`. Front-matter ch.00–13 are STUBS —
source from authored chapters 14–33 + `_plans/` + the Notion PRD, never the stubs.
Structure/arc mirror the Java sibling `~/Dev/modernizing-enterprise-applications/presentation/` (re-author, never copy).

## USER DECISIONS (resolved)
- **Depth split (DRQ-115) = A:** 201 = patterns (concept + just-enough code); **201-fastapi** = the deep async/code idioms (SQLAlchemy 2.0/asyncpg, Pydantic v2, aiokafka + outbox relay, grpc.aio, chassis-as-convention, OTel).
- **Diagrams (DRQ-114) = REUSE:** convert the existing house `assets/diagrams/*.svg` to PNG per deck (cairosvg); author no new per-deck diagrams. ("We typically always reuse our diagrams from the site in the pptx.")
- **Format = `.pptx` 16:9 via pptxgenjs** (lgtm-presentation skill + Java precedent). **NO `.docx` companion — we have never produced a docx; it is not part of this or any deck round.**
- **Slide-count discipline (user standard): each deck's MAIN body ~50 slides MAX; push all extra/reference material into APPENDICES.** This caps 201 (the planner's 60–68 must become ≤~50 main + appendices). 101 and 201-fastapi already fit.

## Binding conventions (restate in every executor prompt — subagents don't inherit skills)
From **lgtm-presentation**: Red Hat Display/Text/Mono fonts, accent red `#EE0000`, 16:9; output is a real `.pptx` from `node deck.js` + bundled `deck-helpers.js`; Red Hat logo on EVERY slide; thick speaker notes on EVERY slide (**notesCount == slideCount**); cross-reference by concept never slide number; reference-heavy material → appendix; versioning `<name>-rNN.x.pptx`; QA = `node deck.js` → `soffice --headless --convert-to pdf` → `pdftoppm` eyeball.
From **lgtm-professional-voice**: peer-to-peer engineer register; **0 ban-tier** on slide text AND speaker notes; no confessional "honest/for honesty" register; **"final project" never "capstone".**
**Advantage-framing (binding):** every deck sells the advantages of moving + the value, not just mechanics; in every before/after, **lead the new thing on the left** (FastAPI/async/owned-data leads; Django/shared/monolith follows).

## Location + format
- `presentation/modernizing-101/`, `presentation/modernizing-201/`, `presentation/modernizing-201-fastapi/` (singular `presentation/`, already in `_config.yml` exclude). Each dir: `deck.js` (authored), `deck-helpers.js` (bundled copy), `assets/` (bundled cover/divider/logo), `png/` (figures for this deck), `package.json`, built `Modernizing-*-r1.0.pptx` committed in-dir; `.gitignore` covers `node_modules/`.
- OUT: `Modernizing_101-r1.0.pptx`, `Modernizing-201-r1.0.pptx`, `Modernizing-201-FastAPI-r1.0.pptx`. REV `r1.0`.

## The three decks
### 101 — "Django to FastAPI, one seam at a time" (~22–24 slides)
Audience: architects/leads/decision-makers + engineers new to modernization. The case for moving + the strangler journey at altitude; diagram-forward, advantage-framed, no deep code. Arc A (Why & How) / B (The Migration) / C (Operating & Reflection). Figures: strangler-four-moves, strangler-proxy-routing, strangler-cutover-timeline, shared-data-vs-owned-data, choreography-vs-orchestration-contrast, rest-grpc-graphql-protocol-fit, mesh-mtls-topology, mesh-hero-trace-waterfall, supply-chain-gate-pipeline, final-monolith-free-topology, pattern-language-map, book-pattern-scorecard.

### 201 — "The patterns" (MAIN ≤~50 slides + appendices)
Audience: engineers/architects implementing. The full technical pattern set across all parts; just-enough code (the async mechanics live in 201-fastapi). **Keep the main body to ~50; move the deeper per-pattern variants, the full figure set, and the OpenShift/CRC appendix material into APPENDICES ("keep open in another window").** Sections (condensed): Why Modernize; the ADLC + equivalence gate; the reference monolith + smells; finding the seams (DDD); the strangler fig (proxy/ACL/event-driven); data across the seam (shared→owned/CDC/outbox/CQRS/ACID→ACD); coordinating (choreographed+orchestrated sagas, resilience, idempotent compensation); communication/contracts/chassis (REST/gRPC/GraphQL, registry); operating & delivering (deploy/mesh/observability/CI-CD/supply-chain); the pattern language revisited. **Appendices:** OpenShift/CRC parity (openshift-crc-topology, openshift-image-delivery, openshift-mesh-mtls-edge); extended per-pattern figures/code that overflow the ~50 main. Reuse the full `assets/diagrams/*` set mapped per section.

### 201-fastapi — "The FastAPI deep dive" (~40–46 slides, MAIN ≤~50)
Audience: Python engineers. The async stack underneath the patterns; code-deepest. Sections: the async foundation (async SQLAlchemy 2.0/asyncpg, session/unit-of-work, outbox write-in-transaction); Pydantic v2 at the edges (models/settings/validation, ACL translation); messaging the async way (aiokafka producer/consumer, the outbox relay as an asyncio task, idempotent dedupe, grpc.aio ACL, Avro/registry envelope); the chassis as convention + OTel (config/logging/health/errors/resilience as convention, DI wiring, opentelemetry-distro zero-code + manual spans → LGTM); together (one request's full async path through the orchestrated saga, CQRS async, crash-resume); appendix (packaging uv/UBI10/Containerfile, testing pytest+Testcontainers+Newman). Code slides from real `examples/` source.

## Build waves (single-writer per disjoint deck dir)
- **W0 scaffold (1 agent):** create the 3 dirs; copy deck-helpers.js + assets + deck template + package.json; resolve pptxgenjs; convert each deck's figure subset `assets/diagrams/*.svg → presentation/<deck>/png/*.png` (cairosvg, ~1400px). Gate: `node deck.js` emits a 1-slide pptx; all mapped PNGs exist.
- **W1 outline (1 agent, or 3):** grow each `deck.js` to full skeleton (cover/dividers/titled stubs + figure/code placeholders + speaker-note placeholders) at the target counts, **enforcing the ≤~50-main + appendix discipline (esp. 201)**. **USER GATE on the outlines** before prose.
- **W2 slide construction (3 parallel, one per deck dir):** fill advantage-framed bullets (lead-new-thing-left), author code slides from real `examples/`, embed diagram slides, thick speaker notes on every slide. Each prompt restates the binding conventions.
- **W3 Opus brand/voice/QA (1, over all 3):** professional-voice 0 ban-tier on slides+notes; 0 "capstone"; advantage-framing + lead-left present; build each deck; soffice→PDF→pdftoppm eyeball; notesCount==slideCount; counts within band; logo on every slide.

## Acceptance (checkable)
- 3 `node deck.js` builds succeed; each emits its `.pptx`. Counts: 101 22–26; 201 MAIN ≤~50 (+appendices); 201-fastapi 38–48. notesCount==slideCount each. Logo every slide. Figures reused from `assets/diagrams/` (PNG), resolve in-deck. Code from real `examples/`. Voice 0 ban-tier (slides+notes); **0 "capstone"**; **0 ".docx"**. Advantage-framing + lead-new-thing-left present. FastAPI-native (grep clean of quarkus/camel/spring/maven/jdk except where naming the Java sibling). Each renders to PDF with no overflow/wrap defects.

## DRQ allocations (continue from DRQ-111)
- DRQ-112 location `presentation/modernizing-{101,201,201-fastapi}/` (confirmed).
- DRQ-113 format `.pptx` via pptxgenjs; **no .docx ever** (confirmed; corrects the planner's "defer docx").
- DRQ-114 diagrams = reuse site figures → PNG (confirmed).
- DRQ-115 depth split = A (confirmed).
- DRQ-117 slide discipline = **~50 main max + appendices for overflow** (user standard; caps 201).

## Risks
- Java residue (build-plan §B.1 nouns, `27-quarkus-microprofile-chassis.md` filename) → source from chapter CONTENT not filenames; grep acceptance.
- 201 bloat > 50 main → W1 outline is the count checkpoint; overflow → appendices.
- 201 vs 201-fastapi overlap → the A split; W1 review catches it.
- Toolchain (pptxgenjs/cairosvg/soffice) offline → W0 verifies before authoring.
- Parallel writers → single-writer per disjoint deck dir.
