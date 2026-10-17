#!/usr/bin/env python3
"""ch.13 figure: context-dependency-graph-cace -- the six contexts' current
dependency graph, each node annotated with the afferent/efferent coupling
(Ca/Ce) the chapter computes for it, resolving into an extraction order that
matches the real build order already run in this repo (tags
`stage/01-review` through `stage/06-order`).

TOP band -- the dependency graph as it exists in `examples/00-monolith/`
today: `order/services.py` imports and calls `inventory.services`,
`payment.services`, and `shipping.services` directly (order's three
synchronous efferent edges -- the god-function orchestration coupling,
SMELL #1), plus one decoupled, asynchronous edge into notification via the
outbox (SMELL #5/#6, already cured, so it is NOT counted as a synchronous
efferent edge). `payment.Payment.order` and `shipping.Shipment.order` each
carry a direct `order_id` foreign key back into order (order's afferent
edges); so does `notification.Notification.order`, even though notification
is reached asynchronously. Review has neither -- "no runtime dependency on
order/inventory/payment/shipping/notification," SMELL #7's one honest
exception being the shared `django.contrib.auth` table, not a context
dependency. The one dashed edge (shipping -> payment) is not part of today's
monolith graph: it is the real dependency `05-payment-service`'s own
`app/refund_consumer.py` gains once payment is extracted, reacting to
`shipment.failed` (r06).

BOTTOM band -- the same six contexts sorted by that score into the order
this repo's own extraction tags already ran in: review (ch.15) ->
notification (ch.17) -> inventory (ch.19) -> payment (ch.23) -> shipping
(ch.24) -> order (ch.26), lowest Ca/Ce first, highest last.

Sourced from `examples/00-monolith/order/services.py`,
`examples/00-monolith/*/models.py` (the FK columns), and the
`stage/01-review` through `stage/06-order` git tags. No codenames;
generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 900

# ============================================================================
# TOP band -- current dependency graph, Ca/Ce per context
# ============================================================================
band_top = {"x": 20, "y": 60, "w": 1260, "h": 480,
            "label": "Dependency graph, current monolith -- Ca/Ce per context",
            "fill": "#fafafa"}

review = node(560, 90, 200, 80,
              ["Review", "Ca: ~0 (nothing calls in)", "Ce: ~0 (no runtime dep)"], style="ghost")

order_n = node(560, 260, 200, 120,
               ["Order", "Ca: highest (3 inbound FKs)", "Ce: highest = 3 sync + 1 async"], style="box")
inventory = node(160, 260, 240, 120,
                 ["Inventory", "Ca: moderate (1 call + 1 FK join)", "Ce: ~0"], style="box")
notification = node(900, 260, 240, 120,
                     ["Notification", "Ca: low (1 async consume)", "Ce: ~0"], style="box")
payment = node(160, 420, 240, 100,
               ["Payment", "Ca: moderate (1 inbound call)", "Ce: ~0 today"], style="box")
shipping = node(900, 420, 240, 100,
                ["Shipping", "Ca: moderate (1 inbound call)", "Ce: ~0 today; +1 post-ch.23"], style="box")

top_nodes = [review, order_n, inventory, notification, payment, shipping]
top_edges = [
    connect(order_n, inventory, amber=True, label="inventory.services.reserve() call", lx=-24, ly=-14),
    connect(order_n, payment, amber=True, label="payment.services.charge()", ly=-16),
    connect(order_n, shipping, amber=True, label="shipping.services.dispatch()", ly=-16),
    connect(order_n, notification, dashed=True, label="outbox -> async consume (SMELL #5/#6 cured)", ly=-16),
    connect(payment, order_n, label="Payment.order FK", ly=18),
    connect(shipping, order_n, label="Shipment.order FK", ly=18),
    connect(notification, order_n, label="Notification.order FK", ly=18),
    connect(shipping, payment, dashed=True, label="future -- 05-payment-service's refund_consumer.py (r06)"),
]

# ============================================================================
# BOTTOM band -- resolved extraction order
# ============================================================================
band_bottom = {"x": 20, "y": 560, "w": 1260, "h": 260,
               "label": "Resolved extraction order -- matches stage/01-review .. stage/06-order, lowest coupling first",
               "fill": "#eaf4ec"}

SEQ = [
    ("1. Review -- ch.15", "Ca~ 0, Ce~ 0 -- lowest score", "ghost"),
    ("2. Notification -- ch.17", "low Ca, low Ce", "box"),
    ("3. Inventory -- ch.19", "moderate Ca, Ce~ 0", "box"),
    ("4. Payment -- ch.23", "moderate Ca, Ce~ 0", "box"),
    ("5. Shipping -- ch.24", "moderate Ca, Ce~ 0", "box"),
    ("6. Order -- ch.26", "highest Ca, highest Ce", "box"),
]
SEQ_W, SEQ_GUTTER, SEQ_X0, SEQ_Y, SEQ_H = 190, 16, 40, 640, 110

seq_nodes = []
for i, (title, detail, style) in enumerate(SEQ):
    x = SEQ_X0 + i * (SEQ_W + SEQ_GUTTER)
    n = node(x, SEQ_Y, SEQ_W, SEQ_H, [title, detail], style=style)
    seq_nodes.append(n)

bottom_edges = []
for i in range(len(seq_nodes) - 1):
    bottom_edges.append(connect(seq_nodes[i], seq_nodes[i + 1], amber=True))

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.13 -- the dependency graph, scored by Ca/Ce, resolves into the extraction order",
     "anchor": "middle", "bold": True, "size": 16},

    {"x": 40, "y": 554,
     "text": "Order's own extraction can't complete until each of the other five has removed one of its three outbound edges -- which is why order goes last, not first.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/00-monolith/order/services.py and each app's models.py; extraction order matches the stage/01-review .. stage/06-order git tags.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "context-dependency-graph-cace", W, H,
    bands=[band_top, band_bottom],
    nodes=top_nodes + seq_nodes,
    edges=top_edges + bottom_edges,
    notes=notes,
)
