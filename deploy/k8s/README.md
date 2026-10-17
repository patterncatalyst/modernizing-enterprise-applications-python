# deploy/k8s -- kustomize manifests (ch.29)

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
  overlays/
    minikube/
      kustomization.yaml        # ../../base; image tags, imagePullPolicy: Never,
                                 # strangler-proxy -> NodePort 30888
  scripts/                      # setup-profile, build-images, deploy, teardown
```

## Cluster, images, deploy (minikube)

```bash
# 1. Profile `mea`: Kubernetes v1.37.1 (override with KUBERNETES_VERSION),
#    docker driver + containerd runtime by default (CONTAINER_ENGINE=podman
#    and MINIKUBE_DRIVER=podman together for a podman-driven profile),
#    NodePort 30888 (strangler-proxy) published on 127.0.0.1.
deploy/k8s/scripts/setup-profile.sh

# 2. Build each service's Containerfile image and load it into the profile
#    (no registry -- the overlay sets imagePullPolicy: Never).
deploy/k8s/scripts/build-images.sh

# 3. kubectl apply -k deploy/k8s/overlays/minikube, wait for rollout, and
#    bootstrap review-service's shared `public` schema (see below).
deploy/k8s/scripts/deploy.sh

# 4. Reach the edge router directly on the published NodePort.
curl -s http://127.0.0.1:30888/api/inventory

# 5. Stop when idle (one local cluster at a time).
deploy/k8s/scripts/teardown.sh            # --delete to remove the profile
```

`graphql-gateway` has its own front door (`:8090`) and is never routed
through `strangler-proxy`; it stays ClusterIP-only in this overlay, so
reach it with `kubectl -n mea port-forward svc/graphql-gateway 8090:8090`.

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
# Both layers render with no error -- pure client-side templating, no
# cluster needed:
kubectl kustomize deploy/k8s/base
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

## Deferred to r10 (ch.30)

- **Istio / mesh, LGTM observability** -- `overlays/minikube/kustomization.yaml`
  leaves a commented `resources:` seam (`../../istio`, `../../observability`)
  for exactly this. Neither directory exists at r09, so the overlay
  resolves against `../../base` alone and `kubectl kustomize` has no
  dangling reference today.
- A live minikube run (pods actually Ready, a request actually flowing
  end to end) -- the `scripts/` path above is user-runnable but is not part
  of any CI gate at r09.
