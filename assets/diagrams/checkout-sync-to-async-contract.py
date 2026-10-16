#!/usr/bin/env python3
"""ch.23 figure: checkout-sync-to-async-contract -- the contract
change r05 makes to POST /api/orders. BEFORE (PAYMENT_MODE=synchronous): one
round trip ends with a TERMINAL status (201 CONFIRMED, 402 declined, 422
ship-fail, 409 out-of-stock). AFTER (PAYMENT_MODE=choreographed): the SAME
round trip only ever answers 202 PENDING (or the still-synchronous 409) --
the terminal outcome arrives later, out of band, and the caller has to ask
for it with a follow-up GET.

Sourced from examples/00-monolith/order/views.py::OrderListCreateView.post,
examples/00-monolith/order/services.py::_place_order_choreographed,
examples/05-payment-service/CUTOVER.md's cutover table.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 620
PANEL_H = 230

band_before = {"x": 30, "y": 60, "w": 1220, "h": PANEL_H,
               "label": "BEFORE -- PAYMENT_MODE=synchronous: one round trip, one terminal answer", "fill": "#fafafa"}
band_after = {"x": 30, "y": 60 + PANEL_H + 40, "w": 1220, "h": PANEL_H,
              "label": "AFTER -- PAYMENT_MODE=choreographed: one round trip, a PROMISE -- the terminal answer comes later", "fill": "#f1f5f9"}

n_post_b = node(70, 150, 200, 110, ["POST /api/orders"], style="box")
n_work_b = node(320, 150, 320, 110, ["reserve + order + charge +", "confirm + ship + outbox,", "ONE local transaction"], style="box")
n_resp_b = node(700, 150, 420, 110, ["201 CONFIRMED | 402 DECLINED |", "422 SHIP-FAILED | 409 OUT_OF_STOCK", "-- terminal, SAME response"], style="accent")
before_nodes = [n_post_b, n_work_b, n_resp_b]
before_edges = [connect(n_post_b, n_work_b), connect(n_work_b, n_resp_b)]

y2 = 150 + PANEL_H + 40
n_post_a = node(70, y2, 200, 110, ["POST /api/orders"], style="box")
n_work_a = node(320, y2, 320, 110, ["reserve + order + outbox,", "ONE local transaction --", "NO charge, NO ship here"], style="box")
n_resp_a = node(700, y2, 220, 110, ["202 PENDING", "(or still-sync 409)"], style="accent")
n_later = node(970, y2, 220, 110, ["...later, async...", "GET /api/orders/{id}", "to find out"], style="ghost")
after_nodes = [n_post_a, n_work_a, n_resp_a, n_later]
after_edges = [
    connect(n_post_a, n_work_a),
    connect(n_work_a, n_resp_a),
    connect(n_resp_a, n_later, dashed=True, amber=True, label="caller must poll"),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.23 -- the contract change: 202 is a PROMISE, not a faster 201",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 50, "y": H - 40, "text": "A dishonest cutover would keep returning 201 and just lie about the status; the equivalence suite is taught to poll",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 50, "y": H - 22, "text": "GET /api/orders/{id} to a bounded terminal status instead, so a stuck PENDING order fails the gate, not passes it.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "checkout-sync-to-async-contract", W, H,
    bands=[band_before, band_after],
    nodes=before_nodes + after_nodes,
    edges=before_edges + after_edges,
    notes=notes,
)
