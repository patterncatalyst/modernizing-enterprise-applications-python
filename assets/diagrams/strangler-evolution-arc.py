#!/usr/bin/env python3
"""ch.04 figure: strangler-evolution-arc -- the staged evolution this book
actually executes: four left-to-right snapshots, each a miniature topology
rather than a text label, re-grounded in this project's own six contexts
and real ports.

Four snapshots:
  1. Monolith (ch.08) -- one Django deployable, six in-process apps, one
     shared Postgres schema.
  2. Proxy-fronted monolith (ch.14) -- the ASGI strangler proxy stands in
     front; every call still passes straight through to the monolith
     unchanged.
  3. Incrementally strangled (ch.15-24) -- review and notification are live
     FastAPI services behind the proxy; the remaining four contexts still
     answer from the shrinking monolith.
  4. Fully extracted (ch.26) -- the proxy is now a flagless edge router in
     front of all six services + the Strawberry GraphQL gateway; the
     monolith is decommissioned from the running topology and kept frozen,
     unwired, as the "before" referent (per
     `final-monolith-free-topology.py`).

Sourced from: `_plans/build-plan.md` ("A. Approach"), `_docs/00-
introduction.md`, and this project's own `final-monolith-free-topology.py`
for the end state and ports.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1560, 560

PANEL_W, GUTTER = 350, 30
X0, PANEL_Y, PANEL_H = 30, 90, 360

panels = [
    {"x": X0 + i * (PANEL_W + GUTTER), "y": PANEL_Y, "w": PANEL_W, "h": PANEL_H, "fill": fill, "label": label}
    for i, (label, fill) in enumerate([
        ("1. Monolith", "#ffffff"),
        ("2. Proxy-fronted", "#ffffff"),
        ("3. Partially strangled", "#ffffff"),
        ("4. Fully extracted", "#eaf4ec"),
    ])
]

nodes = []
edges = []

# ---- panel 1: the monolith, as designed ------------------------------------
p1 = panels[0]
mono1 = node(p1["x"] + 30, p1["y"] + 140, PANEL_W - 60, 90,
             ["Django monolith", "6 apps, 1 shared Postgres schema"], style="box")
nodes.append(mono1)

# ---- panel 2: a proxy stands in front; 100% of traffic still passes through
p2 = panels[1]
proxy2 = node(p2["x"] + 30, p2["y"] + 40, PANEL_W - 60, 70, ["ASGI strangler proxy", "all routes -> monolith"], style="box")
mono2 = node(p2["x"] + 30, p2["y"] + 200, PANEL_W - 60, 90, ["Django monolith", "unchanged, 6 apps"], style="box")
nodes += [proxy2, mono2]
edges.append(connect(proxy2, mono2, label="100% of traffic"))

# ---- panel 3: review + notification extracted; four contexts remain -------
p3 = panels[2]
proxy3 = node(p3["x"] + 30, p3["y"] + 20, PANEL_W - 60, 60, ["ASGI strangler proxy", "full-path content-based routing"], style="box")
rev3 = node(p3["x"] + 20, p3["y"] + 120, (PANEL_W - 70) / 2, 60, ["Review", "extracted"], style="accent")
notif3 = node(p3["x"] + 30 + (PANEL_W - 70) / 2 + 10, p3["y"] + 120, (PANEL_W - 70) / 2, 60, ["Notification", "extracted"], style="accent")
mono3 = node(p3["x"] + 30, p3["y"] + 230, PANEL_W - 60, 90,
             ["Django monolith", "inventory, payment, shipping, order"], style="box")
nodes += [proxy3, rev3, notif3, mono3]
edges += [
    connect(proxy3, rev3),
    connect(proxy3, notif3),
    connect(proxy3, mono3, label="remaining 4 contexts"),
]

# ---- panel 4: fully extracted; monolith frozen and unwired -----------------
p4 = panels[3]
router4 = node(p4["x"] + 30, p4["y"] + 20, PANEL_W - 60, 60, ["Edge router :8888", "flagless, permanent"], style="accent")
services4 = node(p4["x"] + 30, p4["y"] + 110, PANEL_W - 60, 80,
                  ["6 FastAPI services + GraphQL gateway", "each owns its schema"], style="accent")
mono4 = node(p4["x"] + 30, p4["y"] + 250, PANEL_W - 60, 70, ["Django monolith", "FROZEN, unwired, in-repo"], style="ghost")
nodes += [router4, services4, mono4]
edges.append(connect(router4, services4))

bands = panels

timeline_y = 480
timeline_edge = [{"x1": 60, "y1": timeline_y, "x2": 1500, "y2": timeline_y, "amber": True,
                   "label": "extraction order: review -> notification -> inventory -> payment -> shipping -> order + gateway"}]

notes = [
    {"x": W / 2, "y": 32,
     "text": "the staged evolution this book executes: monolith -> proxy-fronted -> partially strangled -> fully extracted",
     "anchor": "middle", "bold": True, "size": 16.5},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/build-plan.md (\"A. Approach\") and final-monolith-free-topology.py.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "strangler-evolution-arc", W, H,
    bands=bands,
    nodes=nodes,
    edges=edges + timeline_edge,
    notes=notes,
)
