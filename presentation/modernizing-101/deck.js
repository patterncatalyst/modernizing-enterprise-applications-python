// deck.js — "Modernizing Enterprise Applications (Python)" — 101 (the ideas).
// Concept-forward companion: the case for moving Django to FastAPI, one seam
// at a time. No deep code — that lives in the 201-fastapi deep dive.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js

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

// ===== SECTION DIVIDER (stub) =================================================
divider("A", "Why, and How", "The case for change, and the method that makes it safe.",
  "STUB divider. Opens the why-modernize argument and introduces the strangler-fig method as the thing that makes changing a live system safe. Expand with the full arc in the content-authoring wave.");

// ===== CONTENT SLIDE (stub) ===================================================
{
  const s = S();
  addContentTitle(s, "WHY MODERNIZE · THE CASE", "Modernize because change got expensive");
  addBullets(s, [
    "STUB bullet — the monolith holds the business value; every change is coupled to everything else.",
    "STUB bullet — the target is independent deployability, not a service count.",
  ], { fontSize: 17 });
  addNotes(s, "STUB speaker notes. This slide opens the why-modernize case; fill in during the content-authoring wave with the advantage-framed argument sourced from the authored chapters.");
}

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p))
  .catch(e => { console.error(e); process.exit(1); });
