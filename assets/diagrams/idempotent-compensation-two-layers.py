#!/usr/bin/env python3
"""ch.23 figure: idempotent-compensation-two-layers -- closing DRQ-043. A
compensating Release has to survive being redelivered at BOTH layers it
could be redelivered at: the Kafka event that triggers it (the saga's own
at-least-once consumer), and the RPC itself (retried for any other reason,
or called twice by hand, as the r05 cutover's double-delivery proof did
directly over gRPC). Layer 1 is a defense-in-depth client-side guard; Layer
2 is the server-side ledger that is the actual arbiter.

Sourced from examples/00-monolith/order/services.py::_is_pending,
_release_order_lines (the stable key f"{order_id}:{sku}:release"),
examples/04-inventory-service/app/repository.py::release (the
INSERT...ON CONFLICT(idempotency_key) DO NOTHING RETURNING id ledger),
tooling/newman/GOLDEN-BASELINE.md's r05 CUTOVER lane double-delivery proof
(stock 94 -> 94 across both redelivery paths).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 700

band_top = {"x": 20, "y": 50, "w": 1280, "h": 260,
            "label": "Layer 1 -- saga-level: status-transition guard (defense-in-depth, client side)", "fill": "#fafafa"}
band_bot = {"x": 20, "y": 50 + 260 + 36, "w": 1280, "h": 280,
            "label": "Layer 2 -- ledger-level: inventory.compensations (the actual arbiter, server side)", "fill": "#f1f5f9"}

t1 = node(60, 130, 260, 110, ["payment.declined", "redelivered (same orderId)"], style="box")
t2 = node(360, 130, 280, 110, ["_is_pending(order)", "status already PAYMENT_DECLINED", "-> logged no-op, RETURN"], style="accent")
t3 = node(700, 130, 280, 110, ["No second Release call", "issued at all"], style="ghost")
top_nodes = [t1, t2, t3]
top_edges = [connect(t1, t2), connect(t2, t3)]

y2 = 50 + 260 + 36 + 40
b1 = node(60, y2, 280, 110,
          ["gRPC Release(sku, qty,", "idempotency_key=", "\"{orderId}:{sku}:release\")"], style="box")
b2 = node(400, y2, 340, 110,
          ["INSERT INTO compensations", "ON CONFLICT(idempotency_key)", "DO NOTHING RETURNING id"], style="accent")
b3 = node(800, y2 - 60, 220, 90, ["row returned", "-> apply +qty UPDATE"], style="box")
b4 = node(800, y2 + 60, 220, 90, ["no row (conflict)", "-> no-op, same reply"], style="ghost")
bot_nodes = [b1, b2, b3, b4]
bot_edges = [
    connect(b1, b2),
    connect(b2, b3, label="first call for this key"),
    connect(b2, b4, dashed=True, label="replayed key"),
]

notes = [
    {"x": W / 2, "y": 28, "text": "ch.23 -- DRQ-043 closed: a compensation survives redelivery at the event layer AND the RPC layer",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 46, "text": "Proven live: on_hand_qty held at 94 across a hand-redelivered payment.declined event AND two direct,",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "identical-key gRPC Release calls that bypassed the saga guard entirely -- the ledger is the real backstop.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "idempotent-compensation-two-layers", W, H,
    bands=[band_top, band_bot],
    nodes=top_nodes + bot_nodes,
    edges=top_edges + bot_edges,
    notes=notes,
)
