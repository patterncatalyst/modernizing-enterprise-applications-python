---
title: "Deployment Patterns"
order: 29
part: "Operating the Modernized System"
description: "Compose to cluster: a kustomize base and overlay for the eight-service topology, config as data, probes that match what each service can answer, zero-downtime rollouts, and what can be verified without a cluster."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Separate the two moves from Compose to Kubernetes: containerizing eight processes, and relocating Postgres and Kafka into in-cluster StatefulSets.
- Read a kustomize `base` and `overlays/minikube` tree and say why patching a base beats Helm templating for one target environment.
- Distinguish a shared `ConfigMap`, a per-service `env:` override and a `secretKeyRef` secret, and see why a frozen-dataclass `Settings.from_env()` needs no code change.
- Match each probe to what the service can answer: `httpGet /health` for six services, `tcpSocket` for `strangler-proxy` and `review-service`, which have no health route.
- Configure `maxUnavailable: 0` and `maxSurge: 1` with a `preStop` sleep and a longer `terminationGracePeriodSeconds` so a Kafka consumer leaves its group cleanly.
- Explain why only `strangler-proxy` is a `NodePort`.
- State what `kubectl kustomize`, `kubeconform` and `kubectl apply --dry-run=client` do and do not verify without a cluster.

## Why this matters

Until now the system has run under `docker compose`: eight Containerfiles, a shared Postgres, a single-broker Kafka, all reached on `localhost`. That is the right tool for building and proving each extraction, and it has been hiding a question: what are these services as Kubernetes workloads, each with its own rollout, health contract and restart policy? `deploy/k8s/` answers it with a kustomize `base` of eight Deployment and Service pairs plus two StatefulSets, and one `overlays/minikube` that adapts the base to a local cluster with no image registry. It is additive: no application code, `compose.yaml` line or CI gate changes.

{% include excalidraw.html file="deploy-k8s-namespace-topology" alt="The mea namespace: strangler-proxy as the single NodePort 30888 edge, six bounded-context services plus graphql-gateway's own ClusterIP-only front door, a shared postgres StatefulSet (schema per service, set in app code) and a shared kafka StatefulSet, with order-service and graphql-gateway each a gRPC client of inventory-service" caption="Figure 29.1: The mea namespace: 8 Deployments and Services, 2 StatefulSets, one NodePort edge" %}

## From compose project to kustomize base

Compose describes one flat list of services on one network. A Deployment describes a replica count and rollout strategy for one workload, and a Service gives it a stable network identity. `deploy/k8s/base/` holds one file per concern:

- `namespace.yaml`: the single `mea` namespace. There is one shared Postgres with a schema per service, so a namespace per bounded context would draw a line the data ownership doesn't.
- `app-config.yaml`: ConfigMap `mea-app-config`, every non-secret value that is the same for all readers.
- `app-secret.yaml`: Secret `mea-postgres-app`, holding the Postgres connection string.
- Eight service manifests, each a Deployment and a Service: `strangler-proxy.yaml`, `review-service.yaml`, `notification-service.yaml`, `inventory-service.yaml`, `payment-service.yaml`, `shipping-service.yaml`, `order-service.yaml`, `graphql-gateway.yaml`.
- `infra/postgres-statefulset.yaml` and `infra/kafka-statefulset.yaml`: the shared Postgres and single-broker Kafka, each with its own `PersistentVolumeClaim`, using the same images, tags and KRaft env block as `compose.yaml`.
- `kustomization.yaml`: ties the eleven files into one `kubectl kustomize deploy/k8s/base` render.

The one overlay, `overlays/minikube/`, holds what the base shouldn't know: it retags every `mea/<svc>` image from `latest` to `1.0`, sets `imagePullPolicy: Never` on every app Deployment because there is no in-cluster registry, and patches `strangler-proxy`'s Service from `ClusterIP` to `NodePort`. A staging or production overlay would sit beside it and patch the same base toward a real registry, another replica count or a `LoadBalancer`, without touching `base/`. The base says what the system is; each overlay says what one environment needs to say differently.

