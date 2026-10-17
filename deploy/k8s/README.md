# deploy/k8s -- kustomize manifests (ch.29 + ch.30)

Kubernetes manifests for the full 8-service running topology
(`examples/01-strangler-proxy` through `examples/08-graphql-gateway`;
`examples/00-monolith` is frozen and has no Deployment here, and
`examples/09-schema-registry-demo` is a standalone demonstrator excluded
from the running topology). Adapted from the layout at
`~/Dev/datamesh-reference-arch-quarkus/k8s/` (`base/` per-service
Deployment+Service, a shared ConfigMap, `kustomization.yaml`,
`overlays/minikube`) and re-authored against this project's own Python
config model -- see `base/app-config.yaml`'s header for how that model
diverges from the Java sibling's per-service JDBC-URL approach.

ch.30 layers an Istio service mesh (mTLS, mesh-wide tracing) and a Grafana
LGTM observability backend onto this same topology (`deploy/k8s/istio/`,
`deploy/k8s/observability/`), activated in `overlays/minikube`.

This tree is additive only -- it does not change any application code,
`compose.yaml`, `.env.example`, CI, or any existing demo.

## Layout

```
deploy/k8s/
  base/
    namespace.yaml              # Namespace "mea"
    app-config.yaml             # ConfigMap mea-app-config -- shared env contract
    app-secret.yaml             # Secret mea-postgres-app -- dev-only DB credential
    strangler-proxy.yaml        # Deployment + Service (edge router, :8888)
    review-service.yaml         # Deployment + Service (:8001, shared `public` schema)
    notification-service.yaml   # Deployment + Service (:8002, `notification` schema)
    inventory-service.yaml      # Deployment + Service (:8084 http + :9004 grpc, `inventory` schema)
    payment-service.yaml        # Deployment + Service (:8085, `payment` schema)
    shipping-service.yaml       # Deployment + Service (:8087, `shipping` schema)
    order-service.yaml          # Deployment + Service (:8088, `order_svc` schema)
    graphql-gateway.yaml        # Deployment + Service (:8090, data-less)
    infra/
      postgres-statefulset.yaml # headless Service + StatefulSet
      kafka-statefulset.yaml    # headless Service + StatefulSet (single-broker KRaft)
    kustomization.yaml
  istio/
    istio-install.yaml           # IstioOperator -- applied via `istioctl install -f`, NOT kustomize
    peer-authentication.yaml     # PeerAuthentication STRICT, mesh-wide in `mea`
    peer-authentication-edge.yaml # PERMISSIVE exception for strangler-proxy's plaintext NodePort edge
    telemetry.yaml                # Telemetry -- Envoy spans + access logs -> the `otel` provider
    kustomization.yaml            # bundles the 3 CRs above (not istio-install.yaml)
  observability/
    lgtm-deployment.yaml          # grafana/otel-lgtm:0.36.0, unmeshed
    lgtm-service.yaml             # ClusterIP (OTLP/Grafana/etc) + NodePort (Grafana, 30300)
    otelcol-configmap.yaml        # ported from infra/otelcol/config.yaml + an istio-mesh scrape receiver
    grafana-datasources-configmap.yaml # ported from infra/grafana/datasources.yaml
    rbac.yaml                     # ServiceAccount + ClusterRole/RoleBinding for the mesh scrape
    kustomization.yaml             # bundles the 5 above
  overlays/
    minikube/
      kustomization.yaml        # ../../base + ../../istio + ../../observability; image tags,
                                 # imagePullPolicy: Never, sidecar.istio.io/inject labels on the
                                 # 8 app Deployments, strangler-proxy -> NodePort 30888
  scripts/                      # setup-profile, install-istio, build-images, deploy, teardown
```

## Cluster, mesh, images, deploy (minikube) -- the ch.30 bring-up sequence

The minikube driver is always `docker` + `containerd` -- this is the only
documented minikube driver for this project (`CONTAINER_ENGINE` is a
separate, unrelated knob: it picks docker or podman to BUILD the container
images in step 3, not which driver starts the cluster).

```bash
# 1. Profile `mea`: Kubernetes v1.37.1 (override with KUBERNETES_VERSION),
#    docker driver + containerd runtime, NodePorts 30888 (strangler-proxy)
#    and 30300 (Grafana) published on 127.0.0.1.
deploy/k8s/scripts/setup-profile.sh

# 2. Install Istio (istioctl 1.31.2 pin) into the profile from
#    deploy/k8s/istio/istio-install.yaml -- istiod + the ingress gateway.
#    Must run before step 4: the activated overlay's Istio CRs need the
#    control plane's CRDs already installed.
deploy/k8s/scripts/install-istio.sh

# 3. Build each service's Containerfile image and load it into the profile
#    (no registry -- the overlay sets imagePullPolicy: Never).
deploy/k8s/scripts/build-images.sh

# 4. kubectl apply -k deploy/k8s/overlays/minikube -- the base topology,
#    the Istio mesh CRs, and the LGTM observability backend together; wait
#    for rollout; bootstrap review-service's shared `public` schema (see
#    below).
deploy/k8s/scripts/deploy.sh

# 5. Reach the edge router directly on the published NodePort.
curl -s http://127.0.0.1:30888/api/inventory

# 6. Grafana (Tempo/Loki/Mimir behind one UI).
open http://127.0.0.1:30300   # or just point a browser at it

# 7. Stop when idle (one local cluster at a time); removes the mesh +
#    observability resources first (see teardown.sh's header).
deploy/k8s/scripts/teardown.sh            # --delete to remove the profile
```

