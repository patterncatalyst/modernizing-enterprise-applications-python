#!/usr/bin/env python3
"""chassis-scorecard figure: the used/partial/deferred
scorecard for the cross-cutting chassis across all 8 FastAPI/Starlette
services, as three stacked bands rather than a single mixed list, so the
reader sees at a glance how much of the chassis is actually wired in
versus named-but-not-built.

Sourced from: config.py dataclass-from-env across 01,03-08 (7 of 8; 02-
review-service still reads os.environ.get directly in app/db.py, the pre-
convention style); RotatingFileHandler logging in app/main.py across all 8;
Containerfile in all 8 example directories; errors.py in 02-07 (6 of 8,
absent in 01-strangler-proxy and 08-graphql-gateway); GET /health in 03-08
(6 of 8, absent in 01-strangler-proxy and 02-review-service); tenacity only
in examples/06-shipping-service/app/enrich_client.py; no opentelemetry or
prometheus import anywhere under examples/*/app/; no pybreaker, no
asyncio-based bulkhead; no pydantic-settings anywhere in this tree.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1220, 900

band_used = {"x": 20, "y": 50, "w": 1180, "h": 190, "label": "USED: every service, proven by real code", "fill": "#f1f5f9"}
band_partial = {"x": 20, "y": 270, "w": 1180, "h": 260, "label": "PARTIAL: real, but not universal or not consumed", "fill": "#fafafa"}
band_deferred = {"x": 20, "y": 560, "w": 1180, "h": 300, "label": "DEFERRED: named, not built", "fill": "#fafafa"}

n_config = node(50, 95, 350, 110,
                ["Config: frozen dataclass + from_env()", "7 of 8 (02-review-service still reads", "os.environ.get directly in db.py)"], style="accent")

n_logging = node(430, 95, 350, 110,
                  ["Logging: stdlib logging to", "logs/<service>.log via RotatingFileHandler", "8 of 8, identical shape"], style="accent")

n_container = node(810, 95, 350, 110,
                     ["Containerfile", "8 of 8: every service ships one", "verified by directory listing"], style="accent")

n_health = node(50, 315, 350, 120,
                 ["Health: GET /health", "6 of 8 (absent: 01-strangler-proxy,", "02-review-service), liveness only,", "no downstream probed anywhere"], style="user")

n_errors = node(430, 315, 350, 120,
                 ["Errors: errors.py uniform mapping", "6 of 8 (absent: 01-strangler-proxy,", "08-graphql-gateway; proxy passes", "status through, GraphQL has its own)"], style="user")

n_resilience = node(810, 315, 350, 120,
                      ["Resilience: tenacity retry", "1 of 8: 06-shipping-service's", "enrich_client.py ONLY; the system's", "one outbound HTTP call site"], style="user")

n_otel = node(50, 605, 350, 130,
               ["Metrics / OTel", "no opentelemetry or prometheus import", "anywhere under examples/*/app/", "OTel added to 3 services"], style="ghost")

n_fault = node(430, 605, 350, 130,
                ["pybreaker / bulkhead", "no circuit breaker, no concurrency cap", "named in build-plan prose, zero", "lines of code anywhere"], style="ghost")

n_shared = node(810, 605, 350, 130,
                 ["A true shared chassis library", "each config.py/errors.py/main.py is", "copied and adapted per service, never", "imported from one shared package"], style="ghost")

nodes = [n_config, n_logging, n_container, n_health, n_errors, n_resilience,
         n_otel, n_fault, n_shared]

edges = []

notes = [
    {"x": W / 2, "y": 30, "text": "The chassis scorecard across all 8 services: used, partial, and deferred, each row cites its file",
     "anchor": "middle", "bold": True, "size": 14},
    {"x": 40, "y": H - 40, "text": "Partial is a real tally (6 of 8, 1 of 8); each gap above has a named reason.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "Deferred means zero footprint today, re-checkable by grep; not a capability quietly half-wired and left unexamined.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "chassis-scorecard", W, H,
    bands=[band_used, band_partial, band_deferred],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
