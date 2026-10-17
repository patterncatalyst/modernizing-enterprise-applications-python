#!/usr/bin/env python3
"""ch.06 figure: structural-vs-behavioral-gates -- two gate kinds, and which
class of mistake each one actually catches, re-grounded for a stack with no
Camel-MCP/Quarkus-Agent-MCP equivalent (DRQ-020).

TOP -- the STRUCTURAL gate, here necessarily weaker and more manual than
the Java sibling's live `camel_validate_route` MCP tool: `ruff check` plus
Python's own import-time wiring (a Starlette/FastAPI app that fails to
construct raises immediately -- an `ImportError`/`AttributeError`/route-
registration `TypeError`, not a live route-graph validator), run during
Generate, before a server ever starts. It catches a malformed route
registration, an unresolved import, a typo'd dependency signature -- the
class of defect that would otherwise surface as a confusing traceback. It
has no opinion about whether a routing predicate matches the right
requests once real traffic flows through it -- that gap is named here
explicitly, not hidden, because this project has no MCP-driven structural
validator to close it the way the Java sibling does.

BOTTOM -- the BEHAVIORAL gate: the Newman behavior-equivalence suite and
its Opus adversarial follow-up, run during Verify against a running
service. This is the layer that caught the strangler proxy's real
chunked-body bug (DRQ-026): the in-process routing tests passed while the
proxy silently sent every POST upstream with no body, because only a real
WSGI socket run surfaces that class of defect -- a misleadingly
correct-looking response, not a traceback.

Neither one substitutes for the other, and knowing which layer is
responsible for which kind of mistake is most of what it takes to trust a
loop this fast.

Sourced from `_plans/build-plan.md` (section F.1's tooling column, DRQ-020)
and `_plans/decisions.md` (DRQ-026, the chunked-body routing bug). No
codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 760

# ============================================================================
# TOP band -- the structural gate
# ============================================================================
band_top = {"x": 20, "y": 80, "w": 1360, "h": 250,
            "label": "Structural gate -- ruff + import-time wiring (Generate phase, before a server starts)",
            "fill": "#fafafa"}

route_check = node(60, 150, 400, 120,
                    ["ruff check + Python import-time wiring",
                     "no live route-graph validator exists for",
                     "this stack (no MCP equivalent, DRQ-020)"], style="accent")
catches1 = node(500, 150, 380, 120,
                ["Catches", "a malformed route registration,",
                 "unresolved import, typo'd dependency signature"], style="box")
miss1 = node(920, 150, 420, 120,
             ["Cannot catch", "whether a routing predicate matches the right",
              "requests once real traffic flows"], style="accent")

top_nodes = [route_check, catches1, miss1]
top_edges = [
    connect(route_check, catches1, amber=True, label="defect surfaces as: a confusing traceback at import/startup", ly=-80),
    connect(catches1, miss1, dashed=True, label="gap this layer leaves open", ly=-80),
]

# ============================================================================
# BOTTOM band -- the behavioral gate
# ============================================================================
band_bottom = {"x": 20, "y": 390, "w": 1360, "h": 280,
               "label": "Behavioral gate -- Newman equivalence suite + adversarial follow-up (Verify phase, against a running service)",
               "fill": "#eaf4ec"}

suite_check = node(60, 460, 400, 120,
                    ["Newman equivalence suite +", "adversarial follow-up",
                     "exercises real requests, running service"], style="accent")
catches2 = node(500, 460, 420, 120,
                ["Catches", "the chunked-body routing bug (DRQ-026) --",
                 "a misleadingly correct-looking response"], style="box")

bottom_nodes = [suite_check, catches2]

# the cross-band connector routes as an L (like the bus-lane pattern) so it
# lands on suite_check's top-center, clear of the amber label sitting above
# suite_check's left side.
GAP_Y = 360
miss1_cx = miss1["x"] + miss1["w"] / 2
suite_cx = suite_check["x"] + suite_check["w"] / 2
miss1_bottom = miss1["y"] + miss1["h"]
suite_top = suite_check["y"]

bottom_edges = [
    connect(suite_check, catches2, amber=True, label="defect surfaces as: a misleadingly correct-looking response", ly=-75),
    {"x1": miss1_cx, "y1": miss1_bottom, "x2": miss1_cx, "y2": GAP_Y, "dashed": True},
    {"x1": miss1_cx, "y1": GAP_Y, "x2": suite_cx, "y2": GAP_Y, "dashed": True,
     "label": "the gap the behavioral gate exists to close"},
    {"x1": suite_cx, "y1": GAP_Y, "x2": suite_cx, "y2": suite_top, "dashed": True},
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.06 -- structural gate vs behavioral gate: two layers, two different classes of mistake",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "no MCP-driven structural validator exists for this stack (DRQ-020) -- the behavioral gate carries more of the weight here than a live route-validator tool would leave it",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 980, "y": 520,
     "text": "the real bug this gate caught: every POST through the proxy silently arrived empty (DRQ-026)",
     "anchor": "start", "size": 10, "color": "#777777"},

    {"x": 40, "y": H - 46,
     "text": "Sourced from _plans/build-plan.md (section F.1's tooling column, DRQ-020).",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": H - 16,
     "text": "Behavioral-gate example: _plans/decisions.md DRQ-026, the strangler proxy's chunked-body bug.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "structural-vs-behavioral-gates", W, H,
    bands=[band_top, band_bottom],
    nodes=top_nodes + bottom_nodes,
    edges=top_edges + bottom_edges,
    notes=notes,
)
