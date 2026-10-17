// deck.js — "Modernizing Enterprise Applications (Python)" — 101 (the ideas).
// Concept-forward companion: the case for moving Django to FastAPI, one seam
// at a time. No deep code — that lives in the 201-fastapi deep dive.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// WAVE 1 SKELETON — every content slide below is a reviewable stub: real
// eyebrow + title + figure/code marker + one-line speaker-note placeholder.
// Bullet bodies are marked "TODO W2" and get full advantage-framed prose in
// the Wave 2 content-construction pass. Arc: A Why & How / B The Migration /
// C Operating & Reflection (mirrors the Java 101 sibling; re-authored, not
// copied; FastAPI-native throughout).

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing_101-r1.0.pptx";
const REV = "r1.0";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python) — 101 (the ideas)";
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
function twoCol(eyebrow, title, left, right, notes) {
  const s = S();
  addContentTitle(s, eyebrow, title);
  addTwoColBullets(s, left, right);
  addNotes(s, notes);
  return s;
}
function diagram(eyebrow, title, png, caption, notes, opts) {
  const s = S();
  addDiagramSlide(s, eyebrow, title, png, caption, opts || {});
  addNotes(s, notes);
  return s;
}

// ===== COVER ==================================================================
{
  const s = pres.addSlide();
  pageNum += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 101", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 13, bold: true, color: COLOR.red, charSpacing: 5, align: "left", valign: "middle" });
  s.addText([{ text: "Django to FastAPI,", options: { breakLine: true } },
             { text: "one seam at a time" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The case for modernizing a Django monolith into async FastAPI services, and the strangler-fig method that gets there without a rewrite.",
    { x: 6.00, y: 4.65, w: 6.80, h: 1.05, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 101 — the ideas deck. It makes the conceptual case for modernizing a Django monolith into FastAPI services and explains the strangler-fig method that drives the migration, without going into async implementation detail; the full pattern set is the 201, and the async/FastAPI code deep dive is the 201-FastAPI. STUB: expand this script in the content-authoring wave.");
}

// ===== AGENDA ==================================================================
twoCol("101 · THE IDEAS", "The whole argument, in one sitting",
  ["TODO W2 — why modernize, and when to leave it alone", "TODO W2 — the strangler fig — grow the new around the old", "TODO W2 — finding the seams in the domain", "TODO W2 — data, ownership, and coordination as ideas"],
  ["TODO W2 — communication and contracts across the seam", "TODO W2 — operating the result: mesh, observability, supply chain", "TODO W2 — the modernization, made measurable", "TODO W2 — where to stop — and where to go next"],
  "STUB speaker notes. The agenda runs the three-act arc: Why & How, The Migration, Operating & Reflection. Expand with the full roadmap framing in the content-authoring wave.");

// ===== ACT A — WHY & HOW ======================================================
divider("A", "Why, and How", "The case for change, and the method that makes it safe.",
  "STUB divider. Opens the why-modernize argument and introduces the strangler-fig method as the thing that makes changing a live system safe. Expand with the full arc in the content-authoring wave.");

content("WHY MODERNIZE · THE CASE", "Modernize because change got expensive",
  ["TODO W2 — the monolith holds the business value; every change is coupled to everything else.",
   "TODO W2 — the target is independent deployability, not a service count — lead with the advantage of shipping on an independent schedule."],
  "STUB speaker notes. This slide opens the why-modernize case; fill in during the content-authoring wave with the advantage-framed argument sourced from the authored chapters.");

content("WHY MODERNIZE · RESTRAINT", "And when not to modernize at all",
  ["TODO W2 — stable and low-value systems are cheapest left exactly as they are; encapsulate before you extract.",
   "TODO W2 — modernization is a means, not a virtue — the test is whether a real change gets safer or cheaper."],
  "STUB speaker notes. This slide makes the restraint case; fill in during the content-authoring wave.");

diagram("THE STRANGLER FIG · THE METHOD", "Grow the new system around the old",
  "strangler-four-moves",
  "TODO W2 caption — the four strangler moves, advantage-framed against a big-bang rewrite.",
  "STUB speaker notes. Introduces the strangler-fig method as the safe alternative to a rewrite; fill in during the content-authoring wave.");

// ===== ACT B — THE MIGRATION ==================================================
divider("B", "The Migration", "Grow the new system around the old, one seam at a time.",
  "STUB divider. Walks the migration as a set of ideas: proxy routing, finding seams, owning data, and coordinating across services. Expand with the full condensed arc in the content-authoring wave.");

diagram("THE STRANGLER FIG · PROXY ROUTING", "A proxy in front, one seam out at a time",
  "strangler-proxy-routing",
  "TODO W2 caption — the edge proxy routes by flag; every cutover is reversible.",
  "STUB speaker notes. Explains the proxy-routing mechanics at altitude, no code; fill in during the content-authoring wave.");

content("FINDING THE SEAMS", "Seams are discovered, not invented",
  ["TODO W2 — event storming and DDD bounded contexts are how a seam is named before it is cut.",
   "TODO W2 — the service count follows the domain — six real bounded contexts, not a target number."],
  "STUB speaker notes. Introduces domain-driven seam-finding; fill in during the content-authoring wave.");

diagram("DATA ACROSS THE SEAM", "Lead with owned data, not the shared schema",
  "shared-data-vs-owned-data",
  "TODO W2 caption — lead-new-thing-left: each FastAPI service owns its Postgres schema versus the monolith's shared tables.",
  "STUB speaker notes. Introduces database-per-service as the hard part of decomposition; fill in during the content-authoring wave.");

diagram("COORDINATING", "Two ways to run a workflow across services",
  "choreography-vs-orchestration-contrast",
  "TODO W2 caption — choreography and orchestration, same checkout; compensation, not rollback.",
  "STUB speaker notes. Introduces the two coordination styles at altitude; fill in during the content-authoring wave.");

diagram("COMMUNICATION · PROTOCOL FIT", "REST, gRPC, and GraphQL each earn their seam",
  "rest-grpc-graphql-protocol-fit",
  "TODO W2 caption — pick the protocol by the shape of the call, not by habit.",
  "STUB speaker notes. Introduces protocol fit across the service boundary; fill in during the content-authoring wave.");

diagram("THE CUTOVER TIMELINE", "Six seams, in dependency order", "strangler-cutover-timeline",
  "TODO W2 caption — each cutover stays behind the equivalence gate until the old module is retired.",
  "STUB speaker notes. Walks the cutover order and the reversibility guarantee; fill in during the content-authoring wave.");

// ===== ACT C — OPERATING & REFLECTION =========================================
divider("C", "Operating & Reflection", "Run the result, measure the win, and know when to stop.",
  "STUB divider. Covers the chassis, mesh, observability, the measurable supply-chain win, and the pattern-language retrospective. Expand with the full arc in the content-authoring wave.");

content("THE CHASSIS AS CONVENTION", "The chassis is a convention, not a framework",
  ["TODO W2 — config, health, logging, and OTel as a shared FastAPI convention across services, not a shared library to maintain.",
   "TODO W2 — the platform answers the operational questions — identity, traffic, discovery — from Kubernetes and the mesh."],
  "STUB speaker notes. Introduces the chassis-as-convention idea; fill in during the content-authoring wave.");

diagram("OPERATING · THE MESH", "mTLS and traffic identity, once services own their data",
  "mesh-mtls-topology",
  "TODO W2 caption — the mesh gives every service an identity and encrypted traffic without application code.",
  "STUB speaker notes. Introduces the service mesh as an operating-model idea; fill in during the content-authoring wave.");

diagram("OPERATING · THE TRACE", "One request, traced end to end", "mesh-hero-trace-waterfall",
  "TODO W2 caption — the migration did not lose observability; it gained a trace across six services.",
  "STUB speaker notes. Shows the hero trace waterfall as proof of operability; fill in during the content-authoring wave.");

diagram("THE MEASURABLE WIN", "The modernization, made measurable", "supply-chain-gate-pipeline",
  "TODO W2 caption — SBOM, scan, gate — the monolith fails it; the modernized service passes clean.",
  "STUB speaker notes. Makes the supply-chain case quantitatively; fill in during the content-authoring wave.");

diagram("THE RESULT", "One monolith, six independent services", "final-monolith-free-topology",
  "TODO W2 caption — the final topology: the monolith is gone; each service owns its data.",
  "STUB speaker notes. Shows the end-state topology; fill in during the content-authoring wave.");

diagram("REFLECTION · THE PATTERN MAP", "Where each pattern lives in the language",
  "pattern-language-map",
  "TODO W2 caption — cross-reference by concept to the 201's deep sections.",
  "STUB speaker notes. Introduces the pattern-language map as a navigation aid; fill in during the content-authoring wave.");

diagram("REFLECTION · THE SCORECARD", "A pattern belongs when it cures a pain you have",
  "book-pattern-scorecard",
  "TODO W2 caption — used versus deferred; deferred is a verdict too.",
  "STUB speaker notes. Walks the pattern scorecard at altitude; fill in during the content-authoring wave.");

content("REFLECTION · WHERE TO STOP", "Over-decomposition is the seductive failure",
  ["TODO W2 — the tell is a coordinated release; stop at context-aligned services.",
   "TODO W2 — nanoservice sprawl is a distributed monolith — all the coupling, plus a network."],
  "STUB speaker notes. Closes the reflection on service-count discipline; fill in during the content-authoring wave.");

// ===== CLOSE ===================================================================
content("101 · CLOSE", "One monolith, six services, a method that verifies itself",
  ["TODO W2 — the claim held: a coupled Django monolith became six FastAPI services that own their data and coordinate without a conductor.",
   "TODO W2 — for the running system and the full pattern set, see the 201; for the async code deep dive, see the 201-FastAPI."],
  "STUB speaker notes. Closing summary and hand-off to the 201 and 201-FastAPI; fill in during the content-authoring wave.");

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum))
  .catch(e => { console.error(e); process.exit(1); });
