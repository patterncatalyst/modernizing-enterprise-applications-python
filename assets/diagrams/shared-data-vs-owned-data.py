#!/usr/bin/env python3
"""ch.18 figure: shared-data-vs-owned-data -- the three data-ownership
postures this book has built so far, stacked so the progression reads top
to bottom: Review stays on the monolith's shared schema (a deliberate,
named deferral); Notification owns its schema from day one because its
seam is asynchronous; Inventory (ch.19, next) owns its schema too, but
getting there needs a one-time transaction-log backfill from the still-live
monolith table during the cutover window, retired once cutover completes.

Sourced from examples/02-review-service/app/models.py (shared-table
mapping, no migration tooling at all), examples/03-notification-service/
app/models.py + migrations/versions/0001_create_notification_schema.py
(owned schema, first Alembic migration), examples/04-inventory-service/
app/models.py + app/cdc_consumer.py + CUTOVER.md (owned schema + transition
CDC, retired after cutover).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 800
PANEL_H = 200

band_a = {"x": 30, "y": 60, "w": 1260, "h": PANEL_H,
          "label": "Panel A -- SHARED (ch.15 Review, deliberate deferral): direct reach into the monolith's own tables, no ACL",
          "fill": "#fafafa"}
band_b = {"x": 30, "y": 60 + PANEL_H + 30, "w": 1260, "h": PANEL_H,
          "label": "Panel B -- OWNED FROM DAY ONE (ch.17 Notification): own schema, reached only via a frozen Kafka contract",
          "fill": "#f1f5f9"}
band_c = {"x": 30, "y": 60 + 2 * (PANEL_H + 30), "w": 1260, "h": PANEL_H + 40,
          "label": "Panel C -- OWNED + CDC BACKFILL (ch.19, next): the hardest cut -- a synchronous seam AND a one-time log tail",
          "fill": "#fafafa"}

# Panel A -- Review
review_svc = node(70, 60 + 70, 280, 100, ["review-service :8001", "app/models.py -- SQLAlchemy mapping", "onto the MONOLITH'S OWN tables"], style="box")
shared_tables = node(440, 60 + 70, 300, 100, ["Shared Postgres schema", "reviews, customers,", "inventory_items, auth_user"], style="sub")
monolith_a = node(820, 60 + 70, 280, 100, ["Django monolith :8000", "writes the same tables", "same schema, same process"], style="box")
edges_a = [
    connect(review_svc, shared_tables, label="direct SELECT/INSERT"),
    connect(monolith_a, shared_tables, label="direct ORM writes"),
]

# Panel B -- Notification
y_b = 60 + PANEL_H + 30 + 70
monolith_b = node(70, y_b, 260, 100, ["Django monolith :8000", "writes an OutboxEvent row", "(order.services.place_order)"], style="box")
kafka_b = node(400, y_b, 240, 100, ["Kafka topic", "order.placed", "frozen JSON contract"], style="sub")
notif_svc = node(720, y_b, 300, 100, ["notification-service", "OWN `notification` schema", "Alembic-migrated, no monolith import"], style="accent")
edges_b = [
    connect(monolith_b, kafka_b, label="publish, at-least-once"),
    connect(kafka_b, notif_svc, label="consume + translate", amber=True),
]

# Panel C -- Inventory
y_c = 60 + 2 * (PANEL_H + 30) + 90
monolith_c = node(70, y_c, 280, 100, ["Django monolith :8000", "public.inventory_items", "SMELL[ch.18]: still shared, pre-cutover"], style="ghost")
cdc_c = node(420, y_c, 260, 100, ["Debezium (ch.19)", "transition-only backfill", "RETIRED after cutover"], style="ghost")
inv_svc = node(760, y_c, 280, 100, ["inventory-service", "OWN `inventory` schema", "gRPC Reserve/Release (ch.19)"], style="accent")
edges_c = [
    connect(monolith_c, cdc_c, label="tail the WAL", dashed=True),
    connect(cdc_c, inv_svc, label="one-time backfill, then sync", dashed=True, amber=True),
    connect(monolith_c, inv_svc, label="gRPC Reserve/Release -- the synchronous seam", amber=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.18 -- shared data is the hardest coupling to break; the three postures this book builds, stacked",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 50, "y": H - 40, "text": "Panel A's shared-schema reach is a named deferral, not an oversight. Panel B shows the clean case: owned from the first migration.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 50, "y": H - 22, "text": "Panel C is the hybrid ch.19 builds: a synchronous gRPC seam plus a one-time, explicitly retired transaction-log backfill.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "shared-data-vs-owned-data", W, H,
    bands=[band_a, band_b, band_c],
    nodes=[review_svc, shared_tables, monolith_a, monolith_b, kafka_b, notif_svc, monolith_c, cdc_c, inv_svc],
    edges=edges_a + edges_b + edges_c,
    notes=notes,
)
