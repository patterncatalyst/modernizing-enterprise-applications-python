#!/usr/bin/env python3
"""ch.26 figure: final-monolith-free-topology -- the end state. A client
reaches six independently deployable services plus the GraphQL gateway
through one flagless edge router (the former strangler proxy, now an
unconditional per-context forwarder with no monolith fallback left). The
monolith is frozen in-repo -- greyed out, unwired, no live traffic -- kept
as the golden-baseline referent and a break-glass fallback, not deleted.

Sourced from examples/01-strangler-proxy/app/config.py +
app/main.py::_select_backend (flagless, six-way lookup, 404 for anything
else), examples/00-monolith/README.md's "FROZEN STATUS (r07)" section, and
tooling/newman/GOLDEN-BASELINE-r07.md's STEP B/C (decommission + the
monolith-free contract suite, 50/133 green).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 640

band = {"x": 20, "y": 50, "w": 1360, "h": 500, "fill": "#fafafa"}

client = node(50, 260, 180, 80, ["Client"], style="box")
proxy = node(290, 260, 240, 80, ["strangler-proxy :8888", "flagless edge router", "6-way lookup, else 404"], style="accent")
gql = node(290, 400, 240, 80, ["graphql-gateway :8090", "its own front door"], style="accent")

review = node(620, 60, 190, 64, ["review-service", ":8001"], style="box")
notif = node(620, 140, 190, 64, ["notification-service", ":8002"], style="box")
inv = node(620, 220, 190, 64, ["inventory-service", ":8084 / :9004"], style="box")
pay = node(620, 300, 190, 64, ["payment-service", ":8085"], style="box")
ship = node(620, 380, 190, 64, ["shipping-service", ":8087"], style="box")
order = node(620, 460, 190, 64, ["order-service", ":8088"], style="box")

services = [review, notif, inv, pay, ship, order]

monolith = node(950, 230, 340, 140,
                ["00-monolith -- FROZEN", "no live traffic, unwired,",
                 "shell builds + 404-only smoke test,",
                 "kept as golden-baseline referent"], style="ghost")

nodes = [client, proxy, gql, monolith] + services
edges = [connect(client, proxy)]
edges += [connect(proxy, s) for s in services]
edges += [connect(gql, order), connect(gql, pay), connect(gql, ship), connect(gql, inv)]
edges.append(connect(proxy, monolith, dashed=True, label="no route left -- break-glass only"))

notes = [
    {"x": W / 2, "y": 28, "text": "the final topology: six services + a GraphQL gateway behind one flagless router, the monolith frozen and unwired",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 24, "text": "Contract suite green against exactly this mesh -- 50 requests / 133 assertions, 0 failed, repeated 4x -- with no monolith process running at all.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "final-monolith-free-topology", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
