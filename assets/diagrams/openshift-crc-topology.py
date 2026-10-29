#!/usr/bin/env python3
"""ch.33 figure: openshift-crc-topology -- the `mea` project (namespace) once
`openshift/deploy.sh` has rolled out the Helm release on OpenShift Local
(CRC). All 8 app Deployments run under the default ServiceAccount with no
`runAsUser` set, admitted by the default `restricted-v2` SCC (the UBI10
`python-314-minimal` images already run as USER 1001:0 -- an arbitrary
assigned UID with group 0, exactly what restricted-v2 expects, DRQ-107).
postgres and kafka run under the dedicated `mea-infra` ServiceAccount bound
to `nonroot-v2` (their upstream images hardcode UID 70 / 1000,
helm/mea/templates/serviceaccount-infra.yaml). otel-lgtm (platform tier,
install-observability.sh) is the one exception, under `anyuid` with only
`runAsUser: 0` set -- no seccompProfile, or admission flips back to
restricted-v2 and its root-owned writes fail again. strangler-proxy and
graphql-gateway are the only two Routes (DRQ-106); every other Service is
ClusterIP-only.

Sourced from openshift/helm/mea/{values.yaml,templates/app-deployment.yaml,
templates/route.yaml,templates/serviceaccount-infra.yaml} and
openshift/platform/observability/lgtm-serviceaccount.yaml.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1540, 820

band = {"x": 230, "y": 40, "w": 1280, "h": 660, "fill": "#fafafa",
        "label": "project: mea -- OpenShift Local (CRC), default restricted-v2 SCC"}

client = node(30, 330, 170, 80, ["Client", "https://<route-host>.apps-crc.testing"], style="box")

proxy = node(270, 300, 230, 100,
             ["strangler-proxy", "Route: edge TLS, redirect",
              "restricted-v2, tcp probe"],
             style="accent")
gql = node(270, 560, 230, 90,
           ["graphql-gateway", "Route: edge TLS, redirect",
            "restricted-v2, http probe"],
           style="accent")

review = node(600, 78, 240, 62, ["review-service", "restricted-v2, schema: public"], style="box")
notif = node(600, 148, 240, 62, ["notification-service", "restricted-v2, kafka consumer"], style="box")
inv = node(600, 218, 240, 70, ["inventory-service", "restricted-v2, grpc :9004"], style="box")
pay = node(600, 296, 240, 62, ["payment-service", "restricted-v2, kafka consumer"], style="box")
ship = node(600, 366, 240, 62, ["shipping-service", "restricted-v2, kafka consumer"], style="box")
order = node(600, 436, 240, 76, ["order-service", "restricted-v2, kafka consumer"], style="box")

services = [review, notif, inv, pay, ship, order]

postgres = node(1020, 148, 260, 90,
                ["postgres StatefulSet", "SA mea-infra, nonroot-v2 (UID 70)"],
                style="sub")
kafka = node(1020, 328, 260, 90,
             ["kafka StatefulSet", "SA mea-infra, nonroot-v2 (UID 1000)"],
             style="sub")
otel = node(1020, 498, 260, 100,
            ["otel-lgtm (platform tier)", "anyuid, runAsUser: 0 only",
             "no seccompProfile set"],
            style="sub")

nodes = [client, proxy, gql, postgres, kafka, otel] + services

db_group_box = {"x": 600, "y": 76, "w": 240, "h": 422}
kafka_group_box = {"x": 600, "y": 146, "w": 240, "h": 352}

edges = [
    connect(client, proxy, label="Route: strangler-proxy"),
    connect(client, gql, dashed=True, label="Route: graphql-gateway"),
]
edges += [connect(proxy, s, amber=True) for s in services]
edges[2]["label"] = "ClusterIP, in-mesh when mesh.enabled (6 backends)"
edges.append(connect(order, inv, amber=True, dashed=True, label="gRPC Reserve (ACL seam)"))
edges.append(connect(gql, inv, dashed=True, label="gRPC"))
edges.append(connect(db_group_box, postgres, label="DATABASE_URL (6 services)"))
edges.append(connect(kafka_group_box, kafka, label="KAFKA_BOOTSTRAP_SERVERS (4 consumers)"))

notes = [
    {"x": W / 2, "y": 24, "text": "the mea project on OpenShift Local: three SCC postures, two Routes as the only edge",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 240, "y": H - 56,
     "text": "restricted-v2 (8 app Deployments, no runAsUser) / nonroot-v2 (postgres, kafka via SA mea-infra) / anyuid+runAsUser:0 (otel-lgtm only).",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 38,
     "text": "strangler-proxy and graphql-gateway are the only externally reachable workloads -- every other Service stays ClusterIP-only.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 240, "y": H - 20,
     "text": "Images are pulled in-cluster from the integrated registry (Figure 33.2); when mesh.enabled, Route traffic needs the PERMISSIVE carve-out (Figure 33.3).",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "openshift-crc-topology", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
