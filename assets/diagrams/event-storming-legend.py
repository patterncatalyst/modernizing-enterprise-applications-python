#!/usr/bin/env python3
"""ch.12 figure: event-storming-legend -- the sticky-note color grammar from
an event-storming session, as a standalone legend card, in the order a
session typically adds them: domain events first (chaotic exploration), then
commands, then actors, then aggregates, then policies/reactions, then read
models, then external systems.

Each row names the real-world sticky color with a small swatch chip, and
maps it onto this project's diagram palette -- the same box/sub/accent/user/
ghost/kernel mapping `event-storm-checkout.py` already uses in its own
legend note, formalized here as its own figure. House style stays the
primary visual language (white cards, green accent, grey arrows); the
swatches are small call-outs, not a repaint of the palette.

Examples quoted in each row are pulled from `event-storm-checkout.py`'s own
reading of the checkout flow: OrderPlaced/StockReserved/PaymentCaptured
(events), Place Order/reserve stock/capture payment (commands), Customer
(actor), Order (aggregate), the two named policies (OrderPlaced->reserve
stock, StockReserved->capture payment), Order Status (read model), and the
Payment Gateway (external system).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node

g.OUT = os.path.dirname(__file__)

W, H = 1180, 970

ROWS = [
    ("Domain event", "orange sticky -- a past-tense fact",
     "e.g. OrderPlaced, StockReserved, PaymentCaptured", "accent", "#f4b183"),
    ("Command", "blue sticky -- the imperative that triggered the fact",
     "e.g. Place Order, reserve stock, capture payment", "user", "#9dc3f0"),
    ("Actor", "small yellow figure, left of its command -- who/what issued it",
     "e.g. Customer; or a job, webhook, or policy", "sub", "#f5ea8a"),
    ("Aggregate", "large yellow sticky -- the data cluster enforcing an invariant",
     "e.g. Order (is place_order() well-formed?), InventoryItem (enough stock?)", "box", "#f0d64a"),
    ("Policy / reaction", "lilac sticky -- \"whenever X, then issue command Y\", no human actor",
     "e.g. whenever OrderPlaced, then reserve stock", "ghost", "#cdb3e8"),
    ("Read model", "green sticky -- a view projected forward from events",
     "e.g. Order Status, fed by OrderPlaced/PaymentCaptured/ShipmentDispatched/OrderConfirmed", "kernel", "#a8d9ad"),
    ("External system", "pink sticky -- outside the team's control, called through a policy",
     "e.g. the Payment Gateway stand-in, a carrier's dispatch API", "sub", "#f0a8c4"),
]

SWATCH_X, SWATCH_W = 70, 32
CARD_X, CARD_W = 118, 960
ROW_Y0, ROW_H, GUTTER = 118, 96, 14

bands = []
nodes = []
notes = [
    {"x": W / 2, "y": 34, "text": "Event-storming note-type legend: the wall's color grammar",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": W / 2, "y": 60,
     "text": "in the order a session adds them -- each sticky color named the way the grammar is usually taught, "
             "mapped onto this book's house-style box types",
     "anchor": "middle", "size": 12, "color": "#555555"},
]

for i, (title, color_desc, example, style, swatch_hex) in enumerate(ROWS):
    y = ROW_Y0 + i * (ROW_H + GUTTER)
    bands.append({"x": SWATCH_X, "y": y, "w": SWATCH_W, "h": ROW_H, "label": "", "fill": swatch_hex})
    n = node(CARD_X, y, CARD_W, ROW_H, [title, color_desc, example], style=style)
    nodes.append(n)
    notes.append({
        "x": SWATCH_X + SWATCH_W / 2, "y": y + ROW_H + 11,
        "text": f"{i + 1}", "anchor": "middle", "size": 9, "color": "#777777",
    })

notes.append({
    "x": CARD_X, "y": H - 64,
    "text": "Style key: ACCENT=domain event * USER=command * SUB=actor/external system * BOX=aggregate * "
            "GHOST(dashed)=policy/reaction * KERNEL=read model",
    "anchor": "start", "size": 10, "color": "#555555",
})
notes.append({
    "x": CARD_X, "y": H - 48,
    "text": "-- the same mapping event-storm-checkout.py (Figure 12.1) already uses.",
    "anchor": "start", "size": 10, "color": "#555555",
})
notes.append({
    "x": CARD_X, "y": H - 20,
    "text": "Sourced from this project's own event-storm-checkout.py reading of order/services.py::_place_order_local.",
    "anchor": "start", "size": 10, "color": "#777777",
})

g.emit(
    "event-storming-legend", W, H,
    bands=bands,
    nodes=nodes,
    edges=[],
    notes=notes,
)
