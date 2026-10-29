#!/usr/bin/env python3
"""ch.12 figure: storm-wall-to-backlog -- "From the wall to the backlog": the
four event boundaries this chapter's process-level storm finds, each mapped
to the extraction chapter that cuts it and the mechanism that chapter uses:
the OrderPlaced -> StockReserved boundary is inventory's seam, cut with a
gRPC proto-as-ACL seam, an atomic conditional-UPDATE reserve, and
transaction-log-tailing backfill in Chapter 19; the StockReserved ->
PaymentCaptured/PaymentDeclined boundary is payment's seam, cut as a
choreographed saga (an `aiokafka` consumer reacting to `order.placed`, then
`payment.captured`/`payment.declined`) in Chapter 23; the PaymentCaptured ->
ShipmentDispatched boundary is shipping's seam, cut in Chapter 24 as an
orchestrated saga using a single FastAPI saga coordinator; and the
ShipmentDispatched -> OrderConfirmed/NotificationSent boundary is
notification's seam, cut first, in Chapter 17, as a transactional outbox
feeding an asynchronous `aiokafka` consumer.

The footnote on `place_order()`/ch.26 and the ch.16 ACL precondition follow
the same reasoning: no single mechanism is claimed for ch.26 because the god
checkout function's own extraction depends on every other boundary already
being cut first. The ch.13 pointer is this chapter's own closing hand-off --
the wall only answers *where* to cut; *in what order* is Chapter 13's
question (coupling analysis), not this figure's.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1600, 900

COL_A_X, COL_A_W = 50, 520
COL_B_X, COL_B_W = 640, 220
COL_C_X, COL_C_W = 930, 620
ROW_Y0, ROW_H, GUTTER = 150, 110, 24

ROWS = [
    ("OrderPlaced -> StockReserved", "inventory's seam",
     "Inventory",
     "gRPC proto-as-ACL + CDC backfill", "atomic conditional-UPDATE reserve, compensating release"),
    ("StockReserved -> PaymentCaptured / PaymentDeclined", "payment's seam",
     "Payment",
     "Choreographed saga", "an aiokafka consumer reacting to order.placed, emitting payment.captured/declined"),
    ("PaymentCaptured -> ShipmentDispatched", "shipping's seam",
     "Shipping",
     "Orchestrated saga", "a single FastAPI saga coordinator sequences dispatch, not peer-to-peer events"),
    ("ShipmentDispatched -> OrderConfirmed / NotificationSent", "notification's seam -- cut first",
     "Notification",
     "Transactional outbox", "feeding an asynchronous aiokafka consumer"),
]

nodes = []
edges = []

for i, (boundary, seam_note, ctx, mech, mech_detail) in enumerate(ROWS):
    y = ROW_Y0 + i * (ROW_H + GUTTER)
    a = node(COL_A_X, y, COL_A_W, ROW_H, [boundary, seam_note], style="sub")
    b = node(COL_B_X, y, COL_B_W, ROW_H, [ctx], style="accent")
    c = node(COL_C_X, y, COL_C_W, ROW_H, [mech, mech_detail], style="box")
    nodes += [a, b, c]
    edges.append(connect(a, b))
    edges.append(connect(b, c))

# ---- footnote: place_order() / ch.26 -- extracted last, no single mechanism --
foot = node(COL_A_X, ROW_Y0 + 4 * (ROW_H + GUTTER) + 10, COL_A_W + (COL_B_X - COL_A_X - COL_A_W) + COL_B_W,
            90,
            ["order/services.py::place_order() itself -- cut last",
             "issues every policy's command above; waits until all four boundaries already fire events"],
            style="ghost")
nodes.append(foot)

notes = [
    {"x": W / 2, "y": 32, "text": "From the storm wall to the extraction backlog",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": W / 2, "y": 58,
     "text": "every boundary this chapter's wall finds, mapped to the chapter that cuts it and the mechanism it uses",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": COL_A_X, "y": ROW_Y0 - 16, "text": "Event boundary (the storm wall)", "anchor": "start", "bold": True, "size": 12.5},
    {"x": COL_B_X, "y": ROW_Y0 - 16, "text": "Extraction chapter", "anchor": "start", "bold": True, "size": 12.5},
    {"x": COL_C_X, "y": ROW_Y0 - 16, "text": "Mechanism", "anchor": "start", "bold": True, "size": 12.5},

    {"x": COL_A_X, "y": foot["y"] + foot["h"] + 26,
     "text": "The anti-corruption layer is the precondition at every row above: an event can't carry "
             "contract-shaped data until the ACL exists at that seam.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": COL_A_X, "y": foot["y"] + foot["h"] + 44,
     "text": "This wall answers *where* to cut; *in what order* is the coupling-analysis question, not this figure's.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": COL_A_X, "y": H - 16,
     "text": "Sourced from examples/00-monolith/order/services.py and the extraction examples (02-review-service through 07-order-service).",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "storm-wall-to-backlog", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
