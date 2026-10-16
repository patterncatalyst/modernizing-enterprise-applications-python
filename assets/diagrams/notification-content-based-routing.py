#!/usr/bin/env python3
"""ch.16 figure: notification-content-based-routing -- the strangler proxy's
routing decision generalized past a single URL-path predicate, using the
SECOND flag (STRANGLER_NOTIFICATION_ENABLED) ch.17 adds alongside ch.14's
STRANGLER_REVIEW_ENABLED.

One topology (client -> proxy -> three possible backends), each outbound
edge labeled with the actual predicate `_select_backend()` evaluates, plus a
side panel naming the two routing dimensions this proxy does NOT use today
but a content-based router could: header-based and payload-based matching.
The point of the figure is the generalization, not a flag-by-flag walkthrough
(ch.14/15 already drew that for Review alone).

Sourced from examples/01-strangler-proxy/app/main.py (_select_backend()),
app/config.py (Settings.notification_enabled/notification_base_url).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1280, 620

client = node(40, 260, 200, 90, ["Client", "(curl / Newman)"], style="user")
proxy = node(320, 240, 280, 130, [
    "Starlette strangler proxy :8888",
    "_select_backend(settings, path)",
    "operator config only, never",
    "anything on the request (SSRF guard)",
], style="accent")

monolith = node(720, 40, 300, 100, [
    "Django monolith :8000",
    "default -- everything not matched",
    "below (incl. checkout, inventory, ...)",
], style="box")

review = node(720, 260, 300, 100, [
    "review-service :8001",
    "path prefix /api/reviews*",
    "AND STRANGLER_REVIEW_ENABLED",
], style="box")

notification = node(720, 480, 300, 100, [
    "notification-service :8002",
    "path prefix /api/notifications*",
    "AND STRANGLER_NOTIFICATION_ENABLED",
], style="accent")

side = {"x": 40, "y": 420, "w": 560, "h": 160, "label": "Content-based routing, generalized past a URL path", "fill": "#f1f5f9"}

nodes = [client, proxy, monolith, review, notification]
edges = [
    connect(client, proxy, label="HTTP, any method"),
    connect(proxy, monolith, label="default"),
    connect(proxy, review, label="path-prefix match"),
    connect(proxy, notification, label="path-prefix match (ch.17's seam)", amber=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.16 -- one routing decision, generalized past a single URL-path predicate",
     "anchor": "middle", "bold": True, "size": 18},

    {"x": 60, "y": 450, "text": "Today, this proxy matches on PATH (request.url.path, the full path -- see ch.14's",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
    {"x": 60, "y": 470, "text": "full-path-prefix lesson). The same _select_backend() shape generalizes to:",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
    {"x": 76, "y": 495, "text": "- HEADER match -- e.g. route by X-Tenant-Id to a tenant-specific backend",
     "anchor": "start", "size": 12, "color": "#64748b"},
    {"x": 76, "y": 515, "text": "- PAYLOAD/content match -- e.g. route by order total or customer segment",
     "anchor": "start", "size": 12, "color": "#64748b"},
    {"x": 60, "y": 545, "text": "The constraint that doesn't generalize away: the predicate's INPUTS stay",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
    {"x": 60, "y": 565, "text": "operator configuration, never caller-supplied data used to BUILD a target URL.",
     "anchor": "start", "size": 12, "color": "#1d1d1d"},
]

g.emit(
    "notification-content-based-routing", W, H,
    bands=[side],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
