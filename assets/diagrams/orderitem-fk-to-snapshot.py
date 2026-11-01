#!/usr/bin/env python3
"""ch.18 figure: orderitem-fk-to-snapshot -- the FK-to-snapshot move,
concretely, on `order.OrderItem`. BEFORE: `inventory_item` is a live FK into
another context's table, so reading an order line's name/price means
joining into inventory -- and a later price change retroactively rewrites
history read through that join (SMELL[ch.18]). AFTER: `sku`/`item_name`/
`unit_price_cents` are a denormalized snapshot captured once at checkout
time; no FK, no join, no retroactive rewrite. The bottom row is the actual
migration sequence that cuts over safely: ADD the new columns, BACKFILL them
from the still-live FK, THEN drop the FK -- never the other order.

Sourced from examples/00-monolith/order/models.py::OrderItem and
order/migrations/0002_orderitem_sku_snapshot.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 760

band_before = {"x": 30, "y": 60, "w": 1220, "h": 220,
               "label": "BEFORE -- OrderItem.inventory_item: a cross-context FK", "fill": "#fafafa"}
band_after = {"x": 30, "y": 320, "w": 1220, "h": 220,
              "label": "AFTER -- sku/item_name/unit_price_cents: a denormalized SNAPSHOT, no FK", "fill": "#f1f5f9"}

order_item_before = node(110, 140, 320, 120,
    ["OrderItem", "order_id, quantity,", "inventory_item_id (FK)"], style="box")
inventory_item_before = node(560, 140, 320, 120,
    ["InventoryItem", "sku, name, price_cents,", "quantity_on_hand"], style="box")
edge_before = connect(order_item_before, inventory_item_before,
                       label="FK join required to read sku/name/price", bidir=True)

order_item_after = node(110, 400, 320, 120,
    ["OrderItem", "order_id, quantity,", "sku, item_name,", "unit_price_cents (own copy)"], style="accent")
inventory_item_after = node(560, 400, 320, 120,
    ["InventoryItem", "sku, name, price_cents,", "quantity_on_hand", "(no longer referenced by order)"], style="ghost")

migration_label = {"x": 50, "y": 300, "text": "A later price change in inventory never retroactively rewrites a historical order line -- correct read-model semantics either way checkout runs.",
                    "anchor": "start", "size": 11, "color": "#555555"}

step1 = node(110, 590, 340, 110, ["1. ADD sku, item_name", "nullable-safe default,", "FK stays live"], style="box")
step2 = node(490, 590, 340, 110, ["2. BACKFILL", "select_related(inventory_item)", "one query per batch, not N+1"], style="box")
step3 = node(870, 590, 340, 110, ["3. DROP inventory_item FK", "snapshot columns are now", "the only source of truth"], style="accent")
step_edges = [
    connect(step1, step2, label="0002_orderitem_sku_snapshot.py"),
    connect(step2, step3, amber=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "from foreign key to snapshot: the denormalization move, concretely",
     "anchor": "middle", "bold": True, "size": 18},
    migration_label,
    {"x": W / 2, "y": 568, "text": "Operation order matters: backfill BEFORE dropping the FK, or there is nothing left to read from.",
     "anchor": "middle", "size": 12, "color": "#1d1d1d", "bold": True},
]

g.emit(
    "orderitem-fk-to-snapshot", W, H,
    bands=[band_before, band_after],
    nodes=[order_item_before, inventory_item_before, order_item_after, inventory_item_after, step1, step2, step3],
    edges=[edge_before] + step_edges,
    notes=notes,
)
