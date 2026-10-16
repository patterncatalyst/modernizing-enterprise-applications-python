#!/usr/bin/env python3
"""ch.17 figure: outbox-write-in-transaction -- the dual-write hazard (SMELL
#5/#6) before and after, inside order.services.place_order()'s single
@transaction.atomic(). The outbox cure doesn't remove a transaction boundary
or add a new one; it changes WHAT the last write inside that boundary is.

BEFORE: the last step is a SYNCHRONOUS call out of the transaction's own
process to a second system (the notification "send") -- a real dual write,
since the DB commit and the external call are not atomic with each other.

AFTER: the last step is an ordinary INSERT into this service's own
`outbox` table, in the SAME transaction as everything else -- atomic with
the inventory reservation, the order row, and the payment capture, for free,
using nothing but Postgres's own rollback.

Sourced from examples/00-monolith/order/services.py::place_order,
examples/00-monolith/common/models.py::OutboxEvent, SMELLS.md (#5, #6).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 640
PANEL_H = 260

band_before = {"x": 30, "y": 60, "w": 1220, "h": PANEL_H,
               "label": "BEFORE (SMELL #5/#6) -- @transaction.atomic() ends with a dual write", "fill": "#fafafa"}
band_after = {"x": 30, "y": 60 + PANEL_H + 40, "w": 1220, "h": PANEL_H,
              "label": "AFTER (r03, CURED) -- @transaction.atomic() ends with one ordinary row", "fill": "#f1f5f9"}


before_steps = [
    node(70, 150, 230, 110, ["Validate + reserve", "customer, inventory,", "create Order row"], style="box"),
    node(330, 150, 230, 110, ["Charge payment", "(decline rolls back", "reservation + order)"], style="box"),
    node(590, 150, 230, 110, ["Dispatch shipping", "(SHIP-FAIL rolls back", "everything above)"], style="box"),
    node(850, 150, 300, 110, ["send_order_confirmation()", "SYNCHRONOUS call out of this", "transaction's own process"], style="ghost"),
]
before_edges = [connect(before_steps[i], before_steps[i + 1]) for i in range(len(before_steps) - 1)]

after_steps = [
    node(70, 150 + PANEL_H + 40, 230, 110, ["Validate + reserve", "customer, inventory,", "create Order row"], style="box"),
    node(330, 150 + PANEL_H + 40, 230, 110, ["Charge payment", "(decline rolls back", "reservation + order)"], style="box"),
    node(590, 150 + PANEL_H + 40, 230, 110, ["Dispatch shipping", "(SHIP-FAIL rolls back", "everything above)"], style="box"),
    node(850, 150 + PANEL_H + 40, 300, 110, ["OutboxEvent.objects.create(...)", "ONE ordinary row, SAME", "transaction, atomic for free"], style="accent"),
]
after_edges = [connect(after_steps[i], after_steps[i + 1]) for i in range(len(after_steps) - 1)]
after_edges[-1]["amber"] = True

notes = [
    {"x": W / 2, "y": 32, "text": "ch.17 -- the outbox cure changes the LAST WRITE inside checkout's transaction, not the transaction itself",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 50, "y": H - 40, "text": "BEFORE: a crash between the DB commit and the provider call loses the notification silently, or a naive retry duplicates it.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 50, "y": H - 22, "text": "AFTER: the outbox row rolls back for free with everything else; a separate relay publishes it at-least-once, independently.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "outbox-write-in-transaction", W, H,
    bands=[band_before, band_after],
    nodes=before_steps + after_steps,
    edges=before_edges + after_edges,
    notes=notes,
)
