// deck.js — "Modernizing Enterprise Applications (Python)" — 201-FastAPI
// (the async deep dive). The async stack underneath the patterns: SQLAlchemy
// 2.0/asyncpg, Pydantic v2, aiokafka + outbox relay, grpc.aio, chassis-as-
// convention, OTel. Code-deepest of the three decks.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// WAVE 1 SKELETON — every content slide below is a reviewable stub: real
// eyebrow + title + figure/code marker + one-line speaker-note placeholder.
// Bullet bodies are marked "TODO W2" and code-slide stubs name the real
// examples/<svc>/... source; real code bodies land in Wave 2. Sections:
// A Async Foundation / B Pydantic v2 at the Edges / C Messaging the Async Way
// / D The Chassis as Convention + OTel / E Together / F Appendix (packaging,
// testing).

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing-201-FastAPI-r1.0.pptx";
const REV = "r1.0";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python) — 201-FastAPI (the async deep dive)";
let pageNum = 0;

function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
}

// ---- local stub helpers (thin wrappers over the bundled deck-helpers) -----
function content(eyebrow, title, bullets, notes, opts) {
  const s = S();
  addContentTitle(s, eyebrow, title);
  addBullets(s, bullets, opts || {});
  addNotes(s, notes);
  return s;
}
function diagram(eyebrow, title, png, caption, notes, opts) {
  const s = S();
  addDiagramSlide(s, eyebrow, title, png, caption, opts || {});
  addNotes(s, notes);
  return s;
}
function code(eyebrow, title, lang, sourcePath, descriptionLine, notes, opts) {
  const s = S();
  addCodeSlide(s, eyebrow, title, lang, [
    `# TODO W2 — draw the real body from ${sourcePath}`,
    `# ${descriptionLine}`,
  ], `TODO W2 caption — ${descriptionLine}`, opts || {});
  addNotes(s, notes);
  return s;
}

