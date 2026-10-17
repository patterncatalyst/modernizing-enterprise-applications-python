---
title: "Deployment Patterns"
order: 29
part: "Operating the Modernized System"
description: "Compose to cluster: a kustomize base/overlay split for the 8-service topology, config-as-data, the real probe and port asymmetries, rolling update and graceful shutdown, and what can be verified without a live cluster."
duration: 35 minutes
---

Every chapter since ch.14 has run this system through `docker compose` —
eight Containerfiles, a shared Postgres, a single-broker Kafka, all wired
together by `compose.yaml` and reached on `localhost`. That has been the
right tool for building and proving each extraction: fast rebuilds, one
`docker compose up`, no cluster to manage. It has also been quietly
standing in for a question none of the first twenty-eight chapters had to
answer — what does this system look like as a set of *Kubernetes*
workloads, each with its own rollout, its own health contract, its own
restart policy, running in a namespace instead of a Compose project? This
chapter answers that question with `deploy/k8s/`: a kustomize `base` of
eight Deployment+Service pairs plus two StatefulSets, and a single
`overlays/minikube` that adapts that base to a local cluster with no
image registry. It is additive — no application code, no `compose.yaml`
line, and no CI gate from any earlier chapter changes — and it is a
*re-authoring*, not a port, of the Java sibling's own `k8s/` tree, because
this project's Python services carry a config model that diverges from
the Java one in a way that changes what the manifests actually say.

{% include excalidraw.html file="deploy-k8s-namespace-topology" alt="The mea namespace: strangler-proxy as the single NodePort 30888 edge, six bounded-context services plus graphql-gateway's own ClusterIP-only front door, a shared postgres StatefulSet (schema-per-service in app code) and a shared kafka StatefulSet, with order-service and graphql-gateway each a gRPC client of inventory-service" caption="Figure 29.1 — The mea namespace: 8 Deployments/Services, 2 StatefulSets, one NodePort edge" %}

## From compose project to kustomize base

A `docker compose` file and a set of Kubernetes manifests solve overlapping
problems with different shapes. Compose describes one flat list of
services on one Docker network; a Deployment describes a desired replica
count and rollout strategy for one workload, a Service describes a stable
network identity in front of it, and neither carries an opinion about any
other workload. `deploy/k8s/base/` makes that translation explicit, one
file per concern:

- `namespace.yaml` — the single `mea` namespace every other resource lives
  in. Not a namespace per bounded context: this book's topology is one
  shared Postgres instance with schema-per-service, not one database
  cluster per context, so a namespace boundary around each service would
  draw a line this system's real data ownership doesn't draw.
- `app-config.yaml` — a ConfigMap, `mea-app-config`, carrying every
  non-secret value that is the *same* across every service that reads it.
- `app-secret.yaml` — a Secret, `mea-postgres-app`, carrying the one value
  that isn't safe in a ConfigMap: the Postgres connection string.
- Eight `*-service.yaml` files, one per service, each a Deployment and a
  Service in a single manifest — `strangler-proxy.yaml`,
  `review-service.yaml`, `notification-service.yaml`,
  `inventory-service.yaml`, `payment-service.yaml`, `shipping-service.yaml`,
  `order-service.yaml`, `graphql-gateway.yaml`.
- `infra/postgres-statefulset.yaml` and `infra/kafka-statefulset.yaml` — the
  shared Postgres and single-broker Kafka, as StatefulSets with their own
  `PersistentVolumeClaim` per pod, mirroring `compose.yaml`'s own `postgres`
  and `kafka` services (same images, same tags, same KRaft env block) rather
  than inventing a different topology for the cluster.
- `kustomization.yaml` — the manifest that ties the eleven files above into
  one `kubectl kustomize deploy/k8s/base` render.

On top of that base sits exactly one overlay, `overlays/minikube/`, whose
whole job is environment-specific adaptation that the base should not have
to know about: retagging every `mea/<svc>` image to a fixed `1.0` instead
of `latest`, setting `imagePullPolicy: Never` on every app Deployment
because there is no in-cluster registry to pull from, and patching
`strangler-proxy`'s Service from `ClusterIP` to `NodePort` so the one
service meant to be reached from outside the cluster actually is. A
production overlay — or a CI overlay, or a staging overlay — would sit
beside `minikube/` as a sibling, patching the same base toward a different
environment's real constraints (an actual registry, a different replica
count, a `LoadBalancer` instead of a fixed `NodePort`) without touching a
single file in `base/`. That is the entire argument for the split: the
base is the one description of *what this system is*; overlays are each
description of *what one environment needs to say differently about it*.

