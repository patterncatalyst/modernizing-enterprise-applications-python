#!/usr/bin/env python3
"""ch.08 figure: monolith-six-contexts: the structural claim this book spends
26 chapters undoing: one Django project, six in-process bounded-context apps,
one shared Postgres schema. Simpler than monolith-architecture.py
(which already shows the full view/service/model stack plus the smell
overlay): this figure's only job is the "apps, not services" framing: no
process boundary, no network hop, no per-context database between any of the
six.

Sourced from `examples/00-monolith/` (the order/inventory/payment/shipping/
notification/review app layout) and the chapter's own framing ("as built,"
all six contexts, review included). No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 560

# ---- the six context apps, one row, one deployable -------------------------
CONTEXTS = [
    ("order", "checkout aggregate, line items", "box"),
    ("inventory", "stock levels per SKU", "box"),
    ("payment", "charge capture against an order", "box"),
    ("shipping", "dispatch to an address", "box"),
    ("notification", "tell the customer what happened", "box"),
    ("review", "a rating on a purchased SKU", "box"),
]

COL_W, GUTTER, COL_X0, ROW_Y, ROW_H = 190, 18, 50, 150, 100
cols = {}
nodes = []
for i, (name, desc, style) in enumerate(CONTEXTS):
    x = COL_X0 + i * (COL_W + GUTTER)
    n = node(x, ROW_Y, COL_W, ROW_H, [name, desc], style=style)
    cols[name] = n
    nodes.append(n)

order_n = cols["order"]
order_mid_y = order_n["y"] + order_n["h"] / 2

# in-process calls fanning out from order into inventory/payment/shipping
# plain Python function calls in the same WSGI worker, same call stack.
# order -> inventory is adjacent, so it gets a direct line; payment/shipping
# share one bus below the row so no line crosses an intervening box.
# notification is NOT one of these: see the dashed outbox note below.
BUS_Y = ROW_Y + ROW_H + 30
ox = order_n["x"] + order_n["w"]
trunk_targets = ["payment", "shipping"]
farthest_x = cols[trunk_targets[-1]]["x"]

edges = [
    connect(order_n, cols["inventory"], amber=True),
    {"x1": ox, "y1": order_mid_y, "x2": ox, "y2": BUS_Y, "amber": True},
    {"x1": ox, "y1": BUS_Y, "x2": farthest_x, "y2": BUS_Y, "amber": True,
     "label": "in-process Python calls: no network hop between apps"},
]
for name in trunk_targets:
    t = cols[name]
    tx = t["x"] + t["w"] / 2
    ty = t["y"] + t["h"]
    edges.append({"x1": tx, "y1": BUS_Y, "x2": tx, "y2": ty, "amber": True})

# notification: reached asynchronously via the outbox, not an in-process call
notif_n = cols["notification"]
edges.append({"x1": ox, "y1": order_mid_y + 10, "x2": notif_n["x"] + notif_n["w"] / 2, "y2": notif_n["y"] + notif_n["h"],
              "dashed": True, "label": "async via outbox: not an in-process call"})

# ---- the one shared Postgres schema ---------------------------------------
PG_Y, PG_H = 400, 90
pg_band = {"x": 40, "y": PG_Y, "w": W - 80, "h": PG_H,
           "label": "PostgreSQL: one shared schema", "fill": "#fafafa"}
pg_box = node(W / 2 - 170, PG_Y + 28, 340, 44, ["one schema, nine tables (Fig. 8.4)"], style="sub")

db_edges = []
for name, n in cols.items():
    db_edges.append(connect(n, pg_box))

bands = [
    {"x": 20, "y": 70, "w": W - 40, "h": 300,
     "label": "Django project: one deployable (gunicorn), one WSGI process", "fill": "#ffffff"},
    pg_band,
]

notes = [
    {"x": W / 2, "y": 32, "text": "Six bounded contexts, one deployable: apps, not services",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56, "text": "no process boundary, no network hop, no per-context database: the opposite of what the extractions build",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": PG_Y + PG_H + 24,
     "text": "every context reads and writes the SAME schema directly: no context owns its tables exclusively (detail in monolith-shared-schema-er).",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/00-monolith/ (app layout: order/, inventory/, payment/, shipping/, notification/, review/, common/, config/).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "monolith-six-contexts", W, H,
    bands=bands,
    nodes=nodes + [pg_box],
    edges=edges + db_edges,
    notes=notes,
)
