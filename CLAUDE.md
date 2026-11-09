# Modernizing Enterprise Applications: Python (FastAPI)

Chaptered Jekyll site (`_docs/`, `_parts/`) that modernizes one running monolith step by step: a
Django monolith migrated to FastAPI services, extracted one bounded context at a time behind a strangler proxy, with runnable code under
`examples/`, demo scripts under `demos/` and decks under `presentation/`. Planning notes live in
`_plans/` and are not published. `_docs/_adlc-traces/` is unpublished source material.

## Writing rules

- **Write like the EIP-Camel book** (`~/Dev/enterprise-integration-patterns-with-camel`): get to
  the point, show the code, state the trade-off, stop. Geewax tone; run
  `lgtm-professional-voice` on every change.
- **Length:** about 2,000 words of prose a chapter is the target and 2,500 the most. There is no
  floor: a chapter that is complete in fewer words stays that way. Never pad.
  `scripts/wordcount.sh` reports; `GATE=1` fails a chapter over 2,500.
- **Spine:** Learning objectives, Why this matters, the topic H2s, a `> **Decision**` callout, the
  AI callout, Build, run, observe, For deeper coverage. A section that teaches an established
  pattern (Strangler Fig, Anti-Corruption Layer, Transactional Outbox, Saga, CQRS, Event Sourcing,
  Change Data Capture and the like) may use `## Pattern: <Name>`.
- **No test names, no code narration, no self-reference.** Prose never names a test or a demo
  assertion and never walks a code block line by line. No "this chapter", "the example shows",
  "the suite". Exception: "By the end of this chapter you can:" before the objectives.
- **Measurements stay.** Numbers from the recorded runs (CUTOVER.md, MIGRATION.md, evidence) are
  facts the reader needs; keep them, with their unit and where they came from.
- **Build, run, observe:** the commands, what passes, then one bullet per experiment (what to
  change, what fails).
- **AI callout ("Explore with your agent"):** exactly one per technique chapter (03 to 31), a
  plain blockquote:

  ```
  > **🤖 Explore with your agent**
  >
  > "<runnable prompt naming the example's own services, endpoints, files and demo scripts, and the chapter's decision rule>"
  >
  > Check: <the command to run or what to look for>
  ```

  No HTML wrapper, no nested quote, never a claim about what an assistant does.
- **Figures** come from specs (`scripts/generate_diagram.py`, SVG + `.excalidraw`). Never
  hand-edit an SVG. Captions read `Figure N.x: <what it shows>`.
- **No em or en dashes** in reader-facing content: chapters, READMEs, `index.html`, `_parts/`,
  example pages, figure labels, deck text and notes.
- **Chapters stand alone:** no "Chapter 10", "ch04" or "as we saw earlier". Name the idea.
- No internal codes (rNN, DRQ-###, `_plans/` paths) in reader-facing files. Say "final project",
  never "capstone".
- Code in listings and codetabs never changes; a listing's label comment may be reworded.

## Gates before a commit

```bash
GATE=1 bash scripts/wordcount.sh
bash ~/.claude/skills/lgtm-professional-voice/scripts/scan.sh --tier ban .
python3 ~/Dev/lgtm-skills/skills/lgtm-host-scrub/scripts/host_ids.py check
```

Build the site in a `ruby` container (the host has no ruby-devel).

## Git

One `release/rNN` branch and PR per iteration, squash-merged on the owner's OK, then an `rNN.x`
tag and a notes-only release. Never commit to `main`. No home paths, account names or machine
details in any tracked file.
