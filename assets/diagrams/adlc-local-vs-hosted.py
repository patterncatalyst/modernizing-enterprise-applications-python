#!/usr/bin/env python3
"""ch.05 figure: adlc-local-vs-hosted.

The agentic loop split into a "local" execution path (local coding agent +
uv + Docker Engine, running pytest/Testcontainers against a real Postgres)
and a "hosted" path (hosted AI platform + GitHub Actions CI, running the
same `code-ci.yml` gates), side by side. Steps 1, 6, 7, 8 are
shared/common; steps 2-5 branch into the two paths and converge again.

Sourced from `_plans/build-plan.md` ("A. Approach" -- toolchain) and
`.github/workflows/code-ci.yml`'s own existence as the hosted equivalent of
a local `uv run pytest` run.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 980, 660

NW, NH = 200, 76

# shared column (steps 1, 8, 7, 6 top to bottom)
shared_x = 60
n1 = node(shared_x, 45, NW, NH, ["1. Express intent", "(Minutes)"], style="accent")
n8 = node(shared_x, 250, NW, NH, ["8. Learn & iterate", "(Ongoing)"], style="accent")
n7 = node(shared_x, 390, NW, NH, ["7. Monitoring & observability", "(Continuous)"], style="accent")
n6 = node(shared_x, 530, NW, NH, ["6. Deploy & ship", "(Minutes)"], style="accent")

# local band (steps 2-5)
local_x = 360
l2 = node(local_x, 110, NW, NH, ["2. Agent understands", "local coding agent"], style="accent")
l3 = node(local_x, 250, NW, NH, ["3. Agent implements", "uv + local coding agent"], style="accent")
l4 = node(local_x, 390, NW, NH, ["4. Agent tests + docs", "pytest + Testcontainers"], style="accent")
l5 = node(local_x, 530, NW, NH, ["5. Human review", "local diff + Docker Engine"], style="accent")

# hosted band (steps 2-5)
hosted_x = 700
h2 = node(hosted_x, 110, NW, NH, ["2. Agent understands", "hosted AI platform"], style="user")
h3 = node(hosted_x, 250, NW, NH, ["3. Agent implements", "hosted AI platform"], style="user")
h4 = node(hosted_x, 390, NW, NH, ["4. Agent tests + docs", "GitHub Actions code-ci.yml"], style="user")
h5 = node(hosted_x, 530, NW, NH, ["5. Human review", "PR + hosted AI platform"], style="user")

nodes = [n1, n8, n7, n6, l2, l3, l4, l5, h2, h3, h4, h5]

edges = [
    # branch: n1 -> l2 stays low (just under n1), n1 -> h2 exits high and
    # arcs over l2's box so the two branch lines don't cross l2.
    {"x1": 260, "y1": 95, "x2": 360, "y2": 140},
    {"x1": 260, "y1": 60, "x2": 700, "y2": 118},
    connect(l2, l3), connect(l3, l4), connect(l4, l5),
    connect(h2, h3), connect(h3, h4), connect(h4, h5),
    connect(l5, n6),
    # h5 -> n6 runs along the row's bottom rail so it doesn't cut through l5
    {"x1": 700, "y1": 606, "x2": 260, "y2": 598},
    connect(n6, n7), connect(n7, n8),
    connect(n8, n1, label="cycle repeats"),
]

bands = [
    {"x": 340, "y": 90, "w": 240, "h": 536, "label": "local", "fill": "#eaf4ec"},
    {"x": 680, "y": 90, "w": 240, "h": 536, "label": "hosted", "fill": "#eef4fb"},
]

notes = [
    {"x": 490, "y": 20, "text": "The Agentic Loop: Local vs. Hosted Execution",
     "anchor": "middle", "bold": True, "size": 18},
]

g.emit("adlc-local-vs-hosted", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