A production-grade alternative considered and set aside here is Helm — the
tool chosen for this book's OpenShift/CRC appendix instead, where
templating and a values file earn their complexity for a platform with its
own operator ecosystem and security-context constraints. For a generic
Kubernetes target with one environment variant, kustomize's patch-over-base
model is the simpler, more literal match: every manifest in `base/` is
still plain, readable YAML, and the overlay is a diff against it, not a
templating language layered on top. A flat manifest directory with no
overlay at all was rejected too — it would still work for a single
environment, but it throws away the one teaching point that matters once a
second environment exists: specialization belongs in a patch, not in a
fork of the base files.

## Images: the same Containerfiles, one more consumer

`deploy/k8s/` does not add a new build. Every image it deploys is built
from the same `Containerfile` each service has carried since its own
extraction chapter — UBI 10's `python-314-minimal` base, a multi-stage
build that resolves dependencies with `uv sync --locked` before copying
application code, and a non-root final stage. Every one of those
Containerfiles ends the same way:

```
USER root
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001:0
```

The UBI minimal image ships no `shadow-utils`, so there's no `useradd` to
reach for; instead, group `0` (root's group, which an arbitrary
OpenShift-style UID still belongs to) is made the owner of `/app` and given
the same permissions the file's owner has, and the final `USER 1001:0`
drops the process to a fixed non-root UID in that group. Every Deployment
in `base/` carries the matching Kubernetes-side half of that contract in
its container `securityContext`:

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

`runAsNonRoot: true` makes the kubelet refuse to start the container at all
if the image's own `USER` directive were ever silently dropped or
overridden — the Kubernetes-side enforcement of a promise the image already
keeps, not a second independent promise. The two StatefulSets need their
own variant of the same idea: the official `postgres:18.6-alpine` image
owns its data directory as uid `70`, and the `apache/kafka` image runs as
uid `1000` under a non-numeric username (`appuser`) that `runAsNonRoot`
can't verify without a numeric UID pinned explicitly — both StatefulSets
set `runAsUser` to the image's real UID and an `fsGroup` so the kubelet can
chown the mounted PVC to a group that UID belongs to, rather than trying to
force either image onto the app services' own `1001`.

`overlays/minikube/kustomization.yaml` retags every app image
`mea/<svc>:latest` to `mea/<svc>:1.0` and sets `imagePullPolicy: Never` on
every app Deployment. There is no in-cluster registry in this topology —
`scripts/build-images.sh` builds each image with `docker build` (or
`podman build`, via `CONTAINER_ENGINE=podman`) directly against the same
`Containerfile` each service already has, then runs
`minikube -p mea image load mea/<svc>:1.0` to copy the built image straight
into the node's container runtime. `imagePullPolicy: Never` turns a missing
load into `ErrImageNeverPull`, naming exactly what went wrong, instead of
Kubernetes defaulting to `IfNotPresent` and attempting (and failing) a pull
from `docker.io/mea/...`, a registry path that was never going to resolve.

## Config as data: one DATABASE_URL, not six

This is the one place this chapter diverges hardest from its Java sibling,
and the divergence changes enough of the manifests that `app-config.yaml`'s own
header comment in this repository spends twenty lines on it. The Java
services each build their own JDBC URL with a `?currentSchema=...` query
parameter baked in, so the Java `k8s/` tree needs six different
ConfigMap keys — one JDBC URL string per service, each pointing at the same
server but a different schema by construction.

