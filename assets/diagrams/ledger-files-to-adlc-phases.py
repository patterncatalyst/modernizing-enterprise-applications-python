#!/usr/bin/env python3
"""ch.02 figure: ledger-files-to-adlc-phases -- maps this project's own
ledger (the build plan, the per-iteration plans, the decision log, and the
reconciliation log) onto the ADLC's seven phases: "Frame -> Map -> Plan ->
Generate -> Verify -> Operate -> Reconcile."

Phase glosses are this project's own tooling column, which differs from the
Java sibling by design: Map substitutes manual reconnaissance plus the
`lgtm-python` skill, because no Quarkus-Agent-MCP or Camel-MCP equivalent
exists for this stack; Plan/Generate/Verify run through the `lgtm-relay`
tiering (Opus plan -> Sonnet execute -> Opus validate).

Ledger-to-phase ties:
- The build plan + each iteration's own per-iteration plan under Plan: the
  master phase table plus an iteration-by-iteration backlog, and the
  per-iteration file that breaks the iteration into lanes and acceptance
  criteria before any of them start (each file's own header records its
  approval status).
- The SAME per-iteration plan under Generate/Verify: its lanes and
  acceptance criteria are what Sonnet executes against and Opus validates
  against; the build plan's status is updated as each iteration lands.
- The decision log + reconciliation log under Reconcile: the decision log
  appends one row per decision outcome; the reconciliation log is this
  project's own artifact-vs-source log -- live here, one section appended per
  iteration's reconcile pass (zero unexplained drift).
- The feedback bus (Reconcile -> build plan) is the same phase-table row:
  Reconcile also updates the build plan's status, so the discipline loops
  back into the same file Plan produced.
- Plan and Verify are tinted "human gate" (style=user): plan approval before
  any code gets written, and an equivalence sign-off before a result counts
  as sufficient evidence.

No codenames; generic/public names only.
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
    ("map", "Map", "manual recon + a scaffolding skill", "sub"),
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

# ---- tier 2: the ledger this project actually keeps -----------------------
LEDGER_Y, LEDGER_H = 235, 110
LEDGER = [
    ("build_plan", 40, 288, ["Build plan", "phase table, iteration backlog,", "status per iteration"], "box"),
    ("rnn_plan", 348, 288, ["Per-iteration plan", "lanes + acceptance criteria,", "header records approval status"], "box"),
    ("decisions", 656, 288, ["Decision log", "append decision outcomes --", "rows: fixed / accepted / proposed"], "box"),
    ("reconciliation", 964, 288, ["Reconciliation log", "append artifact-vs-source verdicts --", "live: one section per iteration"], "box"),
    ("lgtm_python", 1272, 288, ["a scaffolding skill", "Map/Generate substitute --", "no MCP equivalent"], "ghost"),
]
ledger_nodes = {}
for key, x, w, lines, style in LEDGER:
    n = node(x, LEDGER_Y, w, LEDGER_H, lines, style=style)
    ledger_nodes[key] = n
    nodes.append(n)

ledger_band = {"x": 20, "y": 186, "w": W - 40, "h": 174,
               "label": "The ledger this project keeps -- checkable against the repository as you read",
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
            label="append drift verdict -- zero unexplained drift", ly=12),
]

# ---- feedback bus: Reconcile also updates the build plan's status ---------
BUS_Y = 380
dec = ledger_nodes["decisions"]
bp = ledger_nodes["build_plan"]
dec_x = dec["x"] + dec["w"] / 2
bp_x = bp["x"] + bp["w"] / 2
edges += [
    {"x1": dec_x, "y1": dec["y"] + dec["h"], "x2": dec_x, "y2": BUS_Y, "dashed": True, "amber": True},
    {"x1": dec_x, "y1": BUS_Y, "x2": bp_x, "y2": BUS_Y, "dashed": True, "amber": True,
     "label": "Reconcile also updates the build plan's status -- same discipline"},
    {"x1": bp_x, "y1": BUS_Y, "x2": bp_x, "y2": bp["y"] + bp["h"], "dashed": True, "amber": True},
]

# ---- tier 3: the resume mechanism, fed by the files that carry it ---------
RESUME_Y, RESUME_H = 430, 120
resume = node(270, RESUME_Y, 1060, RESUME_H, [
    "Resume mechanism: the iteration's own plan header, read again",
    "Each per-iteration plan opens with its own approval/status line",
    "The build plan gains a status row per iteration, naming what landed and what didn't",
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
     "text": "The ledger's files, mapped onto the ADLC's own phases",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "Plan and Verify (blue) are this project's two human gates; Reconcile (green) is where the ledger actually gets written",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 46,
     "text": "Sourced from the project's build plan (its phase table and per-iteration status rows).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": H - 16,
     "text": "Unlike a chapter-era snapshot frozen at authoring time, the reconciliation log here is a live, append-only record by the time this chapter is read.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "ledger-files-to-adlc-phases", W, H,
    bands=[phase_band, ledger_band, resume_band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