Helm is the tool for the OpenShift appendix, where templating and a values file earn their cost on a platform with its own operators and security constraints. For a generic Kubernetes target with one environment, the patch model is the more literal match: every file in `base/` stays plain YAML and the overlay is a diff against it. A flat directory with no overlay works for one environment but forks the base the moment a second one exists.

## Images and security context

`deploy/k8s/` adds no build. Each image comes from the service's own `Containerfile`: a UBI 10 `python-314-minimal` base, a multi-stage build that runs `uv sync --locked` before copying application code, and a non-root final stage that ends:

```
USER root
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001:0
```

UBI minimal ships no `shadow-utils`, so there is no `useradd`. Group `0` owns `/app` with the owner's permissions, which an arbitrary OpenShift-style UID still belongs to, and `USER 1001:0` drops to a fixed non-root UID. Every Deployment carries the Kubernetes half of that contract:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

`runAsNonRoot: true` makes the kubelet refuse to start the container if the image's `USER` is ever dropped. It enforces a promise the image already keeps. The StatefulSets need a variant: the official Postgres image owns its data directory as uid `70`, and the `apache/kafka` image runs as uid `1000` under the non-numeric name `appuser`, which `runAsNonRoot` can't verify. Both set `runAsUser` to the image's real UID and an `fsGroup` so the kubelet can chown the mounted volume.

With no registry, `scripts/build-images.sh` builds each image (`docker build`, or `podman build` with `CONTAINER_ENGINE=podman`) and runs `minikube -p mea image load mea/<svc>:1.0` to copy it into the node. A missing load then fails as `ErrImageNeverPull`, which names the problem, instead of Kubernetes falling back to `IfNotPresent` and failing a pull from `docker.io/mea/...`.

## Config as data: one DATABASE_URL, not six

The six DB-backed services (`review-`, `notification-`, `inventory-`, `payment-`, `shipping-` and `order-service`) carry no schema in their connection string. A common alternative bakes a `?currentSchema=...` into each service's URL, which needs one ConfigMap key per service. Here every service reads a single `DATABASE_URL` through its own `app/config.py` and `app/db.py`. The schema is chosen in code: `app/db.py` sets `search_path=<schema>,public` on every connection, and each SQLAlchemy model declares `schema="<schema>"` in `__table_args__`. A different URL would not move a service to another schema, so there is exactly one correct value for all six. It embeds the Postgres credentials, so it lives in `app-secret.yaml` as `database-url`, consumed by each Deployment through `secretKeyRef`, never in the ConfigMap and never typed twice.

`app-config.yaml` carries what is safe and identical for every consumer: the Kafka bootstrap address, the six topic names (`ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`, `PAYMENT_DECLINED_TOPIC`, `PAYMENT_REFUNDED_TOPIC`, `SHIPMENT_DISPATCHED_TOPIC`, `SHIPMENT_FAILED_TOPIC`), `INVENTORY_GRPC_TARGET` for the two gRPC clients, the strangler's six `STRANGLER_*_BASE_URL` targets and the gateway's four REST targets. It omits keys whose name is shared but whose value differs: `HTTP_PORT` (`PORT` on notification-service, the one inconsistent name), `GRPC_PORT` and `CONSUMER_GROUP`. A shared `HTTP_PORT: "8085"` would be wrong for seven of the eight services. Those keys sit in each Deployment's own `env:` block next to the matching `containerPort`.

{% include codetabs.html langs="deploy/k8s/base/order-service.yaml: Deployment + Service|deploy/k8s/overlays/minikube/kustomization.yaml: images, NodePort, imagePullPolicy" %}

