#!/usr/bin/env python3
"""ch.29 figure: deploy-k8s-namespace-topology -- the `mea` namespace as
rendered by deploy/k8s/base + overlays/minikube: 8 app Deployments/Services,
one shared Postgres StatefulSet (schema-per-service picked in each service's
own code, not in the connection string -- see app-config.yaml's header),
one shared Kafka StatefulSet, and the strangler-proxy edge router as the
ONLY NodePort in the topology (30888) -- every other Service stays
ClusterIP, including graphql-gateway's own front door.

Sourced from deploy/k8s/base/{namespace,app-config,app-secret,*-service,
infra/postgres-statefulset,infra/kafka-statefulset}.yaml,
deploy/k8s/overlays/minikube/kustomization.yaml (the NodePort 30888 patch),
and deploy/k8s/README.md's Probes table (tcpSocket on strangler-proxy +
review-service, httpGet /health on the other six).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 760

band = {"x": 220, "y": 40, "w": 1250, "h": 680, "fill": "#fafafa", "label": "namespace: mea"}

client = node(30, 350, 160, 80, ["Client"], style="box")

proxy = node(260, 320, 230, 90,
             ["strangler-proxy :8888", "Service: NodePort 30888", "probe: tcpSocket (no /health)"],
             style="accent")
gql = node(260, 460, 230, 90,
           ["graphql-gateway :8090", "Service: ClusterIP only", "probe: httpGet /health (liveness only)"],
           style="accent")

review = node(590, 80, 230, 68, ["review-service :8001", "probe: tcpSocket (no /health)", "shared public schema"], style="box")
notif = node(590, 156, 230, 68, ["notification-service :8002", "probe: httpGet /health", "own schema"], style="box")
inv = node(590, 232, 230, 68, ["inventory-service :8084 / :9004", "probe: httpGet /health", "own schema"], style="box")
pay = node(590, 308, 230, 68, ["payment-service :8085", "probe: httpGet /health", "own schema"], style="box")
ship = node(590, 384, 230, 68, ["shipping-service :8087", "probe: httpGet /health", "own schema"], style="box")
order = node(590, 460, 230, 68, ["order-service :8088", "probe: httpGet /health", "own schema, 60s grace"], style="box")

services = [review, notif, inv, pay, ship, order]
db_backed = services
kafka_services = [notif, inv, pay, ship, order]

postgres = node(1000, 150, 260, 100,
                ["postgres StatefulSet", "db: monolith (shared)", "schema-per-service in app code"],
                style="box")
kafka = node(1000, 340, 260, 100, ["kafka StatefulSet", "single-broker KRaft"], style="box")
config = node(1000, 500, 260, 68, ["mea-app-config ConfigMap", "non-secret env (topics, targets)"], style="sub")
secret = node(1000, 580, 260, 68, ["mea-postgres-app Secret", "shared DATABASE_URL"], style="sub")

# Virtual (undrawn) bounding boxes used only to route one summary edge each
# from the 6-wide and 5-wide service groups, instead of 11 near-duplicate
# per-service lines into postgres/kafka.
db_group_box = {"x": 590, "y": 78, "w": 230, "h": 460}
kafka_group_box = {"x": 590, "y": 154, "w": 230, "h": 384}

nodes = [client, proxy, gql, postgres, kafka, config, secret] + services
edges = [
    connect(client, proxy, label="NodePort 30888"),
    connect(client, gql, dashed=True, label="port-forward only (no NodePort)"),
]
edges += [connect(proxy, s) for s in services]
edges.append(connect(order, inv, dashed=True, label="gRPC client :9004"))
edges.append(connect(gql, inv, dashed=True, label="gRPC client"))
edges.append(connect(db_group_box, postgres, label="DATABASE_URL via Secret (6 services)"))
edges.append(connect(kafka_group_box, kafka, label="KAFKA_BOOTSTRAP_SERVERS via ConfigMap (5 services)"))

notes = [
    {"x": W / 2, "y": 24, "text": "the mea namespace deploy topology (deploy/k8s/base + overlays/minikube)",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 240, "y": H - 24,
     "text": "strangler-proxy is the only NodePort; every other Service (including graphql-gateway's own front door) stays ClusterIP. Probes: tcpSocket on strangler-proxy + review-service (no /health route), httpGet /health on the other six.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "deploy-k8s-namespace-topology", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
