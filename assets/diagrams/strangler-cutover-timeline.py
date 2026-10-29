#!/usr/bin/env python3
"""ch.14 figure: strangler-cutover-timeline -- the four runs that make up
the Review cutover's evidence trail, left to right, plus the still-open
decommission step as a forward reference (ghosted, ch. not-yet-reached).

Each step is a Newman run against examples/01-strangler-proxy on :8888,
all using the SAME unedited collection (tooling/newman/mea.postman_collection.json),
only the flag (and, in step 4, whether review-service is even up) changing:

  1. OFF (baseline)       -- reviews served by the monolith.    58/58 green
  2. ON (cutover)         -- reviews served by review-service.  58/58 green
  3. OFF again (reverted) -- reviews served by the monolith.    58/58 green
  4. Negative check       -- flag ON, review-service killed.    RED by design
                              (502 on every /api/reviews* request, not a
                              silently-passing 200) -- then restarted: green.

Decommissioning the monolith's review/ app is the one deliberate,
irreversible move still ahead -- shown ghosted, past a dashed boundary.

Sourced from examples/01-strangler-proxy/CUTOVER.md ("Evidence trail (all
green, post-fix)" and the summary table) and tooling/newman/GOLDEN-BASELINE.md
(the chunked-body bug and its fix, which is what made all four runs green
through a REAL WSGI socket rather than only the in-process test suite).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1480, 520

step_w, gap, y, h = 280, 40, 150, 140
xs = [60 + i * (step_w + gap) for i in range(4)]

step1 = node(xs[0], y, step_w, h,
             ["1. Baseline -- flag OFF", "reviews <- monolith", "58 / 58 green"], style="box")
step2 = node(xs[1], y, step_w, h,
             ["2. Cutover -- flag ON", "reviews <- review-service", "58 / 58 green"], style="accent")
step3 = node(xs[2], y, step_w, h,
             ["3. Reverted -- flag OFF", "reviews <- monolith again", "58 / 58 green"], style="box")
step4 = node(xs[3], y, step_w, h,
             ["4. Negative check", "flag ON, review-service killed", "RED by design: 502s, exit 1"],
             style="ink")

nodes = [step1, step2, step3, step4]
edges = [
    connect(step1, step2, amber=True, label="flip flag -> true"),
    connect(step2, step3, label="flip flag -> false"),
    connect(step3, step4, label="flip -> true, then kill review-service"),
]

step4b = node(xs[3], y + h + 90, step_w, h,
              ["4b. Restarted", "review-service back up", "16 / 16 green"], style="accent")
nodes.append(step4b)
edges.append(connect(step4, step4b, label="restart review-service"))

decomm = node(xs[3] + step_w + gap + 40, y, 260, h, ["5. Decommission", "(later iteration)", "monolith review/ removed"],
              style="ghost")
nodes.append(decomm)
edges.append(connect(step4b, decomm, dashed=True, label="only after this window closes"))

boundary = {
    "x": xs[3] + step_w + gap + 20, "y": 40, "w": 2, "h": H - 80,
    "label": "", "fill": "#999999",
}

notes = [
    {"x": W / 2, "y": 32,
     "text": "the Review cutover evidence trail: one unedited Newman suite, four runs",
     "anchor": "middle", "bold": True, "size": 18},

    {"x": xs[3] + step_w + gap + 30, "y": y - 14,
     "text": "reversibility window closes here",
     "anchor": "start", "size": 11, "color": "#555555"},

    {"x": 60, "y": H - 40,
     "text": "Runs 1-3 and 4b used the same unedited mea.postman_collection.json, only {{baseUrl}} and the flag changed.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 60, "y": H - 22,
     "text": "Run 4 proves the gate fails LOUD when the extracted service is down -- a silent 200 would be worse than a 502.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "strangler-cutover-timeline", W, H,
    bands=[boundary],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