This project's six DB-backed services (`review-`, `notification-`,
`inventory-`, `payment-`, `shipping-`, `order-service`) don't carry a
schema in their connection string at all. Every one of them reads a single
environment variable, `DATABASE_URL`, through each service's own
`app/config.py`/`app/db.py`. Which Postgres *schema* a service writes to is
decided entirely in that service's own code: `app/db.py` sets
`search_path=<schema>,public` on every connection it opens, and each
SQLAlchemy model declares its own `schema="<schema>"` in `__table_args__`.
Passing a different `DATABASE_URL` to inventory-service would not move it
to a different schema — there is nothing in the connection string that
means "schema" to begin with. That has one direct consequence for the
manifests: there is exactly **one correct value** for `DATABASE_URL`, the
same one, for all six services. Because that single value already embeds
the Postgres username and password
(`postgresql://monolith:monolith@postgres.mea.svc.cluster.local:5432/monolith`),
it lives in `app-secret.yaml` as the Secret key `database-url`, consumed by
each Deployment's own `env:` block via `secretKeyRef` — never copied into
the ConfigMap, never typed twice.

`app-config.yaml` carries everything else that is safe to share and
the same value for every consumer: the Kafka bootstrap address,
the six topic names (`ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`,
`PAYMENT_DECLINED_TOPIC`, `PAYMENT_REFUNDED_TOPIC`,
`SHIPMENT_DISPATCHED_TOPIC`, `SHIPMENT_FAILED_TOPIC`), inventory-service's
gRPC target (`INVENTORY_GRPC_TARGET`, read by both order-service and
graphql-gateway as gRPC clients), the strangler's six fixed
`STRANGLER_*_BASE_URL` backend targets, and graphql-gateway's four REST
targets. What is *not* in that ConfigMap, by design, is any key whose
correct value differs by service even though the variable name is
identical across services — `HTTP_PORT` (or, on notification-service only,
`PORT` — the one place this project's env-var naming isn't uniform),
`GRPC_PORT`, and `CONSUMER_GROUP`. A shared `HTTP_PORT: "8085"` key would
force every service that reads `HTTP_PORT` onto port `8085`, which is
wrong by construction for seven of the eight services that don't use that
port. Each of those keys is set directly in its own Deployment's `env:`
block instead, right next to the matching `containerPort`.

{% include codetabs.html langs="deploy/k8s/base/order-service.yaml — Deployment + Service|deploy/k8s/overlays/minikube/kustomization.yaml — images, NodePort, imagePullPolicy" %}

```yaml
# deploy/k8s/base/order-service.yaml (abbreviated — full file carries header
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

`order-service` is the one manifest in `base/` that uses both delivery
mechanisms side by side — `envFrom` for the whole shared ConfigMap, and a
per-service `env:` block layered on top for the three keys that can't be
shared plus the one secret key that must never sit in a ConfigMap at all.
That combination — `envFrom` plus a short `env:` override list — is the
same pattern every one of the eight service manifests follows, with the
`env:` list's contents being exactly whichever keys that particular
service's own `app/config.py` needs that aren't safe to broadcast.

## Liveness and readiness: an asymmetry worth keeping

Every probe in `base/` matches what the service underneath it can actually
answer, rather than a single convention copied onto all eight. Six of the
eight services — `notification-`, `inventory-`, `payment-`, `shipping-`,
`order-service`, and `graphql-gateway` — carry a `GET /health` route in
`app/main.py`, so their Deployments probe it with `httpGet`:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3
```

`strangler-proxy` and `review-service` have no such route. `strangler-proxy`
is a Starlette app with exactly one responsibility — proxy an inbound
request to the owning backend — and never grew a health endpoint of its
own across twelve chapters of extractions. `review-service`, the very first
extraction, kept the monolith's shared Postgres schema instead of taking
on a database of its own, and its `app/main.py` likewise never added a
`/health` route. Giving either of them an `httpGet` probe against a path
that returns `404` would make every readiness check fail permanently,
which is a worse outcome than the alternative that reflects what each
service can actually answer: both Deployments
probe with `tcpSocket` on the HTTP port instead.

