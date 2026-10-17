#!/usr/bin/env python3
"""ch.30 figure: mesh-mtls-topology -- the `mea` namespace once the ch.30
seam is activated: all 8 app Deployments carry the `sidecar.istio.io/inject`
pod-template LABEL (overlays/minikube/kustomization.yaml) and run 2/2 with an
injected Envoy sidecar; PeerAuthentication STRICT (deploy/k8s/istio/
peer-authentication.yaml) makes every meshed-to-meshed hop mTLS; the one
PERMISSIVE exception is strangler-proxy's own plaintext NodePort inbound
edge (peer-authentication-edge.yaml). postgres + kafka carry no inject label
-- deliberately unmeshed, so their own TLS/plaintext story is unchanged.
The LGTM backend (deploy/k8s/observability/) is unmeshed too (DRQ-099) and
receives two different kinds of telemetry in plaintext: Envoy's own spans +
the istio-proxy Prometheus scrape (mesh breadth, all 8 services free) and
app-level OTLP from the 3 OTel-instrumented services (app depth).

Sourced from deploy/k8s/istio/{peer-authentication,peer-authentication-edge,
telemetry,istio-install}.yaml, deploy/k8s/observability/{lgtm-deployment,
lgtm-service,otelcol-configmap,rbac}.yaml, and deploy/k8s/overlays/minikube/
kustomization.yaml's per-Deployment inject-label patches.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1540, 820

band = {"x": 230, "y": 40, "w": 1280, "h": 660, "fill": "#fafafa", "label": "namespace: mea -- mesh active (sidecar.istio.io/inject label on 8 Deployments)"}

client = node(30, 330, 170, 80, ["Client", "127.0.0.1:30888"], style="box")

proxy = node(270, 300, 230, 100,
             ["strangler-proxy + istio-proxy", "PeerAuth: PERMISSIVE (inbound)",
              "OTel-instrumented (app depth)"],
             style="accent")
gql = node(270, 560, 230, 80,
           ["graphql-gateway + istio-proxy", "ClusterIP only, mesh STRICT"],
           style="box")

review = node(600, 80, 240, 62, ["review-service + istio-proxy", "mesh STRICT"], style="box")
notif = node(600, 150, 240, 62, ["notification-service + istio-proxy", "mesh STRICT"], style="box")
inv = node(600, 220, 240, 70, ["inventory-service + istio-proxy", "mesh STRICT",
                                "OTel-instrumented (app depth)"], style="accent")
pay = node(600, 298, 240, 62, ["payment-service + istio-proxy", "mesh STRICT"], style="box")
ship = node(600, 368, 240, 62, ["shipping-service + istio-proxy", "mesh STRICT"], style="box")
order = node(600, 438, 240, 76, ["order-service + istio-proxy", "mesh STRICT",
                                  "OTel-instrumented (app depth)"], style="accent")

services = [review, notif, inv, pay, ship, order]

postgres = node(1020, 150, 260, 90,
                ["postgres StatefulSet", "NO sidecar.istio.io/inject", "unmeshed -- own TLS unchanged"],
                style="sub")
kafka = node(1020, 330, 260, 90,
             ["kafka StatefulSet", "NO sidecar.istio.io/inject", "unmeshed -- own TLS unchanged"],
             style="sub")
lgtm = node(1020, 500, 260, 100,
            ["lgtm (Tempo/Loki/Mimir/Grafana)", "NO sidecar.istio.io/inject",
             "unmeshed -- OTLP ingest stays plaintext"],
            style="sub")

db_group_box = {"x": 600, "y": 78, "w": 240, "h": 420}
kafka_group_box = {"x": 600, "y": 148, "w": 240, "h": 352}
mesh_group_box = {"x": 600, "y": 218, "w": 240, "h": 296}

nodes = [client, proxy, gql, postgres, kafka, lgtm] + services

edges = [
    connect(client, proxy, dashed=True, label="plaintext NodePort (PERMISSIVE edge)"),
    connect(client, gql, dashed=True, label="port-forward only (no NodePort)"),
]
edges += [connect(proxy, s, amber=True) for s in services]
edges[2]["label"] = "mTLS STRICT (6 backends)"
edges.append(connect(order, inv, amber=True, dashed=True, label="gRPC Reserve, mTLS STRICT (ACL seam, ch.19)"))
edges.append(connect(gql, inv, dashed=True, label="gRPC, mTLS STRICT"))
edges.append(connect(db_group_box, postgres, label="DATABASE_URL (6 services, unmeshed backend)"))
edges.append(connect(kafka_group_box, kafka, label="KAFKA_BOOTSTRAP_SERVERS (5 services, unmeshed backend)"))
edges.append(connect(mesh_group_box, lgtm, dashed=True, label="Envoy spans + istio-proxy :15090 Prometheus scrape (breadth, all 8)"))
edges.append(connect(proxy, lgtm, dashed=True, amber=True, label="app OTLP (depth)"))
edges.append(connect(order, lgtm, dashed=True, amber=True, label="app OTLP (depth)"))

notes = [
    {"x": W / 2, "y": 24, "text": "ch.30 -- the meshed mea namespace: mTLS STRICT inside, one PERMISSIVE edge, two unmeshed backends",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 240, "y": H - 56,
     "text": "Green boxes (strangler-proxy, order-service, inventory-service) are the 3 OTel-instrumented services -- app depth. All 8 get mesh breadth for free via Envoy.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 38,
     "text": "postgres, kafka, and the lgtm backend itself carry no sidecar.istio.io/inject label -- meshing their own TLS/plaintext would collide with the injected sidecar's mTLS wrapping.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 20,
     "text": "PeerAuthentication: default (STRICT, namespace-wide) + strangler-proxy-edge (PERMISSIVE, inbound only) -- deploy/k8s/istio/peer-authentication*.yaml.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "mesh-mtls-topology", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
