#!/usr/bin/env python3
"""ch.32 figure: book-pattern-scorecard -- the whole book's pattern-coverage
verdict, as three stacked bands (same shape as ch.27's chassis-scorecard,
one level up: patterns, not chassis capabilities). Earned (8 cards): a
lasting role across the finished migration. Adapted (5 cards): real and
shipped, but narrower or differently-shaped than the deck's original
version. Named, deferred (6 cards, ghost): scoped out with a stated
condition, not silently skipped.

This card grouping mirrors `_plans/build-plan.md` SS C's own categories --
it condenses the matrix's 45 rows into one card per pattern family (the
same move chassis-scorecard.py made for ch.27's capability-by-capability
grep results) rather than reproducing every row; the verdict and chapter
on every card matches SS C's "landed rNN" / adapted / demoted annotations
as reconciled this iteration (DRQ-102).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node

g.OUT = os.path.dirname(__file__)

W, H = 1460, 700

band_earned = {"x": 20, "y": 50, "w": 1420, "h": 270, "label": "EARNED -- a lasting role across the finished migration", "fill": "#f1f5f9"}
band_adapted = {"x": 20, "y": 340, "w": 1420, "h": 150, "label": "ADAPTED -- real and shipped, narrower than the deck's original shape", "fill": "#fafafa"}
band_deferred = {"x": 20, "y": 510, "w": 1420, "h": 150, "label": "NAMED, DEFERRED -- scoped out with a stated condition, not skipped silently", "fill": "#fafafa"}

# EARNED -- row 1
e1 = node(40, 95, 330, 105, ["Strangler Fig + ASGI proxy", "ch.14 -- the spine;", "decommission complete r07"], style="accent")
e2 = node(390, 95, 330, 105, ["Content-Based Routing + ACL", "ch.16, ch.19 -- notification +", "the inventory.proto gRPC seam"], style="accent")
e3 = node(740, 95, 330, 105, ["Shared -> Owned Data + sync gRPC", "ch.18, ch.19 -- CDC-backfilled,", "then Alembic-migrated"], style="accent")
e4 = node(1090, 95, 330, 105, ["Transactional Outbox + event-driven", "ch.17, ch.20 -- cures the sync-send", "and dual-write smells"], style="accent")

# EARNED -- row 2
e5 = node(40, 210, 330, 105, ["CQRS + ACID -> ACD", "ch.21, ch.22, ch.26 -- order_view,", "the 201 -> 202 PENDING flip"], style="accent")
e6 = node(390, 210, 330, 105, ["Saga: Choreographed + Orchestrated", "ch.23, ch.24 -- payment reacts,", "shipping's coordinator decides"], style="accent")
e7 = node(740, 210, 330, 105, ["Deployment (kustomize)", "ch.29 -- base + overlays/minikube,", "23/23 kubeconform-strict Valid"], style="accent")
e8 = node(1090, 210, 330, 105, ["CI/CD + Supply Chain", "ch.31 -- syft/grype/policy,", "fixable-findings-only gate"], style="accent")

# ADAPTED
d1 = node(40, 375, 260, 105, ["Microservices Chassis", "ch.27 -- convention copied per", "service, not a shared library"], style="user")
d2 = node(320, 375, 260, 105, ["Contracts & Schema Registry", "ch.28 -- Apicurio, scoped to one", "demo, not every event topic"], style="user")
d3 = node(600, 375, 260, 105, ["Service Mesh + Observability", "ch.30 -- mesh mTLS STRICT on all", "8; app-level OTel on 3 of 8"], style="user")
d4 = node(880, 375, 260, 105, ["CDC / Transaction Log Tailing", "ch.19 -- transition-only, retired", "on schedule once owned"], style="user")
d5 = node(1160, 375, 260, 105, ["Event Sourcing (light)", "ch.21 -- outbox-as-event-log", "framing, not full replay"], style="user")

# NAMED, DEFERRED (ghost)
f1 = node(40, 545, 213, 95, ["Full event sourcing", "(replay beyond the", "outbox-as-log framing)"], style="ghost")
f2 = node(273, 545, 213, 95, ["pybreaker / bulkhead", "no second failure mode", "has forced building one"], style="ghost")
f3 = node(506, 545, 213, 95, ["GitOps operator + canary", "progressive delivery beyond", "the flag-gated cutovers"], style="ghost")
f4 = node(739, 545, 213, 95, ["Loki log aggregation", "LGTM ships it; only Tempo", "is wired into ch.30"], style="ghost")
f5 = node(972, 545, 213, 95, ["Kafka saga-hop tracing", "mesh sees the hop; no app-", "level span crosses it"], style="ghost")
f6 = node(1205, 545, 213, 95, ["Caching", "generic, no migration driver;", "demoted to Appendix H"], style="ghost")

nodes = [e1, e2, e3, e4, e5, e6, e7, e8, d1, d2, d3, d4, d5, f1, f2, f3, f4, f5, f6]

notes = [
    {"x": W / 2, "y": 24, "text": "The book's pattern-coverage verdict -- one card per pattern family, matching build-plan.md SS C",
     "anchor": "middle", "bold": True, "size": 15},
]

g.emit(
    "book-pattern-scorecard", W, H,
    bands=[band_earned, band_adapted, band_deferred],
    nodes=nodes,
    edges=[],
    notes=notes,
)
