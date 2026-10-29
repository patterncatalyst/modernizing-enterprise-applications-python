#!/usr/bin/env python3
"""ch.20 figure: multi-outbox-saga-topology -- this project's first
MULTI-SERVICE outbox choreography. Notification (ch.17) was one outbox
feeding one consumer. Payment (r05) chains TWO outboxes end to end, each
owned by a different service, with no coordinator anywhere in the picture:
the monolith's order.placed outbox feeds payment-service's consumer, which
writes ITS OWN outbox (payment.captured/declined), which the monolith's own
order_saga_listener consumes in turn. Each hop is independently
at-least-once; nothing in this picture is a request/response call.

Sourced from examples/00-monolith/order/services.py::_place_order_choreographed,
examples/00-monolith/common/management/commands/outbox_relay.py,
examples/05-payment-service/app/{consumer,service,relay}.py,
examples/00-monolith/order/management/commands/order_saga_listener.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 620

band_mono1 = {"x": 20, "y": 50, "w": 620, "h": 190,
              "label": "Monolith -- order context (owns the checkout)", "fill": "#fafafa"}
band_pay = {"x": 700, "y": 50, "w": 640, "h": 190,
            "label": "payment-service -- owns its OWN schema + outbox", "fill": "#f1f5f9"}
band_mono2 = {"x": 20, "y": 280, "w": 620, "h": 190,
              "label": "Monolith -- order_saga_listener (a second consumer, same process)", "fill": "#fafafa"}

n_checkout = node(50, 130, 250, 90, ["_place_order_choreographed()", "PENDING order + outbox row,", "ONE local transaction"], style="accent")
n_relay1 = node(330, 130, 280, 90, ["outbox_relay", "(this service's OWN relay)"], style="box")
mono1_nodes = [n_checkout, n_relay1]
mono1_edges = [connect(n_checkout, n_relay1)]

n_consume = node(730, 130, 280, 90, ["order.placed consumer", "charge() + persist Payment", "+ OWN outbox row, ONE txn"], style="accent")
n_relay2 = node(1040, 130, 260, 90, ["OutboxRelay", "(payment-service's OWN relay)"], style="box")
pay_nodes = [n_consume, n_relay2]
pay_edges = [connect(n_consume, n_relay2)]

edge_topic1 = {"x1": 610, "y1": 175, "x2": 730, "y2": 175, "label": "Kafka: order.placed", "amber": True}

n_saga = node(50, 360, 280, 90, ["order_saga_listener", "status-transition guard,", "idempotent on redelivery"], style="accent")
n_reaction = node(380, 360, 260, 90, ["handle_payment_captured /", "handle_payment_declined", "confirm+ship | release+decline"], style="box")
mono2_nodes = [n_saga, n_reaction]
mono2_edges = [connect(n_saga, n_reaction)]

edge_topic2 = {"x1": 1170, "y1": 220, "x2": 190, "y2": 360, "label": "Kafka: payment.captured / payment.declined", "amber": True, "dashed": True}

notes = [
    {"x": W / 2, "y": 28, "text": "two outboxes chained end to end, no orchestrator anywhere in this picture",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 40, "y": H - 46, "text": "Each hop (outbox -> relay -> topic -> consumer) is independently at-least-once; the monolith is BOTH the first producer",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "and the final consumer -- a request that started as a checkout ends as a Kafka message the same process reacts to.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "multi-outbox-saga-topology", W, H,
    bands=[band_mono1, band_pay, band_mono2],
    nodes=mono1_nodes + pay_nodes + mono2_nodes,
    edges=mono1_edges + pay_edges + mono2_edges + [edge_topic1, edge_topic2],
    notes=notes,
)
