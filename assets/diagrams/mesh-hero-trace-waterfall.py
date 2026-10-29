#!/usr/bin/env python3
"""mesh-hero-trace-waterfall figure: the synchronous checkout path
(DRQ-096=A) as a span-nesting diagram: mesh breadth (grey, Envoy sidecar
spans, captured for all 8 services with zero app code) versus OTel depth
(green, app-level spans on the 3 OTel-instrumented services only). This is
an illustrative nesting diagram, not a rendering of captured timing data;
the real hero trace (span IDs, durations, the Tempo screenshot) is captured
by the user's live run, not invented here.

Hops: Client -> strangler-proxy (edge, PERMISSIVE) -> order-service (FastAPI
server span + asyncpg spans for the order aggregate write and the CQRS
order_view write) -> inventory-service `Reserve` over gRPC (crossing the
ACL seam), with its own asyncpg reservation span. Each hop's Envoy
mesh span wraps its app span(s); the async Kafka saga hops (order.placed ->
payment -> shipping) are out of this picture: mesh-visible,
app-level-deferred.

Sourced from _plans/r10-build-plan.md section A.3 (DRQ-096=A), deploy/k8s/
istio/telemetry.yaml (Envoy spans -> the otel extensionProvider), and the
lgtm-python skill's zero-code opentelemetry-distro posture.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1480, 940

band1 = {"x": 30, "y": 70, "w": 1420, "h": 190, "fill": "#fafafa",
         "label": "Hop 1: Client -> strangler-proxy (mesh edge, PeerAuth PERMISSIVE)"}
band2 = {"x": 30, "y": 290, "w": 1420, "h": 260, "fill": "#f5f5f5",
         "label": "Hop 2: strangler-proxy -> order-service (mTLS STRICT)"}
band3 = {"x": 30, "y": 580, "w": 1420, "h": 260, "fill": "#fafafa",
         "label": "Hop 3: order-service -> inventory-service, gRPC Reserve (mTLS STRICT, ACL seam)"}

mesh1 = node(60, 118, 1360, 120,
             ["Envoy mesh span: ingress sidecar (strangler-proxy)",
              "breadth: every hop, all 8 services, zero app code"],
             style="ghost")
app1 = node(100, 168, 480, 56,
            ["app span: proxy_handler()",
             "httpx client call to order-service"],
            style="accent")

mesh2 = node(60, 336, 1360, 190,
             ["Envoy mesh span: strangler-proxy -> order-service (client + server sidecar)"],
             style="ghost")
app2 = node(100, 376, 1000, 130,
            ["app span: FastAPI server (order-service), POST /api/orders"],
            style="accent")
db1 = node(130, 414, 280, 36, ["asyncpg span: insert order aggregate"], style="box")
db2 = node(430, 414, 280, 36, ["asyncpg span: write order_view (CQRS)"], style="box")
rpc_out = node(730, 414, 330, 36, ["app span, grpc-client call: inventory.Reserve"], style="accent")

mesh3 = node(60, 626, 1360, 190,
             ["Envoy mesh span: order-service -> inventory-service (gRPC)"],
             style="ghost")
app3 = node(100, 666, 1000, 130,
            ["app span: grpc-server (inventory-service), Reserve()"],
            style="accent")
db3 = node(130, 706, 320, 36, ["asyncpg span: reserve inventory row"], style="box")

nodes = [mesh1, app1, mesh2, app2, db1, db2, rpc_out, mesh3, app3, db3]

edges = [
    connect(mesh1, mesh2, label="traceparent propagated"),
    connect(mesh2, mesh3, label="traceparent propagated across the ACL seam"),
]

notes = [
    {"x": W / 2, "y": 30, "text": "The hero trace: mesh breadth (grey, Envoy) vs OTel depth (green, app SDK), illustrative span nesting, not captured timing",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": 58, "text": "Real span IDs, durations, and the Tempo capture come from a live run, not from this figure.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 40,
     "text": "The async Kafka saga hops (order.placed -> payment -> shipping) are out of this trace: mesh-visible in Kiali, app-level-deferred (same posture as the Java sibling).",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22,
     "text": "Grey = mesh span (Envoy sidecar, free on all 8 services). Green = app span (OTel SDK, only strangler-proxy / order-service / inventory-service). White = asyncpg child span.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "mesh-hero-trace-waterfall", W, H,
    bands=[band1, band2, band3],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
