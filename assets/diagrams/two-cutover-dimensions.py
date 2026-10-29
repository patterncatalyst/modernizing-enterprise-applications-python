#!/usr/bin/env python3
"""ch.19 figure: two-cutover-dimensions -- inventory's cutover has TWO
independent flags, not one, and they are not the same axis. The monolith's
`INVENTORY_MODE` (local|grpc) decides who answers a checkout-time
Reserve/Release; the strangler proxy's `STRANGLER_INVENTORY_ENABLED`
decides who answers a `GET /api/inventory*` read. GOLDEN-BASELINE.md
exercises the two LOCKED-TOGETHER corners (Run A fully-grpc, Run B
fully-local) as a 2x2 grid; the two split corners are sound only during
the CDC-backfilled transition window and were not exercised as a
steady-state configuration.

Sourced from tooling/newman/GOLDEN-BASELINE.md's r04 NEWMAN-GRPC lane
(Run A/Run B tables) and CUTOVER.md's "two independent cutover dimensions"
framing.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 760

cell_ll = node(100, 180, 520, 220,
    ["Run B -- reversibility baseline", "INVENTORY_MODE=local, STRANGLER_INVENTORY_ENABLED unset", "71/71 assertions green, byte-identical to Run A"],
    style="accent")
cell_lt = node(680, 180, 520, 220,
    ["Split (local reserve, service-served reads)", "sound only mid-transition, CDC-backfilled", "not exercised as a steady state"],
    style="ghost")
cell_gf = node(100, 440, 520, 220,
    ["Split (remote reserve, monolith-served reads)", "sound only mid-transition, CDC-backfilled", "not exercised as a steady state"],
    style="ghost")
cell_gt = node(680, 440, 520, 220,
    ["Run A -- fully cut over", "INVENTORY_MODE=grpc, STRANGLER_INVENTORY_ENABLED=true", "71/71 green; net-zero stock proven, Scenarios 3 & 4"],
    style="accent")

notes = [
    {"x": W / 2, "y": 32, "text": "two independent cutover dimensions, locked together in this book's exercised runs",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 360, "y": 150, "text": "STRANGLER_INVENTORY_ENABLED=false/unset", "anchor": "middle", "bold": True, "size": 13},
    {"x": 940, "y": 150, "text": "STRANGLER_INVENTORY_ENABLED=true", "anchor": "middle", "bold": True, "size": 13},
    {"x": 60, "y": 270, "text": "INVENTORY_MODE", "anchor": "middle", "bold": True, "size": 13},
    {"x": 60, "y": 290, "text": "=local", "anchor": "middle", "bold": True, "size": 13},
    {"x": 60, "y": 530, "text": "INVENTORY_MODE", "anchor": "middle", "bold": True, "size": 13},
    {"x": 60, "y": 550, "text": "=grpc", "anchor": "middle", "bold": True, "size": 13},
    {"x": 40, "y": H - 40, "text": "Checkout-time reserve/release and GET /api/inventory* reads are controlled by different flags in different processes --",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "flipping one does not require flipping the other, and in a real rollout they land at different times.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "two-cutover-dimensions", W, H,
    bands=[],
    nodes=[cell_ll, cell_lt, cell_gf, cell_gt],
    edges=[],
    notes=notes,
)
