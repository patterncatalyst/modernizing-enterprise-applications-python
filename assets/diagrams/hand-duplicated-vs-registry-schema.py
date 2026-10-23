#!/usr/bin/env python3
"""ch.28 figure: hand-duplicated-vs-registry-schema -- two panels. Left,
"today": payment-service's and notification-service's own hand-authored
copies of the order.placed Pydantic model, each independently maintained,
with notification's copy missing paymentMethod (it never needed the field,
so it was never added -- the cost of no shared module between three
independently deployable services, DRQ-036). Right, "ch.28's demonstrator":
one order-placed-v1.avsc registered once with Apicurio, a producer and
consumer both resolving the SAME artifact by global id, with a BACKWARD
compatibility rule standing between any future version and the registry.

Sourced from examples/07-order-service/EVENTS.md ("Produces: order.placed"),
examples/05-payment-service/app/schemas.py::OrderPlacedEvent (payment_method
present, optional, net-new r05), examples/03-notification-service/app/
schemas.py::OrderPlacedEvent (six fields, no payment_method at all), and
examples/09-schema-registry-demo/schemas/order-placed-v1.avsc +
app/registry_client.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 620
PANEL_H = 480

band_left = {"x": 30, "y": 60, "w": 610, "h": PANEL_H,
             "label": "Today -- two hand-authored copies of the same contract",
             "fill": "#fafafa"}
band_right = {"x": 680, "y": 60, "w": 610, "h": PANEL_H,
              "label": "ch.28's demonstrator -- one schema, registered once",
              "fill": "#f1f5f9"}

# Left panel
order_svc = node(70, 110, 530, 70,
                  ["07-order-service -- EVENTS.md", "\"order.placed\": orderId, customerId, customerEmail,",
                   "totalCents, confirmationMessage, placedAt, paymentMethod"],
                  style="box")
payment_copy = node(70, 230, 250, 110,
                     ["05-payment-service", "app/schemas.py::OrderPlacedEvent", "7 fields -- paymentMethod", "present (choreographed", "decline rule needs it)"],
                     style="sub")
notif_copy = node(350, 230, 250, 110,
                   ["03-notification-service", "app/schemas.py::OrderPlacedEvent", "6 fields -- NO paymentMethod", "(never needed, so never", "added to this copy)"],
                   style="ghost")
drift_note = node(70, 400, 530, 90,
                   ["Two independent authors, two independent understandings,", "no mechanism checking they still agree -- a hand-maintained",
                    "JSON contract re-declared per consumer (DRQ-036)"],
                   style="box")
edges_left = [
    connect(order_svc, payment_copy, label="publishes, payment reads"),
    connect(order_svc, notif_copy, label="publishes, notification reads"),
    connect(payment_copy, drift_note, dashed=True),
    connect(notif_copy, drift_note, dashed=True),
]

# Right panel
avsc = node(720, 110, 530, 80,
            ["schemas/order-placed-v1.avsc", "one Avro record, field-for-field mirror", "of the real order.placed JSON shape"],
            style="accent")
registry = node(800, 230, 370, 80,
                ["Apicurio registry", "artifact: order-placed-value", "BACKWARD compatibility rule attached"],
                style="box")
producer = node(720, 350, 240, 90,
                ["OrderAvroProducer", "registers/resolves the", "artifact, stamps the", "global id on the wire"],
                style="sub")
consumer = node(1010, 350, 240, 90,
                ["OrderAvroConsumer", "fetches the EXACT writer", "schema by global id,", "never assumes its own copy"],
                style="sub")
edges_right = [
    connect(avsc, registry, label="register once", amber=True),
    connect(producer, registry, label="register_or_resolve"),
    connect(consumer, registry, label="get_schema_by_global_id"),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.28 -- the hand-maintained JSON contract's drift, and the registry-governed alternative demonstrated alongside it",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 50, "y": H - 22, "text": "The registry is additive: order.placed stays plain JSON. The demonstrator publishes an Avro mirror to its own topic, order.events.avro.demo.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "hand-duplicated-vs-registry-schema", W, H,
    bands=[band_left, band_right],
    nodes=[order_svc, payment_copy, notif_copy, drift_note, avsc, registry, producer, consumer],
    edges=edges_left + edges_right,
    notes=notes,
)
