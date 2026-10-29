#!/usr/bin/env python3
"""ch.19 figure: inventory-grpc-proto-acl -- the proto IS the anti-corruption
layer for the synchronous order<->inventory seam. Two distinct
vocabularies meet only at the wire: the monolith's domain vocabulary
(sku/name/priceCents/quantityOnHand) on one side, inventory.proto's wire
vocabulary (stock_keeping_unit/display_name/unit_price_cents/on_hand_qty)
in the middle, and inventory-service's OWN domain vocabulary
(sku/quantity_on_hand) on the other -- each side's client/server translates,
so the two shapes never get to "happen to already agree."

Sourced from examples/00-monolith/order/inventory_client.py
(RemoteInventoryClient, client-side ACL), proto/.../inventory.proto (the
frozen wire contract), examples/04-inventory-service/app/grpc_server.py
(server-side ACL, _to_stock_reply), app/repository.py (own domain vocab).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 440

monolith_dom = node(30, 150, 240, 120,
    ["Monolith domain vocab", "order.services.place_order()", "sku, quantity"], style="box")
client = node(300, 150, 230, 120,
    ["order/inventory_client.py", "RemoteInventoryClient", "CLIENT-SIDE ACL translator"], style="accent")
proto = node(560, 150, 280, 120,
    ["inventory.proto -- frozen, versioned", "stock_keeping_unit, display_name,", "unit_price_cents, on_hand_qty"], style="accent")
server = node(870, 150, 230, 120,
    ["app/grpc_server.py", "InventoryGrpcServiceServicer", "SERVER-SIDE ACL translator"], style="accent")
inv_dom = node(1130, 150, 240, 120,
    ["Inventory's OWN domain vocab", "app/repository.py", "sku, quantity_on_hand"], style="box")

edges = [
    connect(monolith_dom, client, label="sku, quantity"),
    connect(client, proto, label="ReserveRequest{stock_keeping_unit, requested_qty}", amber=True, bidir=True),
    connect(proto, server, label="wire bytes, :9004", amber=True, bidir=True),
    connect(server, inv_dom, label="sku, quantity_on_hand"),
]

notes = [
    {"x": W / 2, "y": 40, "text": "the proto IS the ACL: two distinct vocabularies meet only at the wire",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 40, "y": H - 60, "text": "Wire vocab (stock_keeping_unit/display_name/unit_price_cents/on_hand_qty) is distinct from domain vocab",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 42, "text": "(sku/name/priceCents/quantityOnHand) so each side's translator does the mapping, instead of the shapes happening to agree.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 24, "text": "ReserveReply/StockReply carry the reply back through the SAME two translators, in reverse -- the boundary is symmetric.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "inventory-grpc-proto-acl", W, H,
    bands=[],
    nodes=[monolith_dom, client, proto, server, inv_dom],
    edges=edges,
    notes=notes,
)
