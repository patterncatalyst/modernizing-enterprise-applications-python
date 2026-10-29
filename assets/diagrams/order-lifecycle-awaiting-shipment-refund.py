#!/usr/bin/env python3
"""ch.24 figure: order-lifecycle-awaiting-shipment-refund -- the full order
lifecycle once SHIPPING_MODE=orchestrated: PENDING -> AWAITING_SHIPMENT ->
CONFIRMED or SHIPPING_FAILED, PLUS the refund hop that closes r05's
stranded-payment gap (DRQ-054) the instant a SHIP-FAIL saga compensates.

Sourced from examples/00-monolith/order/services.py (handle_payment_captured's
orchestrated branch, handle_shipment_dispatched, handle_shipment_failed,
_is_awaiting_shipment), examples/05-payment-service/app/refund_consumer.py
(ShipmentFailedConsumer / process_shipment_failed, CAPTURED -> REFUNDED),
examples/06-shipping-service/CUTOVER.md's "refund gap -- CLOSED" section.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 760

n_pending = node(520, 20, 280, 70, ["PENDING", "checkout returned 202"], style="box")
n_awaiting = node(520, 140, 280, 80,
                   ["AWAITING_SHIPMENT", "payment.captured consumed,", "SHIPPING_MODE=orchestrated"], style="accent")
n_saga = node(880, 140, 380, 80, ["shipping-service's own saga", "(Figure 24.1) runs independently"], style="box")

n_confirmed = node(180, 280, 280, 80, ["CONFIRMED", "shipment.dispatched consumed"], style="accent")
n_shipfailed = node(620, 280, 300, 80, ["SHIPPING_FAILED", "shipment.failed consumed,", "gRPC Release issued"], style="ghost")

n_refund_consumer = node(620, 420, 300, 70, ["payment-service:", "ShipmentFailedConsumer"], style="box")
n_captured = node(620, 530, 300, 60, ["Payment: CAPTURED"], style="box")
n_refunded = node(620, 630, 300, 70, ["Payment: REFUNDED", "payment.refunded emitted"], style="accent")

n_stuck = node(180, 420, 280, 90,
               ["stuck AWAITING_SHIPMENT", "(shipping-service down --", "RED, not a false green)"], style="ghost")

nodes = [n_pending, n_awaiting, n_saga, n_confirmed, n_shipfailed,
         n_refund_consumer, n_captured, n_refunded, n_stuck]

edges = [
    connect(n_pending, n_awaiting, label="payment.captured"),
    connect(n_awaiting, n_saga, dashed=True, label="same event, independent consumer"),
    connect(n_saga, n_confirmed, label="shipment.dispatched"),
    connect(n_saga, n_shipfailed, dashed=True, label="shipment.failed"),
    connect(n_shipfailed, n_refund_consumer, amber=True, label="same shipment.failed event"),
    connect(n_captured, n_refund_consumer),
    connect(n_refund_consumer, n_refunded),
    connect(n_awaiting, n_stuck, dashed=True, amber=True, label="no event arrives within the bounded wait"),
]

notes = [
    {"x": W / 2, "y": 20, "text": "AWAITING_SHIPMENT is a real intermediate status, and SHIPPING_FAILED now closes the refund gap an earlier step left open",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 40, "text": "Before the refund hop: a SHIP-FAIL order compensated inventory but left a captured payment stranded (documented, not silent).",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "After the refund hop: the SAME shipment.failed event that triggers the order's SHIPPING_FAILED transition also drives CAPTURED -> REFUNDED.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "order-lifecycle-awaiting-shipment-refund", W, H,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
