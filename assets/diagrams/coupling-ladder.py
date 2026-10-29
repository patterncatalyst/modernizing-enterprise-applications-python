#!/usr/bin/env python3
"""ch.13 figure: coupling-ladder -- the Constantine coupling taxonomy, walked
worst to best, with every rung pinned to its live example in
`examples/00-monolith/` (the two rungs the monolith hasn't reached yet --
message coupling and API/data-structure coupling -- are the target
architecture the extracted services, `examples/02-review-service` through
`examples/07-order-service`, already reach for).

Rung order, definitions, and every monolith example:
  1. Content coupling (worst) -- `order/services.py::_place_order_local`
     reads a live, Django-managed `InventoryItem` straight from
     `inventory.services.get_by_sku()`/`reserve()` (SMELL #1: "no
     anti-corruption layer at the seam").
  2. Common coupling -- the single shared Postgres schema every context
     (order, inventory, payment, shipping, notification, customers) reads
     and writes with no enforced ownership boundary (SMELL #3).
  3. Control coupling -- `OrderCreateSerializer.paymentMethod` threaded into
     `payment.services.charge()`, where the literal string `"DECLINE"`
     selects an approve/decline code path (`payment/services.py::
     DECLINE_SENTINEL`).
  4. Stamp coupling -- `_place_order_local`'s checkout loop is handed the
     FULL `InventoryItem` entity back from `get_by_sku()`/`reserve()`, but
     only reads 3 of its 5 fields (`sku`, `name`, `price_cents`) to build
     `OrderItem`'s snapshot columns.
  5. Data coupling -- `inventory/views.py::InventoryListView.get()` and
     `order/views.py` return `InventoryItemSerializer`/`OrderSerializer`
     output, not raw Django model instances, at the HTTP boundary --
     already done right.
  6. Message coupling and 7. API/data-structure coupling (best) -- no
     monolith example; this is what the extracted services already built in
     this repo (`examples/02-review-service` through
     `examples/07-order-service`) look like once ch.14-26 are done.

No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1100, 1120

RUNGS = [
    ("1. Content coupling (worst)",
     "reaches inside, reads/writes internals directly",
     ["Monolith example -- SMELL #1",
      "_place_order_local reads a live InventoryItem",
      "(sku, name, price_cents) from get_by_sku()/reserve()",
      "no ACL at the seam, only Python's lack of access modifiers"],
     "box", "sub"),
    ("2. Common coupling",
     "shares one global/shared data store",
     ["Monolith example -- SMELL #3",
      "order, inventory, payment, shipping, notification +",
      "customers: one shared Postgres schema, no owner"],
     "box", "sub"),
    ("3. Control coupling",
     "passes a flag that dictates the callee's branching",
     ["Monolith example",
      "OrderCreateSerializer.paymentMethod threaded into",
      "payment.services.charge -- DECLINE_SENTINEL selects approve/decline"],
     "box", "sub"),
    ("4. Stamp coupling",
     "passes a whole structure, receiver uses part",
     ["Monolith example",
      "_place_order_local's loop gets the full InventoryItem back",
      "from get_by_sku()/reserve(), reads 3 of its 5 fields"],
     "box", "sub"),
    ("5. Data coupling",
     "passes only simple, purpose-built parameters",
     ["Monolith example -- already done right",
      "InventoryListView.get() / order/views.py return",
      "InventoryItemSerializer/OrderSerializer output, not raw models"],
     "accent", "accent"),
    ("6. Message coupling",
     "interaction only through message passing",
     ["No monolith example",
      "target architecture after extraction --",
      "interaction only through message passing (examples/02-07)"],
     "ghost", "ghost"),
    ("7. API / data-structure coupling (best)",
     "well-defined contract at the boundary",
     ["No monolith example",
      "target architecture after extraction --",
      "well-defined contract types at the boundary (examples/02-07)"],
     "ghost", "ghost"),
]

LEFT_X, LEFT_W = 50, 330
RIGHT_X, RIGHT_W = 410, 620
ROW_Y0, ROW_H, GUTTER = 100, 120, 16

rung_nodes = []
example_nodes = []
nodes = []
edges = []
for i, (title, defn, example_lines, rstyle, estyle) in enumerate(RUNGS):
    y = ROW_Y0 + i * (ROW_H + GUTTER)
    rn = node(LEFT_X, y, LEFT_W, ROW_H, [title, defn], style=rstyle)
    en = node(RIGHT_X, y, RIGHT_W, ROW_H, example_lines, style=estyle)
    rung_nodes.append(rn)
    example_nodes.append(en)
    nodes.append(rn)
    nodes.append(en)
    edges.append(connect(rn, en))

# ladder chain down the left column, worst (top) to best (bottom)
for i in range(len(rung_nodes) - 1):
    kw = {}
    if i == 0:
        kw = {"amber": True, "label": "Constantine's ladder: worst to best"}
    if i == 4:
        kw = {"amber": True, "label": "no monolith example beyond this point"}
    edges.append(connect(rung_nodes[i], rung_nodes[i + 1], **kw))

notes = [
    {"x": W / 2, "y": 32,
     "text": "the Constantine coupling ladder, scored against the monolith",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "worst (content) at top, best (API/data-structure) at bottom -- five of seven rungs already have a live example",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": LEFT_X, "y": H - 40,
     "text": "Message and API/data-structure coupling have no monolith example today -- they're what the extracted services (examples/02-07) already reach.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": LEFT_X, "y": H - 16,
     "text": "Sourced from examples/00-monolith/SMELLS.md (smells #1 and #3), order/services.py, payment/services.py, inventory/views.py, order/views.py.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "coupling-ladder", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
