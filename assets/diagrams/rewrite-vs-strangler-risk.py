#!/usr/bin/env python3
"""ch.03 figure: rewrite-vs-strangler-risk -- a risk-shape contrast between
the big-bang rewrite and the strangler fig.

LEFT -- the big-bang rewrite makes three bets simultaneously: it bets the
team correctly understood every piece of behavior the Django monolith had
accumulated; it bets a FastAPI rebuild of comparable scope can be built
faster than the old system decays; and it bets the business can tolerate a
long stretch where almost no new value ships to users. All three bets have
to land before a single irreversible cutover -- a rewrite that is not yet
feature-complete cannot be partially shipped.

RIGHT -- the strangler fig distributes that same risk across many small,
independently reversible steps instead of concentrating it into one
irreversible moment at the end. This project's own concrete anchor is the
first step: the review extraction (ch.15) is a small slice of the system,
and it is live behind the ASGI strangler proxy's flag before any other
bounded context has been touched. Because the monolith and the new service
run side by side behind that flag until the new service is proven
equivalent, the project can pause, slow down, or reverse a single
extraction without threatening anything else in flight.

Sourced from `_plans/build-plan.md` ("A. Approach") and
`examples/01-strangler-proxy/CUTOVER.md` (the review seam's own
OFF -> ON -> reversible -> negative-check discipline). No codenames;
generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 640

band_left = {"x": 20, "y": 60, "w": 710, "h": 540,
             "label": "BIG-BANG REWRITE -- risk concentrated, payoff late", "fill": "#fafafa"}
band_right = {"x": 770, "y": 60, "w": 710, "h": 540,
              "label": "STRANGLER FIG -- risk spread, payoff continuous", "fill": "#eaf4ec"}

# ---- LEFT: one irreversible bet, stacked -----------------------------------
bets = node(60, 120, 390, 150,
            ["Three bets, made at once",
             "1. team understood every old behavior",
             "2. new build outruns old-system decay",
             "3. business tolerates zero value for",
             "   quarters while nothing ships"],
            style="box")
cutover = node(60, 320, 390, 110,
               ["One irreversible cutover",
                "not feature-complete = not shippable;",
                "nothing ships until everything does"],
               style="accent")
payoff_l = node(60, 480, 390, 100,
                ["Payoff -- late, all-or-nothing",
                 "any one of the three bets failing",
                 "sinks the project"],
                style="box")

left_nodes = [bets, cutover, payoff_l]
left_edges = [
    connect(bets, cutover, amber=True, label="all three must land"),
    connect(cutover, payoff_l, amber=True, label="if it ships at all"),
]

# ---- RIGHT: many small, reversible, continuously shipping steps -----------
STEP_W, STEP_GUTTER = 150, 18
STEP_X0, STEP_Y = 800, 150
steps_meta = [
    ("Step 1", "review (ch.15) --", "ships behind a flag"),
    ("Step 2", "notification,", "same pattern"),
    ("Step 3", "inventory,", "same pattern"),
    ("Step 4", "payment, shipping,", "order, gateway"),
]
step_nodes = []
for i, (title, l1, l2) in enumerate(steps_meta):
    x = STEP_X0 + i * (STEP_W + STEP_GUTTER)
    step_nodes.append(node(x, STEP_Y, STEP_W, 110, [title, l1, l2], style="accent"))

step_edges = []
for i in range(len(step_nodes) - 1):
    step_edges.append(connect(step_nodes[i], step_nodes[i + 1]))

reversible = node(800, 360, STEP_W * 4 + STEP_GUTTER * 3, 110,
                   ["Reversible at every step",
                    "monolith and new service run side by",
                    "side -- pause, slow, or reverse any one",
                    "step without threatening the rest"],
                   style="box")

payoff_r = node(800, 500, STEP_W * 4 + STEP_GUTTER * 3, 80,
                ["Payoff -- continuous",
                 "value ships at every step, not just the last one"],
                style="box")

right_nodes = step_nodes + [reversible, payoff_r]
right_edges = step_edges + [connect(s, reversible) for s in step_nodes]
right_edges.append(connect(reversible, payoff_r))

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.03 -- same migration, two risk shapes: one irreversible bet versus many reversible steps",
     "anchor": "middle", "bold": True, "size": 16},

    {"x": STEP_X0 + (STEP_W * 4 + STEP_GUTTER * 3) / 2, "y": STEP_Y - 16,
     "text": "each step proven equivalent before the next one starts",
     "anchor": "middle", "size": 10.5, "color": "#2f5f3d"},

    {"x": 60, "y": 596,
     "text": "A rewrite that is not yet feature-complete cannot be partially shipped --",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 60, "y": 612,
     "text": "the third bet failing is usually what kills the project.",
     "anchor": "start", "size": 11, "color": "#555555"},

    {"x": 800, "y": 596,
     "text": "Risk is distributed across many small, independently reversible steps",
     "anchor": "start", "size": 11, "color": "#2f5f3d"},
    {"x": 800, "y": 612,
     "text": "instead of concentrated into one irreversible moment at the end.",
     "anchor": "start", "size": 11, "color": "#2f5f3d"},

    {"x": 20, "y": H - 14,
     "text": "Sourced from _plans/build-plan.md (\"A. Approach\") and examples/01-strangler-proxy/CUTOVER.md.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "rewrite-vs-strangler-risk", W, H,
    bands=[band_left, band_right],
    nodes=left_nodes + right_nodes,
    edges=left_edges + right_edges,
    notes=notes,
)
