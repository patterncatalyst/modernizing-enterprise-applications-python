#!/usr/bin/env python3
"""ch.11 figure: context-map — the six bounded contexts (order, inventory,
payment, shipping, notification, review) drawn as a DDD context map, with
the relationship TYPE labelled on each edge.

order -> inventory: conformist today — `order/services.py::_place_order_local`
calls `inventory.services.get_by_sku()`/`reserve()` directly and gets back a
live `InventoryItem` Django model instance, not a translated DTO (SMELL #1:
"no anti-corruption layer at the seam"). The relationship this seam SHOULD
have is customer/supplier (order is the downstream consumer of inventory's
stock data, inventory is the upstream supplier) — and a stable, versioned
contract for exactly that ALREADY EXISTS, just not on this path: `order/
proto/.../inventory.proto` + `order/inventory_client.py::
RemoteInventoryClient` is the gRPC ACL `INVENTORY_MODE=grpc` uses (r04/ch.19)
— built, tested, and simply not the default.

order -> payment / shipping: direct, synchronous, in-process calls inside
`_place_order_local`'s one `transaction.atomic()` — `order/services.py`
imports `payment.services`/`shipping.services` and calls their functions
directly, four other contexts' concrete modules, not four ports.

order -> notification: the ONE edge this chapter can point to as already
cured — `_place_order_local` does not import `notification.services` at
all; it writes a `common.models.OutboxEvent` row and a separate relay +
consumer pair (outside this transaction) carries it the rest of the way
(SMELL #5/#6, CURED at r03).

All six -> PostgreSQL: one shared schema — a shared kernel with no edges,
the whole database treated as if it belonged equally to all six contexts at
once. Review's edge is read-only lookups against customers/inventory_items;
review has zero outbound edges to its sibling contexts' code (SMELL #7's
auth coupling is the one exception, already cured for everything except
review's own extraction).

Sourced from `examples/00-monolith/order/services.py`,
`examples/00-monolith/inventory/services.py`, `order/inventory_client.py`,
`order/proto/.../inventory.proto`. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 620

# ---- the six context boxes, one row --------------------------------------
CONTEXTS = [
    ("order", ["order", "checkout aggregate -- 3 outbound edges + 1 async"], "accent"),
    ("inventory", ["inventory", "stock per SKU -- conformed-to by order"], "box"),
    ("payment", ["payment", "charge capture -- called from place_order()"], "box"),
    ("shipping", ["shipping", "dispatch -- called from place_order()"], "box"),
    ("notification", ["notification", "confirmation msg -- reached via outbox only"], "box"),
    ("review", ["review", "a rating on a purchased SKU"], "ghost"),
]

COL_W, GUTTER, COL_X0, ROW_Y, ROW_H = 200, 20, 50, 200, 100
cols = {}
nodes = []
for i, (name, lines, style) in enumerate(CONTEXTS):
    x = COL_X0 + i * (COL_W + GUTTER)
    n = node(x, ROW_Y, COL_W, ROW_H, lines, style=style)
    cols[name] = n
    nodes.append(n)

order_n, inv_n = cols["order"], cols["inventory"]

# ---- the missing ACL, sitting above the order<->inventory seam -----------
acl_box = node(110, 108, 340, 62,
               ["Anti-corruption layer -- unused by default",
                "RemoteInventoryClient/inventory.proto exist (ch.19)",
                "should be: customer/supplier (negotiated contract)"],
               style="ghost")
nodes.append(acl_box)

edges = []

# the central seam: conformist today, no ACL on the default path -- routed
# along the TOP edge of both boxes (not through their vertical center) so
# the label lands in the clear gap below the ACL callout instead of
# printing over either box's text
edges.append({"x1": order_n["x"] + order_n["w"], "y1": ROW_Y, "x2": inv_n["x"], "y2": ROW_Y,
              "amber": True, "label": "conformist -- raw model instance, no ACL on default path", "ly": -22})

# the ACL gap, drawn as a bridge from the callout box into both sides of the seam
edges.append(connect(acl_box, order_n, dashed=True))
edges.append(connect(acl_box, inv_n, dashed=True))

# order's two other synchronous outbound edges: direct calls, no port --
# routed below the row (bus pattern) so no line crosses an intervening box
BUS_Y = ROW_Y + ROW_H + 25
ox = order_n["x"] + order_n["w"]
order_mid_y = order_n["y"] + order_n["h"] / 2
bus_targets = ["payment", "shipping"]
farthest_x = cols[bus_targets[-1]]["x"]

edges.append({"x1": ox, "y1": order_mid_y, "x2": ox, "y2": BUS_Y, "amber": True})
edges.append({"x1": ox, "y1": BUS_Y, "x2": farthest_x, "y2": BUS_Y, "amber": True,
              "label": "direct synchronous call -- no port, same transaction.atomic()"})
for name in bus_targets:
    t = cols[name]
    tx = t["x"] + t["w"] / 2
    ty = t["y"] + t["h"]
    edges.append({"x1": tx, "y1": BUS_Y, "x2": tx, "y2": ty, "amber": True})

# order -> notification: the one edge already cured, drawn dashed/non-amber
notif_n = cols["notification"]
edges.append({"x1": ox, "y1": order_mid_y + 16, "x2": notif_n["x"] + notif_n["w"] / 2, "y2": notif_n["y"],
              "dashed": True, "label": "async via outbox -- cured (SMELL #5/#6)"})

# ---- the one shared Postgres schema: shared kernel with no edges ---------
PG_Y, PG_H = 410, 90
pg_band = {"x": 40, "y": PG_Y, "w": W - 80, "h": PG_H,
           "label": "PostgreSQL -- one shared schema (shared kernel, ungoverned -- no edges)",
           "fill": "#fafafa"}
pg_box = node(W / 2 - 220, PG_Y + 28, 440, 44,
              ["one schema -- every table joinable by any context's Django ORM"], style="sub")
nodes.append(pg_box)

db_edges = []
for name, n in cols.items():
    if name == "review":
        e = connect(n, pg_box)
        e["label"] = "read-only lookups (customers, inventory_items)"
        db_edges.append(e)
    else:
        db_edges.append(connect(n, pg_box))

bands = [
    {"x": 20, "y": 70, "w": W - 40, "h": 300,
     "label": "Six bounded contexts -- edge = the context-mapping relationship that actually exists", "fill": "#ffffff"},
    pg_band,
]

review_n = cols["review"]
notes = [
    {"x": W / 2, "y": 32, "text": "ch.11 -- Context map: six bounded contexts, one relationship nobody decided",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "order->inventory is conformist with no ACL on the default path; order's other sync edges are direct; notification is already reached only via outbox",
     "anchor": "middle", "size": 11.5, "color": "#555555"},

    {"x": review_n["x"] + review_n["w"] / 2, "y": ROW_Y - 12,
     "text": "zero outbound edges to siblings -- own extraction is ch.15",
     "anchor": "middle", "size": 10, "color": "#3d7a4e"},

    {"x": 40, "y": PG_Y + PG_H + 24,
     "text": "Shared kernel with no edges: nobody drew a narrow, governed slice of shared model -- the whole schema is treated as commonly",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": PG_Y + PG_H + 38,
     "text": "owned by all six contexts, because a foreign key is the cheapest way to relate two rows that happen to live in the same schema.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 40, "y": H - 32,
     "text": "Sourced from examples/00-monolith/order/services.py, inventory/services.py, order/inventory_client.py, order/proto/.../inventory.proto.",
     "anchor": "start", "size": 10, "color": "#777777"},
    {"x": 40, "y": H - 16,
     "text": "SMELL numbers quoted from examples/00-monolith/SMELLS.md.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "context-map", W, H,
    bands=bands,
    nodes=nodes,
    edges=edges + db_edges,
    notes=notes,
)
