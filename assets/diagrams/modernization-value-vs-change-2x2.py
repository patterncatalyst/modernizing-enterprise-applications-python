#!/usr/bin/env python3
"""ch.04 figure: modernization-value-vs-change-2x2 -- the strategic-value x
change-frequency quadrant used to decide which strategy fits a candidate
system, built as a plain in-generator quadrant (four bands + corner
labels), not a charting engine.

Plot a candidate system's strategic value against its change frequency, and
the quadrant it lands in suggests which strategy fits. This book's
monolith sits in exactly that quadrant by design: high strategic value (it
is the order-taking and fulfillment path for a shipping business), and on
the ease-of-migration rubric, difficult on data (one shared Postgres schema
with cross-app foreign keys, per `examples/00-monolith/SMELLS.md`) and
moderate everywhere else -- a believable, unglamorous candidate for
re-architecture.

Sourced from: `_plans/build-plan.md` ("A. Approach") and
`examples/00-monolith/SMELLS.md`.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node

g.OUT = os.path.dirname(__file__)

W, H = 1040, 820

PLOT_X, PLOT_Y, PLOT_W, PLOT_H = 160, 110, 760, 600
HALF_W, HALF_H = PLOT_W / 2, PLOT_H / 2

q_top_left = {"x": PLOT_X, "y": PLOT_Y, "w": HALF_W, "h": HALF_H,
              "label": "Quick wins", "fill": "#fafafa"}
q_top_right = {"x": PLOT_X + HALF_W, "y": PLOT_Y, "w": HALF_W, "h": HALF_H,
               "label": "Strategic re-architecture", "fill": "#eaf4ec"}
q_bottom_left = {"x": PLOT_X, "y": PLOT_Y + HALF_H, "w": HALF_W, "h": HALF_H,
                  "label": "Retain", "fill": "#fafafa"}
q_bottom_right = {"x": PLOT_X + HALF_W, "y": PLOT_Y + HALF_H, "w": HALF_W, "h": HALF_H,
                   "label": "Reconsider / Repurchase", "fill": "#fafafa"}

q1_detail = node(PLOT_X + 20, PLOT_Y + 40, HALF_W - 40, 70,
                  ["rehost / replatform", "fast, low risk, no architecture change"], style="sub")
q2_detail = node(PLOT_X + HALF_W + 20, PLOT_Y + 40, HALF_W - 40, 70,
                  ["incremental re-architecture", "where this book's strategy applies"], style="sub")
q3_detail = node(PLOT_X + 20, PLOT_Y + HALF_H + 40, HALF_W - 40, 70,
                  ["no return on deeper investment", "leave it running as-is"], style="sub")
q4_detail = node(PLOT_X + HALF_W + 20, PLOT_Y + HALF_H + 40, HALF_W - 40, 70,
                  ["high cost, low payoff", "buy instead, or do not touch it"], style="sub")

monolith_marker = node(PLOT_X + HALF_W + 30, PLOT_Y + HALF_H - 130, HALF_W - 60, 80,
                        ["This book's Django monolith", "difficult data, moderate elsewhere"], style="accent")

nodes = [q1_detail, q2_detail, q3_detail, q4_detail, monolith_marker]

notes = [
    {"x": W / 2, "y": 36,
     "text": "prioritizing what to modernize: strategic value x change frequency",
     "anchor": "middle", "bold": True, "size": 17},

    {"x": PLOT_X - 12, "y": PLOT_Y + 14, "text": "high value", "anchor": "end", "size": 11.5, "color": "#555555"},
    {"x": PLOT_X - 12, "y": PLOT_Y + PLOT_H - 4, "text": "low value", "anchor": "end", "size": 11.5, "color": "#555555"},
    {"x": PLOT_X, "y": PLOT_Y + PLOT_H + 26, "text": "low change frequency", "anchor": "start", "size": 11.5, "color": "#555555"},
    {"x": PLOT_X + PLOT_W, "y": PLOT_Y + PLOT_H + 26, "text": "high change frequency", "anchor": "end", "size": 11.5, "color": "#555555"},

    {"x": PLOT_X - 70, "y": PLOT_Y + PLOT_H / 2, "text": "strategic value", "anchor": "middle", "size": 11.5, "bold": True, "color": "#1d1d1d"},
    {"x": PLOT_X + PLOT_W / 2, "y": PLOT_Y + PLOT_H + 52, "text": "change frequency", "anchor": "middle", "size": 11.5, "bold": True, "color": "#1d1d1d"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/build-plan.md (\"A. Approach\") and examples/00-monolith/SMELLS.md -- "
             "the monolith's own placement: high strategic value, difficult on data, moderate elsewhere.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "modernization-value-vs-change-2x2", W, H,
    bands=[q_top_left, q_top_right, q_bottom_left, q_bottom_right],
    nodes=nodes,
    edges=[],
    notes=notes,
)
