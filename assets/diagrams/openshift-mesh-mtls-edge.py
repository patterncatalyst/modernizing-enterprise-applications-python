#!/usr/bin/env python3
"""ch.33 figure: openshift-mesh-mtls-edge -- the opt-in platform tier once
`openshift/platform/install-mesh.sh` has run: OSSM 3 (Sail) injects
`istio-proxy` by the `istio.io/rev: default` pod-template LABEL (NOT the
classic `sidecar.istio.io/inject` annotation the minikube path uses --
Sail's revisioned webhook ignores that annotation entirely, DRQ-109). A
namespace-wide `PeerAuthentication` named `default` sets STRICT; a second,
workload-scoped `PeerAuthentication` per Route-facing service
(`<name>-edge`) sets PERMISSIVE, because the OpenShift router is not a mesh
member and OSSM 3 provisions no ingress gateway of its own here -- the
Route IS the edge (DRQ-106/109). Kiali has no cluster Prometheus to read on
CRC, so it points at otel-lgtm's own bundled Prometheus instead
(install-observability.sh's 4/4 step).

Sourced from openshift/helm/mea/templates/{peerauthentication.yaml,
app-deployment.yaml,route.yaml}, openshift/platform/mesh/{istio.yaml,
kiali.yaml}, and openshift/platform/install-observability.sh.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1540, 820

band = {"x": 230, "y": 40, "w": 1280, "h": 660, "fill": "#fafafa",
        "label": "project: mea -- OSSM 3 (Sail), Istio v1.30.5, mesh.enabled=true"}

client = node(30, 330, 170, 80, ["Client", "no sidecar -- plain HTTPS"], style="box")

route_note = node(30, 460, 170, 80,
                   ["OSSM provisions no", "ingress gateway here --", "the Route IS the edge"],
                   style="sub")

proxy = node(270, 300, 230, 110,
             ["strangler-proxy + istio-proxy", "PeerAuth strangler-proxy-edge: PERMISSIVE",
              "istio.io/rev: default label"],
             style="accent")
gql = node(270, 560, 230, 100,
           ["graphql-gateway + istio-proxy", "PeerAuth graphql-gateway-edge: PERMISSIVE",
            "istio.io/rev: default label"],
           style="accent")

review = node(600, 80, 240, 62, ["review-service + istio-proxy", "default PeerAuth: STRICT"], style="box")
notif = node(600, 150, 240, 62, ["notification-service + istio-proxy", "default PeerAuth: STRICT"], style="box")
inv = node(600, 220, 240, 70, ["inventory-service + istio-proxy", "default PeerAuth: STRICT"], style="box")
pay = node(600, 298, 240, 62, ["payment-service + istio-proxy", "default PeerAuth: STRICT"], style="box")
ship = node(600, 368, 240, 62, ["shipping-service + istio-proxy", "default PeerAuth: STRICT"], style="box")
order = node(600, 438, 240, 76, ["order-service + istio-proxy", "default PeerAuth: STRICT"], style="box")

services = [review, notif, inv, pay, ship, order]

postgres = node(1020, 150, 260, 90,
                ["postgres StatefulSet", "no istio.io/rev label -- unmeshed"],
                style="sub")
kafka = node(1020, 330, 260, 90,
             ["kafka StatefulSet", "no istio.io/rev label -- unmeshed"],
             style="sub")
kiali = node(1020, 500, 260, 100,
             ["Kiali -> otel-lgtm Prometheus", "lgtm.<ns>.svc.cluster.local:9090",
              "(no cluster Prometheus on CRC)"],
             style="sub")

nodes = [client, route_note, proxy, gql, postgres, kafka, kiali] + services

mesh_group_box = {"x": 600, "y": 78, "w": 240, "h": 436}

edges = [
    connect(client, proxy, dashed=True, label="Route: edge TLS (plaintext to the sidecar)"),
    connect(client, gql, dashed=True, label="Route: edge TLS (plaintext to the sidecar)"),
]
edges += [connect(proxy, s, amber=True) for s in services]
edges[2]["label"] = "mTLS STRICT, sidecar-to-sidecar (6 backends)"
edges.append(connect(order, inv, amber=True, dashed=True, label="gRPC Reserve, mTLS STRICT"))
edges.append(connect(gql, inv, dashed=True, label="gRPC, mTLS STRICT"))
edges.append(connect(mesh_group_box, kiali, dashed=True, label="Envoy spans + :15020 Prometheus scrape"))

notes = [
    {"x": W / 2, "y": 24, "text": "ch.33 -- OSSM 3 on OpenShift: STRICT mesh-wide, a PERMISSIVE carve-out at each Route, Kiali reading otel-lgtm",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 240, "y": H - 56,
     "text": "Injection is by the istio.io/rev: default pod-template LABEL (app-deployment.yaml) -- Sail's revisioned webhook ignores sidecar.istio.io/inject entirely.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 38,
     "text": "Without the per-Route PERMISSIVE PeerAuthentication, the STRICT default would 502 every Route request: the router is not a mesh member.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 20,
     "text": "postgres and kafka carry no istio.io/rev label -- unmeshed, same as the minikube path (ch.30).",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "openshift-mesh-mtls-edge", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
