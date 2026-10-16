#!/usr/bin/env python3
"""ch.23 figure: choreographed-payment-saga-sequence -- the full choreographed
saga, top to bottom, branching into its three possible terminal outcomes. No
box in this picture coordinates the others; each one reacts only to an event
it observes on a topic it already subscribes to.

Sourced from examples/00-monolith/order/services.py
(_place_order_choreographed, handle_payment_captured, handle_payment_declined),
examples/05-payment-service/app/service.py::process_order_placed,
examples/00-monolith/order/management/commands/order_saga_listener.py,
tooling/newman/GOLDEN-BASELINE.md's r05 CUTOVER lane (attempt 2/20 numbers).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 960

n1 = node(500, 30, 300, 70, ["Client: POST /api/orders"], style="box")
n2 = node(470, 130, 360, 90, ["Monolith: reserve gRPC + persist", "Order PENDING + outbox, ONE txn", "-> 202 Accepted, PENDING"], style="accent")
n3 = node(500, 250, 300, 70, ["Kafka: order.placed", "(key = orderId)"], style="box")
n4 = node(460, 350, 380, 90, ["payment-service: charge() +", "persist Payment + OWN outbox,", "ONE txn -- idempotent by order_id"], style="accent")
n5 = node(460, 470, 190, 70, ["Kafka:", "payment.captured"], style="box")
n6 = node(680, 470, 190, 70, ["Kafka:", "payment.declined"], style="box")
n7 = node(460, 580, 190, 90, ["order_saga_listener:", "status guard,", "dispatch shipping"], style="accent")
n8 = node(680, 580, 190, 90, ["order_saga_listener:", "status guard,", "gRPC Release"], style="accent")
n9 = node(230, 710, 220, 90, ["CONFIRMED", "(shipping dispatched OK)"], style="accent")
n10 = node(460, 710, 220, 90, ["SHIPPING_FAILED", "+ gRPC Release", "(known refund deferral)"], style="ghost")
n11 = node(700, 710, 220, 90, ["PAYMENT_DECLINED", "+ gRPC Release"], style="accent")
n12 = node(460, 850, 380, 90, ["Client: GET /api/orders/{id}", "bounded-wait poll -- resolved", "attempt 2/20 in the r05 cutover run"], style="box")

nodes = [n1, n2, n3, n4, n5, n6, n7, n8, n9, n10, n11, n12]
edges = [
    connect(n1, n2),
    connect(n2, n3, amber=True, label="outbox_relay publishes"),
    connect(n3, n4),
    connect(n4, n5, label="charge() captures"),
    connect(n4, n6, label="charge() declines"),
    connect(n5, n7, amber=True, label="relay publishes"),
    connect(n6, n8, amber=True, label="relay publishes"),
    connect(n7, n9, label="ship OK"),
    connect(n7, n10, dashed=True, label="ShippingFailed"),
    connect(n8, n11),
    connect(n9, n12),
    connect(n10, n12),
    connect(n11, n12),
]

notes = [
    {"x": W / 2, "y": 20, "text": "ch.23 -- the choreographed saga: every arrow is an event one side reacted to, nothing is called synchronously",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 40, "text": "No orchestrator box exists in this picture -- compare ch.24's orchestrated shipping step, where one does.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "Every reaction is idempotent (status guard / order_id uniqueness), so Kafka's at-least-once redelivery is safe here.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "choreographed-payment-saga-sequence", W, H,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
