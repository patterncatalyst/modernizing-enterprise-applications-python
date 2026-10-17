#!/usr/bin/env python3
"""ch.05 figure: sdlc-vs-adlc -- the centerpiece.

Traditional SDLC (8 steps, weeks-months, muted/neutral) vs. the agentic
SDLC (8 steps, hours-days, green) with a transformation arrow and a "Key
Differences" table. Generic throughout -- no stack-specific tool names, so
nothing to re-author here beyond the shared house style.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, octagon_positions, connect

g.OUT = os.path.dirname(__file__)

W, H = 1950, 1080
NW, NH = 170, 84

traditional_labels = [
    ["1. Requirements & planning", "(Days-Weeks)"],
    ["2. System design", "(Weeks)"],
    ["3. Implementation & coding", "(Weeks-Months)"],
    ["4. Testing & QA", "(Days-Weeks)"],
    ["5. Code review", "(Days)"],
    ["6. Deploy & release", "(Days)"],
    ["7. Monitoring & observability", "(Ongoing)"],
    ["8. Feedback & iteration", "(Continuous)"],
]
agentic_labels = [
    ["1. Express intent", "(Minutes)"],
    ["2. Agent understands", "(Seconds)"],
    ["3. Agent implements", "(Minutes)"],
    ["4. Agent tests + docs", "(Minutes)"],
    ["5. Human review", "(Min-Hours)"],
    ["6. Deploy & ship", "(Minutes)"],
    ["7. Monitoring & observability", "(Continuous)"],
    ["8. Learn & iterate", "(Ongoing)"],
]

left_centers = octagon_positions(500, 480, 320, 230)
right_centers = octagon_positions(1500, 480, 320, 230)

left_nodes = [node(cx - NW / 2, cy - NH / 2, NW, NH, lbl, style="kernel")
              for (cx, cy), lbl in zip(left_centers, traditional_labels)]
right_nodes = [node(cx - NW / 2, cy - NH / 2, NW, NH, lbl, style="accent")
               for (cx, cy), lbl in zip(right_centers, agentic_labels)]

edges = []
for i in range(8):
    j = (i + 1) % 8
    lbl = "cycle repeats" if i == 7 else None
    edges.append(connect(left_nodes[i], left_nodes[j], label=lbl))
    edges.append(connect(right_nodes[i], right_nodes[j], label=lbl))

# transformation arrow between the two loops
edges.append({"x1": 905, "y1": 480, "x2": 1095, "y2": 480, "amber": True})

# Key Differences table
diff_rows = [
    ("Sequential handoffs", "Fluid agent flow"),
    ("Human codes everything", "Human guides, agent executes"),
    ("Docs as afterthought", "Docs generated inline"),
    ("Manual incident response", "Agent-assisted remediation"),
]
BW, BH = 320, 42
left_x, right_x = 590, 940
row_y0, row_gap = 822, 58

diff_nodes = []
diff_edges = []
for i, (before, after) in enumerate(diff_rows):
    y = row_y0 + i * row_gap
    bnode = node(left_x, y, BW, BH, [before], style="kernel")
    anode = node(right_x, y, BW, BH, [after], style="accent")
    diff_nodes += [bnode, anode]
    diff_edges.append(connect(bnode, anode, amber=True))

bands = [
    {"x": 560, "y": 790, "w": 880, "h": 270, "label": "Key differences", "fill": "#fafafa"},
]

notes = [
    {"x": 1000, "y": 40, "text": "Software Development Life Cycle: Before and After Agentic Coding Tools",
     "anchor": "middle", "bold": True, "size": 20},
    {"x": 500, "y": 465, "text": "Traditional SDLC", "anchor": "middle", "bold": True, "size": 14},
    {"x": 500, "y": 485, "text": "Weeks-Months per cycle", "anchor": "middle", "size": 12},
    {"x": 1500, "y": 465, "text": "Agentic SDLC", "anchor": "middle", "bold": True, "size": 14},
    {"x": 1500, "y": 485, "text": "Hours-Days per cycle", "anchor": "middle", "size": 12},
    {"x": 1000, "y": 455, "text": "Transformation", "anchor": "middle", "bold": True, "size": 13},
]

g.emit(
    "sdlc-vs-adlc", W, H,
    bands=bands,
    nodes=left_nodes + right_nodes + diff_nodes,
    edges=edges + diff_edges,
    notes=notes,
)
