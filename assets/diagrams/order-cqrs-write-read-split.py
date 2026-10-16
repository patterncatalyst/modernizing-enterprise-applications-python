#!/usr/bin/env python3
"""ch.21 figure: order-cqrs-write-read-split -- the command/query split inside
07-order-service, with the SAME-TRANSACTION order_view projection as the
concrete mechanism. Top band: the command path -- place_order() reserves
every line over gRPC OUTSIDE any local transaction, then persists the write
aggregate (orders/order_items), upserts order_view, and writes the
order.placed outbox row, all in ONE transaction
(repository.py::create_order_with_outbox_and_view). Bottom band: the query
path -- GET /api/orders[/{id}] reads order_view EXCLUSIVELY; the write
tables are never touched by a read.

Sourced from examples/07-order-service/app/repository.py
(create_order_with_outbox_and_view, transition_order_status_with_view),
app/routes.py, app/models.py::OrderView's docstring.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 620

band_cmd = {"x": 20, "y": 56, "w": 1320, "h": 240,
            "label": "COMMAND SIDE -- place_order() / transition_order_status_with_view()", "fill": "#fafafa"}
band_qry = {"x": 20, "y": 56 + 240 + 32, "w": 1320, "h": 190,
            "label": "QUERY SIDE -- GET /api/orders[/{id}] reads order_view ONLY", "fill": "#f1f5f9"}

reserve = node(50, 110, 220, 80, ["gRPC Reserve/GetStock", "OUTSIDE any local tx"], style="box")
tx = {"x": 320, "y": 100, "w": 760, "h": 160,
      "label": "ONE local transaction (create_order_with_outbox_and_view)", "fill": "#eef2ff"}
agg = node(350, 150, 200, 90, ["orders + order_items", "write aggregate, PENDING"], style="box")
view = node(590, 150, 200, 90, ["order_view upsert", "SAME transaction"], style="accent")
outbox = node(830, 150, 200, 90, ["outbox row", "order.placed"], style="box")
relay = node(1130, 150, 180, 90, ["OutboxRelay", "polls -> Kafka"], style="box")

cmd_nodes = [reserve, agg, view, outbox, relay]
cmd_edges = [
    connect(reserve, agg, label="line snapshots"),
    connect(agg, view),
    connect(view, outbox),
    connect(outbox, relay, amber=True, label="at-least-once"),
]

y2 = 56 + 240 + 32
client = node(50, y2 + 60, 170, 80, ["GET /api/orders", "or /{id}"], style="box")
routes = node(300, y2 + 60, 220, 80, ["app/routes.py", "repository.get_order_view_*"], style="accent")
orderview = node(600, y2 + 60, 220, 80, ["order_view", "ONE row per order"], style="box")
neverwrite = node(900, y2 + 60, 360, 80,
                  ["orders / order_items NEVER queried here --",
                   "app/routes.py imports OrderView, not Order"], style="ghost")

qry_nodes = [client, routes, orderview, neverwrite]
qry_edges = [
    connect(client, routes),
    connect(routes, orderview, amber=True, label="read-your-writes: same tx as the write above"),
    connect(orderview, neverwrite, dashed=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.21 -- CQRS, concretely: one write aggregate, one projection, upserted in the SAME transaction as every mutation",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 40, "text": "This buys read-after-write consistency WITHIN this service: a GET issued right after a 202 sees the new PENDING row with",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "no delay. It does not buy cross-service consistency -- CONFIRMED is only as fresh as the saga event that drives it there.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "order-cqrs-write-read-split", W, H,
    bands=[band_cmd, band_qry, tx],
    nodes=cmd_nodes + qry_nodes,
    edges=cmd_edges + qry_edges,
    notes=notes,
)
