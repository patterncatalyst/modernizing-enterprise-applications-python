#!/usr/bin/env python3
"""ch.22 figure: acid-to-acd-boundary -- what the single transaction.atomic()
used to span versus what it spans now. BEFORE: one atomic block wraps the
order row, the payment charge, shipping dispatch, and the outbox write --
Atomicity, Consistency, Isolation (nobody sees the order until it's
CONFIRMED or rolled back entirely), and Durability, all from one commit.
AFTER: the SAME call keeps Atomicity/Consistency/Durability for what's left
inside it (order + items + outbox), but Isolation is gone for the gap it
no longer covers -- a PENDING order is visible, queryable, and real the
instant that smaller transaction commits, well before payment or shipping
have an opinion.

Sourced from examples/00-monolith/order/services.py (_place_order_local vs
_place_order_choreographed), order/models.py::Order.Status.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1340, 760

band_before = {"x": 20, "y": 56, "w": 1300, "h": 260,
               "label": "BEFORE -- PAYMENT_MODE=synchronous: ACID, one atomic() spans everything", "fill": "#fafafa"}
band_after = {"x": 20, "y": 56 + 260 + 36, "w": 1300, "h": 340,
              "label": "AFTER -- PAYMENT_MODE=choreographed: ACD kept for a smaller scope, Isolation traded away for the gap outside it", "fill": "#f1f5f9"}

inner_before = {"x": 60, "y": 130, "w": 1200, "h": 150,
                "label": "transaction.atomic() -- Atomicity + Consistency + Isolation + Durability", "fill": "#eef2ff"}
b_order = node(90, 170, 220, 90, ["Order row", "(CONFIRMED on commit)"], style="box")
b_pay = node(340, 170, 220, 90, ["Charge payment", "(decline rolls back all)"], style="box")
b_ship = node(590, 170, 220, 90, ["Dispatch shipping", "(fail rolls back all)"], style="box")
b_outbox = node(840, 170, 220, 90, ["Outbox row", "confirmationMessage=\"confirmed\""], style="box")
b_nolook = node(1090, 170, 150, 90, ["Nobody sees a", "partial order"], style="ghost")
before_nodes = [b_order, b_pay, b_ship, b_outbox, b_nolook]
before_edges = [
    connect(b_order, b_pay), connect(b_pay, b_ship), connect(b_ship, b_outbox),
    connect(b_outbox, b_nolook, dashed=True),
]

y2 = 56 + 260 + 36
inner_after = {"x": 60, "y": y2 + 70, "w": 480, "h": 140,
               "label": "transaction.atomic() -- A+C+D kept, smaller scope", "fill": "#eef2ff"}
a_order = node(90, y2 + 110, 190, 80, ["Order row", "status=PENDING"], style="box")
a_outbox = node(320, y2 + 110, 190, 80, ["Outbox row", "+paymentMethod"], style="box")
after_inner_nodes = [a_order, a_outbox]
after_inner_edges = [connect(a_order, a_outbox)]

a_window = node(580, y2 + 90, 340, 130,
                ["ISOLATION GONE HERE:", "PENDING is visible, queryable, REAL --", "other transactions see it before payment", "or shipping have an opinion"], style="ghost")
a_async = node(970, y2 + 90, 310, 130,
               ["payment + shipping resolve", "OUTSIDE any local transaction,", "asynchronously, via the saga"], style="accent")
after_outer_nodes = [a_window, a_async]
after_outer_edges = [
    connect(a_outbox, a_window, dashed=True, amber=True, label="the window ch.22 names"),
    connect(a_window, a_async),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.22 -- ACID -> ACD: Atomicity, Consistency, Durability survive the cut; Isolation does not",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 40, "y": H - 46, "text": "This is not a bug introduced by the extraction -- it's the real cost of a saga replacing a single shared",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "write-ahead log; compensation (explicit Release/decline handling) is what rebuilds consistency across the gap.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "acid-to-acd-boundary", W, H,
    bands=[band_before, band_after, inner_before, inner_after],
    nodes=before_nodes + after_inner_nodes + after_outer_nodes,
    edges=before_edges + after_inner_edges + after_outer_edges,
    notes=notes,
)
