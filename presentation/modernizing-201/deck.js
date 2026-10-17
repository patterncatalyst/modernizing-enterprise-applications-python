// deck.js — "Modernizing Enterprise Applications (Python)" — 201 (the patterns).
// Full technical pattern set across the strangler-fig migration; just-enough
// code (the async mechanics live in 201-fastapi). MAIN body target: <=~50
// slides, overflow pushed into appendices.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// WAVE 1 SKELETON — every content slide below is a reviewable stub: real
// eyebrow + title + figure/code marker + one-line speaker-note placeholder.
// Bullet bodies are marked "TODO W2" and get full advantage-framed prose plus
// real code bodies in the Wave 2 content-construction pass. MAIN body is
// sections 01-10 (exactly ~50 slides incl. cover/agenda/dividers/close);
// everything past "APPENDIX — Overflow Starts Here" is appendix material and
// does not count against the ~50 cap. Code-slide stubs name the real
// examples/<svc>/... source they draw from in Wave 2.

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing-201-r1.0.pptx";
const REV = "r1.0";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python) — 201 (the patterns)";
let pageNum = 0;
let mainCount = 0;    // slides counted toward the ~50-main cap
let appendixCount = 0; // slides after the MAIN/APPENDIX boundary

let inAppendix = false;
function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); if (inAppendix) appendixCount += 1; else mainCount += 1; return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
  if (inAppendix) appendixCount += 1; else mainCount += 1;
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
  pageNum += 1; mainCount += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 13, bold: true, color: COLOR.red, charSpacing: 5, align: "left", valign: "middle" });
  s.addText([{ text: "The patterns," , options: { breakLine: true } },
             { text: "end to end" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The full technical pattern set behind the Django-to-FastAPI migration: seams, data ownership, coordination, contracts, and operating the result.",
    { x: 6.00, y: 4.65, w: 6.80, h: 1.05, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 201 — the patterns deck, for engineers and architects implementing the migration. It walks the full pattern set at just-enough-code depth; the deep async/FastAPI mechanics live in the 201-FastAPI companion. MAIN body is capped near 50 slides with overflow material (extended per-pattern variants, the full figure set, the OpenShift/CRC parity appendix) pushed into appendices. STUB: expand this script in the content-authoring wave.");
}

// ===== AGENDA ==================================================================
{
  const s = S();
  addContentTitle(s, "201 · THE PATTERNS", "The implementation, one section per part — plus an appendix");
  addTwoColBullets(s,
    ["TODO W2 — why modernize, and the ADLC equivalence gate", "TODO W2 — the reference monolith and its smells", "TODO W2 — finding the seams (DDD)", "TODO W2 — the strangler fig: proxy, ACL, event-driven", "TODO W2 — data across the seam: owned data, outbox, CQRS"],
    ["TODO W2 — coordinating: choreographed + orchestrated sagas", "TODO W2 — communication, contracts, and the chassis", "TODO W2 — operating and delivering the result", "TODO W2 — the pattern language, revisited", "TODO W2 — appendix: OpenShift/CRC parity + extended figures"]);
  addNotes(s, "STUB speaker notes. Agenda mirrors the ten-section main body plus the appendix; fill in during the content-authoring wave.");
}

// ===== SECTION 01 — WHY MODERNIZE =============================================
divider("01", "Why Modernize", "The case for change, and the discipline to leave most of it alone.",
  "STUB divider. Opens with why-modernize and the restraint case. Expand with the full section arc in the content-authoring wave.");

content("WHY MODERNIZE · THE CASE", "Modernize because change got expensive",
  ["TODO W2 — the Django monolith holds the business value; every change is coupled to everything else.",
   "TODO W2 — the target is independent deployability, not a service count."],
  "STUB speaker notes. Opens the why-modernize case for an implementer audience; fill in during the content-authoring wave.");

content("WHY MODERNIZE · RESTRAINT", "And when not to modernize at all",
  ["TODO W2 — stable, low-value contexts are cheapest left alone; encapsulate before you extract.",
   "TODO W2 — the test is whether a specific change gets safer or cheaper — never whether it looks more modern."],
  "STUB speaker notes. Makes the restraint case before the deep dive begins; fill in during the content-authoring wave.");

// ===== SECTION 02 — THE ADLC + EQUIVALENCE GATE ===============================
divider("02", "The ADLC + the Equivalence Gate", "The lifecycle — and the automated check — that make agent-driven change safe.",
  "STUB divider. Introduces the AI Development Lifecycle and the behaviour-equivalence gate that makes every cutover reviewable. Expand in the content-authoring wave.");

content("THE ADLC · FROM SDLC", "The human moves up a level",
  ["TODO W2 — the agent authors the change; the human frames the seam, sets the acceptance bar, and gates the merge.",
   "TODO W2 — the method is built around an automated gate, not around trust in the model's output."],
  "STUB speaker notes. Introduces the ADLC reassignment of roles; fill in during the content-authoring wave.");

content("THE ADLC · THE LOOP", "Frame, Plan, Generate, Verify, Reconcile",
  ["TODO W2 — the five-phase loop runs once per seam; Verify is the gate the other four phases exist to make meaningful.",
   "TODO W2 — Reconcile records what was claimed against what actually ran, increment by increment."],
  "STUB speaker notes. Walks the ADLC loop phase by phase; fill in during the content-authoring wave.");

code("THE ADLC · THE EQUIVALENCE GATE", "The behaviour-equivalence suite pins observable behaviour",
  "python · pytest", "examples/00-monolith/tests/test_checkout.py + test_smoke.py",
  "the equivalence suite that must stay green across every seam cutover, old position and new",
  "STUB speaker notes. Shows the real pytest suite that gates every cutover; real test excerpts land in the content-authoring wave.");

// ===== SECTION 03 — THE REFERENCE MONOLITH + SMELLS ===========================
divider("03", "The Reference Monolith", "Six bounded contexts, one shared schema, and planted coupling smells.",
  "STUB divider. Introduces the Django reference monolith this whole migration starts from. Expand in the content-authoring wave.");

code("THE MONOLITH · ARCHITECTURE", "One Django project, six apps, one shared schema",
  "python · django", "examples/00-monolith/config/settings.py",
  "the shared-schema Django settings that every extraction unwinds",
  "STUB speaker notes. Shows the monolith's shared-schema starting point; fill in during the content-authoring wave.");

content("THE MONOLITH · SMELLS", "Each smell maps to the pattern that removes it",
  ["TODO W2 — shared tables, chatty calls, and mixed responsibilities — the coupling smells that mark a seam.",
   "TODO W2 — table mapping each smell to the pattern that cures it, cross-referenced by concept to sections 05-08."],
  "STUB speaker notes. Walks the smell-to-pattern mapping; fill in during the content-authoring wave, consider addStatusTable.");

// ===== SECTION 04 — FINDING THE SEAMS (DDD) ===================================
divider("04", "Finding the Seams", "Event storming, bounded contexts, and the coupling ladder.",
  "STUB divider. Introduces domain-driven seam-finding as the technique that precedes every extraction. Expand in the content-authoring wave.");

content("FINDING THE SEAMS · EVENT STORMING", "Lay out the events, then cluster by aggregate",
  ["TODO W2 — event storming maps the domain before any code moves.",
   "TODO W2 — the clusters are the bounded contexts: order, inventory, payment, shipping, notification, review."],
  "STUB speaker notes. Introduces event storming as the seam-finding technique; fill in during the content-authoring wave.");

content("FINDING THE SEAMS · BOUNDED CONTEXTS", "A real seam has a clean boundary",
  ["TODO W2 — the data crossing a real seam is data the domain already exchanged — the ACL has almost nothing to translate.",
   "TODO W2 — service count follows the domain; stop when you run out of real seams."],
  "STUB speaker notes. Closes the seam-finding section; fill in during the content-authoring wave.");

// ===== SECTION 05 — THE STRANGLER FIG (PROXY / ACL / EVENT-DRIVEN) ============
divider("05", "The Strangler Fig in Practice", "A proxy in front, an ACL at the seam, events to notify.",
  "STUB divider. Walks the strangler-fig mechanics this migration actually used. Expand in the content-authoring wave.");

diagram("THE STRANGLER FIG · THE FOUR MOVES", "Observe, seam, divert, retire",
  "strangler-four-moves",
  "TODO W2 caption — the four moves, mapped to the real cutover sequence.",
  "STUB speaker notes. Introduces the four-move strangler method; fill in during the content-authoring wave.");

diagram("THE STRANGLER FIG · PROXY ROUTING", "The edge router chooses old or new by flag",
  "strangler-proxy-routing",
  "TODO W2 caption — the FastAPI edge proxy and the reversible cutover flag.",
  "STUB speaker notes. Pairs with the proxy implementation in examples/01-strangler-proxy; fill in during the content-authoring wave.");

diagram("THE STRANGLER FIG · THE ACL", "An anti-corruption layer keeps the new service honest",
  "acl-contract-seam",
  "TODO W2 caption — the ACL translates at the boundary so the new service never leaks the old schema.",
  "STUB speaker notes. Introduces the anti-corruption-layer pattern at the seam; fill in during the content-authoring wave.");

diagram("THE STRANGLER FIG · EVENT-DRIVEN NOTIFICATION", "The first extraction reacts to an event, not a call",
  "event-driven-notification-topology",
  "TODO W2 caption — the notification service as the first, lowest-risk extraction.",
  "STUB speaker notes. Introduces event-driven extraction via the notification service; fill in during the content-authoring wave.");

// ===== SECTION 06 — DATA ACROSS THE SEAM ======================================
divider("06", "Data Across the Seam", "From a shared schema to owned data — without losing an event.",
  "STUB divider. Walks database-per-service, the outbox, CDC as a bridge, CQRS, and ACID-to-ACD. Expand in the content-authoring wave.");

diagram("DATA · OWNED, NOT SHARED", "Database-per-service is the goal",
  "shared-data-vs-owned-data",
  "TODO W2 caption — lead-new-thing-left: each service's own Postgres schema versus the monolith's shared tables.",
  "STUB speaker notes. Introduces database-per-service; fill in during the content-authoring wave.");

diagram("DATA · THE OUTBOX WRITE", "Write the business row and the event row in one transaction",
  "outbox-write-in-transaction",
  "TODO W2 caption — the transactional outbox solves the dual-write problem.",
  "STUB speaker notes. Introduces the outbox-write pattern at concept depth; the async mechanics live in 201-FastAPI. Fill in during the content-authoring wave.");

code("DATA · THE OUTBOX RELAY", "Relay the outbox row; the consumer dedupes idempotently",
  "python · fastapi", "examples/07-order-service/app/relay.py",
  "the relay loop that publishes outbox rows at least once, safely",
  "STUB speaker notes. Just-enough code for the relay; the asyncio-task mechanics are the 201-FastAPI's job. Fill in during the content-authoring wave.");

diagram("DATA · CDC AS A BRIDGE", "Change data capture backfills, then gets torn down",
  "cdc-backfill-then-retire",
  "TODO W2 caption — CDC is a bridge during cutover, never a permanent dependency.",
  "STUB speaker notes. Introduces CDC as a temporary migration aid; fill in during the content-authoring wave.");

diagram("DATA · CQRS", "Split the write model from the read model where shapes diverge",
  "order-cqrs-write-read-split",
  "TODO W2 caption — the order service's write side and its read-optimized projection.",
  "STUB speaker notes. Introduces CQRS at concept depth; fill in during the content-authoring wave.");

diagram("DATA · ACID BECOMES ACD", "Across services, eventual consistency with compensation",
  "acid-to-acd-boundary",
  "TODO W2 caption — the single-transaction boundary gives way to compensation at the seam.",
  "STUB speaker notes. Closes the data section with the ACID-to-ACD framing; fill in during the content-authoring wave.");

// ===== SECTION 07 — COORDINATING ACROSS SERVICES ==============================
divider("07", "Coordinating Across Services", "Sagas — two styles, same checkout — and failure as a first-class concern.",
  "STUB divider. Walks choreographed and orchestrated sagas, plus idempotent compensation. Expand in the content-authoring wave.");

diagram("COORDINATING · TWO STYLES", "Choreography and orchestration, same checkout",
  "choreography-vs-orchestration-contrast",
  "TODO W2 caption — no conductor versus one conductor; this project used both, on the same checkout.",
  "STUB speaker notes. Introduces the two coordination styles; fill in during the content-authoring wave.");

code("COORDINATING · THE CHOREOGRAPHED SAGA", "Payment reacts to the order-placed event",
  "python · aiokafka", "examples/05-payment-service/app/consumer.py",
  "the payment service's choreographed reaction to the checkout event stream",
  "STUB speaker notes. Just-enough code for the choreographed path; full async mechanics live in 201-FastAPI. Fill in during the content-authoring wave.");

code("COORDINATING · THE ORCHESTRATED SAGA", "Shipping conducts its own steps and compensations",
  "python · fastapi", "examples/06-shipping-service/app/orchestrator.py",
  "the shipping service's orchestrator, sequencing steps and their compensations",
  "STUB speaker notes. Just-enough code for the orchestrated path; fill in during the content-authoring wave.");

diagram("COORDINATING · IDEMPOTENT CONSUMERS", "A redelivered event must not double-apply",
  "idempotent-consumer-dedupe",
  "TODO W2 caption — the dedupe key that makes at-least-once delivery safe to consume.",
  "STUB speaker notes. Introduces idempotent-consumer dedupe; fill in during the content-authoring wave.");

diagram("COORDINATING · COMPENSATION, NOT ROLLBACK", "Undo a committed step with a compensating action",
  "idempotent-compensation-two-layers",
  "TODO W2 caption — compensation at two layers: the business action and the idempotency guard around it.",
  "STUB speaker notes. Closes the coordination section with compensation mechanics; fill in during the content-authoring wave.");

// ===== SECTION 08 — COMMUNICATION, CONTRACTS & THE CHASSIS ====================
divider("08", "Communication, Contracts & the Chassis", "REST, gRPC, GraphQL — and the registry that keeps them compatible.",
  "STUB divider. Walks protocol fit, contract enforcement, and the FastAPI chassis. Expand in the content-authoring wave.");

diagram("COMMUNICATION · PROTOCOL FIT", "Pick the protocol by the shape of the call",
  "rest-grpc-graphql-protocol-fit",
  "TODO W2 caption — REST for the edge, gRPC between services, GraphQL for the aggregate view.",
  "STUB speaker notes. Introduces protocol selection across the service boundary; fill in during the content-authoring wave.");

code("CONTRACTS · THE gRPC CONTRACT", "Inventory's contract is a .proto file, not a shared model",
  "protobuf", "examples/04-inventory-service/proto/dev/patterncatalyst/inventory/v1/inventory.proto",
  "the inventory service's protobuf contract, the seam's anti-corruption boundary",
  "STUB speaker notes. Just-enough code for the gRPC contract; the grpc.aio mechanics live in 201-FastAPI. Fill in during the content-authoring wave.");

code("CONTRACTS · THE GRAPHQL GATEWAY", "One query, five sources, fanned out",
  "python · strawberry", "examples/08-graphql-gateway/app/schema.py",
  "the GraphQL gateway schema that fans a single query out across services",
  "STUB speaker notes. Just-enough code for the GraphQL gateway; fill in during the content-authoring wave.");

diagram("CONTRACTS · THE SCHEMA REGISTRY", "Avro, wrapped in a registry-aware envelope",
  "avro-wire-envelope-registry-flow",
  "TODO W2 caption — hand-duplicated schemas versus one registry everyone resolves against.",
  "STUB speaker notes. Introduces the schema-registry pattern; fill in during the content-authoring wave.");

diagram("THE CHASSIS", "Config, health, logging, and tracing — as a convention",
  "fastapi-chassis-anatomy",
  "TODO W2 caption — the FastAPI chassis every service opts into, not a shared framework to maintain.",
  "STUB speaker notes. Closes the chassis section; the deep chassis code lives in 201-FastAPI. Fill in during the content-authoring wave.");

// ===== SECTION 09 — OPERATING & DELIVERING ====================================
divider("09", "Operating & Delivering", "Deploy, mesh, observe, and gate the supply chain.",
  "STUB divider. Walks deployment topology, the mesh, observability, and the supply-chain gate. Expand in the content-authoring wave.");

diagram("OPERATING · DEPLOY TOPOLOGY", "Six services, one Kubernetes namespace",
  "deploy-k8s-namespace-topology",
  "TODO W2 caption — the deployment topology each extracted service lands in.",
  "STUB speaker notes. Introduces the Kubernetes deployment topology; fill in during the content-authoring wave.");

diagram("OPERATING · THE MESH", "mTLS and traffic identity, from the platform",
  "mesh-mtls-topology",
  "TODO W2 caption — the mesh answers the identity and traffic questions the chassis used to own.",
  "STUB speaker notes. Introduces the service mesh's operational role; fill in during the content-authoring wave.");

diagram("OPERATING · THE TRACE", "One request, traced end to end across services",
  "mesh-hero-trace-waterfall",
  "TODO W2 caption — the hero trace that proves the migration did not lose observability.",
  "STUB speaker notes. Shows the end-to-end trace waterfall; fill in during the content-authoring wave.");

code("DELIVERING · THE SUPPLY-CHAIN GATE", "SBOM, scan, and a policy threshold that fails the build",
  "bash · syft · grype", "examples/10-supply-chain/demo.sh + policy.yaml",
  "the three-step supply-chain gate: generate the SBOM, scan it, apply the policy",
  "STUB speaker notes. Just-enough code for the supply-chain gate, with the real evidence numbers; fill in during the content-authoring wave.");

diagram("OPERATING · THE RESULT", "One monolith, six services, no shared schema",
  "final-monolith-free-topology",
  "TODO W2 caption — the end-state topology after the sixth and hardest extraction.",
  "STUB speaker notes. Closes the operating section with the end-state topology; fill in during the content-authoring wave.");

// ===== SECTION 10 — THE PATTERN LANGUAGE, REVISITED ===========================
divider("10", "The Pattern Language, Revisited", "Which patterns we used — and where to stop.",
  "STUB divider. Closes the main body with the pattern-language retrospective. Expand in the content-authoring wave.");

diagram("THE PATTERN LANGUAGE MAP", "Where each pattern lives in the catalog",
  "pattern-language-map",
  "TODO W2 caption — cross-referenced by concept to sections 05-09 above.",
  "STUB speaker notes. Introduces the pattern-language map as a navigation aid; fill in during the content-authoring wave.");

diagram("THE PATTERN SCORECARD", "Used because it cured a pain we had; deferred is a verdict too",
  "book-pattern-scorecard",
  "TODO W2 caption — strangler fig, database-per-service, the outbox, both saga styles: used. Full event sourcing, the rewrite: deferred.",
  "STUB speaker notes. Walks the pattern scorecard; fill in during the content-authoring wave.");

content("WHERE TO STOP", "Over-decomposition is the seductive failure",
  ["TODO W2 — the tell is a coordinated release; stop at context-aligned services, split further only when a real seam demands it.",
   "TODO W2 — the named next horizons (GitOps, durable sagas, remaining observability) are each a bounded increment, not a rewrite."],
  "STUB speaker notes. Closes the main body on service-count discipline; fill in during the content-authoring wave.");

// ===== CLOSE (end of MAIN body — ~50 slides through here) =====================
content("201 · CLOSE", "The patterns, end to end — now go deeper",
  ["TODO W2 — the main body covered the full pattern arc at just-enough-code depth.",
   "TODO W2 — for the async/FastAPI code deep dive, see the 201-FastAPI; for the OpenShift/CRC parity material and the extended figure set, keep this appendix open in another window."],
  "STUB speaker notes. Closes the MAIN body and hands off to the appendix and the 201-FastAPI; fill in during the content-authoring wave.");

// ===============================================================================
// APPENDIX — overflow starts here. Slides below do NOT count against the
// ~50-slide MAIN cap (tracked separately as appendixCount).
// ===============================================================================
inAppendix = true;

// ----- APPENDIX A — OpenShift/CRC Parity --------------------------------------
divider("APP-A", "Appendix A — OpenShift/CRC Parity", "Keep this open in another window.",
  "STUB appendix divider. OpenShift/CRC parity material: topology, image delivery, mesh mTLS edge. Expand in the content-authoring wave.");

diagram("APPENDIX · OPENSHIFT TOPOLOGY", "The same six services, on OpenShift Local",
  "openshift-crc-topology",
  "TODO W2 caption — namespace and project layout on CRC.",
  "STUB speaker notes. OpenShift/CRC topology parity slide; fill in during the content-authoring wave.");

diagram("APPENDIX · IMAGE DELIVERY", "In-cluster builds, no external registry required",
  "openshift-image-delivery",
  "TODO W2 caption — S2I / binary build delivering each service's image on-cluster.",
  "STUB speaker notes. OpenShift image-delivery parity slide; fill in during the content-authoring wave.");

diagram("APPENDIX · MESH mTLS AT THE EDGE", "STRICT mTLS and a Route at the edge",
  "openshift-mesh-mtls-edge",
  "TODO W2 caption — OpenShift Service Mesh parity with the minikube/Istio mesh in section 09.",
  "STUB speaker notes. OpenShift mesh-mTLS parity slide; fill in during the content-authoring wave.");

// ----- APPENDIX B — Extended Pattern Variants & the Full Figure Set ----------
divider("APP-B", "Appendix B — Extended Pattern Variants", "The deeper per-pattern figures that didn't fit the main 50.",
  "STUB appendix divider. Houses every diagram from the house set not already used in the MAIN body, for completeness and deeper per-pattern variants. Expand in the content-authoring wave.");

diagram("APPENDIX · SAGA CRASH-RESUME", "The saga's state machine survives a crash",
  "saga-state-machine-crash-resume", "TODO W2 caption.",
  "STUB speaker notes. Extended saga-resilience variant; fill in during the content-authoring wave.");
diagram("APPENDIX · THE CHASSIS SCORECARD", "Which chassis capabilities each service adopted",
  "chassis-scorecard", "TODO W2 caption.",
  "STUB speaker notes. Extended chassis-adoption variant; fill in during the content-authoring wave.");
diagram("APPENDIX · SHIPPING RESILIENCE", "Retries, timeouts, and the circuit breaker in the shipping chassis",
  "shipping-resilience-chassis", "TODO W2 caption.",
  "STUB speaker notes. Extended resilience-chassis variant; fill in during the content-authoring wave.");
diagram("APPENDIX · SCHEMA EVOLUTION", "A compatible Avro schema change, end to end",
  "avro-compatibility-evolution", "TODO W2 caption.",
  "STUB speaker notes. Extended schema-registry evolution variant; fill in during the content-authoring wave.");
diagram("APPENDIX · SYNC-TO-ASYNC CONTRACT", "The checkout call crosses from sync REST to an async event",
  "checkout-sync-to-async-contract", "TODO W2 caption.",
  "STUB speaker notes. Extended contract variant for the sync/async seam; fill in during the content-authoring wave.");
diagram("APPENDIX · BEFORE THE REGISTRY", "Hand-duplicated schemas were the starting smell",
  "hand-duplicated-vs-registry-schema", "TODO W2 caption.",
  "STUB speaker notes. Before/after registry variant; fill in during the content-authoring wave.");
diagram("APPENDIX · THE gRPC CONTRACT, VISUALLY", "Inventory's protobuf ACL, as a diagram",
  "inventory-grpc-proto-acl", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-08 gRPC code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · THE GRAPHQL FAN-OUT, VISUALLY", "One query, five sources, as a diagram",
  "graphql-gateway-five-source-fanout", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-08 GraphQL code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · MULTI-OUTBOX SAGA", "A saga that spans more than one service's outbox",
  "multi-outbox-saga-topology", "TODO W2 caption.",
  "STUB speaker notes. Extended multi-service outbox variant; fill in during the content-authoring wave.");
diagram("APPENDIX · CONTENT-BASED ROUTING", "The notification service routes by event content",
  "notification-content-based-routing", "TODO W2 caption.",
  "STUB speaker notes. Extended notification-routing variant; fill in during the content-authoring wave.");
diagram("APPENDIX · THE CHOREOGRAPHED SAGA, VISUALLY", "Payment's reaction to checkout, as a sequence diagram",
  "choreographed-payment-saga-sequence", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-07 choreography code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · THE ORCHESTRATED SAGA, VISUALLY", "Shipping's orchestration, as a sequence diagram",
  "orchestrated-shipping-saga-sequence", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-07 orchestration code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · ORDER-ITEM SNAPSHOT", "The order-item foreign key becomes an owned snapshot",
  "orderitem-fk-to-snapshot", "TODO W2 caption.",
  "STUB speaker notes. Extended data-ownership variant for order items; fill in during the content-authoring wave.");
diagram("APPENDIX · ORDER LIFECYCLE (AWAITING SHIPMENT / REFUND)", "The order state machine's less-common branches",
  "order-lifecycle-awaiting-shipment-refund", "TODO W2 caption.",
  "STUB speaker notes. Extended order-lifecycle variant; fill in during the content-authoring wave.");
diagram("APPENDIX · ORDER LIFECYCLE (PENDING TO TERMINAL)", "The order state machine's main path",
  "order-pending-to-terminal-lifecycle", "TODO W2 caption.",
  "STUB speaker notes. Extended order-lifecycle variant; fill in during the content-authoring wave.");
diagram("APPENDIX · THE REBUILDABLE READ MODEL", "The order view projection can be rebuilt from the log",
  "order-view-rebuildable-projection", "TODO W2 caption.",
  "STUB speaker notes. Extended CQRS-projection variant; fill in during the content-authoring wave.");
diagram("APPENDIX · THE OUTBOX RELAY, AT LEAST ONCE", "Delivery guarantees the relay actually makes",
  "outbox-relay-at-least-once", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-06 outbox-relay code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · A LIGHTER RESERVE/RELEASE SAGA", "A smaller saga shape for a smaller workflow",
  "reserve-release-saga-lite", "TODO W2 caption.",
  "STUB speaker notes. Extended lighter-weight saga variant; fill in during the content-authoring wave.");
diagram("APPENDIX · REVIEW, PHASE A VS. PHASE B", "The review service's two extraction phases",
  "review-phase-a-vs-phase-b", "TODO W2 caption.",
  "STUB speaker notes. Extended phased-extraction variant for the review service; fill in during the content-authoring wave.");
diagram("APPENDIX · THE CUTOVER TIMELINE, VISUALLY", "Six seams, in dependency order, as a timeline",
  "strangler-cutover-timeline", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the 101's cutover-timeline slide, at implementer depth; fill in during the content-authoring wave.");
diagram("APPENDIX · THE SUPPLY-CHAIN GATE, VISUALLY", "SBOM, scan, gate — as a pipeline diagram",
  "supply-chain-gate-pipeline", "TODO W2 caption.",
  "STUB speaker notes. Visual companion to the section-09 supply-chain code slide; fill in during the content-authoring wave.");
diagram("APPENDIX · TWO CUTOVER DIMENSIONS", "Reversibility and blast radius, scored per seam",
  "two-cutover-dimensions", "TODO W2 caption.",
  "STUB speaker notes. Extended cutover-risk variant; fill in during the content-authoring wave.");

// ----- APPENDIX C — Reference (examples, stack, glossary) --------------------
divider("APP-C", "Appendix C — Reference", "The runnable examples, the stack, and the terms used in this deck.",
  "STUB appendix divider. Reference material for follow-along: the examples/ map, stack versions, and a glossary. Expand in the content-authoring wave.");

content("APPENDIX · THE EXAMPLES", "Eleven runnable examples, one per seam",
  ["TODO W2 — examples/00-monolith through examples/10-supply-chain, mapped to the section each one supports.",
   "TODO W2 — every code slide in this deck draws from one of these directories; this is the index."],
  "STUB speaker notes. Lists the examples/ directory map; fill in during the content-authoring wave, consider addStatusTable.");

content("APPENDIX · STACK & VERSIONS", "FastAPI, SQLAlchemy 2.0, aiokafka, Postgres, Kafka",
  ["TODO W2 — the Python/FastAPI stack versions behind every example, pinned.",
   "TODO W2 — the platform stack: Kubernetes, the mesh, the schema registry, the observability pipeline."],
  "STUB speaker notes. Lists stack and version pins; fill in during the content-authoring wave.");

content("APPENDIX · GLOSSARY", "Terms used in this deck",
  ["TODO W2 — strangler fig, seam, ACL, outbox, saga, CQRS, ACD, chassis — one line each.",
   "TODO W2 — cross-referenced by concept to the section where each term is introduced."],
  "STUB speaker notes. Closing glossary; fill in during the content-authoring wave.");

content("CLOSING · GO DEEPER", "Where to go from here",
  ["TODO W2 — for the ideas and the advantage case, see the 101; for the async/FastAPI code deep dive, see the 201-FastAPI.",
   "TODO W2 — every pattern in this deck is grounded in a runnable example in the repository."],
  "STUB speaker notes. Final closing slide of the appendix; fill in during the content-authoring wave.");

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum, "main:", mainCount, "appendix:", appendixCount))
  .catch(e => { console.error(e); process.exit(1); });
