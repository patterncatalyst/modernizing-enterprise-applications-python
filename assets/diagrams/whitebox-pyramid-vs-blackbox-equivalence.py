#!/usr/bin/env python3
"""ch.10 figure: whitebox-pyramid-vs-blackbox-equivalence: the chapter's one
new idea, drawn as a legitimate side-by-side.

LEFT: white-box: the pytest-django pyramid from test-pyramid.py (50 tests,
8 files). It imports `order.services.place_order`, `OrderItem`, and every
other internal name directly, and in several tiers inspects real rows in a
real (disposable) Postgres test database it is free to reset between runs.
A white-box test can't even import a module that doesn't share the
monolith's Python package names, let alone its database rows.

RIGHT: black-box: the Newman behavior-equivalence suite
(`tooling/newman/mea.postman_collection.json`, 12 folders / 39 requests)
earns that name for a specific, concrete reason: every request targets the
`{{baseUrl}}` collection variable rather than a hardcoded host, so the exact
same collection can point at this monolith on one run and at a freshly
extracted FastAPI service (or the strangler proxy in front of it) on the
next, with not one assertion edited in between. It sees a status code, a
JSON body, and a second HTTP response it chose to fetch itself (the
bounded-wait polls): that restriction is the whole point.

Sourced from `examples/00-monolith/tests/` and
`tooling/newman/mea.postman_collection.json`. No codenames; generic/public
names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1560, 760

# ============================================================================
# LEFT band: white-box: the pytest-django pyramid, calling Python directly
# ============================================================================
band_left = {"x": 20, "y": 70, "w": 740, "h": 560,
             "label": "White-box: pytest-django calls Python directly, inspects a real DB",
             "fill": "#fafafa"}

tier3m = node(270, 140, 240, 70, ["API / acceptance (21)", "APIClient, real Postgres"], style="box")
tier2m = node(220, 240, 340, 70, ["Service & consumer integration (28)", "direct calls, db fixture"], style="box")
tier1m = node(170, 340, 440, 70, ["Pure unit (1)", "OrderItem._meta.get_fields()"], style="box")
internals = node(110, 440, 560, 110, [
    "Monolith internals",
    "order.services.place_order, live Postgres rows",
    "called directly in-process; every tier needs a real test database",
], style="sub")

left_nodes = [tier3m, tier2m, tier1m, internals]
left_edges = [
    connect(tier3m, tier2m),
    connect(tier2m, tier1m),
    connect(tier1m, internals, label="direct Python calls, DB inspection", amber=True),
]

# ============================================================================
# RIGHT band: black-box: the Newman behavior-equivalence suite
# ============================================================================
band_right = {"x": 800, "y": 70, "w": 740, "h": 560,
              "label": "Black-box: the behavior-equivalence suite sees only HTTP",
              "fill": "#eaf4ec"}

newman = node(940, 140, 460, 120, [
    "Newman: mea.postman_collection.json",
    "12 folders, 39 requests: smoke, 4 checkout scenarios,",
    "6 per-context contracts, GraphQL gateway contract",
], style="accent")

baseurl = node(990, 300, 360, 80, [
    "baseUrl: collection variable",
    "re-pointable: monolith today, an extracted service tomorrow",
], style="box")

monolith_target = node(830, 440, 300, 110, [
    "This Django monolith (today)",
    "baseline this suite is captured from",
], style="box")

extracted_target = node(1200, 440, 300, 110, [
    "Extracted FastAPI service (after extraction)",
    "equivalence gate: unedited collection",
], style="ghost")

right_nodes = [newman, baseurl, monolith_target, extracted_target]
right_edges = [
    connect(newman, baseurl, label="HTTP only: status code + JSON body"),
    connect(baseurl, monolith_target),
    connect(baseurl, extracted_target, dashed=True, label="re-pointed, zero assertions edited", amber=True),
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.10: same system, two kinds of test: white-box pytest pyramid vs. black-box equivalence suite",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": W / 2, "y": 56,
     "text": "the pyramid imports Python package names; the equivalence suite only knows baseUrl and HTTP",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 110, "y": 575,
     "text": "A white-box test can't import a module that doesn't share the monolith's package names,",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 110, "y": 591,
     "text": "let alone its database rows: it proves the implementation, not the behavior, is correct.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 940, "y": 575,
     "text": "Every request targets {{baseUrl}}, not a hardcoded host: the same collection, unedited, can point",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 940, "y": 591,
     "text": "at this monolith today or an extracted service tomorrow, with not one assertion changed in between.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 20, "y": H - 32,
     "text": "Sourced from examples/00-monolith/tests/ (test-pyramid.py's own counts) and tooling/newman/mea.postman_collection.json.",
     "anchor": "start", "size": 10, "color": "#777777"},
    {"x": 20, "y": H - 16,
     "text": "Collection: tooling/newman/mea.postman_collection.json (12 folders, 39 requests).",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "whitebox-pyramid-vs-blackbox-equivalence", W, H,
    bands=[band_left, band_right],
    nodes=left_nodes + right_nodes,
    edges=left_edges + right_edges,
    notes=notes,
)
