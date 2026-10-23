#!/usr/bin/env python3
"""ch.05 figure: agentic-sdlc-to-adlc.

Maps the 8-step agentic SDLC onto this book's 7-phase ADLC (Frame -> Map ->
Plan -> Generate -> Verify -> Operate -> Reconcile, per `_plans/build-
plan.md` section F.1), marking the two human gates: plan approval and
equivalence sign-off. Phase glosses are this project's own tooling column,
which differs from the Java sibling by design: Map has no Quarkus-Agent-
MCP / Camel-MCP equivalent to lean on (DRQ-020), so it substitutes manual
reconnaissance plus the `lgtm-python` skill.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1670, 440

TOP_Y = 110
BOT_Y = 330
NH = 74

top_steps = [
    ["1. Express intent", "(Minutes)"],
    ["2. Agent understands", "(Seconds)"],
    ["3. Agent implements", "(Minutes)"],
    ["4. Agent tests + docs", "(Minutes)"],
    ["5. Human review", "(Min-Hours)"],
    ["6. Deploy & ship", "(Minutes)"],
    ["7. Monitoring & observability", "(Continuous)"],
    ["8. Learn & iterate", "(Ongoing)"],
]
top_x = [40, 240, 440, 640, 840, 1040, 1240, 1440]
top_w = 190
top_nodes = [node(x, TOP_Y, top_w, NH, lbl, style="accent") for x, lbl in zip(top_x, top_steps)]

bottom_phases = [
    ["Frame", "author intent + PRD"],
    ["Map", "manual recon + lgtm-python"],
    ["Plan", "Opus drafts the step plan"],
    ["Generate", "Sonnet: scaffold + code + tests"],
    ["Verify", "Opus: pytest/Newman + scan"],
    ["Operate", "flagged rollout + LGTM"],
    ["Reconcile", "ledger + drift record"],
]
# x/w chosen so each phase sits roughly under the agentic step(s) it maps from
bottom_x = [60, 260, 380, 535, 850, 1100, 1450]
bottom_w = [150, 150, 140, 230, 170, 270, 170]
bottom_nodes = [node(x, BOT_Y, w, NH, lbl, style="box")
                for x, w, lbl in zip(bottom_x, bottom_w, bottom_phases)]

# step index (0-based) -> bottom phase index/indices it maps to
mapping = [
    (0, 0),   # Express intent -> Frame
    (1, 1),   # Agent understands -> Map
    (2, 2),   # Agent implements -> Plan
    (2, 3),   # Agent implements -> Generate (spans both; plan gate sits here)
    (3, 3),   # Agent tests + docs -> Generate
    (4, 4),   # Human review -> Verify
    (5, 5),   # Deploy & ship -> Operate
    (6, 5),   # Monitoring & observability -> Operate
    (7, 6),   # Learn & iterate -> Reconcile
]
edges = [connect(top_nodes[i], bottom_nodes[j], dashed=True) for i, j in mapping]

# sequential flow along each row
for i in range(7):
    edges.append(connect(top_nodes[i], top_nodes[i + 1]))
for i in range(6):
    edges.append(connect(bottom_nodes[i], bottom_nodes[i + 1]))

# two human gates, marked where they land in both rows
gate_nodes = [
    node(330, 235, 220, 40, ["GATE: plan approval"], style="accent"),
    node(720, 235, 260, 40, ["GATE: equivalence sign-off"], style="accent"),
]

bands = [
    {"x": 20, "y": 70, "w": 1630, "h": 130, "label": "The agentic SDLC (8 steps)", "fill": "#eaf4ec"},
    {"x": 20, "y": 290, "w": 1630, "h": 130, "label": "This book's ADLC (7 phases)", "fill": "#fafafa"},
]

notes = [
    {"x": 835, "y": 30, "text": "From the Agentic SDLC to This Book's ADLC",
     "anchor": "middle", "bold": True, "size": 19},
    {"x": 835, "y": 55, "text": "dashed lines map each agentic-SDLC step to the ADLC phase(s) it corresponds to; two human gates block progress",
     "anchor": "middle", "size": 12, "color": "#555555"},
]

g.emit(
    "agentic-sdlc-to-adlc", W, H,
    bands=bands,
    nodes=top_nodes + bottom_nodes + gate_nodes,
    edges=edges,
    notes=notes,
)
