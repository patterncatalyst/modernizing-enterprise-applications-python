#!/usr/bin/env python3
"""ch.32 figure: pattern-language-map -- the book's pattern language as one
connected flow rather than a 45-row table, now that the migration described
by that table is finished. Two chained rows walk the patterns roughly in the
chapter order they were built (strangler -> ACL/gRPC -> outbox -> CQRS ->
choreographed saga -> orchestrated saga -> registry/chassis/deploy/mesh-
observability/CI-supply-chain), colored by verdict: accent (earned a lasting
role) and user-blue (adapted -- real, but narrower than the deck's original
shape). A ghost row below names five further horizons this project scoped
out rather than built, each one a dashed arrow from the pattern that would
be extended to reach it.

Sourced from `_plans/build-plan.md` SS C (the pattern-coverage matrix, as
reconciled this iteration) and the chapters cited on each node.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1520, 540

band = {"x": 10, "y": 68, "w": 1500, "h": 400, "label": "", "fill": "#ffffff"}

# Legend -- three small swatches, same styles used below
leg_earned = node(30, 34, 170, 28, ["Earned a lasting role"], style="accent")
leg_adapted = node(220, 34, 170, 28, ["Adapted -- real, narrower"], style="user")
leg_deferred = node(410, 34, 230, 28, ["Named horizon -- scoped, not built"], style="ghost")

# Row A -- the synchronous/transactional spine, ch.14-24
a1 = node(30, 80, 230, 110, ["Strangler Fig + ASGI proxy", "decommission", "complete"], style="accent")
a2 = node(280, 80, 230, 110, ["ACL + gRPC seam", "notification", "+ inventory"], style="accent")
a3 = node(530, 80, 230, 110, ["Transactional Outbox", "cures the", "sync-send/dual-write smells"], style="accent")
a4 = node(780, 80, 230, 110, ["CQRS (order_view)", "same-DB,", "same-tx projection"], style="accent")
a5 = node(1030, 80, 230, 110, ["Saga: Choreographed", "payment reacts to", "order.placed, no coordinator"], style="accent")
a6 = node(1280, 80, 230, 110, ["Saga: Orchestrated", "shipping's crash-", "resumable coordinator"], style="accent")

# Row B -- the platform layer, ch.27-31
b1 = node(30, 220, 280, 110, ["Contracts & Schema Registry", "Apicurio, scoped to", "one demo, not every topic"], style="user")
b2 = node(330, 220, 280, 110, ["Microservices Chassis", "convention copied", "per service, not a library"], style="user")
b3 = node(630, 220, 280, 110, ["Deployment (kustomize)", "base + overlays/", "minikube, 8 Deployments"], style="accent")
b4 = node(930, 220, 280, 110, ["Service Mesh + Observability", "Istio mTLS STRICT +", "LGTM; OTel app-level on 3 of 8"], style="user")
b5 = node(1230, 220, 280, 110, ["CI/CD + Supply Chain", "syft/grype/policy,", "fixable-findings-only gate"], style="accent")

# Ghost row -- named further horizons, not built this book
g1 = node(30, 390, 280, 100, ["Full event sourcing (replay)", "beyond the outbox-as-log", "framing shown earlier"], style="ghost")
g2 = node(330, 390, 280, 100, ["pybreaker / bulkhead", "no second failure mode yet", "has forced building one"], style="ghost")
g3 = node(630, 390, 280, 100, ["GitOps operator + canary", "progressive delivery beyond", "the flag-gated cutovers"], style="ghost")
g4 = node(930, 390, 280, 100, ["Loki log aggregation", "LGTM ships L+G+T+M; only", "T (Tempo) is wired in"], style="ghost")
g5 = node(1230, 390, 280, 100, ["Kafka saga-hop tracing", "mesh sees the hop; no app-", "level span crosses it yet"], style="ghost")

nodes = [leg_earned, leg_adapted, leg_deferred,
         a1, a2, a3, a4, a5, a6,
         b1, b2, b3, b4, b5,
         g1, g2, g3, g4, g5]

edges = [
    connect(a1, a2), connect(a2, a3), connect(a3, a4), connect(a4, a5), connect(a5, a6),
    connect(a6, b1, label="extractions -> platform"),
    connect(b1, b2), connect(b2, b3), connect(b3, b4), connect(b4, b5),
    connect(a4, g1, dashed=True),
    connect(b2, g2, dashed=True),
    connect(b3, g3, dashed=True),
    connect(b4, g4, dashed=True),
    connect(b4, g5, dashed=True),
]

notes = [
    {"x": W / 2, "y": 20, "text": "The pattern language, revisited -- one connected flow, colored by verdict, not a list of 45 isolated rows",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 30, "y": H - 14, "text": "Dashed arrows: the pattern that would be extended to reach each named horizon, not a dependency that blocks it today.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "pattern-language-map", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
