#!/usr/bin/env python3
"""ch.14 figure: strangler-four-moves -- Fowler's strangler fig pattern as
four ordered engineering moves (intercept, route, incrementally replace,
retire). The point is the ordering: the window in which a cutover is still
reversible spans moves 1-3 and closes the instant "retire" happens.
Retiring the monolith's code before that window is supposed to close --
before a real behavioral check, not just a green test suite -- is how an
"incremental" migration quietly turns into a big-bang rewrite with extra
ceremony.

This book's own move 1 is the Starlette+httpx proxy on :8888
(`examples/01-strangler-proxy`); move 2 is `STRANGLER_REVIEW_ENABLED`
deciding the backend for `/api/reviews*`; move 3 is the Review service
(`examples/02-review-service`) going live behind that flag while the
monolith's own Review module is left in place; move 4 (decommissioning the
monolith's Review app) is a later iteration, referenced here only as the
one irreversible step still ahead.

Sourced from `examples/01-strangler-proxy/README.md` and `CUTOVER.md` (the
flag, the reversibility window, the chunked-body bug found while proving
it) and `examples/00-monolith/SMELLS.md` #7.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 700

band_reversible = {
    "x": 40, "y": 170, "w": 960, "h": 220,
    "label": "reversible -- STRANGLER_REVIEW_ENABLED can flip either direction (config + restart, not code)",
    "fill": "#fafafa",
}
band_irreversible = {
    "x": 1000, "y": 170, "w": 320, "h": 220,
    "label": "irreversible once crossed",
    "fill": "#f4f4f4",
}

box1 = node(60, 220, 280, 110,
            ["1. Intercept", "the proxy sees every request first", ":8888, Starlette + httpx"],
            style="box")
box2 = node(380, 220, 280, 110,
            ["2. Route", "the flag decides the backend", "for /api/reviews* only"],
            style="box")
box3 = node(700, 220, 280, 110,
            ["3. Incrementally replace", "review-service goes live,", "cutover proven by Newman first"],
            style="accent")
box4 = node(1020, 220, 280, 110,
            ["4. Retire -- later iteration", "the monolith's Review app", "removed last, not first"],
            style="ink")

nodes = [box1, box2, box3, box4]

edges = [
    connect(box1, box2, label="flag defaults to false (monolith)"),
    connect(box2, box3, label="flag flips true, 58/58 green"),
    connect(box3, box4, amber=True,
            label="verified first, not just tested", lx=0, ly=-145),
]

ghost = node(460, 480, 560, 110,
             ["Retire before that check passes?",
              "the fallback backend is gone --",
              "\"incremental\" becomes a big-bang rewrite"],
             style="ghost")
nodes.append(ghost)
edges.append(connect(box3, ghost, dashed=True,
                      label="retire before the check passes ->"))

notes = [
    {"x": W / 2, "y": 32,
     "text": "the strangler fig's four moves, in the order that matters",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "retiring out of order is how an \"incremental\" migration quietly becomes a big-bang rewrite",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 60, "y": 375,
     "text": "both backends still exist here -- the flag can flip either way, no redeploy required",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 1020, "y": 352,
     "text": "the flag still routes; the destination",
     "anchor": "start", "size": 10, "color": "#555555"},
    {"x": 1020, "y": 367,
     "text": "it used to select is gone (404)",
     "anchor": "start", "size": 10, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/01-strangler-proxy/CUTOVER.md and examples/00-monolith/SMELLS.md #7.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "strangler-four-moves", W, H,
    bands=[band_reversible, band_irreversible],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