```yaml
readinessProbe:
  tcpSocket:
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

A `tcpSocket` probe answers a narrower question than `httpGet
/health` does — "is something listening on this port" rather than "is the
application layer able to serve a request" — and that narrower answer is
the right one here precisely because it's the only one either service can
actually give. Writing a decorative `/health` route purely so the
Deployment could use `httpGet` like its six siblings would manufacture a
signal with no content behind it; `deploy/k8s/README.md` keeps this table
next to the manifests specifically so the asymmetry reads as a fact about
the running services, not an inconsistency in the manifests themselves.

`inventory-service`'s `httpGet /health` carries one more piece of
information than the others: its JSON body reports
`grpcServerListening` once the service's separate gRPC server has bound
`:9004`, alongside the HTTP server on `:8084`. One probe, on the HTTP port,
covers readiness for both surfaces becoming available together, because
both are started from the same process in the same `uvicorn` startup
sequence. `graphql-gateway`'s `/health` is liveness-only by design — its
own module docstring is explicit that it never probes a
downstream REST or gRPC dependency, so an outage in order-service or
payment-service fails the one GraphQL field that depends on it, not this
gateway's own readiness.

## Resources, rolling updates, and graceful shutdown

Every Deployment sets `resources.requests`/`limits` sized to what that
service actually does rather than one blanket number: `strangler-proxy`
and `graphql-gateway`, which hold no database connection pool and no Kafka
client, request `50m`/`128Mi` and `75m`/`192Mi` respectively; `order-service`,
which runs a 5-table CQRS write/read model plus an outbox relay plus a
four-topic saga consumer, requests `150m`/`320Mi`, the highest of the
eight. The two StatefulSets scale further still — `postgres` at
`250m`/`512Mi` requests and `1000m`/`1Gi` limits, `kafka` at
`250m`/`768Mi` requests and `1000m`/`1Gi` limits — because they are shared
infrastructure every other workload depends on, not one bounded context's
own process.

Every app Deployment uses the same rolling-update shape:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
```

`maxUnavailable: 0` means a rollout never takes the last ready replica of a
service out of rotation before a new one is confirmed ready to take over —
with every service at `replicas: 1` in this topology, that is what keeps a
deploy from producing a visible gap in availability at all. `maxSurge: 1`
is what makes that possible: the new pod starts *alongside* the old one,
passes its own startup and readiness probes, and only then does Kubernetes
terminate the old one.

Terminating the old one is where `terminationGracePeriodSeconds` and the
pod's `preStop` hook matter, and where the eight services differ most.
Most of them default to Kubernetes' own `30`s or set a shorter `10`s
(`strangler-proxy`, `review-service`, `graphql-gateway` — none holds a
Kafka consumer group membership or an in-flight background task worth
waiting on). `order-service` sets the widest grace period in this
topology, `60`s, with a `preStop` hook that sleeps 15 seconds before
`SIGTERM` is even delivered:

```yaml
terminationGracePeriodSeconds: 60
lifecycle:
  preStop:
    exec:
      command: ["sh", "-c", "sleep 15"]
```

`order-service` is the widest fan-in of any service in this topology: one
Kafka consumer group (`app/consumer.py::OrderSagaConsumer`) subscribed to
*four* inbound topics at once — `payment.captured`, `payment.declined`,
`shipment.dispatched`, `shipment.failed` — the same four topics the
monolith's own `order_saga_listener` used to consume in one group, plus its
own outbox relay publishing `order.placed` outbound. A rolling update that
sends `SIGTERM` to that process the instant the new pod is marked ready
risks a consumer-group rebalance storm: the old member leaves mid-poll, the
broker reassigns its four topic-partitions before the new member has
finished its own startup sequence, and the group churns through an extra
rebalance it didn't need to. The 15-second `preStop` sleep buys the
consumer loop time to notice the pod is terminating, commit its offsets,
and leave the group cleanly through Kafka's own `LeaveGroup` protocol
*before* `SIGTERM` reaches the process at all — the 60-second total grace
period is there so the kubelet doesn't force-kill the container partway
through that sequence.

## The strangler as the one front door

`strangler-proxy` is the only Service in this entire namespace patched to
`NodePort` in the minikube overlay. Every other Service — the six bounded
contexts, `graphql-gateway`, `postgres`, `kafka` — stays `ClusterIP`,
reachable only from inside the cluster. That isn't an oversight; it's the
topology this book has been building toward since ch.14: one flagless edge
router, with nothing left to fall back to, is the single path a client
outside the cluster is meant to use. `graphql-gateway` is the one
deliberate exception to "everything goes through the proxy" — it has
always been, since ch.26, its own front door, never routed through
`strangler-proxy` — but "its own front door" means `ClusterIP`-only here,
not a second `NodePort`. Reaching it from outside the cluster in this
topology means `kubectl -n mea port-forward svc/graphql-gateway 8090:8090`,
the same local-only path an operator would use for any other internal
Service that has no reason to be dialed directly from outside.