```yaml
# deploy/k8s/base/order-service.yaml (abbreviated; full file carries header
# comments on the saga fan-in and the schema-per-service story)
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: order-service
          image: mea/order-service:latest
          ports:
            - name: http
              containerPort: 8088
          envFrom:
            - configMapRef:
                name: mea-app-config
          env:
            - name: HTTP_PORT
              value: "8088"
            - name: CONSUMER_GROUP
              value: "order-service"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: mea-postgres-app
                  key: database-url
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 15"]
          livenessProbe:
            httpGet:
              path: /health
              port: http
```

```yaml
# deploy/k8s/overlays/minikube/kustomization.yaml (abbreviated)
resources:
  - ../../base
images:
  - name: mea/order-service
    newTag: "1.0"
patches:
  - target:
      kind: Service
      name: strangler-proxy
    patch: |-
      - op: replace
        path: /spec/type
        value: NodePort
      - op: add
        path: /spec/ports/0/nodePort
        value: 30888
  - target:
      kind: Deployment
      name: order-service
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/imagePullPolicy
        value: Never
```

Every service manifest follows the `order-service` shape: `envFrom` for the shared ConfigMap, then a short `env:` list for the keys that can't be shared and the one secret.

## Probes that match the service

Each probe asks what its service can actually answer. Six services (`notification-`, `inventory-`, `payment-`, `shipping-`, `order-service` and `graphql-gateway`) have a `GET /health` route in `app/main.py` and probe it with `httpGet`:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3
```

`strangler-proxy` and `review-service` have no such route. The proxy is a Starlette app with one job, forwarding to the owning backend. `review-service`, the first extraction, kept the monolith's shared schema and never added one. An `httpGet` against a path that returns `404` would fail readiness permanently, so both probe the HTTP port with `tcpSocket`:

```yaml
readinessProbe:
  tcpSocket:
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

`tcpSocket` asks whether something is listening, not whether the application can serve, and that is the only answer these two services can give. A decorative `/health` route written so they match their siblings would be a signal with nothing behind it. `deploy/k8s/README.md` keeps the probe table next to the manifests so the asymmetry reads as a fact about the services.

Two `/health` routes carry extra meaning. `inventory-service` reports `grpcServerListening` once its gRPC server has bound `:9004` next to HTTP on `:8084`; both start in one `uvicorn` startup, so one probe on the HTTP port covers both. `graphql-gateway`'s `/health` is liveness-only: it never probes a downstream, so an outage in order-service or payment-service fails the one GraphQL field that depends on it, not the gateway's readiness.

## Resources, rolling updates and graceful shutdown

Requests and limits follow what each service does. `strangler-proxy` and `graphql-gateway` hold no connection pool or Kafka client and request `50m`/`128Mi` and `75m`/`192Mi`. `order-service` runs a five-table CQRS model, an outbox relay and a four-topic saga consumer, and requests `150m`/`320Mi`, the highest of the eight. The StatefulSets are shared infrastructure: `postgres` requests `250m`/`512Mi` with limits `1000m`/`1Gi`, and `kafka` requests `250m`/`768Mi` with the same limits.

Every app Deployment rolls the same way:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
```

With every service at `replicas: 1`, `maxUnavailable: 0` keeps the last ready replica in rotation until its replacement is ready, so a deploy leaves no gap. `maxSurge: 1` makes that possible: the new pod starts beside the old one, passes its probes, and only then does Kubernetes terminate the old one.

Termination is where the services differ. `strangler-proxy`, `review-service` and `graphql-gateway` hold no consumer-group membership or background task, and use the default `30`s or a shorter `10`s. `order-service` has the widest fan-in: one consumer group subscribed to four topics (`payment.captured`, `payment.declined`, `shipment.dispatched`, `shipment.failed`) plus an outbox relay publishing `order.placed`. It sets `terminationGracePeriodSeconds: 60` and a `preStop` hook that sleeps 15 seconds before `SIGTERM` is delivered:

```yaml
terminationGracePeriodSeconds: 60
lifecycle:
  preStop:
    exec:
      command: ["sh", "-c", "sleep 15"]
