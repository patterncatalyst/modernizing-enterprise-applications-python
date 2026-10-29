#!/usr/bin/env python3
"""ch.08 figure: place-order-transaction-sequence: the structural heart of
the book's "before" picture: `order/services.py::_place_order_local` (the
default checkout path: `INVENTORY_MODE=local`, `PAYMENT_MODE=synchronous`,
`SHIPPING_MODE=inprocess`) as ONE `transaction.atomic()` spanning five
bounded contexts, in-process, one database, atomic rollback automatically. Reused
conceptually by ch.09 (Smells 1-4), ch.12 (event storming), ch.22 (ACID ->
ACD), and ch.23/24 (sagas rebuild explicitly what Postgres gave away here
automatically).

Call order and exception semantics sourced verbatim from
`examples/00-monolith/order/services.py::_place_order_local` and
`order/services.py::place_order`'s own module docstring. Notification is
not a synchronous step here: SMELL #5/#6 (sync send,
dual-write) are already CURED as of r03: the only notification-shaped thing
this transaction does is write one `OutboxEvent` row; a separate relay +
consumer pair (outside this transaction) carries it to `notification`
afterward. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1680, 700

client = node(30, 270, 150, 80, ["Client", "POST /api/orders"], style="sub")

band = {"x": 200, "y": 170, "w": 1310, "h": 300,
        "label": "ONE transaction.atomic() -- order/services.py::_place_order_local",
        "fill": "#eaf4ec"}

STEP_Y, STEP_H, STEP_W, GUTTER = 240, 120, 145, 12
STEP_X0 = 220
steps = [
    ("validate", ["Validate customer", "Customer.objects.get", "404 if missing"]),
    ("reserve", ["Reserve stock (loop)", "inventory_services.reserve()", "row lock -- SMELL #1 no ACL"]),
    ("persist", ["Persist order", "Order/OrderItem.objects.create", "snapshot sku/name/price"]),
    ("charge", ["Charge payment", "payment_services.charge()", "decline -> rolls back all above"]),
    ("confirm", ["Confirm order", "order.confirm()", "status -> CONFIRMED"]),
    ("dispatch", ["Dispatch shipment", "shipping_services.dispatch()", "SHIP-FAIL sentinel raises here"]),
    ("outbox", ["Write outbox row", "OutboxEvent(event_type=order.placed)", "SMELL #5/#6 CURED"]),
    ("commit", ["COMMIT", "one Postgres transaction", "five contexts' writes, atomic"]),
]

step_nodes = {}
nodes = [client]
for i, (key, lines) in enumerate(steps):
    x = STEP_X0 + i * (STEP_W + GUTTER)
    style = "accent" if key == "commit" else "box"
    n = node(x, STEP_Y, STEP_W, STEP_H, lines, style=style)
    step_nodes[key] = n
    nodes.append(n)

response = node(1540, 270, 120, 80, ["201 Created", "OrderSerializer"], style="accent")
nodes.append(response)

edges = [connect(client, step_nodes["validate"])]
order_keys = [k for k, _ in steps]
for a, b in zip(order_keys, order_keys[1:]):
    edges.append(connect(step_nodes[a], step_nodes[b]))
edges.append(connect(step_nodes["commit"], response, amber=True, label="txn commits"))

# ---- failure branch 1: insufficient stock: exits before any write --------
insufficient = node(step_nodes["reserve"]["x"] - 10, 480, 260, 90,
                     ["409 Conflict", "OUT_OF_STOCK", "no writes yet: exits before persist"],
                     style="ghost")
nodes.append(insufficient)
edges.append(connect(step_nodes["reserve"], insufficient, dashed=True, label="quantity exceeds on-hand"))

# ---- failure branch 2: payment decline: rolls back everything written ----
rollback = node(step_nodes["charge"]["x"] - 40, 480, 300, 100,
                ["402 Payment Required", "PAYMENT_DECLINED", "ROLLBACK ALL: reserve + persist undone"],
                style="ghost")
nodes.append(rollback)
edges.append(connect(step_nodes["charge"], rollback, dashed=True, label="paymentMethod contains DECLINE"))
edges.append({"x1": rollback["x"] + 20, "y1": rollback["y"], "x2": step_nodes["persist"]["x"] + 40,
              "y2": step_nodes["persist"]["y"] + step_nodes["persist"]["h"],
              "dashed": True, "amber": True})
edges.append({"x1": rollback["x"] + 60, "y1": rollback["y"], "x2": step_nodes["reserve"]["x"] + 160,
              "y2": step_nodes["reserve"]["y"] + step_nodes["reserve"]["h"],
              "dashed": True, "amber": True,
              "label": "one shared Postgres transaction: undone automatically, free", "ly": -8})

notes = [
    {"x": W / 2, "y": 32, "text": "_place_order_local: one transaction.atomic() spans five bounded contexts",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "validate -> reserve -> persist -> charge -> confirm -> dispatch -> write outbox row -> commit, in-process, one database",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 46,
     "text": "SMELL #2: this rollback-for-free behavior disappears the moment any one of these contexts gets its own database.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/00-monolith/order/services.py::_place_order_local (the INVENTORY_MODE=local / PAYMENT_MODE=synchronous / SHIPPING_MODE=inprocess default path).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "place-order-transaction-sequence", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
