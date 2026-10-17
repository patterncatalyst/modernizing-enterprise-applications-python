#!/usr/bin/env python3
"""ch.09 figure: smell-map — the visual form of SMELLS.md. All seven
deliberately-planted smells overlaid on the monolith's six-context structure
(the same skeleton as monolith-six-contexts), each annotated with where it
lives and the chapter(s) that cure it. Smells #5 and #6 (synchronous
notification send, dual-write hazard) are drawn as already CURED — r03's
transactional outbox — and smell #7 (review tangled into shared auth) is
drawn as the one still-open smell that review's own extraction (ch.15)
resolves by giving review its own, independent auth configuration.

Numbering, locations, and curing chapters are quoted verbatim from
`examples/00-monolith/SMELLS.md`. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1540, 900

# ---- base structure: six context apps, one deployable -------------------
CONTEXTS = [
    ("order", "accent"),
    ("inventory", "box"),
    ("payment", "box"),
    ("shipping", "box"),
    ("notification", "box"),
    ("review", "box"),
]
COL_W, GUTTER, COL_X0, ROW_Y, ROW_H = 200, 24, 70, 150, 100
cols = {}
nodes = []
for i, (name, style) in enumerate(CONTEXTS):
    x = COL_X0 + i * (COL_W + GUTTER)
    n = node(x, ROW_Y, COL_W, ROW_H, [name], style=style)
    cols[name] = n
    nodes.append(n)

# ---- shared Postgres schema --------------------------------------------
PG_Y, PG_H = 300, 80
pg_band = {"x": 40, "y": PG_Y, "w": W - 80, "h": PG_H,
           "label": "PostgreSQL — one shared schema", "fill": "#fafafa"}
pg_box = node(W / 2 - 160, PG_Y + 22, 320, 40, ["9 tables, cross-context FKs"], style="sub")
nodes.append(pg_box)

struct_edges = [connect(n, pg_box) for name, n in cols.items()]

# ---- the transaction.atomic() bracket over order..shipping (Smell #2) -----
bracket_y = ROW_Y - 18
left_x = cols["order"]["x"] + cols["order"]["w"] / 2
right_x = cols["shipping"]["x"] + cols["shipping"]["w"] / 2
bracket_edges = [
    {"x1": left_x, "y1": bracket_y, "x2": right_x, "y2": bracket_y, "dashed": True, "amber": True,
     "label": "SMELL #2 — one transaction.atomic() spans these four contexts"},
    {"x1": left_x, "y1": bracket_y, "x2": left_x, "y2": bracket_y + 14, "dashed": True, "amber": True},
    {"x1": right_x, "y1": bracket_y, "x2": right_x, "y2": bracket_y + 14, "dashed": True, "amber": True},
]

bands = [
    {"x": 20, "y": 70, "w": W - 40, "h": 210,
     "label": "Django monolith — one deployable", "fill": "#ffffff"},
    pg_band,
]

# ---- seven numbered smell call-outs, grounded in SMELLS.md ------------------
CARD_Y, CARD_H, CARD_W, CARD_GUTTER = 500, 190, 200, 14
CARD_X0 = 30
cards_def = [
    ("#1 God checkout function",
     "order/services.py::place_order() reaches directly into inventory/payment/shipping's services/models",
     "cures: ch.26 (hardest, last)", "sub"),
    ("#2 One ACID txn, five contexts",
     "_place_order_local's transaction.atomic() — free rollback across order+inventory+payment+shipping+outbox",
     "cures: ch.22 (ACID->ACD), ch.23/24 (sagas)", "sub"),
    ("#3 Shared single schema/DB",
     "config/settings.py — one Postgres schema, one set of Django migrations, all six apps deploy together",
     "cures: ch.18 (owned data)", "sub"),
    ("#4 Cross-context FKs",
     "orders->customers, payments/shipments/notifications->orders, reviews->customers+inventory_items",
     "cures: ch.18, ch.19 (CDC)", "sub"),
    ("#5 Sync notification — CURED",
     "place_order() used to call notification/services.py in-process; now it only writes an OutboxEvent row",
     "ch.17 — cured at r03", "accent"),
    ("#6 Dual-write hazard — CURED",
     "DB row + provider call were two independent writes; outbox_relay now publishes at-least-once",
     "ch.17 — cured at r03", "accent"),
    ("#7 Review tangled in shared auth",
     "review/views.py gates POST with HTTP Basic auth against the shared django.contrib.auth table",
     "cures: ch.15 — review's own auth config", "sub"),
]

cards = []
for i, (title, detail, cure, style) in enumerate(cards_def):
    x = CARD_X0 + i * (CARD_W + CARD_GUTTER)
    n = node(x, CARD_Y, CARD_W, CARD_H, [title, detail, cure], style=style)
    cards.append(n)
nodes += cards

# ---- connectors from each card up to the structure it annotates -----------
LANE_Y = CARD_Y - 40
callout_edges = []


def callout(card, target_x, target_y, amber=True):
    cx = card["x"] + card["w"] / 2
    cy = card["y"]
    return [
        {"x1": cx, "y1": cy, "x2": cx, "y2": LANE_Y, "dashed": True, "amber": amber},
        {"x1": cx, "y1": LANE_Y, "x2": target_x, "y2": LANE_Y, "dashed": True, "amber": amber},
        {"x1": target_x, "y1": LANE_Y, "x2": target_x, "y2": target_y, "dashed": True, "amber": amber},
    ]


order_n = cols["order"]
# #1 -> order module
callout_edges += callout(cards[0], order_n["x"] + order_n["w"] / 2, order_n["y"] + order_n["h"])

# #2 -> the transaction.atomic() bracket midpoint
bracket_mid_x = (left_x + right_x) / 2
callout_edges += callout(cards[1], bracket_mid_x, bracket_y)

# #3 -> shared schema band
pg_target_x, pg_target_y = pg_box["x"] + pg_box["w"] / 2, pg_box["y"] + pg_box["h"]
callout_edges += callout(cards[2], pg_target_x, pg_target_y)

# #4 -> shared schema band (same target, offset)
callout_edges += callout(cards[3], pg_target_x - 60, pg_target_y)

# #5 -> notification module
notif_n = cols["notification"]
callout_edges += callout(cards[4], notif_n["x"] + notif_n["w"] / 2, notif_n["y"] + notif_n["h"])

# #6 -> notification module (same target, offset)
callout_edges += callout(cards[5], notif_n["x"] + notif_n["w"] / 2 + 20, notif_n["y"] + notif_n["h"])

# #7 -> review module
review_n = cols["review"]
callout_edges += callout(cards[6], review_n["x"] + review_n["w"] / 2, review_n["y"] + review_n["h"])

notes = [
    {"x": W / 2, "y": 32, "text": "ch.09 — The seven deliberate smells, mapped onto the monolith's structure",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56, "text": "the visual form of SMELLS.md — five smells still standing, two already cured",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/00-monolith/SMELLS.md (grep 'SMELL\\[ch\\.' for every in-code tag).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "smell-map", W, H,
    bands=bands,
    nodes=nodes,
    edges=struct_edges + bracket_edges + callout_edges,
    notes=notes,
)