```

Without the sleep, `SIGTERM` reaches the old pod as soon as the new one is ready. The old member leaves mid-poll, the broker reassigns its four topic-partitions before the new member has finished starting, and the group churns through an extra rebalance. The sleep gives the consumer loop time to commit offsets and leave through Kafka's `LeaveGroup`, and the 60 seconds keep the kubelet from killing the container partway through.

## The strangler as the one front door

`strangler-proxy` is the only Service patched to `NodePort`. The six bounded contexts, `graphql-gateway`, `postgres` and `kafka` stay `ClusterIP`, reachable only inside the cluster. With the monolith flag-free and nothing left to fall back to, the proxy is the one path an outside client uses. `graphql-gateway` is the planned exception to "everything goes through the proxy": it has always been its own front door, but here that means `ClusterIP` only. From outside the cluster it is reached with `kubectl -n mea port-forward svc/graphql-gateway 8090:8090`, as for any internal Service.

## Shared Postgres and Kafka in the cluster

Each StatefulSet is a headless Service plus one pod with its own `PersistentVolumeClaim`, so data survives a restart the way a Docker named volume does under Compose. Postgres keeps the `wal_level=logical`, `max_replication_slots=4` and `max_wal_senders=4` flags from `compose.yaml`, left over from the change-data-capture transition. No Kafka Connect or Debezium deployment exists here, but a future one would need no Postgres restart. The flags go in `args`, not `command`: `command` replaces the image's `ENTRYPOINT` and skips `docker-entrypoint.sh`'s `initdb` and `POSTGRES_*` handling, while `args` only appends flags to the `postgres` process it execs.

Kafka is a single-broker KRaft cluster with no ZooKeeper, mirroring `compose.yaml` down to the `apache/kafka:4.3.1` tag and the combined broker and controller role. A Kubernetes StatefulSet has one network, so a single `PLAINTEXT` listener serves every client, and `KAFKA_ADVERTISED_LISTENERS` and `KAFKA_CONTROLLER_QUORUM_VOTERS` use Kubernetes DNS names. The headless Service sets `publishNotReadyAddresses: true`: by default it would publish DNS only for ready endpoints, but the single broker must resolve its own controller address (`kafka-0.kafka.mea.svc.cluster.local`) to become ready, so without the flag it waits forever on a record that can't exist yet.

Schema creation needs no bootstrap ConfigMap. Each service's Alembic migration issues its own `CREATE SCHEMA IF NOT EXISTS` as part of `alembic upgrade head`, which is every container's startup command. `review-service` is the exception.

## review-service's bootstrap

`review-service` runs no Alembic migration. Its `app/db.py` sets no `search_path` because it never owned a schema: it reads and writes the monolith's original `public` schema (`reviews`, plus read-only lookups into `customers`, `inventory_items` and `auth_user`). That schema must exist and be seeded before the service can answer a request, and nothing in the eight-service topology creates it, because the monolith has no Deployment here.

`scripts/deploy.sh` closes the gap once per fresh Postgres volume. It opens a temporary `kubectl port-forward` to the `postgres` Service, then runs the monolith's `manage.py migrate` and `manage.py seed` against it with `DATABASE_URL` pointed at `127.0.0.1`. It checks `to_regclass('public.reviews')` first and skips the step if the schema exists, so re-running against an existing volume is a no-op. This is the one manual dependency left, and it comes from the data-ownership decision made at the review extraction, not from Kubernetes.

## Verifying without a cluster

Three commands cover three different amounts of ground:

```sh
# Pure client-side templating (no cluster, no network call at all):
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/minikube

# Offline schema validation against the upstream Kubernetes OpenAPI
# schemas (no cluster, no call to a live apiserver):
kubectl kustomize deploy/k8s/overlays/minikube | kubeconform -strict -ignore-missing-schemas -summary

