// deck.js — "Modernizing Enterprise Applications (Python)" — 201-FastAPI
// (the async deep dive). The async stack underneath the patterns: SQLAlchemy
// 2.0/asyncpg, Pydantic v2, aiokafka + outbox relay, grpc.aio, chassis-as-
// convention, OTel. Code-deepest of the three decks.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js

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

// ===== SECTION DIVIDER (stub) =================================================
divider("A", "The Async Foundation", "SQLAlchemy 2.0, asyncpg, the unit of work, and the outbox write.",
  "STUB divider. Opens the async-foundation section: async SQLAlchemy 2.0/asyncpg sessions, the unit-of-work pattern, and writing the outbox record in the same transaction as the business change. Expand with the full section arc in the content-authoring wave.");

// ===== CONTENT SLIDE (stub) ===================================================
{
  const s = S();
  addContentTitle(s, "ASYNC FOUNDATION · OUTBOX WRITE", "Write the outbox row in the same transaction");
  addBullets(s, [
    "STUB bullet — an async SQLAlchemy 2.0 session commits the business row and the outbox row together, or neither.",
    "STUB bullet — this is what makes the relay safe to crash and resume without losing or duplicating an event.",
  ], { fontSize: 17 });
  addNotes(s, "STUB speaker notes. This slide introduces the outbox-write-in-transaction pattern with real code from examples/; fill in during the content-authoring wave sourced from the authored chapters (_docs/14-33).");
}

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p))
  .catch(e => { console.error(e); process.exit(1); });
