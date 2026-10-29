#!/usr/bin/env python3
"""ch.07 figure: adlc-safety-net-layers -- the closing argument: the safety
net has three layers, not one, and removing any single layer lets a
specific, named class of mistake through.

LAYER 1 -- the automated layer: the Newman behavior-equivalence suite,
cheap enough to re-run against every candidate build. This is what the
in-process `httpx.ASGITransport` mock-transport tests alone could NOT
catch -- the real chunked-body bug (DRQ-026) only surfaced once the suite
ran against the real WSGI backend over a real socket. Remove this layer and
every POST through the proxy keeps silently arriving empty.

LAYER 2 -- adversarial verification: checking the suite's result against
what actually persisted in the shared table (DRQ-028), not just the HTTP
response shape -- the gap named in `shared-table-routing-defect`. Remove
this layer and a shape-only green run is trusted even when both backends
happen to produce similarly shaped responses for different reasons.

LAYER 3 -- the two human gates: plan approval (Plan phase, before any diff
exists) and equivalence sign-off (Verify phase, judging whether the suite's
specific coverage is the right coverage for the stakes). Remove this layer
and a green suite run is trusted as self-certifying -- nobody asks what
would make it pass by accident.

Sourced from `_plans/decisions.md` (DRQ-026, DRQ-028) and
`examples/01-strangler-proxy/CUTOVER.md` ("A bug this cutover caught",
"Evidence trail"). No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1300, 900

band1 = {"x": 20, "y": 80, "w": 1260, "h": 230,
         "label": "Layer 1 -- automated: the Newman behavior-equivalence suite, over a real socket", "fill": "#fafafa"}
band2 = {"x": 20, "y": 330, "w": 1260, "h": 230,
         "label": "Layer 2 -- adversarial verification: check the shared table, not just the response shape", "fill": "#eaf4ec"}
band3 = {"x": 20, "y": 580, "w": 1260, "h": 230,
         "label": "Layer 3 -- human judgment: the two gates", "fill": "#fafafa"}

# ---- Layer 1 ---------------------------------------------------------------
suite = node(60, 150, 520, 120,
             ["Newman suite, real WSGI backend, real socket", "re-run against every candidate build",
              "58/58 -- baseline, cutover, reverted (CUTOVER.md)"], style="accent")
remove1 = node(660, 150, 580, 120,
               ["Remove this layer:", "the chunked-body bug ships silently --",
                "every POST through the proxy arrives empty"], style="accent")

# ---- Layer 2 ---------------------------------------------------------------
adversarial = node(60, 400, 520, 120,
                    ["Ask a sharper question than \"does the", "suite pass\": did the right row land",
                     "in the shared reviews/auth_user table?"], style="accent")
remove2 = node(660, 400, 580, 120,
               ["Remove this layer:", "a shape-only green run hides which backend",
                "actually answered -- both share one table"], style="accent")

# ---- Layer 3 ---------------------------------------------------------------
gate1 = node(60, 650, 290, 120,
             ["Gate 1 -- plan approval", "Plan phase", "a human commits before any diff exists"], style="user")
gate2 = node(380, 650, 260, 120,
             ["Gate 2 -- equivalence sign-off", "Verify phase",
              "a human judges whether coverage fits the stakes"], style="user")
remove3 = node(690, 650, 550, 120,
               ["Remove this layer:", "a green suite run is trusted as self-certifying --",
                "nobody asks what would make it pass by accident"], style="accent")

nodes = [suite, remove1, adversarial, remove2, gate1, gate2, remove3]

edges = [
    connect(suite, remove1, amber=True, label="catches: a real-socket defect no mock transport surfaces", ly=-75),
    connect(adversarial, remove2, amber=True, label="catches: shared state masking which backend answered", ly=-75),
    connect(gate1, gate2),
    connect(gate2, remove3, amber=True, label="decides: is this coverage the right coverage?", ly=-75),

    connect(suite, adversarial, dashed=True, label="compensates for layer 1's blind spot"),
    connect(adversarial, gate1, dashed=True, label="judges whether layers 1+2's coverage fit the stakes"),
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "the safety net has three layers; removing any one lets a specific bug through",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "the ADLC is not safe because an agent is careful -- it is safe because all three layers hold at once",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/decisions.md and examples/01-strangler-proxy/CUTOVER.md.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "adlc-safety-net-layers", W, H,
    bands=[band1, band2, band3],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
