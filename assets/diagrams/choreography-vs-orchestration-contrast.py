#!/usr/bin/env python3
"""ch.24 figure: choreography-vs-orchestration-contrast -- r05's payment saga
(left) and r06's shipping saga (right) side by side, same book, same kind of
problem (react to an event, do a multi-step job, compensate on failure),
opposite control-flow topology. The point of the picture is structural, not
cosmetic: the left panel has no box that knows the whole sequence; the right
panel has exactly one.

Sourced from examples/05-payment-service/app/service.py::process_order_placed
(no knowledge of order_saga_listener downstream), examples/00-monolith/order/
management/commands/order_saga_listener.py, examples/06-shipping-service/
app/orchestrator.py (the single STEPS table one process owns end to end).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 760

band_l = {"x": 20, "y": 60, "w": 620, "h": 660, "label": "r05 -- choreographed payment (ch.23)", "fill": "#fafafa"}
band_r = {"x": 680, "y": 60, "w": 620, "h": 660, "label": "r06 -- orchestrated shipping (ch.24)", "fill": "#f1f5f9"}

# Left: choreography -- three independent reactive boxes, no coordinator
l1 = node(60, 120, 540, 70, ["monolith: order.placed outbox", "(no knowledge of payment-service)"], style="box")
l2 = node(60, 230, 540, 70, ["payment-service: reacts to order.placed,", "writes ITS OWN outbox"], style="box")
l3 = node(60, 340, 540, 70, ["monolith order_saga_listener: reacts to", "payment.captured/declined"], style="box")
l4 = node(60, 470, 540, 100,
          ["No box above knows the other two exist.", "The sequence EMERGES from three", "independent event subscriptions."], style="ghost")

# Right: orchestration -- one coordinator box owns the whole sequence
r1 = node(720, 120, 540, 70, ["shipping-service consumer: reacts to", "payment.captured (the ONLY trigger)"], style="box")
r2 = node(720, 230, 540, 90,
          ["orchestrator.advance()/compensate():", "ONE coordinator sequences enrich -> dispatch ->", "book_carrier -> emit, AND decides to compensate"], style="accent")
r3 = node(720, 360, 540, 70, ["This same coordinator calls every step", "and owns the undo decision"], style="box")
r4 = node(720, 470, 540, 100,
          ["The coordinator knows the whole sequence.", "A failure anywhere routes through ONE", "decision point, not three independent reactions."], style="accent")

nodes = [l1, l2, l3, l4, r1, r2, r3, r4]
edges = [
    connect(l1, l2, label="order.placed"),
    connect(l2, l3, label="payment.captured/declined"),
    connect(r1, r2),
    connect(r2, r3, label="one step at a time"),
    connect(r3, r4),
]

notes = [
    {"x": W / 2, "y": 30, "text": "The difference is where the \"what happens next\" decision lives -- not service count or topology shape",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 20, "text": "Both sagas compensate on failure; only the orchestrated one has a single box that can be pointed to as \"the decision-maker.\"",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "choreography-vs-orchestration-contrast", W, H,
    bands=[band_l, band_r],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
