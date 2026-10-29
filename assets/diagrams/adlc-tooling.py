#!/usr/bin/env python3
"""ch.05 figure: adlc-tooling -- the ADLC's seven phases annotated with the
REAL tool role at each one for this project's stack: the `lgtm-relay`
tiering (Opus plan -> Sonnet execute -> Opus validate), the `lgtm-python`
skill, and the three ledger files -- not a generic "coding assistant"
label.

This is a public repo naming its own tooling, including the gap:
Map has no live, version-matched MCP server to lean on the way the Java
sibling's Quarkus-Agent-MCP / Camel-MCP servers do (DRQ-020) -- it
substitutes manual reconnaissance plus the `lgtm-python` skill's scaffold
conventions. That gap is named in the figure, not glossed over.

Sourced from `_plans/build-plan.md` (section F.1's phase table, the
tooling column) and `_plans/decisions.md` (DRQ-020).
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1020, 1000
NW, NH = 230, 100


def heptagon_positions(cx, cy, rx, ry):
    """7 (x, y) centers around an ellipse, clockwise from the top."""
    angles = [-90 + i * (360 / 7) for i in range(7)]
    return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in angles]


phases = [
    ["1. Frame", "human: intent + PRD"],
    ["2. Map", "manual recon + a scaffolding skill", "(no MCP equivalent)"],
    ["3. Plan", "the relay -- Opus plans"],
    ["4. Generate", "the relay -- Sonnet executes", "+ a scaffolding skill"],
    ["5. Verify", "the relay -- Opus validates", "pytest + Newman + scan"],
    ["6. Operate", "a local-stack /", "cluster-stack skill + flags"],
    ["7. Reconcile", "the three ledger files"],
]

centers = heptagon_positions(500, 520, 340, 340)
styles = ["sub", "ghost", "accent", "accent", "accent", "box", "accent"]
nodes = [node(cx - NW / 2, cy - NH / 2, NW, NH, lbl, style=st)
         for (cx, cy), lbl, st in zip(centers, phases, styles)]

edges = []
for i in range(7):
    j = (i + 1) % 7
    lbl = "cycle repeats" if i == 6 else None
    edges.append(connect(nodes[i], nodes[j], label=lbl))

notes = [
    {"x": 500, "y": 40, "text": "ADLC Tooling: the Real Role at Each Phase",
     "anchor": "middle", "bold": True, "size": 20},
    {"x": 500, "y": 68, "text": "the relay tiers Plan/Generate/Verify; Map has no MCP equivalent and says so",
     "anchor": "middle", "size": 12, "color": "#555555"},
    {"x": 500, "y": H - 24,
     "text": "Sourced from _plans/build-plan.md (section F.1) and _plans/decisions.md.",
     "anchor": "middle", "size": 10, "color": "#777777"},
]

g.emit("adlc-tooling", W, H, nodes=nodes, edges=edges, notes=notes)
