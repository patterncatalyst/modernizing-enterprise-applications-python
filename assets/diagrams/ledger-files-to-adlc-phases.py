#!/usr/bin/env python3
"""ch.02 figure: ledger-files-to-adlc-phases -- maps this project's own
ledger files (`_plans/build-plan.md`, `_plans/rNN-build-plan.md`,
`_plans/decisions.md`, `_plans/reconciliation.md`) onto the ADLC's seven
phases, using this book's own phase table (`_plans/build-plan.md` section
F.1, lines ~570-576): "Frame -> Map -> Plan -> Generate -> Verify ->
Operate -> Reconcile."

Phase glosses are this project's own tooling column, which differs from
the Java sibling on purpose (DRQ-020): Map substitutes manual
reconnaissance plus the `lgtm-python` skill, because no Quarkus-Agent-MCP
or Camel-MCP equivalent exists for this stack; Plan/Generate/Verify run
through the `lgtm-relay` tiering (Opus plan -> Sonnet execute -> Opus
validate).

File-to-phase ties:
- `build-plan.md` + each iteration's own `_plans/rNN-build-plan.md` under
  Plan: the master phase table plus an iteration-by-iteration backlog, and
  the per-iteration file that "breaks the iteration into lanes and
  acceptance criteria before any of them start" (each file's own header
  line records its approval status).
- The SAME `rNN-build-plan.md` under Generate/Verify: its lanes and
  acceptance criteria are what Sonnet executes against and Opus validates
  against; `build-plan.md`'s own section J iteration table is updated as
  each iteration's work lands.
- `decisions.md` + `reconciliation.md` under Reconcile: `decisions.md`
  appends one `DRQ-NNN` row per decision outcome; `reconciliation.md` is
  this project's own artifact-vs-source reconciliation log -- unlike the
  Java sibling's chapter-era snapshot, this file is LIVE here: over 1,900
  lines, one section appended per iteration's reconcile pass (section F.1,
  requirement R4: "zero unexplained drift").
- The feedback bus (Reconcile -> build-plan.md) is the same phase-table
  row: Reconcile also "updates build-plan status" -- so the discipline
  loops back into the same file Plan produced.
- Plan and Verify are tinted "human gate" (style=user): plan approval
  before any code gets written, and an equivalence sign-off before a
  result counts as sufficient evidence.

Sourced from `_plans/build-plan.md` (section F.1's phase table, section J's
iteration rows) and `_plans/reconciliation.md` (its own header + "how to
use this file" section). No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1600, 680

# ---- tier 1: the seven ADLC phases, as this project states them ----------
PHASE_Y, PHASE_H, PHASE_W, GUTTER, PHASE_X0 = 90, 70, 200, 20, 40
PHASES = [
    ("frame", "Frame", "human states intent + PRD", "sub"),
    ("map", "Map", "manual recon + lgtm-python", "sub"),
    ("plan", "Plan", "Opus drafts the step plan", "user"),
    ("generate", "Generate", "Sonnet writes code + tests", "box"),
    ("verify", "Verify", "Opus validates: pytest/Newman", "user"),
    ("operate", "Operate", "deploy behind a flag", "sub"),
    ("reconcile", "Reconcile", "records the outcome", "accent"),
]
phase_nodes = {}
nodes = []
for i, (key, name, gloss, style) in enumerate(PHASES):
    x = PHASE_X0 + i * (PHASE_W + GUTTER)
    n = node(x, PHASE_Y, PHASE_W, PHASE_H, [name, gloss], style=style)
    phase_nodes[key] = n
    nodes.append(n)

phase_band = {"x": 20, "y": 68, "w": W - 40, "h": 112,
              "label": "ADLC phases -- this project's own cycle (Frame -> Map -> Plan -> Generate -> Verify -> Operate -> Reconcile)",
              "fill": "#ffffff"}

# ---- tier 2: the ledger files this project actually keeps -----------------
LEDGER_Y, LEDGER_H = 235, 110
LEDGER = [
    ("build_plan", 40, 288, ["_plans/build-plan.md", "phase table, iteration backlog,", "section J status per iteration"], "box"),
    ("rnn_plan", 348, 288, ["_plans/rNN-build-plan.md", "lanes + acceptance criteria,", "header records approval status"], "box"),
    ("decisions", 656, 288, ["_plans/decisions.md", "append decision outcomes --", "DRQ rows: fixed / accepted / proposed"], "box"),
    ("reconciliation", 964, 288, ["_plans/reconciliation.md", "append artifact-vs-source verdicts --", "LIVE: 1,900+ lines by r10"], "box"),
    ("lgtm_python", 1272, 288, ["lgtm-python skill", "Map/Generate substitute --", "no MCP equivalent (DRQ-020)"], "ghost"),
]
ledger_nodes = {}
for key, x, w, lines, style in LEDGER:
    n = node(x, LEDGER_Y, w, LEDGER_H, lines, style=style)
    ledger_nodes[key] = n
    nodes.append(n)

ledger_band = {"x": 20, "y": 186, "w": W - 40, "h": 174,
               "label": "This project's own `_plans/` files -- checkable against the repository as you read",
               "fill": "#fafafa"}

# ---- phase -> file edges (clear space between the two bands) --------------
edges = [
    connect(phase_nodes["map"], ledger_nodes["lgtm_python"], dashed=True),
    connect(phase_nodes["plan"], ledger_nodes["build_plan"]),
    connect(phase_nodes["plan"], ledger_nodes["rnn_plan"]),
    connect(phase_nodes["generate"], ledger_nodes["rnn_plan"], label="lanes executed", ly=-18),
    connect(phase_nodes["verify"], ledger_nodes["reconciliation"], label="equivalence-gate result recorded", ly=14),
    connect(phase_nodes["reconcile"], ledger_nodes["decisions"], amber=True, label="append decision outcomes", ly=-16),
    connect(phase_nodes["reconcile"], ledger_nodes["reconciliation"], amber=True,
            label="append drift verdict -- R4: zero unexplained drift", ly=12),
]

# ---- feedback bus: Reconcile also updates build-plan.md's section J -------
BUS_Y = 380
dec = ledger_nodes["decisions"]
bp = ledger_nodes["build_plan"]
dec_x = dec["x"] + dec["w"] / 2
bp_x = bp["x"] + bp["w"] / 2
edges += [
    {"x1": dec_x, "y1": dec["y"] + dec["h"], "x2": dec_x, "y2": BUS_Y, "dashed": True, "amber": True},
    {"x1": dec_x, "y1": BUS_Y, "x2": bp_x, "y2": BUS_Y, "dashed": True, "amber": True,
     "label": "Reconcile also appends a build-plan.md section J row -- same file, same discipline"},
    {"x1": bp_x, "y1": BUS_Y, "x2": bp_x, "y2": bp["y"] + bp["h"], "dashed": True, "amber": True},
]

# ---- tier 3: the resume mechanism, fed by the files that carry it ---------
RESUME_Y, RESUME_H = 430, 120
resume = node(270, RESUME_Y, 1060, RESUME_H, [
    "Resume mechanism: the iteration's own build-plan header, read again",
    "Each _plans/rNN-build-plan.md opens with its own approval/status line",
    "build-plan.md's section J gains one long row per iteration, naming what landed and what didn't",
    "Next session reads that header plus the lane definitions and continues",
], style="accent")
nodes.append(resume)

rnn_n = ledger_nodes["rnn_plan"]
edges.append(connect(rnn_n, resume, dashed=True, amber=True,
                      label="status line read again to resume", lx=260, ly=-6))

resume_band = {"x": 150, "y": 400, "w": 1300, "h": 180,
               "label": "Interruption and resume -- not hypothetical; this project's own checkpoint discipline",
               "fill": "#eaf4ec"}

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.02 -- The ledger's files, mapped onto the ADLC's own phases",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "Plan and Verify (blue) are this project's two human gates; Reconcile (green) is where the ledger actually gets written",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 46,
     "text": "Sourced from _plans/build-plan.md (section F.1's phase table, section J's iteration rows).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": H - 16,
     "text": "Unlike a chapter-era snapshot frozen at authoring time, reconciliation.md here is a LIVE, append-only log by the time this chapter is read.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "ledger-files-to-adlc-phases", W, H,
    bands=[phase_band, ledger_band, resume_band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
