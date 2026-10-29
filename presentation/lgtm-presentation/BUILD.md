# Modernizing Enterprise Applications (Python) — deck build record

Red Hat-branded 16:9 `.pptx` decks in the house style (Red Hat Display / Red Hat Text /
Red Hat Mono, brand accents, logo on every slide, speaker notes on every slide). Three
companion decks cover the ideas, the full implementation, and the FastAPI deep dive.

## The three decks

| Deck | Scope | Slides |
|------|-------|-------:|
| `Modernizing-101.pptx` | Ideas deck: why modernize, the strangler fig method, data ownership, pattern catalog | 24 |
| `Modernizing-201.pptx` | Full implementation, end to end, one section per Part, plus the appendix | 83 |
| `Modernizing-201-FastAPI.pptx` | FastAPI async deep dive, deployment, testing (pytest/Testcontainers, Newman) | 43 |

The slide counts are the number of `## [NNN]` sections in the matching file under
`text/`.

## How the decks are maintained

No generator source exists for these decks, so every change is an in-place edit of the
committed `.pptx` files with a small toolkit vendored from the `cloud-native-design-patterns`
deck toolchain, under `scripts/`:

| Tool | Role |
|------|------|
| `scripts/deck_text.py` | pptx to Markdown (standard library only); `--write` regenerates `text/`, `--check` fails on drift, a missing or extra copy, or a slide without notes |
| `scripts/deck_edit.py` | applies an edit file to a deck in place (python-pptx and lxml): `replace`, `set_notes`, `set_code`, `set_text`, `clone_slide`, `replace_picture` and layout operations; slides are addressed by `sldId`; `--dry-run` prints the text diff |
| `scripts/deck_font.py` | retargets title fonts to Red Hat Display across a `.pptx`, in place |
| `scripts/deck_render.sh` | soffice to PDF to PNG for selected slides; refuses to run without the brand fonts |
| `scripts/deck_fit.py` | checks a render for text outside its frame, over the page number or logo, off the slide, or on top of other text; needs the brand fonts, including Overpass |
| `scripts/deck_embed_fonts.py` | LibreOffice/UNO helper that embeds fonts into a throwaway copy, used only to generate correctly subset Red Hat EOT font data |
| `scripts/deck_inject_fonts.py` | splices the harvested Red Hat `.fntdata` into a pristine `.pptx` (content parts byte-for-byte unchanged); run after edits to re-embed |
| `presentation/lgtm-presentation/edits/` | the committed edit files: `<deck>.json` (edits in apply order) and `<deck>.fixN.json` (later repairs, each applied once) |

Rules for an edit:

- Edit files are applied once, to the committed deck. Every `replace` carries the exact
  match count it expects, so a second run fails instead of changing anything.
- New slides are clones of existing slides of the same deck; their figures come from
  the deck's own `png/` or `assets/` directories.
- A code slide is an excerpt of a real example file in this repository and names the
  example in its first comment line.
- After an edit run `python3 scripts/deck_text.py --write --root presentation/lgtm-presentation`,
  then render every changed slide with the brand fonts installed
  (`fc-list | grep -iE "Red Hat (Display|Text|Mono)"` to confirm they are present).

Run the tools from the repository root. `deck_edit.py`, `deck_font.py` and `deck_fit.py`
need python-pptx 1.0.2 (lxml comes with it); keep them in the `.venv-decks` virtual
environment at the repository root, never global. `deck_text.py` is standard library
only and runs with any Python 3. `DECK_BACKUP_DIR` keeps the pre-edit backup somewhere
other than the default, and `LO_PROFILE` selects the LibreOffice profile for rendering.

## The text copies

`text/<name>.md` is a Markdown copy of every deck: one section per slide
(`## [NNN] EYEBROW · Title (sldId N)`), code boxes as fenced blocks tagged with the chip
language, speaker notes as a `>` block. Keep these current with `deck_text.py --write`
so a deck cannot drift from its text copy unnoticed.

## Embedded fonts

Each committed `.pptx` embeds the Red Hat families (Display, Text, Mono) as subset EOT
font data under `ppt/fonts/*.fntdata`, with `embedTrueTypeFonts="1"` and a
`<p:embeddedFontLst>` in `ppt/presentation.xml`, so the decks render in the brand fonts on
a machine that does not have them installed. LibreOffice cannot save these decks directly
without reflowing the theme and pulling in large fallback fonts, so embedding is a two
step process: `deck_embed_fonts.py` embeds into a throwaway copy, then `deck_inject_fonts.py`
copies only the Red Hat font parts into the untouched committed deck. Re-run
`deck_inject_fonts.py` after any edit run so the embedded fonts match the final glyphs.

## Pins

- python-pptx 1.0.2, lxml 6.1.3 (its dependency), cairosvg 2.9.1, all in `.venv-decks`.
- Fonts: Red Hat Display, Red Hat Text, Red Hat Mono, and Overpass (for `deck_fit.py`),
  installed for fontconfig.

## Known cosmetic note

`deck_fit.py` reports a uniform ~4 to 5 pt overflow on the figure-caption text boxes. This
is inherited from the original r1.1 baselines (identical counts before and after this
rewrite) and is a sizing trait of those caption frames, not a regression from the content
edits.

## Status

Rebuilt on this workflow from the r1.1 baselines: slide and note content rewritten to
stand alone (no external chapter or book cross-references), voice cleaned to zero ban-tier,
notes tightened, the two embedded diagrams (chassis scorecard, mesh hero trace) made
standalone, and the Red Hat fonts embedded. The committed `.pptx` files here, their
`edits/` and their `text/` copies are the source of truth. The old per-deck generator
(`deck.js`, `deck-helpers.js`, npm packages) and the r1.1 baselines were retired and remain
in git history; `presentation/modernizing-*/png/` and `assets/` are kept as the figure and
cover image sources the edit files reference.
