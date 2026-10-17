#!/usr/bin/env python3
"""ch.08 figure: monolith-shared-schema-er — the shared-database ER that
makes SMELL #3/#4 (SMELLS.md: "shared single schema/DB" + "cross-context
foreign keys") visceral: eight tables, one Postgres schema, seven foreign
keys crossing bounded-context ownership lines freely. Deliberately drawn
clean and general (table name + key columns only, no view/service framing)
so it can be re-embedded unchanged in ch.18 ("From Shared Data to Owned
Data") and referenced again from ch.09, ch.11, and ch.13. The transactional
outbox table (`common.models.OutboxEvent`, the ch.17/r03 cure for smells #5
and #6) is deliberately out of scope here — this figure is the "as planted"
smell schema, not the full current table list.

Tables and every foreign key below are read directly from each app's
`models.py` under `examples/00-monolith/` (`common/models.py`,
`order/models.py`, `inventory/models.py`, `payment/models.py`,
`shipping/models.py`, `notification/models.py`, `review/models.py`),
cross-checked against `SMELLS.md`'s smell #3/#4 rows. One deliberate
departure from a naive shared-schema design is called out explicitly:
`order_items` carries no FK to `inventory_items` — `sku`/`item_name`/
`unit_price_cents` are captured as a snapshot at checkout time instead (see
`OrderItem`'s own docstring), so that particular cross-context join was
already designed out from day one. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 760

# ---- top row: the two tables referenced from multiple contexts ------------
TOP_Y, TOP_H = 90, 120
customers = node(300, TOP_Y, 260, TOP_H,
                  ["customers (shared kernel)", "id PK", "name, email, created_at"], style="sub")
inventory_items = node(900, TOP_Y, 260, TOP_H,
                        ["inventory_items", "id PK", "sku, name, price_cents",
                         "quantity_on_hand, updated_at"], style="box")

# ---- bottom row: the six context-owned, referencing tables -----------------
BOT_Y, BOT_H, BOT_W, GUTTER = 330, 150, 220, 20
BOT_X0 = 40
bottom_defs = [
    ("orders", ["orders", "id PK", "customer_id FK", "status, total_cents, shipping_address"]),
    ("order_items", ["order_items", "id PK", "order_id FK", "sku, item_name, quantity, unit_price_cents (snapshot, no FK)"]),
    ("payments", ["payments", "id PK", "order_id FK", "amount_cents, method, status"]),
    ("shipments", ["shipments", "id PK", "order_id FK", "address, status"]),
    ("notifications", ["notifications", "id PK", "customer_id FK, order_id FK (nullable)", "channel, message"]),
    ("reviews", ["reviews", "id PK", "customer_id FK, inventory_item_id FK", "rating, comment"]),
]
bottom = {}
for i, (name, lines) in enumerate(bottom_defs):
    x = BOT_X0 + i * (BOT_W + GUTTER)
    bottom[name] = node(x, BOT_Y, BOT_W, BOT_H, lines, style="box")

all_tables = {"customers": customers, "inventory_items": inventory_items, **bottom}
nodes = list(all_tables.values())

# ---- FK edges ---------------------------------------------------------------
# within the bottom row: order_items -> orders is same-context (not a smell)
# and adjacent, a plain direct line, not highlighted.
edges = [connect(bottom["order_items"], bottom["orders"])]

# bottom-row -> bottom-row, non-adjacent (payments/shipments/notifications -> orders):
# dip BELOW the row.
DIP_DOWN_Y = BOT_Y + BOT_H + 30


def dip_down(a_name, b_name):
    a, b = bottom[a_name], bottom[b_name]
    ax = a["x"] + a["w"] / 2
    ay = a["y"] + a["h"]
    bx = b["x"] + b["w"] * 0.75  # land on orders' bottom edge, offset per source, so lines don't overlap
    by = b["y"] + b["h"]
    return [
        {"x1": ax, "y1": ay, "x2": ax, "y2": DIP_DOWN_Y, "amber": True},
        {"x1": ax, "y1": DIP_DOWN_Y, "x2": bx, "y2": DIP_DOWN_Y, "amber": True},
        {"x1": bx, "y1": DIP_DOWN_Y, "x2": bx, "y2": by, "amber": True},
    ]


for src in ["payments", "shipments", "notifications"]:
    edges += dip_down(src, "orders")

# bottom-row -> top-row: route through the clear lane between the two rows
# (top row ends at TOP_Y+TOP_H; bottom row starts at BOT_Y — the gap between
# them has no boxes in it).
LANE_Y = TOP_Y + TOP_H + (BOT_Y - (TOP_Y + TOP_H)) / 2


def dip_up(a_name, b_name):
    a, b = bottom[a_name], all_tables[b_name]
    ax = a["x"] + a["w"] / 2
    ay = a["y"]
    bx = b["x"] + b["w"] / 2
    by = b["y"] + b["h"]
    return [
        {"x1": ax, "y1": ay, "x2": ax, "y2": LANE_Y, "amber": True},
        {"x1": ax, "y1": LANE_Y, "x2": bx, "y2": LANE_Y, "amber": True},
        {"x1": bx, "y1": LANE_Y, "x2": bx, "y2": by, "amber": True},
    ]


edges += dip_up("orders", "customers")
edges += dip_up("notifications", "customers")
edges += dip_up("reviews", "customers")
edges += dip_up("reviews", "inventory_items")

bands = [
    {"x": 20, "y": 70, "w": W - 40, "h": H - 100,
     "label": "PostgreSQL — one shared schema (per-app Django migrations)", "fill": "#fafafa"},
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.08 — Shared schema: eight tables, one Postgres schema, seven cross-context foreign keys",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "SMELL #3/#4: every amber FK below crosses a bounded-context ownership boundary, enforced only because everything shares one database",
     "anchor": "middle", "size": 11.5, "color": "#555555"},

    {"x": 40, "y": DIP_DOWN_Y + 36,
     "text": "order_items -> inventory_items is deliberately NOT one of these FKs: sku/item_name/unit_price_cents are captured as a snapshot at checkout time instead.",
     "anchor": "start", "size": 10, "color": "#777777"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from each app's models.py under examples/00-monolith/ and SMELLS.md smells #3/#4. Reused in ch.18.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "monolith-shared-schema-er", W, H,
    bands=bands,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
