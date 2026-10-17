#!/usr/bin/env python3
"""ch.11 figure: hexagonal-ports-adapters -- the ports-and-adapters
discipline as the structural counterpart to strategic/tactical DDD: a domain
core sits in the middle, holding entities, aggregates, and business logic,
and depends on nothing -- no web framework, no ORM, no message broker. It
declares ports: inbound ports describing what it can be asked to do,
outbound ports describing what it needs from the world. Driving adapters --
a REST route, a gRPC service, a message consumer -- translate an incoming
protocol into a call on an inbound port. Driven adapters -- a database
repository, an event publisher -- implement the outbound ports the core
declared. Every dependency arrow points inward, toward the core.

This generator draws rectangles, not literal hexagons -- the hexagon's only
real content is "ports in the middle, adapters on the outside, dependencies
pointing in," which this layered left-core-right layout preserves without
inventing a new primitive.

The REST adapter / repository module are drawn with `examples/02-review-
service`'s own worked example (`app/routes.py`'s FastAPI `APIRouter`,
`app/repository.py`'s async SQLAlchemy query functions); gRPC service and
message consumer are left at the generic level, matching `order/
inventory_client.py` (ch.19's gRPC ACL) and `notification/management/
commands/order_placed_consumer.py` (ch.17's Kafka consumer). The caveat note
is this chapter's own: `app/repository.py` is a module of plain async
functions, not a declared Port interface/Protocol the domain owns -- "not
textbook hexagonal with an explicit Port abstraction."

Sourced from `examples/02-review-service/app/routes.py`,
`examples/02-review-service/app/repository.py`,
`examples/00-monolith/order/inventory_client.py`,
`examples/00-monolith/notification/management/commands/
order_placed_consumer.py`. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 620

# ---- domain core, center ---------------------------------------------------
core = node(610, 230, 280, 160,
            ["Domain core",
             "entities, aggregates, business logic",
             "no web framework, no ORM, no message broker"],
            style="accent")

# ---- ports, flanking the core ----------------------------------------------
inbound_port = node(380, 260, 190, 100,
                     ["Inbound port(s)",
                      "what the core can be asked to do",
                      "e.g. create_review(), place_order()"],
                     style="box")
outbound_port = node(950, 260, 190, 100,
                      ["Outbound port(s)",
                       "what the core needs from the world",
                       "e.g. get_by_sku(), persist()"],
                      style="box")

# ---- driving adapters, left column -----------------------------------------
rest_adapter = node(50, 90, 260, 110,
                     ["REST route",
                      "e.g. app/routes.py (ch.11 excerpt)",
                      "translates an HTTP request into a port call"],
                     style="sub")
grpc_adapter = node(50, 255, 260, 110,
                     ["gRPC service",
                      "translates an incoming RPC into a port call",
                      "e.g. order/inventory_client.py's ACL (ch.19)"],
                     style="sub")
consumer_adapter = node(50, 420, 260, 110,
                         ["Message consumer",
                          "translates an incoming broker message",
                          "e.g. order_placed_consumer.py (ch.17)"],
                         style="sub")

# ---- driven adapters, right column -----------------------------------------
repo_adapter = node(1190, 160, 260, 130,
                     ["Database repository module",
                      "e.g. app/repository.py (ch.11 excerpt)",
                      "implements the outbound port"],
                     style="sub")
publisher_adapter = node(1190, 360, 260, 130,
                          ["Event publisher",
                           "implements the outbound port",
                           "the core declared"],
                          style="sub")

nodes = [core, inbound_port, outbound_port,
         rest_adapter, grpc_adapter, consumer_adapter,
         repo_adapter, publisher_adapter]

# ---- every dependency arrow points inward, toward the core ----------------
edges = [
    connect(rest_adapter, inbound_port, amber=True),
    connect(grpc_adapter, inbound_port, amber=True),
    connect(consumer_adapter, inbound_port, amber=True),
    connect(inbound_port, core, amber=True,
            label="dependency points inward -- adapters are swappable", ly=130),

    connect(repo_adapter, outbound_port, amber=True),
    connect(publisher_adapter, outbound_port, amber=True),
    connect(outbound_port, core, amber=True,
            label="core declares the port; the adapter implements it", ly=130),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.11 -- Hexagonal architecture: ports and adapters, dependencies pointing inward",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "driving adapters translate a protocol into an inbound-port call; driven adapters implement the outbound port the core declared",
     "anchor": "middle", "size": 11.5, "color": "#555555"},

    {"x": W / 2, "y": core["y"] - 14,
     "text": "the core never imports a protocol -- a protocol can be swapped without the core noticing",
     "anchor": "middle", "size": 10.5, "color": "#3d7a4e"},

    {"x": 40, "y": H - 60,
     "text": "Caveat (this chapter's own): examples/02-review-service's app/repository.py is a module of plain async functions, not a declared",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 40, "y": H - 46,
     "text": "Port abstraction the core programs against -- what made review cheap to extract was zero outbound edges to other contexts.",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/02-review-service/app/routes.py + app/repository.py, examples/00-monolith/order/inventory_client.py + notification/management/commands/order_placed_consumer.py.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "hexagonal-ports-adapters", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
