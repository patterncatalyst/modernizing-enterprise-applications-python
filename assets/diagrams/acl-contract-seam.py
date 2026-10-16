#!/usr/bin/env python3
"""ch.16 figure: acl-contract-seam -- the anti-corruption layer as a CONTRACT,
not a request. Two panels contrast the two extractions this book has built
so far:

  - Panel A (ch.15, Review): no ACL at this seam -- review-service reads and
    writes the MONOLITH'S OWN shared Postgres tables directly (reviews,
    customers, inventory_items, auth_user). That's a deliberate, named
    deferral (ch.18/19 give it its own schema), not a hidden smell.
  - Panel B (ch.16/17, Notification): an ACL IS at this seam -- the only
    thing that crosses from the monolith's world into notification-service's
    world is a frozen JSON event on Kafka; `app/schemas.py::OrderPlacedEvent`
    is this service's OWN translation of that contract, and the service never
    reaches into the monolith's `notifications`/`customers` tables at all.

Sourced from examples/02-review-service/app/models.py (shared-table mapping),
examples/03-notification-service/app/schemas.py (OrderPlacedEvent),
app/models.py (the service's OWN `notification` schema).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 640
PANEL_H = 260

band_a = {"x": 30, "y": 60, "w": 1220, "h": PANEL_H, "label": "Panel A -- no ACL (ch.15 Review): a request into someone else's tables", "fill": "#fafafa"}
band_b = {"x": 30, "y": 60 + PANEL_H + 40, "w": 1220, "h": PANEL_H, "label": "Panel B -- an ACL (ch.16/17 Notification): a contract, not a request", "fill": "#f1f5f9"}

# Panel A
review_svc = node(70, 150, 260, 100, ["review-service :8001", "app/models.py -- SQLAlchemy mapping", "onto the MONOLITH'S OWN tables"], style="box")
shared_tables = node(420, 150, 320, 100, ["Shared Postgres schema", "reviews, customers,", "inventory_items, auth_user"], style="sub")
monolith_a = node(820, 150, 300, 100, ["Django monolith :8000", "writes the same tables", "(same schema, same process)"], style="box")

edges_a = [
    connect(review_svc, shared_tables, label="direct SELECT/INSERT", amber=False),
    connect(monolith_a, shared_tables, label="direct ORM writes"),
]

# Panel B
monolith_b = node(70, 150 + PANEL_H + 40, 260, 100, ["Django monolith :8000", "order.services.place_order()", "writes an OutboxEvent row"], style="box")
kafka = node(400, 150 + PANEL_H + 40, 260, 100, ["Kafka topic order.placed", "FROZEN JSON contract", "orderId, customerId, ..."], style="sub")
acl = node(730, 150 + PANEL_H + 40, 260, 100, ["app/schemas.py::OrderPlacedEvent", "THIS SERVICE'S OWN COPY", "of the contract -- the ACL"], style="accent")
own_schema = node(1030, 150 + PANEL_H + 40, 190, 100, ["notification schema", "OWNED, Alembic-migrated", "no monolith import"], style="accent")

edges_b = [
    connect(monolith_b, kafka, label="publish (at-least-once)"),
    connect(kafka, acl, label="consume + validate", amber=True),
    connect(acl, own_schema, label="translate -> own row", amber=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.16 -- the ACL is a translation boundary, not just \"another request\"",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 50, "y": H - 40, "text": "Panel A's shared-schema reach is a deliberate, named deferral (ch.18/19 give review its own schema) --",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 50, "y": H - 22, "text": "Panel B's OrderPlacedEvent is what makes notification-service genuinely independent of the monolith's schema.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "acl-contract-seam", W, H,
    bands=[band_a, band_b],
    nodes=[review_svc, shared_tables, monolith_a, monolith_b, kafka, acl, own_schema],
    edges=edges_a + edges_b,
    notes=notes,
)
