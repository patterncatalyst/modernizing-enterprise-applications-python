---
output: false
---

# Plan — Rebuild the three companion decks on the lgtm-presentation JSON-spec workflow

Status: COMPLETE (lgtm-relay, branch `docs/decks-lgtm-presentation-rebuild`). Opus validation: all 8 criteria met; one validator nit (in-code `SMELL[ch.NN]` tags) fixed in a repair round. Not yet pushed / no PR.

## Goal
Rebuild `modernizing-101`, `modernizing-201`, `modernizing-201-fastapi` so they match the
quality and house style of the CNDP Python deck. Scope: this project only.

## Key findings (grounded)
- Decks already use the lgtm-presentation generator and already NAME Red Hat fonts.
  The real font bug: fonts are NOT embedded (`ppt/fonts/*.fntdata` absent) so they
  substitute off-machine. CNDP embeds them. Embedding is the fix.
- Voice already near-clean at ban tier: 201=0, 201-fastapi=0, 101=8 (all em dashes in
  `deck-helpers.js` comments, none in slide/note content).
- Substantive work = de-chaptering speaker notes (literal "chapter"/"book" in 101 & 201).
- Slide counts: 101=24, 201=83, 201-fastapi=43.
- Diagram sources in `assets/diagrams/` are SHARED with the Jekyll site; 6 SVGs contain "chapter".
- Chapters (authority for standalone rewrites) in `_docs/00..33`. ADLC = "Agentic Development Lifecycle".

## Approach
Option A — rebuild on lgtm-presentation JSON-spec workflow (committed `.pptx` + `edits/*.json`
+ derived `text/*.md`). Adopt existing `*-r1.1.pptx` as committed baselines; land fixes as edit
ops; retire `deck.js`/`node_modules`. In-place deck.js fixes rejected in favor of native workflow.

## User decisions (gated)
- Layout: `presentation/lgtm-presentation/` (mirror CNDP exactly).
- Old generator: delete now, recoverable in git history.

## Steps
| # | Step | Files | Depends | Status |
|---|------|-------|---------|--------|
| S0 | Vendor deck_*.py + voice scanner; venv (python-pptx, lxml, cairosvg); confirm brand fonts | scripts/, venv | — | pending |
| S1 | Stand up presentation/lgtm-presentation/{*.pptx,edits/,text/,BUILD.md}; gen text/*.md | new dir | S0 | pending |
| S2a | 101: author+apply edits (de-chapter, standalone notes, terse) | edits/modernizing-101.json, pptx | S1 | pending |
| S2b | 201: same | edits/modernizing-201.json, pptx | S1 | pending |
| S2c | 201-fastapi: same | edits/modernizing-201-fastapi.json, pptx | S1 | pending |
| S2s | _shared.json (single owner) | edits/_shared.json | S1 | pending |
| S3 | De-chapter 6 diagram SVGs; re-render; replace_picture (keep site green) | assets/diagrams/*, edits/* | S0 | pending |
| S4 | deck_font --apply + EMBED brand fonts per deck | *.pptx | S2,S3 | pending |
| S5 | Gate: text --check, scan.sh ban=0, render+fit, assert fntdata present | — | S4 | pending |
| S6 | Delete deck.js/helpers/package*/node_modules; finalize BUILD.md | presentation/modernizing-*/ | S5 | pending |

## Acceptance criteria
- No deck.js/node_modules in the three deck dirs; each deck = pptx + edits/ + text/.
- `deck_text.py --check` passes all three (in sync; every slide has notes).
- `lgtm-professional-voice scan.sh --tier ban` = 0 across text/, edit prose, BUILD.md, diagram SVGs.
- 0 "chapter"/"this book"/"as we saw" cross-refs in text/*.md and diagrams ("Appendix N" dividers OK).
- Every pptx has embedded `ppt/fonts/*.fntdata` + `embedTrueTypeFonts`; run typefaces Red Hat only.
- Each deck renders (deck_render.sh) and passes deck_fit.py; opens without error.
- Titles 2–5-word noun phrases, claim in subtitle, one-line bullets, 0 em dashes, no rule-of-three.

## Risks
- Font embedding has no committed CNDP script → make "fntdata present" a gating assertion.
- `_shared.json` expect-count contention → single owner.
- Shared diagram sources → run site validators after S3.
- Baseline layout quirks / run-length overflow → deck_fit.py after S2/S4.
- Edit specs legitimately contain banned phrases on the `find` side → gate on text/ not edits/ find side.