// ===== COVER ==================================================================
{
  const s = pres.addSlide();
  pageNum += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201-FASTAPI", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 12, bold: true, color: COLOR.red, charSpacing: 4, align: "left", valign: "middle" });
  s.addText([{ text: "The async", options: { breakLine: true } },
             { text: "deep dive" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The async stack underneath the patterns: SQLAlchemy 2.0/asyncpg, Pydantic v2, aiokafka and the outbox relay, grpc.aio, the chassis as convention, and OTel.",
    { x: 6.00, y: 4.55, w: 6.80, h: 1.15, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 201-FastAPI deep dive, for Python engineers who build the services. It is the code-deepest of the three decks: the async foundation, Pydantic v2 at the edges, messaging the async way, the chassis as convention plus OTel, and a together section that traces one request's full async path. Code slides come from real examples/ source. STUB: expand this script in the content-authoring wave.");
}

// ===== AGENDA ==================================================================
{
  const s = S();
  addContentTitle(s, "201-FASTAPI · THE ASYNC DEEP DIVE", "The stack underneath every pattern in the 201");
  addTwoColBullets(s,
    ["TODO W2 — the async foundation: SQLAlchemy 2.0, asyncpg, the outbox write", "TODO W2 — Pydantic v2 at the edges: models, settings, ACL translation", "TODO W2 — messaging the async way: aiokafka, the relay, grpc.aio"],
    ["TODO W2 — the chassis as convention, plus OTel", "TODO W2 — together: one request's full async path", "TODO W2 — appendix: packaging and testing"]);
  addNotes(s, "STUB speaker notes. Agenda mirrors the five-section arc plus the packaging/testing appendix; fill in during the content-authoring wave.");
}

// ===== SECTION A — THE ASYNC FOUNDATION =======================================
divider("A", "The Async Foundation", "SQLAlchemy 2.0, asyncpg, the unit of work, and the outbox write.",
  "STUB divider. Opens the async-foundation section: async SQLAlchemy 2.0/asyncpg sessions, the unit-of-work pattern, migrations as a contract, and writing the outbox record in the same transaction as the business change. Expand with the full section arc in the content-authoring wave.");

code("ASYNC FOUNDATION · THE ASYNC SESSION", "An async engine and session factory, once per service",
  "python · sqlalchemy", "examples/07-order-service/app/db.py",
  "the async SQLAlchemy 2.0 engine/session wiring every service repeats as a convention",
  "STUB speaker notes. Shows the real async-session setup; fill in during the content-authoring wave.");

code("ASYNC FOUNDATION · THE UNIT OF WORK", "The repository commits the business row and the outbox row together",
  "python · sqlalchemy", "examples/07-order-service/app/repository.py",
  "the repository/unit-of-work pattern wrapping the async session",
  "STUB speaker notes. Shows the unit-of-work implementation; fill in during the content-authoring wave.");

code("ASYNC FOUNDATION · MIGRATIONS AS A CONTRACT", "Alembic owns the schema, service by service",
  "python · alembic", "examples/07-order-service/migrations/versions/0001_create_order_schema.py",
  "the Alembic migration that is the order service's schema contract",
  "STUB speaker notes. Shows a real Alembic migration as a contract artifact; fill in during the content-authoring wave.");

diagram("ASYNC FOUNDATION · THE OUTBOX WRITE", "Write the outbox row in the same transaction",
  "outbox-write-in-transaction",
  "TODO W2 caption — an async SQLAlchemy 2.0 session commits the business row and the outbox row together, or neither.",
  "STUB speaker notes. This slide introduces the outbox-write-in-transaction pattern with real code from examples/; fill in during the content-authoring wave sourced from the authored chapters (_docs/14-33).");

diagram("ASYNC FOUNDATION · THE RELAY, AT LEAST ONCE", "The relay is what makes a crash survivable",
  "outbox-relay-at-least-once",
  "TODO W2 caption — the relay loop publishes at least once; the consumer side (section C) dedupes.",
  "STUB speaker notes. Closes the foundation section on the relay's delivery guarantee; fill in during the content-authoring wave.");

// ===== SECTION B — PYDANTIC V2 AT THE EDGES ===================================
divider("B", "Pydantic v2 at the Edges", "Models, settings, validation, and the ACL translation.",
  "STUB divider. Opens the Pydantic v2 section: typed settings, request/response models, ACL translation at the boundary, and the GraphQL and sync-to-async edges. Expand with the full section arc in the content-authoring wave.");

code("PYDANTIC V2 · SETTINGS", "Typed, validated settings via BaseSettings",
  "python · pydantic", "examples/07-order-service/app/config.py",
  "the service's typed settings model, loaded once at startup",
  "STUB speaker notes. Shows the real Pydantic v2 settings model; fill in during the content-authoring wave.");

code("PYDANTIC V2 · REQUEST/RESPONSE MODELS", "Validation at the edge, not scattered through the service",
  "python · pydantic", "examples/07-order-service/app/schemas.py",
  "the request/response schema models FastAPI validates against automatically",
  "STUB speaker notes. Shows the real Pydantic v2 schema models; fill in during the content-authoring wave.");

diagram("PYDANTIC V2 · ACL TRANSLATION", "Translate at the boundary, not throughout the service",
  "acl-contract-seam",
  "TODO W2 caption — the anti-corruption layer as a thin Pydantic translation, not a scattered one.",
  "STUB speaker notes. Introduces ACL translation as a Pydantic v2 idiom; fill in during the content-authoring wave.");

code("PYDANTIC V2 · THE GRAPHQL EDGE", "Strawberry types are the edge's own validated shape",
  "python · strawberry", "examples/08-graphql-gateway/app/schema.py",
  "the GraphQL gateway's typed schema, the edge's own Pydantic-adjacent contract",
  "STUB speaker notes. Shows the real Strawberry GraphQL schema; fill in during the content-authoring wave.");

diagram("PYDANTIC V2 · THE GRAPHQL FAN-OUT", "One validated query, five sources underneath",
  "graphql-gateway-five-source-fanout",
  "TODO W2 caption — the gateway's single typed query fans out to five backing services.",
  "STUB speaker notes. Pairs with the Strawberry schema code slide; fill in during the content-authoring wave.");

diagram("PYDANTIC V2 · SYNC TO ASYNC", "The checkout call crosses from a sync request to an async event",
  "checkout-sync-to-async-contract",
  "TODO W2 caption — the Pydantic model that is the contract on both sides of that crossing.",
  "STUB speaker notes. Closes the Pydantic section on the sync/async edge; fill in during the content-authoring wave.");

// ===== SECTION C — MESSAGING THE ASYNC WAY ====================================
divider("C", "Messaging the Async Way", "aiokafka, the relay as an asyncio task, grpc.aio, and the registry envelope.",
  "STUB divider. Opens the messaging section: aiokafka producer/consumer, the outbox relay running as an asyncio task, idempotent dedupe, grpc.aio, and the Avro/registry envelope. Expand with the full section arc in the content-authoring wave.");

code("MESSAGING · THE AIOKAFKA PRODUCER", "An async producer publishes the registry-aware envelope",
  "python · aiokafka", "examples/09-schema-registry-demo/app/producer.py",
  "the async Kafka producer wrapping the Avro/registry envelope",
  "STUB speaker notes. Shows the real aiokafka producer; fill in during the content-authoring wave.");

code("MESSAGING · THE AIOKAFKA CONSUMER", "An async consumer reacts to the choreographed event",
  "python · aiokafka", "examples/05-payment-service/app/consumer.py",
  "the async Kafka consumer driving the payment service's choreographed reaction",
  "STUB speaker notes. Shows the real aiokafka consumer; fill in during the content-authoring wave.");

code("MESSAGING · THE RELAY AS AN ASYNCIO TASK", "The outbox relay runs as a background asyncio task",
  "python · asyncio", "examples/06-shipping-service/app/relay.py",
  "the relay implemented as an asyncio background task alongside the FastAPI app",
  "STUB speaker notes. Shows the real asyncio-task relay; this is the async mechanic the 201 only gestures at. Fill in during the content-authoring wave.");

diagram("MESSAGING · IDEMPOTENT DEDUPE", "A redelivered message must not double-apply",
  "idempotent-consumer-dedupe",
  "TODO W2 caption — the dedupe key and the async transaction that makes the check-and-apply atomic.",
  "STUB speaker notes. Introduces the async idempotent-consumer mechanics; fill in during the content-authoring wave.");

diagram("MESSAGING · COMPENSATION AS A CONSUMER", "A compensating action is just another async consumer",
  "idempotent-compensation-two-layers",
  "TODO W2 caption — the compensation handler, idempotent at two layers, implemented as an async consumer.",
  "STUB speaker notes. Closes the saga-messaging thread; fill in during the content-authoring wave.");

diagram("MESSAGING · THE gRPC.AIO CONTRACT", "Inventory's protobuf contract, seen from the async client",
  "inventory-grpc-proto-acl",
  "TODO W2 caption — the .proto contract that grpc.aio generates an async stub from.",
  "STUB speaker notes. Introduces the gRPC contract before the server-side code slide; fill in during the content-authoring wave.");

code("MESSAGING · THE gRPC.AIO SERVER", "An async gRPC server behind the same FastAPI chassis",
  "python · grpc.aio", "examples/04-inventory-service/app/grpc_server.py",
  "the async gRPC server implementation, running the service's grpc.aio ACL",
  "STUB speaker notes. Shows the real grpc.aio server; fill in during the content-authoring wave.");

diagram("MESSAGING · THE REGISTRY ENVELOPE", "Avro, wrapped for safe schema evolution",
  "avro-wire-envelope-registry-flow",
  "TODO W2 caption — the wire envelope every async producer and consumer agrees on.",
  "STUB speaker notes. Closes the messaging section on the registry envelope; fill in during the content-authoring wave.");

// ===== SECTION D — THE CHASSIS AS CONVENTION + OTEL ===========================
divider("D", "The Chassis as Convention, plus OTel", "Config, logging, health, and errors as convention; OTel as the trace.",
  "STUB divider. Opens the chassis section: config/logging/health/errors as a repeated FastAPI convention, DI wiring, and OTel zero-code plus manual spans. Expand with the full section arc in the content-authoring wave.");

code("CHASSIS · CONFIG, LOGGING, HEALTH", "The same shape, repeated as a convention across services",
  "python · fastapi", "examples/06-shipping-service/app/config.py",
  "the config/logging/health convention every service repeats, not a shared library",
  "STUB speaker notes. Shows the real config module as the chassis-as-convention example; fill in during the content-authoring wave.");

code("CHASSIS · ERRORS & RESILIENCE AS CONVENTION", "A typed error hierarchy, mapped to HTTP status once",
  "python · fastapi", "examples/04-inventory-service/app/errors.py",
  "the typed error hierarchy and the exception handler that maps it to HTTP once",
  "STUB speaker notes. Shows the real errors module; fill in during the content-authoring wave.");

diagram("CHASSIS · ANATOMY", "DI wiring and the shape every service shares",
  "fastapi-chassis-anatomy",
  "TODO W2 caption — dependency injection, lifespan, and the chassis anatomy common to every service.",
  "STUB speaker notes. Introduces the chassis anatomy diagram; fill in during the content-authoring wave.");

diagram("CHASSIS · RESILIENCE TOPOLOGY", "Retries, timeouts, and the circuit breaker, as convention",
  "shipping-resilience-chassis",
  "TODO W2 caption — resilience primitives wired the same way in every service that needs them.",
  "STUB speaker notes. Shows the resilience-chassis topology; fill in during the content-authoring wave.");

diagram("CHASSIS · OTEL, ZERO-CODE PLUS MANUAL SPANS", "opentelemetry-distro auto-instruments; manual spans fill the gaps",
  "mesh-hero-trace-waterfall",
  "TODO W2 caption — the hero trace produced by zero-code instrumentation plus a handful of manual spans, into the LGTM stack.",
  "STUB speaker notes. Introduces OTel instrumentation strategy; fill in during the content-authoring wave.");

diagram("CHASSIS · THE SCORECARD", "Which chassis capabilities each service actually adopted",
  "chassis-scorecard",
  "TODO W2 caption — config, health, errors, resilience, OTel — scored per service.",
  "STUB speaker notes. Closes the chassis section with the adoption scorecard; fill in during the content-authoring wave.");

// ===== SECTION E — TOGETHER ====================================================
divider("E", "Together", "One request's full async path, start to finish.",
  "STUB divider. Traces one request through the orchestrated saga, the choreographed path, CQRS, and crash-resume, all stitched together. Expand with the full section arc in the content-authoring wave.");

diagram("TOGETHER · THE ORCHESTRATED PATH", "Checkout to shipped, one async path at a time",
  "orchestrated-shipping-saga-sequence",
  "TODO W2 caption — the full async call sequence from the orchestrator through its compensations.",
  "STUB speaker notes. Traces the orchestrated saga's full async path; fill in during the content-authoring wave.");

diagram("TOGETHER · THE CHOREOGRAPHED PATH", "The same checkout, reacting instead of conducting",
  "choreographed-payment-saga-sequence",
  "TODO W2 caption — the same workflow traced through choreography instead of orchestration.",
  "STUB speaker notes. Traces the choreographed saga's full async path; fill in during the content-authoring wave.");

diagram("TOGETHER · CQRS, ASYNC", "The write path and the read projection, both async",
  "order-cqrs-write-read-split",
  "TODO W2 caption — the async write path and the async projection rebuild, together.",
  "STUB speaker notes. Traces the async CQRS path; fill in during the content-authoring wave.");

diagram("TOGETHER · CRASH-RESUME", "Kill the process mid-saga; it resumes from the outbox",
  "saga-state-machine-crash-resume",
  "TODO W2 caption — the crash-resume test that proves the async relay and the state machine agree after a restart.",
  "STUB speaker notes. Traces the crash-resume path, tying the foundation section back together; fill in during the content-authoring wave.");

diagram("TOGETHER · THE EVENT-DRIVEN PATH", "Notification reacts to the same event stream",
  "event-driven-notification-topology",
  "TODO W2 caption — the lowest-risk async path, end to end, as the closing example.",
  "STUB speaker notes. Closes the Together section with the simplest async path; fill in during the content-authoring wave.");

// ===== SECTION F — APPENDIX (PACKAGING + TESTING) =============================
divider("F", "Appendix — Packaging & Testing", "uv, UBI10, and the Containerfile; pytest, Testcontainers, and Newman.",
  "STUB appendix divider. Packaging and testing conventions that apply uniformly across every service in this deck. Expand in the content-authoring wave.");

code("APPENDIX · PACKAGING", "uv-managed dependencies, built on UBI10",
  "containerfile", "examples/07-order-service/Containerfile + pyproject.toml",
  "the uv-managed pyproject.toml and the UBI10-based Containerfile every service shares as a convention",
  "STUB speaker notes. Shows the real packaging convention; fill in during the content-authoring wave.");

code("APPENDIX · TESTING", "pytest + Testcontainers exercise the real async stack",
  "python · pytest", "examples/06-shipping-service/tests/integration/test_crash_resume.py",
  "the integration test that drives the crash-resume scenario against a real Testcontainers Postgres and Kafka",
  "STUB speaker notes. Shows the real pytest + Testcontainers integration test; fill in during the content-authoring wave.");

content("APPENDIX · REST CONTRACT CHECKS", "Newman exercises the REST edges from outside the process",
  ["TODO W2 — a Newman/Postman collection checks the REST contract at the edge, independent of the async internals.",
   "TODO W2 — this is the same behavioural-contract idea as the 201's equivalence gate, scoped to one service's edge."],
  "STUB speaker notes. Closes the appendix with the REST-contract testing convention; fill in during the content-authoring wave.");

// ===== CLOSE ===================================================================
content("201-FASTAPI · CLOSE", "The async stack, end to end",
  ["TODO W2 — every pattern in the 201 rests on the async mechanics walked in this deck: SQLAlchemy 2.0, Pydantic v2, aiokafka, grpc.aio, the chassis, and OTel.",
   "TODO W2 — for the pattern set at just-enough-code depth, see the 201; for the ideas and the advantage case, see the 101."],
  "STUB speaker notes. Closing summary and hand-off back to the 201 and the 101; fill in during the content-authoring wave.");

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum))
  .catch(e => { console.error(e); process.exit(1); });
