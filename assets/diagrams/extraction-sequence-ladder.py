#!/usr/bin/env python3
"""ch.00 figure: extraction-sequence-ladder -- the six extractions in the
order this book actually executes them, each rung tagged with its chapter
and the one new mechanism it forces, rising in difficulty left to right.

Order and rationale mirror the Java sibling's own "review first, and why"
argument, re-grounded in this project's real iteration history
(`_plans/build-plan.md` section J, r02-r07): review (REST leaf, shares the
monolith's schema, zero coupling) -> notification (first event-driven
service, transactional outbox) -> inventory (data ownership forces CDC via
Debezium + a gRPC reserve/release seam) -> payment (choreographed saga, the
ACID transaction's first casualty) -> shipping (orchestrated saga, same
problem solved the other way, DB-backed crash-resume) -> order + the
Strawberry GraphQL gateway (highest coupling, CQRS, saved for when the
mechanism is most proven).

Sourced from: `_plans/build-plan.md` (section J, the r02-r07 iteration
rows) and `_docs/00-introduction.md` for the running example and chapter
numbers.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 620

RUNGS = [
    ("1. Review", "REST leaf, shared schema", "box", 440),
    ("2. Notification", "async transactional outbox", "box", 360),
    ("3. Inventory", "CDC (Debezium) + gRPC seam", "box", 280),
    ("4. Payment", "choreographed saga", "box", 200),
    ("5. Shipping", "orchestrated saga, crash-resume", "box", 150),
    ("6. Order + Gateway", "CQRS + Strawberry GraphQL", "accent", 80),
]

COL_W, GUTTER = 210, 24
X0 = 50
nodes = []
step_nodes = []
for i, (title, pattern, style, y) in enumerate(RUNGS):
    x = X0 + i * (COL_W + GUTTER)
    n = node(x, y, COL_W, 90, [title, pattern], style=style)
    nodes.append(n)
    step_nodes.append(n)

edges = [connect(step_nodes[i], step_nodes[i + 1]) for i in range(len(step_nodes) - 1)]

axis_y = 560
axis_edge = [{"x1": 40, "y1": axis_y, "x2": 1460, "y2": axis_y, "amber": True,
              "label": "extraction order: increasing coupling, risk, and data entanglement"}]

notes = [
    {"x": W / 2, "y": 32,
     "text": "the extraction sequence: rising difficulty, not rising domain importance",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "the mechanism (proxy, anti-corruption layer, equivalence gate) is proven on the cheapest seam first",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": step_nodes[0]["x"] + COL_W / 2, "y": step_nodes[0]["y"] - 10,
     "text": "lowest coupling, lowest risk", "anchor": "middle", "size": 10, "color": "#555555"},
    {"x": step_nodes[-1]["x"] + COL_W / 2, "y": step_nodes[-1]["y"] - 10,
     "text": "highest coupling (the god order flow)", "anchor": "middle", "size": 10, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/build-plan.md (section J) and _docs/00-introduction.md.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "extraction-sequence-ladder", W, H,
    bands=[],
    nodes=nodes,
    edges=edges + axis_edge,
    notes=notes,
)