`graphql-gateway` has its own front door (`:8090`) and is never routed
through `strangler-proxy`; it stays ClusterIP-only in this overlay, so
reach it with `kubectl -n mea port-forward svc/graphql-gateway 8090:8090`.

### Mesh verification

Once `deploy.sh` reports every Deployment Ready, each of the 8 app pods
runs 2/2 (app container + the injected `istio-proxy` sidecar):

```bash
# Confirm injection + the mTLS mode Istio is actually enforcing on a pod.
istioctl x describe pod -n mea <pod-name>
# Expect: "Pilot reports that transport socket is implicit" style sidecar
# detail and "Suspicious: no VirtualServices" is fine (none are used here);
# the line to look for is a mesh mTLS mode of STRICT (PERMISSIVE on
# strangler-proxy's inbound side, per peer-authentication-edge.yaml).

# Envoy access logs (meshConfig.accessLogFile: /dev/stdout, telemetry.yaml).
kubectl --context mea -n mea logs <pod-name> -c istio-proxy

# Per-service mesh metrics once the otelcol prometheus/istio-mesh receiver
# has scraped a cycle -- query Mimir (Prometheus-compatible) via Grafana at
# http://127.0.0.1:30300, e.g. `istio_requests_total{destination_service=~"order-service.*"}`.
```

If a pod shows 1/1 instead of 2/2, check that its Deployment's pod template
carries the `sidecar.istio.io/inject: "true"` LABEL (not an annotation --
see `overlays/minikube/kustomization.yaml`'s header) and that it was
created or restarted AFTER `install-istio.sh` completed (the injection
webhook only acts on admission, not retroactively).

### review-service's shared schema

`review-service` runs no Alembic migration of its own -- it reads the
monolith's shared `public` schema (`reviews`/`customers`/`inventory_items`/
`auth_user`), created and seeded by `examples/00-monolith`'s own
`manage.py migrate`/`manage.py seed`. `scripts/deploy.sh` runs that once
against the in-cluster Postgres, through a temporary `kubectl port-forward`,
the same one-time step `examples/02-review-service/README.md` documents for
a local Postgres. Every other service's own Alembic migration
(`alembic upgrade head`) runs as that service's own container startup
command and needs no separate bootstrap step.

## Verifying without a cluster

```bash
# All four trees render with no error -- pure client-side templating, no
# cluster needed:
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/istio
kubectl kustomize deploy/k8s/observability
kubectl kustomize deploy/k8s/overlays/minikube

# Offline schema validation against the upstream Kubernetes OpenAPI schemas
# (no cluster, no network call to a live apiserver):
kubectl kustomize deploy/k8s/overlays/minikube | kubeconform -strict -summary

# Client-side structural validation of every rendered object:
kubectl kustomize deploy/k8s/base | kubectl apply --dry-run=client -f -
```

`kubectl kustomize` and `kubeconform -strict` both run fully offline and
catch manifest-shape errors (missing required fields, wrong types, unknown
fields under `-strict`). `kubectl apply --dry-run=client` additionally needs
a RESTMapping discovery step -- it resolves each manifest's `kind` to a REST
resource before validating, which requires a reachable apiserver (a running
`minikube`/`kind`, or a cached discovery document from a previous
connection). In a sandbox with no reachable apiserver at all, that step
fails at discovery (`dial tcp ...: connection refused`), not at manifest
validation -- `kubeconform` is what covers structural validation in that
case. Server-side dry-run, real admission control, and webhook evaluation
all require a live cluster and are exercised through the `scripts/` path
above, not by this offline check.

### Istio CRs and kubeconform

