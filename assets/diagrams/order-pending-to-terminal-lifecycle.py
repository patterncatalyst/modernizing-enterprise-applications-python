#!/usr/bin/env python3
"""ch.22 figure: order-pending-to-terminal-lifecycle -- the state machine the
ACD model introduces. An order persisted PENDING has exactly three terminal
exits, each driven by an event the order_saga_listener reacts to, each
protected by the SAME status-transition guard so a redelivered event can
never drive a second transition out of an already-terminal state.

Sourced from examples/00-monolith/order/models.py::Order.Status,
order/services.py (handle_payment_captured, handle_payment_declined,
_is_pending), tooling/newman/GOLDEN-BASELINE.md's r05 CUTOVER lane (the
stuck-PENDING negative: 20x750ms budget exhausted, 15.1s, newman exit 1).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1260, 640

n_pending = node(500, 40, 260, 110,
                 ["PENDING", "(checkout returned 202;", "the consistency window)"], style="accent")
n_confirmed = node(80, 280, 280, 120,
                    ["CONFIRMED", "payment.captured +", "shipping dispatch OK"], style="accent")
n_shipfail = node(490, 280, 280, 120,
                   ["SHIPPING_FAILED", "payment.captured, then", "ShippingFailed -> gRPC Release"], style="ghost")
n_declined = node(900, 280, 280, 120,
                   ["PAYMENT_DECLINED", "payment.declined", "-> gRPC Release"], style="accent")
n_stuck = node(500, 480, 260, 110,
               ["stuck PENDING", "(consumer down --", "RED, not a false green)"], style="ghost")

nodes = [n_pending, n_confirmed, n_shipfail, n_declined, n_stuck]
edges = [
    connect(n_pending, n_confirmed, label="payment.captured + ship OK"),
    connect(n_pending, n_shipfail, dashed=True, label="payment.captured + ShippingFailed"),
    connect(n_pending, n_declined, label="payment.declined"),
    connect(n_pending, n_stuck, dashed=True, amber=True, label="no event arrives within the bounded wait"),
    {"x1": n_confirmed["x"] + 20, "y1": n_confirmed["y"], "x2": n_confirmed["x"] + 220, "y2": n_confirmed["y"],
     "dashed": True, "label": "redelivery -> guard -> no-op"},
    {"x1": n_declined["x"] + 20, "y1": n_declined["y"], "x2": n_declined["x"] + 220, "y2": n_declined["y"],
     "dashed": True, "label": "redelivery -> guard -> no-op"},
]

notes = [
    {"x": W / 2, "y": 20, "text": "PENDING has exactly three terminal exits, each idempotent against redelivery",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 40, "text": "\"stuck PENDING\" is not a fourth terminal state -- it's the real failure mode of a dead consumer, caught by a",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "bounded-wait poll that fails strictly (20x750ms, 15.1s, newman exit 1) rather than waiting forever or lying green.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "order-pending-to-terminal-lifecycle", W, H,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
