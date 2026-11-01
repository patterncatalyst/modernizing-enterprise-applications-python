#!/usr/bin/env python3
"""ch.26 figure: graphql-gateway-five-source-fanout -- the data-less
aggregation gateway. One order(id) query resolves the order itself over REST
from order-service, then four more fields are resolved lazily, only if a
client's selection set asks for them: payments and shipments over REST
(order-level), and per line item, stock over gRPC and reviews over REST
(inventory/review-level, by sku). Every one of those four is a nullable
field -- a downstream failure nulls just that field and appends an entry to
errors[], never a 500; an unknown order id is a plain null with no error.

Sourced from examples/08-graphql-gateway/app/schema.py (OrderView/
OrderItemView field resolvers, build_schema's depth/token limiters) and
app/clients.py (DownstreamUnavailable, left uncaught).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 620

band = {"x": 20, "y": 56, "w": 1360, "h": 500,
        "label": "graphql-gateway :8090 -- owns no data, bounded by depth/token limits", "fill": "#fafafa"}

client = node(50, 110, 220, 80, ["Client", "{ order(id) { ... } }"], style="box")
gw = node(330, 110, 280, 80, ["Query.order", "fetch_order(), then lazy", "per-field resolvers"], style="accent")

order_svc = node(700, 70, 260, 70, ["order-service :8088", "REST GET /api/orders/{id}"], style="box")
pay_svc = node(700, 160, 260, 70, ["payment-service :8085", "REST, order.payments"], style="box")
ship_svc = node(700, 250, 260, 70, ["shipping-service :8087", "REST, order.shipments"], style="box")
inv_svc = node(700, 340, 260, 70, ["inventory-service :9004", "gRPC GetStock, item.stock"], style="box")
rev_svc = node(700, 430, 260, 70, ["review-service :8001", "REST, item.reviews by sku"], style="box")

sources = [order_svc, pay_svc, ship_svc, inv_svc, rev_svc]
source_edges = [connect(gw, s, label=lbl) for s, lbl in zip(
    sources, ["order (always)", "payments (if selected)", "shipments (if selected)",
              "stock (if selected)", "reviews (if selected)"])]

fail = node(1020, 250, 320, 100,
            ["A downstream failure nulls JUST that", "field + one entry in errors[] --",
             "siblings still resolve, never a 500"], style="ghost")
nullcase = node(1020, 400, 320, 100,
                ["Unknown order id: data.order = null,", "NO errors[] entry --",
                 "a missing order is a legitimate answer"], style="ghost")

bound = node(330, 230, 280, 90,
             ["QueryDepthLimiter / MaxTokensLimiter", "fixed operator config, not", "derived from the request"], style="accent")

nodes = [client, gw, bound] + sources + [fail, nullcase]
edges = [connect(client, gw)] + source_edges + [
    connect(gw, bound, dashed=True),
    connect(inv_svc, fail, dashed=True, amber=True),
    connect(order_svc, nullcase, dashed=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "one query, five sources, no data owned locally: partial failure is a null field, never a crashed request",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 24, "text": "Every target above is fixed operator configuration -- never derived from the incoming request -- which is what keeps a fan-out gateway from becoming an SSRF/amplification vector.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "graphql-gateway-five-source-fanout", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