`kubeconform -strict` has no bundled schema for Istio's CRDs
(`PeerAuthentication`, `Telemetry`) -- they are cluster-defined types, not
part of the upstream Kubernetes OpenAPI set kubeconform ships. Running it
plain reports them as validation **errors** ("could not find schema for
..."), not as structurally invalid:

```bash
kubectl kustomize deploy/k8s/istio | kubeconform -strict -summary
# 3 resources found -- Errors: 3 (missing schema), not Invalid.
```

Add `-ignore-missing-schemas` to turn those into explicit **skips** instead
of errors -- the point of this flag is to let the plain Kubernetes objects
(everywhere else in this tree) keep failing `-strict` on real problems while
the Istio CRs, which have no schema to check against here, are called out
rather than silently passed:

```bash
kubectl kustomize deploy/k8s/istio | kubeconform -strict -ignore-missing-schemas -summary
# 3 resources found -- Skipped: 3. This does NOT mean the Istio CRs passed
# strict schema validation -- it means no schema was available to check
# them against. They are still well-formed YAML with the fields
# istio/api's own Go types define (verified by hand against the upstream
# Istio CRD source, not by kubeconform).
```

`deploy/k8s/istio/istio-install.yaml` (the `IstioOperator`) is excluded
from both commands above: it is not listed in any `kustomization.yaml`
`resources:` (see its own header), is applied via `istioctl install -f`
rather than `kubectl apply -k`, and is cluster-only by construction.

## Probes

Probes match each service's actual health surface rather than a uniform
convention across all eight:

| Service | Probe | Why |
|---|---|---|
| `strangler-proxy` | `tcpSocket` | No `/health` route (confirmed: `examples/01-strangler-proxy/app`) |
| `review-service` | `tcpSocket` | No `/health` route (confirmed: `examples/02-review-service/app/main.py`) |
| `notification-service` | `httpGet /health` | Reports consumer partition-assignment |
| `inventory-service` | `httpGet /health` | Reports `grpcServerListening` once the gRPC server is bound |
| `payment-service` | `httpGet /health` | Reports consumer partition-assignment |
| `shipping-service` | `httpGet /health` | Reports consumer partition-assignment + resume-complete flag |
| `order-service` | `httpGet /health` | Liveness/readiness only |
| `graphql-gateway` | `httpGet /health` | Liveness only -- it never probes a downstream (see its own docstring) |

## Env contract

`base/app-config.yaml`'s header comment is the authoritative write-up of why
this ConfigMap has exactly one `DATABASE_URL` value (in `app-secret.yaml`,
not here) rather than one per service the way the Java sibling's
per-service JDBC URLs work. Summary:

| Env var(s) | Consumed by | Source |
|---|---|---|
| `DATABASE_URL` | review-/notification-/inventory-/payment-/shipping-/order-service | `app-secret.yaml` (`database-url` key) -- ONE value for all six; each service's own `app/db.py` picks its schema in code |
| `KAFKA_BOOTSTRAP_SERVERS` | notification-/inventory-/payment-/shipping-/order-service | ConfigMap |
| `ORDER_PLACED_TOPIC` / `PAYMENT_CAPTURED_TOPIC` / `PAYMENT_DECLINED_TOPIC` / `PAYMENT_REFUNDED_TOPIC` / `SHIPMENT_DISPATCHED_TOPIC` / `SHIPMENT_FAILED_TOPIC` | the services producing/consuming each topic | ConfigMap |
| `INVENTORY_CDC_ENABLED` | inventory-service | ConfigMap (`"false"` -- transition-only consumer, off) |
| `INVENTORY_GRPC_TARGET` | order-service, graphql-gateway | ConfigMap |
| `STRANGLER_REVIEW_BASE_URL` .. `STRANGLER_ORDER_BASE_URL` | strangler-proxy | ConfigMap |
| `ORDER_BASE_URL` | shipping-service (saga enrich step) | ConfigMap |
| `ORDER_SERVICE_URL` / `PAYMENT_SERVICE_URL` / `SHIPPING_SERVICE_URL` / `REVIEW_SERVICE_URL` | graphql-gateway | ConfigMap |
| `OUTBOX_POLL_MS` | payment-/shipping-/order-service | ConfigMap (same `1000` default for all three) |
| `HTTP_PORT` / `PORT` / `GRPC_PORT` / `CONSUMER_GROUP` | each service that reads one | set directly in that Deployment's own `env:` block -- the same env var name needs a different value per service, so these can't live in the shared ConfigMap |

Every app Deployment pulls the whole ConfigMap via `envFrom`; a service with
no matching `Settings.from_env()` field for a given key ignores it.

## ch.30: mesh + observability

The Istio mesh (`deploy/k8s/istio/`) and the LGTM observability backend
(`deploy/k8s/observability/`) are activated in `overlays/minikube/
kustomization.yaml`'s `resources:`, alongside a `sidecar.istio.io/inject`
pod-template label on each of the 8 app Deployments (postgres/kafka carry
none -- meshing a stateful workload's own TLS would collide with the
injected sidecar's mTLS wrapping). See "Cluster, mesh, images, deploy"
above for the bring-up order and "Mesh verification" for confirming it live.

A live minikube run (pods actually Ready 2/2, mTLS actually enforced, a
trace actually captured end to end) is not part of any CI gate -- the
`scripts/` path above is user-runnable; the separate `mesh-manifests.yml`
CI gate (if present) only covers the headless render + kubeconform checks
in this README, never a live cluster.
