#!/usr/bin/env python3
"""ch.14 figure: strangler-proxy-routing -- the Starlette+httpx strangler
proxy's content-based routing, flag OFF vs flag ON, side by side.

Two stacked panels, each a small topology rather than a text label:
  - OFF (default): STRANGLER_REVIEW_ENABLED=false. Every request, including
    /api/reviews*, goes to the monolith (:8000).
  - ON: STRANGLER_REVIEW_ENABLED=true. The proxy's _select_backend() checks
    the FULL request.url.path against "/api/reviews" and routes those
    requests to examples/02-review-service (:8001); everything else still
    goes to the monolith.

Both panels show the same single Postgres instance behind both backends --
this is Phase B of the extraction (ch.18/19 give review its own database;
until then it's a shared-schema read/write, not a shared-nothing service).

Sourced from examples/01-strangler-proxy/app/main.py (_select_backend(),
proxy_handler()), app/config.py (Settings, STRANGLER_REVIEW_ENABLED), and
README.md's routing table.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 900
PANEL_H = 380


def build_panel(panel_y, flag_on):
    client = node(40, panel_y + 140, 220, 90,
                   ["Client", "(curl / Newman)"], style="user")

    if not flag_on:
        proxy_lines = ["Starlette strangler proxy", ":8888",
                       "STRANGLER_REVIEW_ENABLED=false"]
        monolith_lines = ["Django monolith", ":8000 -- all contexts", "incl. review/"]
        review_style = "ghost"
        review_lines = ["review-service (FastAPI)", ":8001", "(built, not serving reviews)"]
        proxy_review_edge = {"label": "/api/reviews* (unused while flag=false)", "dashed": True}
        proxy_mono_edge_label = "every path, incl. /api/reviews*"
        pg_note = "(shared schema)"
    else:
        proxy_lines = ["Starlette strangler proxy", ":8888",
                       "STRANGLER_REVIEW_ENABLED=true"]
        monolith_lines = ["Django monolith", ":8000 -- everything else", "review/ app still present"]
        review_style = "accent"
        review_lines = ["review-service (FastAPI)", ":8001", "serving /api/reviews*"]
        proxy_review_edge = {"label": "/api/reviews* matched on request.url.path", "amber": True}
        proxy_mono_edge_label = "everything else"
        pg_note = "(shared schema, Phase B)"

    proxy = node(330, panel_y + 140, 260, 110, proxy_lines, style="accent" if flag_on else "box")
    monolith = node(660, panel_y + 10, 260, 100, monolith_lines, style="box")
    review = node(660, panel_y + 270, 260, 100, review_lines, style=review_style)
    pg = node(1000, panel_y + 130, 240, 120,
              ["PostgreSQL 18", "monolith schema", "reviews, customers,", "inventory_items, auth_user " + pg_note],
              style="sub")

    nodes = [client, proxy, monolith, review, pg]
    edges = [
        connect(client, proxy, label="HTTP"),
        connect(proxy, monolith, label=proxy_mono_edge_label),
        connect(proxy, review, **proxy_review_edge),
        connect(monolith, pg),
        connect(review, pg, dashed=(not flag_on)),
    ]
    return nodes, edges


off_nodes, off_edges = build_panel(70, flag_on=False)
on_nodes, on_edges = build_panel(70 + PANEL_H + 60, flag_on=True)

notes = [
    {"x": W / 2, "y": 32,
     "text": "content-based routing: STRANGLER_REVIEW_ENABLED flag OFF vs ON",
     "anchor": "middle", "bold": True, "size": 18},

    {"x": 40, "y": 65, "text": "FLAG OFF (default) -- /api/reviews* still answered by the monolith",
     "anchor": "start", "bold": True, "size": 14},
    {"x": 40, "y": 70 + PANEL_H + 48,
     "text": "FLAG ON -- /api/reviews* answered by review-service; everything else unchanged",
     "anchor": "start", "bold": True, "size": 14},

    {"x": 40, "y": H - 34,
     "text": "_select_backend() matches request.url.path -- the FULL path the client sent -- never a value",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 18,
     "text": "relative to a mount point or route prefix (the full-path-prefix lesson, see CUTOVER.md).",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "strangler-proxy-routing", W, H,
    bands=[],
    nodes=off_nodes + on_nodes,
    edges=off_edges + on_edges,
    notes=notes,
)
