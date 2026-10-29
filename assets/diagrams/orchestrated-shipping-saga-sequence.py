#!/usr/bin/env python3
"""ch.24 figure: orchestrated-shipping-saga-sequence -- the four-step
orchestrated saga top to bottom, with ONE coordinator (app/orchestrator.py)
deciding what happens next at every step, and the reverse-order compensation
path it takes on a book_carrier failure. Contrast with ch.23's
choreographed-payment-saga-sequence, where no such coordinator box exists.

Sourced from examples/06-shipping-service/app/orchestrator.py (advance(),
_advance_one_step(), compensate()), app/steps.py (enrich/dispatch/
book_carrier/emit, cancel_shipment), app/enrich_client.py (the tenacity-
wrapped HTTP call), EVENTS.md (the shipment.dispatched/shipment.failed wire
shapes).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 1020

n_trigger = node(500, 25, 320, 65, ["Kafka: payment.captured", "(key = orderId)"], style="box")
n_consumer = node(470, 115, 380, 75,
                   ["service.handle_payment_captured:", "check-then-insert + uq_sagas_order_id"], style="box")
n_orch = node(460, 215, 400, 70, ["orchestrator.advance(saga_id)", "THE coordinator -- decides each next step"], style="accent")

n_s1 = node(80, 320, 280, 90, ["Step 1: enrich", "GET monolith /api/orders/{id}", "tenacity retry + bounded timeout"], style="box")
n_s2 = node(400, 320, 280, 90, ["Step 2: dispatch", "persist Shipment DISPATCHED", "(own shipping schema)"], style="box")
n_s3 = node(720, 320, 280, 90, ["Step 3: book_carrier", "SHIP-FAIL sentinel check", "no persistence of its own"], style="box")
n_s4 = node(1040, 320, 240, 90, ["Step 4: emit", "shipment.dispatched outbox +", "saga -> COMPLETED, one txn"], style="accent")

n_lock = node(80, 460, 1200, 50,
              ["each step above: ONE transaction, SELECT ... FOR UPDATE + idempotent status guard, step_index++ on success"],
              style="sub")

n_fail = node(720, 560, 280, 70, ["BookCarrierFailed raised", "saga -> COMPENSATING"], style="ghost")
n_comp = node(400, 660, 320, 70, ["compensate(): reverse order", "over only-COMPLETED steps"], style="accent")
n_cancel = node(80, 760, 280, 80, ["cancel_shipment", "(dispatch's only inverse)", "Shipment -> CANCELLED, not deleted"], style="box")
n_shipfailed = node(400, 760, 320, 90,
                     ["shipment.failed outbox write +", "saga -> COMPENSATED, SAME txn", "reason: SHIP-FAIL sentinel"], style="accent")

n_dispatched_topic = node(1040, 460, 240, 70, ["Kafka:", "shipment.dispatched"], style="box")
n_failed_topic = node(400, 890, 320, 70, ["Kafka:", "shipment.failed"], style="box")

nodes = [n_trigger, n_consumer, n_orch, n_s1, n_s2, n_s3, n_s4, n_lock,
         n_fail, n_comp, n_cancel, n_shipfailed, n_dispatched_topic, n_failed_topic]

edges = [
    connect(n_trigger, n_consumer),
    connect(n_consumer, n_orch),
    connect(n_orch, n_s1, label="step_index=0"),
    connect(n_s1, n_s2, label="advance() recurses"),
    connect(n_s2, n_s3, label="advance() recurses"),
    connect(n_s3, n_s4, label="booked ok"),
    connect(n_s4, n_dispatched_topic),
    connect(n_s3, n_fail, dashed=True, label="SHIP-FAIL address"),
    connect(n_fail, n_comp),
    connect(n_comp, n_cancel, label="undo step 2 (only completed inverse)"),
    connect(n_comp, n_shipfailed),
    connect(n_shipfailed, n_failed_topic),
]

notes = [
    {"x": W / 2, "y": 18, "text": "the orchestrated saga: ONE coordinator sequences every step and owns the compensation decision",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 46, "text": "enrich and book_carrier persist nothing of their own, so neither has a compensation entry -- only dispatch's Shipment row needs undoing.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "Compare the choreographed payment saga: no box in this picture's counterpart decides anything for another box.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "orchestrated-shipping-saga-sequence", W, H,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
