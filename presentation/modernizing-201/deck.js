// deck.js — "Modernizing Enterprise Applications (Python)" — 201 (the patterns).
// Full technical pattern set across the strangler-fig migration; just-enough
// code (the async mechanics live in 201-fastapi). MAIN body target: <=~50
// slides, overflow pushed into appendices.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js

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
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 13, bold: true, color: COLOR.red, charSpacing: 5, align: "left", valign: "middle" });
  s.addText([{ text: "The patterns," , options: { breakLine: true } },
             { text: "end to end" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The full technical pattern set behind the Django-to-FastAPI migration: seams, data ownership, coordination, contracts, and operating the result.",
    { x: 6.00, y: 4.65, w: 6.80, h: 1.05, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 201 — the patterns deck, for engineers and architects implementing the migration. It walks the full pattern set at just-enough-code depth; the deep async/FastAPI mechanics live in the 201-FastAPI companion. MAIN body is capped near 50 slides with overflow material (extended per-pattern variants, the OpenShift/CRC parity appendix) pushed into appendices. STUB: expand this script in the content-authoring wave.");
}

// ===== SECTION DIVIDER (stub) =================================================
divider("A", "Why Modernize, and the ADLC", "The case for change, and the lifecycle that makes it safe.",
  "STUB divider. Opens with why-modernize and the ADLC equivalence-gate method that keeps the strangler migration safe at every seam. Expand with the full condensed arc (seams, data, coordination, contracts, operating) in the content-authoring wave.");

// ===== CONTENT SLIDE (stub) ===================================================
{
  const s = S();
  addContentTitle(s, "THE REFERENCE MONOLITH · SMELLS", "Where the seams hide");
  addBullets(s, [
    "STUB bullet — the reference Django monolith and the smells that mark a seam (shared tables, chatty calls, mixed responsibilities).",
    "STUB bullet — DDD bounded contexts are how we name a seam before we cut it.",
  ], { fontSize: 17 });
  addNotes(s, "STUB speaker notes. This slide introduces the reference monolith and the domain-driven seam-finding method; fill in during the content-authoring wave sourced from the authored chapters (_docs/14-33).");
}

// ===== APPENDIX DIVIDER (stub) ================================================
divider("APP", "Appendix — OpenShift/CRC Parity", "Keep this open in another window.",
  "STUB appendix divider. The OpenShift/CRC parity appendix (topology, image delivery, mesh mTLS edge) and the extended per-pattern figures that overflow the ~50-slide main body land here in the content-authoring wave.");

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p))
  .catch(e => { console.error(e); process.exit(1); });
