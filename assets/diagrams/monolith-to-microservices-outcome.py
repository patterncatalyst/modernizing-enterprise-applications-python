#!/usr/bin/env python3
"""ch.00 figure: monolith-to-microservices-outcome -- the book's headline
before/after arc (side-by-side: this IS the required before/after
comparison, not an arbitrary merge of unrelated diagrams).

LEFT -- "before": one Django 5.2 LTS + DRF deployable (uv + Python 3.14)
containing six in-process bounded-context apps (order, inventory, payment,
shipping, notification, review) sharing one PostgreSQL schema. Checkout
wraps everything in one `transaction.atomic()` block reaching into
inventory, payment, shipping, and notification -- drawn as an amber bus so
the lines never cross a box -- per `_plans/build-plan.md` ("Django 5.2 LTS
+ DRF, not Spring Boot... one shared Postgres schema") and
`examples/00-monolith/SMELLS.md` (smell #2, the one-`transaction.atomic()`-
spanning-five-contexts smell).

RIGHT -- "after": six independent FastAPI services, each owning its own
schema, plus the Strawberry GraphQL gateway, all reached through one
Starlette + httpx ASGI strangler proxy; a Kafka event backbone carries the
outbox and saga-coordination traffic for notification, payment, shipping,
and order. Ports mirror this project's own real topology (see
`final-monolith-free-topology.py`) -- same six services, same ports.

Sourced from: `_plans/build-plan.md` ("A. Approach" -- the Django-to-FastAPI
stack decisions), `examples/00-monolith/SMELLS.md`, and
`examples/01-strangler-proxy/app/config.py` / `final-monolith-free-
topology.py` for the "after" topology and ports.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1560, 860

# ============================= LEFT: before ================================
outer_band_L = {"x": 40, "y": 70, "w": 710, "h": 680,
                "label": "Django monolith -- one deployable (uv + Python 3.14)", "fill": "#ffffff"}

order = node(70, 110, 200, 74, ["Order", "Django app"], style="box")
inventory = node(290, 110, 200, 74, ["Inventory", "Django app"], style="box")
payment = node(510, 110, 200, 74, ["Payment", "Django app"], style="box")
shipping = node(70, 210, 200, 74, ["Shipping", "Django app"], style="box")
notification = node(290, 210, 200, 74, ["Notification", "Django app"], style="box")
review = node(510, 210, 200, 74, ["Review", "Django app"], style="accent")

left_ctx_nodes = [order, inventory, payment, shipping, notification, review]

# ACID-transaction bus: order -> inventory, shipping are adjacent (direct);
# order -> payment, notification are not adjacent, so route through the
# gutter between the two rows so the lines never cross a box.
bus_y = 197
left_bus_edges = [
    connect(order, inventory, amber=True),
    connect(order, shipping, amber=True),
    {"x1": 170, "y1": 184, "x2": 170, "y2": bus_y, "amber": True},
    {"x1": 170, "y1": bus_y, "x2": 610, "y2": bus_y, "amber": True,
     "label": "one transaction.atomic() checkout (ACID): order -> inventory, payment, shipping, notification"},
    {"x1": 390, "y1": bus_y, "x2": 390, "y2": 210, "amber": True},
    {"x1": 610, "y1": bus_y, "x2": 610, "y2": 184, "amber": True},
]

pg_band = {"x": 70, "y": 340, "w": 640, "h": 150, "label": "One shared PostgreSQL schema", "fill": "#fafafa"}
pg_tables = node(90, 372, 600, 90,
                  ["customers * orders * order_items * inventory_items",
                   "payments * shipments * notifications * reviews",
                   "one Django-migrations-managed schema, cross-app foreign keys"], style="sub")

left_nodes = left_ctx_nodes + [pg_tables]
left_edges = left_bus_edges

left_notes = [
    {"x": 395, "y": 745, "text": "review is REST-only -- no synchronous collaborator, outside the checkout transaction",
     "anchor": "middle", "size": 10.5, "color": "#555555"},
]

# ============================= RIGHT: after =================================
outer_band_R = {"x": 850, "y": 70, "w": 670, "h": 680,
                "label": "Six FastAPI services + Strawberry GraphQL gateway, behind one ASGI edge router", "fill": "#ffffff"}

router = node(870, 100, 220, 160, ["ASGI strangler proxy", ":8888 -- single entry point"], style="accent")
kafka = node(870, 300, 220, 160, ["Kafka (KRaft)", "event backbone -- outbox + saga coordination"], style="box")

rev_svc = node(1210, 95, 280, 70, ["Review service :8001", "owns review schema"], style="box")
notif_svc = node(1210, 182, 280, 70, ["Notification service :8002", "owns notification schema"], style="box")
inv_svc = node(1210, 269, 280, 70, ["Inventory service :8084 / :9004", "owns inventory schema"], style="box")
pay_svc = node(1210, 356, 280, 70, ["Payment service :8085", "owns payment schema"], style="box")
ship_svc = node(1210, 443, 280, 70, ["Shipping service :8087", "owns shipping schema"], style="box")
order_svc = node(1210, 530, 280, 70, ["Order service :8088", "owns order schema, CQRS"], style="accent")
gateway = node(1210, 617, 280, 70, ["GraphQL gateway :8090", "Strawberry -- aggregates, owns no data"], style="accent")

right_stack = [rev_svc, notif_svc, inv_svc, pay_svc, ship_svc, order_svc, gateway]

router_edges = [connect(router, n) for n in right_stack[:-1]]
router_edges.append(connect(router, gateway, amber=True, label="/graphql"))

kafka_edges = [connect(kafka, n, amber=True, dashed=True) for n in (notif_svc, pay_svc, ship_svc, order_svc)]

right_nodes = [router, kafka] + right_stack
right_edges = router_edges + kafka_edges

right_notes = [
    {"x": 1350, "y": 745, "text": "events: outbox relay (notification, payment, shipping) + saga coordination (order)",
     "anchor": "middle", "size": 10.5, "color": "#555555"},
]

# ============================= divider =======================================
divider_edge = [{"x1": 760, "y1": 400, "x2": 840, "y2": 400, "amber": True}]
divider_notes = [
    {"x": 800, "y": 370, "text": "strangler fig,", "anchor": "middle", "bold": True, "size": 12.5, "color": "#2f5f3d"},
    {"x": 800, "y": 386, "text": "one seam at", "anchor": "middle", "bold": True, "size": 12.5, "color": "#2f5f3d"},
    {"x": 800, "y": 402, "text": "a time", "anchor": "middle", "bold": True, "size": 12.5, "color": "#2f5f3d"},
    {"x": 800, "y": 428, "text": "extraction", "anchor": "middle", "size": 10, "color": "#555555"},
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "the outcome: one deployable, one shared schema -> six owned-data services behind an edge router",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 395, "y": 58, "text": "Before", "anchor": "middle", "bold": True, "size": 14, "color": "#555555"},
    {"x": 1185, "y": 58, "text": "After", "anchor": "middle", "bold": True, "size": 14, "color": "#2f5f3d"},
    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/build-plan.md (\"A. Approach\"), examples/00-monolith/SMELLS.md, and "
             "examples/01-strangler-proxy/app/config.py / final-monolith-free-topology.py -- same six services, same ports.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
] + left_notes + right_notes + divider_notes

g.emit(
    "monolith-to-microservices-outcome", W, H,
    bands=[outer_band_L, pg_band, outer_band_R],
    nodes=left_nodes + right_nodes,
    edges=left_edges + right_edges + divider_edge,
    notes=notes,
)
