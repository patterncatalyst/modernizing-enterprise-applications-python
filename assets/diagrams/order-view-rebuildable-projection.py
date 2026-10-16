#!/usr/bin/env python3
"""ch.21 figure: order-view-rebuildable-projection -- the read model is a
cache of the aggregate's shape, never a second source of truth. Top row:
aggregate -> projection -> view, kept current by every write path upserting
in the same transaction. Bottom row (ghosted): rebuild_order_view recomputes
order_view from the CURRENT aggregate state at any time -- and the
projection-disabled negative test proves what happens when the sync stops:
the aggregate transitions correctly, but a GET against order_view goes
stale and the bounded-wait poll exhausts its budget.

Sourced from examples/07-order-service/app/repository.py::rebuild_order_view,
app/service.py::rebuild_order_view, app/models.py::OrderView's docstring, and
tooling/newman/GOLDEN-BASELINE-r07.md's "Projection-disabled -> stale read"
negative check.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 560

band_top = {"x": 20, "y": 56, "w": 1260, "h": 200,
            "label": "NORMAL PATH -- every write upserts order_view in the SAME transaction", "fill": "#fafafa"}
band_bot = {"x": 20, "y": 56 + 200 + 32, "w": 1260, "h": 220,
            "label": "WHAT PROVES IT'S REBUILDABLE, NOT A SECOND SOURCE OF TRUTH", "fill": "#f1f5f9"}

agg = node(60, 110, 260, 100, ["orders / order_items", "the write aggregate", "(status, totals, items)"], style="box")
proj = node(400, 110, 260, 100, ["_upsert_order_view()", "runs inside the caller's", "own transaction"], style="accent")
view = node(740, 110, 260, 100, ["order_view", "ONE row, replaced wholesale", "never appended to"], style="box")
reader = node(1040, 110, 220, 100, ["GET /api/orders/{id}", "reads THIS, only this"], style="box")

top_nodes = [agg, proj, view, reader]
top_edges = [connect(agg, proj), connect(proj, view), connect(view, reader)]

y2 = 56 + 200 + 32
rebuild = node(60, y2 + 50, 280, 110,
               ["rebuild_order_view(order_id)",
                "recomputes order_view from the",
                "CURRENT aggregate -- a cache,",
                "not a parallel source of truth"], style="ghost")
disabled = node(400, y2 + 50, 300, 110,
                ["Negative test: skip the upsert", "on one transition -- aggregate",
                 "still reaches CONFIRMED correctly"], style="ghost")
stale = node(760, y2 + 50, 290, 110,
             ["GET keeps returning PENDING --", "bounded-wait poll exhausts",
              "its full 40x750ms budget, RED"], style="ghost")
restored = node(1100, y2 + 50, 160, 110, ["Restore the", "upsert ->", "GREEN again"], style="box")

bot_nodes = [rebuild, disabled, stale, restored]
bot_edges = [
    connect(agg, rebuild, dashed=True, label="repairable at any time"),
    connect(disabled, stale, amber=True, label="proves reads are view-only"),
    connect(stale, restored, dashed=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.21 -- a rebuildable read model: the projection-disabled negative is the proof the read path never falls back to the aggregate",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 24, "text": "This is CQRS-lite, not event sourcing: order_view is derived from current rows, not replayed from an event log -- see ch.21's scoping section.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "order-view-rebuildable-projection", W, H,
    bands=[band_top, band_bot],
    nodes=top_nodes + bot_nodes,
    edges=top_edges + bot_edges,
    notes=notes,
)
