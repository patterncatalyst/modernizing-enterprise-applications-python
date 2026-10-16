#!/usr/bin/env python3
"""ch.26 figure: rest-grpc-graphql-protocol-fit -- three communication styles
this project actually uses, side by side, each labeled with the real seam it
was chosen for and why. REST: request/reply a caller waits on, used for
every service's own read/write surface. gRPC: a strongly-typed, low-latency
call on a hot path that cannot proceed without an answer -- order-service's
Reserve/Release/GetStock calls into inventory-service. GraphQL: one client
query aggregating several services' data in a single round trip, bounded by
depth/token limits -- the gateway's one job. Async events (the fourth style,
covered in depth in ch.23/24) are named at the bottom for completeness, not
re-drawn here.

Sourced from examples/07-order-service/app/inventory_client.py (gRPC seam),
examples/08-graphql-gateway/app/schema.py (GraphQL aggregation), and every
service's own REST contract.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 560

band_rest = {"x": 20, "y": 56, "w": 420, "h": 400, "label": "REST", "fill": "#fafafa"}
band_grpc = {"x": 460, "y": 56, "w": 420, "h": 400, "label": "gRPC", "fill": "#f1f5f9"}
band_gql = {"x": 900, "y": 56, "w": 440, "h": 400, "label": "GraphQL", "fill": "#fafafa"}

r1 = node(50, 110, 360, 70, ["Client -> any service", "request/reply, caller waits"], style="box")
r2 = node(50, 200, 360, 70, ["GET/POST /api/orders", "/api/payments, /api/shipments..."], style="box")
r3 = node(50, 290, 360, 70, ["Fits: a user directly", "waiting on one answer"], style="accent")
r4 = node(50, 380, 360, 60, ["Used by every service", "in this project, since ch.1"], style="ghost")
rest_nodes = [r1, r2, r3, r4]
rest_edges = [connect(r1, r2), connect(r2, r3), connect(r3, r4)]

g1 = node(490, 110, 360, 70, ["order-service -> inventory-service", "Reserve / Release / GetStock"], style="box")
g2 = node(490, 200, 360, 70, ["Strongly typed wire contract", "(proto), versioned, fast"], style="box")
g3 = node(490, 290, 360, 70, ["Fits: checkout cannot proceed", "without a synchronous stock answer"], style="accent")
g4 = node(490, 380, 360, 60, ["The ACL from ch.19,", "unchanged through order's extraction"], style="ghost")
grpc_nodes = [g1, g2, g3, g4]
grpc_edges = [connect(g1, g2), connect(g2, g3), connect(g3, g4)]

q1 = node(930, 110, 380, 70, ["Client -> graphql-gateway :8090", "order(id) { ... }, one round trip"], style="box")
q2 = node(930, 200, 380, 70, ["Fans out to 5 sources lazily,", "per-field, depth/token bounded"], style="box")
q3 = node(930, 290, 380, 70, ["Fits: a view that needs several", "services' data in one response"], style="accent")
q4 = node(930, 380, 380, 60, ["Partial failure = null field +", "errors[], never a 500 -- see Fig 26.4"], style="ghost")
gql_nodes = [q1, q2, q3, q4]
gql_edges = [connect(q1, q2), connect(q2, q3), connect(q3, q4)]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.26 -- three protocols, three different problems, used side by side in one system",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 24, "text": "A fourth style, asynchronous saga events (choreographed ch.23, orchestrated ch.24), coordinates every cross-service outcome none of the three above resolves synchronously.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "rest-grpc-graphql-protocol-fit", W, H,
    bands=[band_rest, band_grpc, band_gql],
    nodes=rest_nodes + grpc_nodes + gql_nodes,
    edges=rest_edges + grpc_edges + gql_edges,
    notes=notes,
)
