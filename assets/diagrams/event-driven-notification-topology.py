#!/usr/bin/env python3
"""ch.17 figure: event-driven-notification-topology -- the full pipeline, end
to end: checkout commits an outbox row -> a relay publishes it at-least-once
-> Kafka -> TWO INDEPENDENT consumer groups race to read the same topic, one
in the still-running monolith (the "decorating collaborator" move: the
monolith becomes a consumer of its own event) and one in the new
notification-service. The strangler proxy's STRANGLER_NOTIFICATION_ENABLED
flag only decides which read path GET /api/notifications hits -- both
consumers keep running throughout the strangle window.

Sourced from examples/00-monolith/common/management/commands/outbox_relay.py,
examples/00-monolith/notification/management/commands/order_placed_consumer.py
(group monolith-notification), examples/03-notification-service/app/consumer.py
(group notification-service), examples/01-strangler-proxy/app/main.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 680

checkout = node(30, 290, 190, 110, ["Checkout", "place_order()", "@transaction.atomic()"], style="box")
outbox = node(260, 290, 190, 110, ["outbox table", "unpublished rows,", "oldest-first"], style="sub")
relay = node(490, 290, 210, 110, ["outbox_relay", "AIOKafkaProducer", "poll ~1s, at-least-once"], style="box")
kafka = node(740, 290, 210, 110, ["Kafka topic", "order.placed", "key = orderId"], style="accent")

mono_consumer = node(1000, 100, 330, 120, [
    "monolith order_placed_consumer",
    "group: monolith-notification",
    "-> Notification row, monolith schema",
], style="box")
svc_consumer = node(1000, 460, 330, 120, [
    "notification-service OrderPlacedConsumer",
    "group: notification-service",
    "-> Notification row, OWN schema",
], style="accent")

proxy = node(640, 540, 260, 110, [
    "strangler proxy :8888",
    "GET /api/notifications*",
    "STRANGLER_NOTIFICATION_ENABLED",
], style="user")

nodes = [checkout, outbox, relay, kafka, mono_consumer, svc_consumer, proxy]
edges = [
    connect(checkout, outbox, label="INSERT, same txn"),
    connect(outbox, relay, label="poll unpublished"),
    connect(relay, kafka, label="send_and_wait()"),
    connect(kafka, mono_consumer, label="consume (earliest)"),
    connect(kafka, svc_consumer, label="consume (earliest)", amber=True),
    connect(proxy, mono_consumer, label="flag OFF", dashed=True),
    connect(proxy, svc_consumer, label="flag ON", amber=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.17 -- one outbox row, two independent consumer groups, one flag choosing who answers the read",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 30, "y": 250, "text": "Both consumer groups run for the ENTIRE strangle window -- the monolith becomes a consumer of its own event",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
    {"x": 30, "y": 270, "text": "(the decorating-collaborator pattern), not a placeholder removed once notification-service ships.",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
    {"x": 30, "y": H - 24, "text": "Kafka delivery is AT-LEAST-ONCE end to end: the relay can republish, and each consumer can redeliver on its own restart.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "event-driven-notification-topology", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
