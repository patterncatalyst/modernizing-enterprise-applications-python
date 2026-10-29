#!/usr/bin/env python3
"""ch.08 figure: monolith-architecture: the reference monolith "before"
picture. One Django project (`config/`) containing six bounded-context apps
(order, inventory, payment, shipping, notification, review), each drawn as a
DRF view -> services.py -> models.py stack, all built against ONE shared
Postgres schema (one set of per-app Django migrations, one DATABASES entry).
Sourced from `examples/00-monolith/SMELLS.md` and the app layout under
`examples/00-monolith/` (order/, inventory/, payment/, shipping/,
notification/, review/, common/, config/).

Smells drawn as the seams this book later cuts:
  - SMELL #1 (ch.26): `order/services.py::place_order()` -- the "god"
    checkout function -- reaches directly into inventory's, payment's, and
    shipping's services/models, with no anti-corruption layer at the seam.
  - SMELL #4 (ch.18/ch.19): cross-context FK joins living in the one shared
    schema (orders->customers, payments/shipments/notifications->orders,
    reviews->customers+inventory_items).
Notification is drawn as the one leg place_order() does NOT call directly:
SMELL #5/#6 (synchronous send + dual-write) are already CURED as of r03 --
place_order() writes a `common.models.OutboxEvent` row in the SAME
transaction instead, and a separate relay/consumer pair carries it to
`notification` asynchronously. Review is annotated as the first context
extracted (ch.15) -- this figure still draws it as designed (all six
contexts), per ch.08's own framing of the monolith "as built" before that
first cut.

No tool/product codenames beyond this stack's real ones (Django, DRF,
Postgres, Kafka); only the book's own context names otherwise.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1460, 760

# ---- context columns --------------------------------------------------
COL_W, GUTTER = 200, 24
COL_X0 = 40
CONTEXTS = [
    ("order", "OrderListCreateView", "order/services.py", "order/models.py", "box"),
    ("inventory", "InventoryListView", "inventory/services.py", "inventory/models.py", "box"),
    ("payment", "PaymentListView", "payment/services.py", "payment/models.py", "box"),
    ("shipping", "ShippingListView", "shipping/services.py", "shipping/models.py", "box"),
    ("notification", "(no view -- consumer only)", "notification/services.py", "notification/models.py", "box"),
    ("review", "ReviewListCreateView", "review/services.py", "review/models.py", "accent"),
]

CTRL_Y, ROW_H = 110, 55
SVC_Y = 180
REPO_Y = 250

cols = {}
for i, (ctx, view_lbl, svc_lbl, repo_lbl, style) in enumerate(CONTEXTS):
    x = COL_X0 + i * (COL_W + GUTTER)
    extra = ["(SMELL #1: god function)"] if ctx == "order" else []
    ctrl = node(x, CTRL_Y, COL_W, ROW_H, [view_lbl, f"{ctx} app"], style=style)
    svc = node(x, SVC_Y, COL_W, ROW_H, [svc_lbl] + extra, style=style)
    repo = node(x, REPO_Y, COL_W, ROW_H, [repo_lbl], style=style)
    cols[ctx] = {"x": x, "ctrl": ctrl, "svc": svc, "repo": repo}

nodes = []
edges = []
for ctx, c in cols.items():
    nodes += [c["ctrl"], c["svc"], c["repo"]]
    edges += [connect(c["ctrl"], c["svc"]), connect(c["svc"], c["repo"])]

# ---- god-function smell: place_order() reaches directly into inventory/   --
# payment/shipping's services (SMELL[ch.26]), with no ACL at the seam.      --
# Drawn as one highlighted "bus": a drop from order's services.py right     --
# edge into a lane below the context stacks, a trunk line across, and a    --
# branch rising into each target service's left edge -- so the arrows      --
# never cross through an intervening box. Notification is kept apart     --
# NOT one of the bus targets -- see the outbox lane below.
BUS_Y = 400
order_svc = cols["order"]["svc"]
order_edge_x = order_svc["x"] + order_svc["w"]
order_mid_y = order_svc["y"] + order_svc["h"] / 2

# order -> inventory is an adjacent column: a direct line, no detour needed.
inv_svc = cols["inventory"]["svc"]
edges.append(connect(order_svc, inv_svc, amber=True,
                      label="direct call, no ACL (SMELL #1)"))

bus_targets = ["payment", "shipping"]
farthest_x = cols[bus_targets[-1]]["svc"]["x"]
edges.append({"x1": order_edge_x, "y1": order_mid_y, "x2": order_edge_x, "y2": BUS_Y, "amber": True})
edges.append({"x1": order_edge_x, "y1": BUS_Y, "x2": farthest_x, "y2": BUS_Y, "amber": True,
              "label": "god function -- direct calls into other apps (SMELL #1)"})
for ctx in bus_targets:
    svc = cols[ctx]["svc"]
    bx = svc["x"]
    by = svc["y"] + svc["h"] / 2
    edges.append({"x1": bx, "y1": BUS_Y, "x2": bx, "y2": by, "amber": True})

# ---- the outbox lane: notification is reached asynchronously, not called --
# in-process -- SMELL #5/#6 already CURED (r03): place_order() writes an    --
# OutboxEvent row in its own transaction; a relay + consumer pair carries   --
# it the rest of the way.
outbox_box = node(cols["order"]["x"], 330, 260, 46,
                   ["common.models.OutboxEvent row", "written in the SAME transaction"], style="sub")
relay_box = node(640, 330, 260, 46,
                  ["outbox_relay -> Kafka order.placed", "order_placed_consumer"], style="sub")
nodes += [outbox_box, relay_box]
edges.append(connect(cols["order"]["svc"], outbox_box, label="SMELL #5/#6 CURED"))
edges.append({"x1": outbox_box["x"] + outbox_box["w"], "y1": outbox_box["y"] + outbox_box["h"] / 2,
              "x2": relay_box["x"], "y2": relay_box["y"] + relay_box["h"] / 2, "dashed": True})
edges.append({"x1": relay_box["x"] + relay_box["w"], "y1": relay_box["y"] + relay_box["h"] / 2,
              "x2": cols["notification"]["svc"]["x"] + cols["notification"]["svc"]["w"] / 2,
              "y2": cols["notification"]["svc"]["y"] + cols["notification"]["svc"]["h"],
              "dashed": True, "label": "async, at-least-once"})

# ---- PostgreSQL: one shared schema -------------------------------------
PG_BAND_Y, PG_BAND_H = 440, 150
pg_band = {"x": 20, "y": PG_BAND_Y, "w": W - 40, "h": PG_BAND_H,
           "label": "PostgreSQL -- one shared schema (per-app Django migrations, one DATABASES entry)", "fill": "#fafafa"}

TABLE_Y, TABLE_H = 470, 50
TABLE_W, TABLE_GUTTER = 148, 10
TABLE_NAMES = ["customers", "orders", "order_items", "inventory_items",
               "payments", "shipments", "notifications", "reviews", "outbox"]
tables = {}
for i, t in enumerate(TABLE_NAMES):
    x = 40 + i * (TABLE_W + TABLE_GUTTER)
    tables[t] = node(x, TABLE_Y, TABLE_W, TABLE_H, [t], style="sub")

table_nodes = list(tables.values())

repo_links = [
    ("order", "orders"), ("order", "order_items"), ("order", "outbox"),
    ("inventory", "inventory_items"),
    ("payment", "payments"),
    ("shipping", "shipments"),
    ("notification", "notifications"),
    ("review", "reviews"),
]
repo_edges = [connect(cols[ctx]["repo"], tables[t]) for ctx, t in repo_links]

# cross-context FK-join smell (SMELL #4): adjacent pairs get a direct
# highlighted line; non-adjacent pairs dip into a sub-lane beneath the
# table row so the line never crosses an intervening table box.
FK_DIP_Y = TABLE_Y + TABLE_H + 25


def fk_direct(a_name, b_name):
    return connect(tables[a_name], tables[b_name], amber=True)


def fk_dip(a_name, b_name):
    a, b = tables[a_name], tables[b_name]
    ax, ay = a["x"] + a["w"] / 2, a["y"] + a["h"]
    bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"]
    return [
        {"x1": ax, "y1": ay, "x2": ax, "y2": FK_DIP_Y, "amber": True},
        {"x1": ax, "y1": FK_DIP_Y, "x2": bx, "y2": FK_DIP_Y, "amber": True},
        {"x1": bx, "y1": FK_DIP_Y, "x2": bx, "y2": by, "amber": True},
    ]


fk_edges = []
fk_edges.append(fk_direct("orders", "customers"))
fk_edges += fk_dip("payments", "orders")
fk_edges += fk_dip("shipments", "orders")
fk_edges += fk_dip("notifications", "orders")
fk_edges += fk_dip("reviews", "customers")
fk_edges += fk_dip("reviews", "inventory_items")

nodes += table_nodes
edges += repo_edges
edges += fk_edges

bands = [
    {"x": 20, "y": 70, "w": W - 40, "h": 310,
     "label": "Django project -- one deployable (gunicorn), six bounded-context apps", "fill": "#ffffff"},
    pg_band,
]

notes = [
    {"x": W / 2, "y": 30, "text": "The reference monolith (before): six bounded contexts, one deployable, one shared schema",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56, "text": "one DRF REST API surface, documented by drf-spectacular's OpenAPI schema",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": W - 40, "y": 420,
     "text": "SMELL #2: place_order() wraps inventory + order + payment + shipment + the outbox write in ONE transaction.atomic() spanning five contexts (ACID -> ACD).",
     "anchor": "end", "size": 10.5, "color": "#555555"},

    {"x": 40, "y": 598,
     "text": "SMELL #4: FK joins cross bounded-context boundaries freely inside the one shared schema -- "
             "orders->customers, payments/shipments/notifications->orders, reviews->customers+inventory_items.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": 614,
     "text": "common.Customer is a shared-kernel entity (not its own bounded context) FK'd directly from order, notification, and review.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": cols["review"]["x"] + COL_W / 2, "y": 95,
     "text": "review: first context extracted", "anchor": "middle", "bold": True, "size": 11.5,
     "color": "#3d7a4e"},
    {"x": cols["review"]["x"] + COL_W / 2, "y": REPO_Y + ROW_H + 18,
     "text": "SMELL #7: REST-only, no runtime collaborator -- yet governed by the",
     "anchor": "middle", "size": 9.5, "color": "#555555"},
    {"x": cols["review"]["x"] + COL_W / 2, "y": REPO_Y + ROW_H + 30,
     "text": "monolith's one shared django.contrib.auth table alongside every other context.",
     "anchor": "middle", "size": 9.5, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/00-monolith/SMELLS.md and order/services.py::place_order (reference for the smell numbers and the outbox cure).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "monolith-architecture", W, H,
    bands=bands,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