## Shared Postgres and Kafka, in-cluster

`infra/postgres-statefulset.yaml` and `infra/kafka-statefulset.yaml` bring
the same two pieces of shared infrastructure `compose.yaml` has run since
ch.1 into the cluster as StatefulSets — a headless Service plus one pod
with its own `PersistentVolumeClaim`, so data survives a pod restart the
way a Docker named volume already does for Compose. Postgres keeps the
exact same `wal_level=logical`, `max_replication_slots=4`, and
`max_wal_senders=4` flags `compose.yaml`'s own `command:` sets — inherited
from the now-closed ch.19 CDC transition window and kept here even though
no Kafka Connect/Debezium deployment exists in this manifest-only
topology, so a future Connect deployment would never need a Postgres
restart to turn logical replication on. Those flags are passed as `args`,
not `command`: in Kubernetes, `command` replaces the image's own
`ENTRYPOINT` outright, which would skip `docker-entrypoint.sh`'s own
`initdb`/`POSTGRES_*` handling entirely — `args` keeps that entrypoint
intact and only appends flags to the `postgres` process it eventually
execs.

Kafka runs as a single-broker, KRaft-mode cluster — no ZooKeeper — mirroring
`compose.yaml`'s own `kafka` service down to the image tag
(`apache/kafka:4.3.1`) and the broker+controller-combined-role
environment block. Two details change only because a Kubernetes
StatefulSet has one network, not Compose's host-versus-container-network
split: a single `PLAINTEXT` listener serves every client the same way
(there's no separate `DOCKER:9094` listener to carry), and
`KAFKA_ADVERTISED_LISTENERS`/`KAFKA_CONTROLLER_QUORUM_VOTERS` point at
Kubernetes DNS names instead of `compose.yaml`'s `localhost`/`kafka`
aliases. The headless Service backing it sets
`publishNotReadyAddresses: true` for a reason specific to a single-node
KRaft cluster: that Service would otherwise only publish DNS for *ready*
endpoints, but the one broker must resolve its own controller address
(`kafka-0.kafka.mea.svc.cluster.local`) to become ready in the first
place — without that flag, the broker would deadlock waiting on a DNS
record that can't exist until the broker itself is marked ready.

Schema creation is simpler here than it is in the Java sibling's own
`infra/` tree. Each Python service's own Alembic migration already issues
its own `CREATE SCHEMA IF NOT EXISTS` as part of `alembic upgrade head`,
which runs as every service's own container startup command — there is no
separate schema-bootstrap ConfigMap the way the Java StatefulSet needs one
for Flyway. `review-service` is the one exception, and it needs a
deliberate bootstrap step of its own.

## review-service's bootstrap: a one-time dependency on the frozen monolith

`review-service` runs no Alembic migration — its `app/db.py` sets no
`search_path` override at all, because it was never meant to own a schema.
It reads and writes the monolith's original shared `public` schema
(`reviews`, plus read-only lookups into `customers`, `inventory_items`,
`auth_user`), the same schema `examples/00-monolith` has always owned. That
schema has to exist and be seeded before `review-service` can serve a
single request, and nothing in this eight-service topology creates it —
the monolith itself has no Deployment here; it is frozen, and
`deploy/k8s/README.md` is explicit that it stays that way.

`scripts/deploy.sh` closes that gap with a one-time bootstrap step, run
once per fresh Postgres volume: it opens a temporary
`kubectl port-forward` to the in-cluster `postgres` Service, then runs the
monolith's own `manage.py migrate` and `manage.py seed` against that
forwarded port with `DATABASE_URL` pointed at `127.0.0.1` — exactly the
one-time local setup step `examples/02-review-service/README.md` already
documents for a bare local Postgres, aimed at the cluster's Postgres
instead of a developer's own. The script checks
`to_regclass('public.reviews')` first and skips the whole step if the
schema is already present, so re-running `deploy.sh` against an existing
volume is a no-op rather than a second, redundant seed attempt. Every
other service's own migration runs automatically, every time its container
starts; `review-service`'s dependency on the monolith's migration tooling
is the one manual step left in this topology, and it exists
because of a data-ownership decision made back in ch.15, not because of
anything particular to Kubernetes.

## Verifying without a cluster

None of this chapter's claims about manifest correctness depend on a
reachable Kubernetes apiserver, and it's worth being precise about exactly
how far that goes, because three different commands cover three different
amounts of ground:

```sh
# Pure client-side templating -- no cluster, no network call at all:
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/minikube

# Offline schema validation against the upstream Kubernetes OpenAPI
# schemas -- no cluster, no call to a live apiserver:
kubectl kustomize deploy/k8s/overlays/minikube | kubeconform -strict -summary

# Client-side structural validation -- needs apiserver DISCOVERY first:
kubectl kustomize deploy/k8s/base | kubectl apply --dry-run=client -f -
```

`kubectl kustomize` resolves every patch and image retag in `base/` and
`overlays/minikube/` and prints the fully rendered manifests — a pure
templating step with no cluster involved anywhere. `kubeconform -strict`
takes that rendered output and checks every object's shape against the
upstream Kubernetes OpenAPI schemas, entirely offline, catching the class
of error `kubectl kustomize` itself can't — a missing required field, a
value of the wrong type, or (under `-strict`) a field Kubernetes doesn't
recognize at all. Both of those run with no network reachability
requirement whatsoever, which is exactly why they are the two checks this
project's CI gate (`deploy-manifests.yml`) runs on every change to this
tree.

`kubectl apply --dry-run=client` sits one step further out. Before it can
validate anything, it needs a RESTMapping discovery step — resolving each
manifest's `kind` to a concrete REST resource — and that discovery call
goes to a real apiserver (a running `minikube`/`kind` cluster, or a cached
discovery document left over from a previous connection to one). Run it
with no reachable apiserver at all and it fails at that discovery step,
with a connection error, before manifest validation has even started — it
is a different kind of check from `kubeconform`, not a stricter
version of the same one, and the two aren't interchangeable.

None of the three touches **server-side** dry-run, real admission control,
or webhook evaluation — the checks that would catch a `PersistentVolumeClaim`
that can't actually bind on a given storage class, an `ImagePullBackOff`
that only shows up once the kubelet tries to honor `imagePullPolicy:
Never` against an image that was never loaded, or a `PodSecurity` admission
rule rejecting the `securityContext` block this chapter spent a section
describing. Those require a cluster that is actually running, and in this
topology that means the live minikube path `scripts/` documents —
`setup-profile.sh`, `build-images.sh`, `deploy.sh`, `teardown.sh` — which
is user-runnable today but isn't wired into any CI gate at this point in
the book. ch.30 picks that thread back up once Istio and the LGTM
observability stack land on top of this same base, on a cluster that is
actually up.

> **ADLC in Action** — This chapter's probe table could have been written
> by copying the Java sibling's uniform `httpGet /health` convention onto
> all eight services and calling it done; every one of that book's services
> has a health endpoint, courtesy of a shared MicroProfile Health
> dependency. Confirming whether the same convention held here meant
> opening `examples/01-strangler-proxy/app/main.py` and
> `examples/02-review-service/app/main.py` directly rather than assuming
> symmetry with the other six services' `app/main.py` files — and finding,
> in both, no `/health` route of any kind. The same discipline applied to
> the config model: drafting this chapter from the Java `k8s/` tree's shape
> alone would have produced six per-service JDBC-URL ConfigMap keys that
> don't correspond to anything in this project's actual `app/db.py` files.
> Reading `app-config.yaml`'s own header comment first, and then the six
> services' `search_path` logic it describes, is what kept this chapter's
> "one `DATABASE_URL`" claim grounded in code instead of in the pattern the
> Java sibling happened to use.

---

*Verification status: <span class="status status--unverified">unverified</span>.
Both the base and the minikube overlay render with `kubectl kustomize`
(23 resources each) and pass `kubeconform -strict` with zero invalid;
applying to a live cluster was not exercised in this sandbox (no reachable
apiserver), the exact "needs a live cluster" limit this chapter's own
"Verifying without a cluster" section describes, not a manifest defect.*