# Client-side structural validation (needs apiserver discovery first):
kubectl kustomize deploy/k8s/base | kubectl apply --dry-run=client -f -
```

| Command | Needs an apiserver | Catches |
| --- | --- | --- |
| `kubectl kustomize` | No | patches or image retags that don't resolve |
| `kubeconform -strict` | No | missing required fields, wrong types, unknown fields |
| `kubectl apply --dry-run=client` | Yes, for discovery | kinds that don't map to a REST resource, once a cluster is reachable |

`kubectl kustomize` and `kubeconform` need no network, which is why CI (`deploy-manifests.yml`) runs those two on every change to the tree. `--dry-run=client` first resolves each manifest's `kind` to a REST resource, and that discovery call goes to a real apiserver, a running `minikube` or `kind`, or a cached discovery document from an earlier connection. With none reachable it fails at discovery with a connection error before validating anything. It is a different check from `kubeconform`, not a stricter one.

None of the three runs server-side dry-run, admission control or webhooks. Those catch a `PersistentVolumeClaim` that can't bind on a storage class, an `ImagePullBackOff` from an image that was never loaded under `imagePullPolicy: Never`, or `PodSecurity` admission rejecting the `securityContext` block. They need a running cluster, which means the live path in `scripts/`: `setup-profile.sh`, `build-images.sh`, `deploy.sh` and `teardown.sh`. That path is user-runnable but not wired into CI.

> **ADLC in Action**
>
> The probe table could have been written by assuming a uniform `httpGet /health` and moving on. Checking meant opening `examples/01-strangler-proxy/app/main.py` and `examples/02-review-service/app/main.py` and finding no health route in either. The same discipline applied to config: drafting from an assumed manifest shape would have produced six per-service connection-URL keys that match nothing in the services' `app/db.py` files. Reading `app-config.yaml`'s header comment, then the `search_path` logic it describes, kept the single `DATABASE_URL` claim grounded in code.

> **Decision**
>
> Put what is the same everywhere in the base, what differs per environment in an overlay, and what differs per service in that service's own `env:`. Probe only what a service can answer. Give a Kafka consumer a `preStop` sleep and a grace period long enough to leave its group before `SIGTERM`.

> **🤖 Explore with your agent**
>
> "Review deploy/k8s/base for the eight services against the probe and rollout rules: list each service's liveness and readiness probe type and whether its app/main.py actually serves /health, flag any Kafka consumer (notification-service, payment-service, shipping-service, order-service) without a preStop sleep and a terminationGracePeriodSeconds above it, and propose the patch without changing any application code."
>
> Check: run `kubectl kustomize deploy/k8s/base | kubeconform -strict -summary` and confirm it reports 23 resources valid and none invalid.

## Build, run, observe

Render and validate without a cluster:

```sh
kubectl kustomize deploy/k8s/base | kubeconform -strict -summary
```

The base renders 23 resources, all valid. The minikube overlay now also composes the Istio and observability trees, whose Istio custom resources have no published schema, so CI validates it with `kubeconform -strict -ignore-missing-schemas`.

To run it, `deploy/k8s/scripts/` takes a fresh machine to a live `mea` namespace on minikube (docker driver, containerd runtime):

```sh
deploy/k8s/scripts/setup-profile.sh   # creates the mea profile, publishes NodePort 30888
deploy/k8s/scripts/build-images.sh    # builds and loads mea/<svc>:1.0 into the node
deploy/k8s/scripts/deploy.sh          # applies the overlay, bootstraps review-service's schema
deploy/k8s/scripts/teardown.sh
```

The strangler-proxy edge answers on `127.0.0.1:30888`.

- **Skip `build-images.sh`:** pods stay in `ErrImageNeverPull`, which names the missing image.
- **Point `review-service` at a probe path of `/health`:** readiness fails permanently, because it has no such route.
- **Run `kubectl apply --dry-run=client` with no cluster reachable:** it fails at discovery with a connection error, while `kubeconform` passes.
