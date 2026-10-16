#!/usr/bin/env python3
"""ch.17 figure: idempotent-consumer-dedupe -- what actually happens when the
at-least-once outbox relay redelivers the SAME order.placed event twice, and
why exactly one Notification row survives either way: application-level
check-then-insert is the fast path, a database-level partial unique index on
order_id is the backstop for a concurrent race between two redeliveries.

Sourced from examples/00-monolith/notification/services.py::record_order_placed
and examples/03-notification-service/app/service.py::record_order_placed (same
shape in both the Django and the FastAPI service), plus the partial unique
index in both common/models.py::OutboxEvent's sibling (Notification's
uniq_notification_per_order) and migrations/versions/0001_...py
(uq_notifications_order_id).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 560

relay = node(30, 60, 220, 100, ["outbox_relay", "publish succeeds,", "CRASH before stamping", "published_at"], style="ghost")
redeliver_note = node(290, 60, 220, 100, ["Next poll: row still", "unpublished -- the", "SAME event is", "republished"], style="sub")

delivery1 = node(560, 30, 260, 90, ["Delivery #1", "order.placed, orderId=555"], style="box")
delivery2 = node(560, 160, 260, 90, ["Delivery #2 (redelivery)", "order.placed, orderId=555"], style="box")

check1 = node(880, 30, 180, 90, ["get_by_order_id()", "-> None", "INSERT row"], style="accent")
check2 = node(880, 160, 180, 90, ["get_by_order_id()", "-> existing row", "no-op, skip"], style="accent")

race_note = node(560, 320, 500, 100, [
    "Concurrent race (two deliveries check at once):",
    "both see None, both INSERT -> second INSERT raises IntegrityError",
    "on the partial unique index -> caught, rolled back, treated as a duplicate",
], style="sub")

result = node(1120, 95, 140, 150, ["Exactly ONE", "Notification", "row", "for orderId=555"], style="accent")

nodes = [relay, redeliver_note, delivery1, delivery2, check1, check2, race_note, result]
edges = [
    connect(relay, redeliver_note),
    connect(redeliver_note, delivery1),
    connect(redeliver_note, delivery2),
    connect(delivery1, check1),
    connect(delivery2, check2),
    connect(check1, result, amber=True),
    connect(check2, result, dashed=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.17 -- at-least-once delivery, exactly-once effect: check-then-insert plus a DB backstop",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 30, "y": H - 40, "text": "Two layers, not one: the application-level check (get_by_order_id) is the common case; the partial unique index",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 30, "y": H - 22, "text": "on order_id is the backstop for the narrow window where two redeliveries race the check itself.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "idempotent-consumer-dedupe", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
