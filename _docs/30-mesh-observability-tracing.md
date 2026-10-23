---
title: "Mesh, Observability & Distributed Tracing"
order: 30
part: "Operating the Modernized System"
description: "Istio (mesh/mTLS/canary), Kiali, OpenTelemetry + the LGTM stack, spans/causality/context propagation, and cross-context debugging — on minikube."
duration: 40 minutes
---

Chapter 29 put this system on a cluster: eight Deployments, two StatefulSets,
one namespace, reachable through a single NodePort. Nothing in that chapter
changed how the services talk to each other — `httpx` still calls
`order-service` over plain HTTP, `grpcio` still dials `inventory-service`
directly, and nothing on the wire between any two pods carries encryption,
a trace header, or a request-level metric unless the service's own code
produces one. This chapter changes that, without touching a single line of
application code. It wires an Istio service mesh across the same eight
Deployments, switches every pod-to-pod hop to mutual TLS, and stands up a
Grafana LGTM backend in the cluster that receives two different kinds of
telemetry at once: Envoy's own spans and metrics for every service, and
application-level OpenTelemetry spans from the three services instrumented
to produce them. Both are additive on top of `deploy/k8s/`'s existing
`base` + `overlays/minikube` split — the same kustomize tree ch.29 built,
with `../../istio` and `../../observability` composed in as new sibling
overlays (`deploy/k8s/overlays/minikube/kustomization.yaml`).

## Why a mesh, and what it actually buys

A service mesh puts a proxy — Envoy, in Istio's case — in front of every
workload's network traffic, as a sidecar container in the same pod, and
moves a specific set of cross-cutting concerns out of application code and
into that proxy: encryption between services, retries and timeouts at the
transport layer, per-hop metrics, and distributed trace spans for every
request that crosses the mesh. None of that requires a service to import a
library, open a different port, or know the mesh exists. `order-service`'s
`grpcio` client still dials `inventory-service:9004` exactly as it did in
ch.29; the only thing that changes is which process on each end of that
TCP connection actually terminates it. Once a pod's template carries the
`sidecar.istio.io/inject` label, Istio's mutating admission webhook adds an
`istio-proxy` container to it at creation time, and from that point every
byte the application container sends or receives on a meshed port passes
through that sidecar first.

That buys three things this chapter cares about, in order. First, transport
security that doesn't depend on every service's own TLS configuration being
correct, or even present — `PeerAuthentication` turns on mutual TLS for a
whole namespace from one resource, not eight. Second, telemetry that exists
whether or not a given service's own code was written with observability in
mind — Envoy emits a span and a handful of Prometheus metrics for every
request it proxies, for all eight services, the moment the sidecar is
injected. Third, a point of leverage for traffic management (canary
weighting, fault injection, circuit breaking) that this chapter does not
use but that the same `PeerAuthentication`/`Telemetry`/`VirtualService`
resource family would cover without a second architecture. What a mesh
does *not* buy is insight into what happens inside a service's own process
— a query against Postgres, an in-memory cache lookup, a decision branch in
business logic — because none of that work ever reaches the sidecar. That
gap is the reason this chapter does not stop at Istio.

## Bringing the mesh up on minikube

The bring-up sequence extends ch.29's, in place, rather than replacing it.
`deploy/k8s/scripts/setup-profile.sh` still creates the `mea` minikube
profile with `--driver=docker --container-runtime=containerd` — the only
driver/runtime pair this project documents — now publishing a second
NodePort, `30300`, for Grafana, alongside `30888` for `strangler-proxy`.
A new script, `deploy/k8s/scripts/install-istio.sh`, runs between profile
creation and image build:

```bash
deploy/k8s/scripts/setup-profile.sh
deploy/k8s/scripts/install-istio.sh      # new: istioctl install, pinned 1.31.2
deploy/k8s/scripts/build-images.sh
deploy/k8s/scripts/deploy.sh             # now also waits on the lgtm Deployment
```

`install-istio.sh` pins `istioctl` to `1.31.2` — the client installs a
control plane of its own version, so a mismatched `istioctl` on `PATH`
would silently stand up the wrong Istio — and checks that pin against
`istioctl version --remote=false` before doing anything else. It then runs
`istioctl install -y --context mea -f deploy/k8s/istio/istio-install.yaml`,
not `kubectl apply -k`: `istio-install.yaml` is an `IstioOperator`
resource, reconciled by the Istio operator controller rather than applied
as a plain object, and its CRD isn't in the Kubernetes OpenAPI schema set
any offline validator ships with. That's why `deploy/k8s/istio/
kustomization.yaml` bundles only the three namespace-scoped CRs
(`PeerAuthentication` ×2, `Telemetry`) and not this file — a header comment
on `istio-install.yaml` itself spells out the reason, and
`deploy/k8s/scripts/install-istio.sh` is its only consumer.

The `IstioOperator` spec picks the `default` profile — `istiod` plus the
ingress gateway — over `minimal` (no gateway) or `demo` (bundles its own
Prometheus/Jaeger/Grafana addons that would duplicate the LGTM stack this
chapter adds separately). Two fields in that spec matter beyond the
profile name: `meshConfig.extensionProviders` names an `otel` provider
pointed at `lgtm.mea.svc.cluster.local:4317`, and `deploy/k8s/istio/
telemetry.yaml` — a namespace-wide `Telemetry` resource with no selector —
turns that provider on for every meshed workload, at
`randomSamplingPercentage: 100.00`. That number is a header comment's own
flag: 100% trace sampling at mesh scale is a cost and cardinality problem
in any real deployment; it's set here so a single capture run is guaranteed
to produce the hero trace this chapter walks through, not because it's a
number this book would ship into a production overlay.

`deploy/k8s/scripts/deploy.sh` checks for `istiod` in the `istio-system`
namespace before running `kubectl apply -k deploy/k8s/overlays/minikube`
and fails with a direct instruction — "run `install-istio.sh` first" —
rather than letting the apply fail on a missing CRD. That ordering
dependency exists because the activated overlay's `PeerAuthentication` and
`Telemetry` resources are Istio's own custom types; Kubernetes rejects any
object whose CRD it doesn't know about yet, which is also why those two
resource kinds are excluded from the `kubeconform` check this chapter's
CI gate runs (see "When render-time checks aren't enough," below).

{% include excalidraw.html file="mesh-mtls-topology" alt="The mea namespace with the ch.30 mesh active: all 8 app Deployments carry the sidecar.istio.io/inject pod-template label and run with an injected Envoy sidecar; PeerAuthentication STRICT makes every meshed-to-meshed hop mTLS, with one PERMISSIVE exception on strangler-proxy's plaintext NodePort inbound edge; postgres, kafka, and the lgtm observability backend carry no inject label and stay unmeshed; the three OTel-instrumented services (strangler-proxy, order-service, inventory-service) export app-level OTLP spans to lgtm alongside the mesh-wide Envoy spans and the istio-proxy Prometheus scrape every service contributes." caption="Figure 30.1 — The meshed mea namespace: mTLS STRICT inside, one PERMISSIVE edge, two unmeshed backends" %}

## The opt-in gotcha: a label, not an annotation

Every one of the eight app Deployments in `overlays/minikube/
kustomization.yaml` already carried one JSON-patch operation before this
chapter — `imagePullPolicy: Never`, the ch.29 fix for a topology with no
in-cluster registry. This chapter adds a second operation to those same
eight patches:

```yaml
- op: add
  path: /spec/template/metadata/labels/sidecar.istio.io~1inject
  value: "true"
```

That `~1` is RFC 6901's escape for a literal `/` inside a JSON-pointer
path segment — the key being set is `sidecar.istio.io/inject`, a single
label key containing a slash, not a nested path. The choice that matters
more than the escaping is what kind of Kubernetes metadata this is: a pod-
template **label**, not an annotation. Istio's sidecar-injection webhook
decides whether to mutate an incoming pod admission request based on an
`objectSelector`, and `objectSelector` matches against labels — not
annotations, and not a namespace-wide marker like `istio-injection:
enabled` applied to `mea` itself. Set the same key as an annotation instead
of a label, and the webhook's `objectSelector` simply never matches; the
pod admits with no sidecar, no error, and no event pointing at what went
wrong. The `mea` namespace stays unlabelled in this topology for a
separate reason — injection here is opt-in per Deployment, not
namespace-wide, which is what lets `postgres` and `kafka` opt out.

`deploy/k8s/overlays/minikube/kustomization.yaml` gives both of those
infrastructure StatefulSets no such patch at all, and no inject label — the
reason is the same collision a meshed database or broker runs into in any
Istio deployment: wrapping Postgres's or Kafka's own TLS-terminating
connection inside a second, sidecar-originated mTLS layer doesn't compose,
it conflicts. Keeping both StatefulSets unmeshed means their wire protocol
is exactly what it was in ch.29 — the sidecar never sees that traffic at
all, because no sidecar exists on either pod.

{% include codetabs.html langs="deploy/k8s/istio/peer-authentication.yaml — namespace-wide STRICT|deploy/k8s/overlays/minikube/kustomization.yaml — the inject-label patch|deploy/k8s/scripts/install-istio.sh — the pinned istioctl install" %}

```yaml
# deploy/k8s/istio/peer-authentication.yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: mea
spec:
  mtls:
    mode: STRICT
```

```yaml
# deploy/k8s/overlays/minikube/kustomization.yaml (one of eight identical patches)
- target:
    kind: Deployment
    name: order-service
  patch: |-
    - op: replace
      path: /spec/template/spec/containers/0/imagePullPolicy
      value: Never
    - op: add
      path: /spec/template/metadata/labels/sidecar.istio.io~1inject
      value: "true"
```

```bash
# deploy/k8s/scripts/install-istio.sh (excerpt)
ISTIO_VERSION="${ISTIO_VERSION:-1.31.2}"
client="$(istioctl version --remote=false 2>/dev/null | awk '{print $NF}')"
[[ "${client%.*}" == "${ISTIO_VERSION%.*}" ]] \
  || fail "istioctl is ${client:-unknown}; this chapter pins ${ISTIO_VERSION}"
istioctl install -y --context "$PROFILE" -f deploy/k8s/istio/istio-install.yaml
```

## mTLS: STRICT inside, one PERMISSIVE edge

`deploy/k8s/istio/peer-authentication.yaml` is a namespace-wide
`PeerAuthentication` named `default` — the exact name Istio requires for a
namespace-scoped default policy to take effect — setting `mtls.mode:
STRICT` across all of `mea`. STRICT mode is enforced on the *receiving*
sidecar, not by the API server and not by anything the sending workload
does: every meshed pod's own `istio-proxy` container refuses an inbound
connection that didn't arrive wrapped in mTLS it originated with another
sidecar's certificate. Because enforcement lives entirely in the Envoy
proxies, `postgres` and `kafka` — no sidecar, no inject label — are
unaffected by this policy in either direction; they keep accepting
whatever they always accepted.

One workload in this topology has a legitimate reason to receive plaintext
from outside the mesh entirely: `strangler-proxy`, reached by the host
through the NodePort at `127.0.0.1:30888`. A client outside the cluster has
no sidecar of its own to originate mTLS with, so under a blanket STRICT
policy `strangler-proxy`'s own sidecar would reset every inbound request
that arrives through that NodePort — the edge would stop answering the
moment STRICT was applied. `deploy/k8s/istio/peer-authentication-edge.yaml`
is the fix, a second, workload-scoped `PeerAuthentication` matching only
`app.kubernetes.io/name: strangler-proxy` and setting `mtls.mode:
PERMISSIVE` on that one workload:

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: strangler-proxy-edge
  namespace: mea
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: strangler-proxy
  mtls:
    mode: PERMISSIVE
```

Istio resolves the most specific `PeerAuthentication` that applies to a
given workload, so `strangler-proxy`'s own sidecar accepts plaintext on its
*inbound* side while every service behind it stays on the namespace-wide
STRICT policy — `strangler-proxy`'s own outbound calls to
`review-`, `notification-`, `inventory-`, `payment-`, `shipping-`, and
`order-service` are still originated by its sidecar and still mTLS, the
same as every other hop in the mesh.

Confirming that split is enforced, rather than just configured, is a
single command against a running pod:

```bash
istioctl x describe pod -n mea <strangler-proxy-pod-name>
```

The expected output reports a workload mTLS mode of `STRICT` for most
pods in this namespace and `PERMISSIVE` for `strangler-proxy`'s inbound
side specifically — the one place `istioctl x describe pod`'s own output
distinguishes rendered policy from policy an Envoy sidecar is actually
enforcing against a live connection, which is the entire difference
between `kubectl kustomize`'s render and what the mesh does once a request
lands on a pod.

## The LGTM stack, in the cluster

`deploy/k8s/observability/` ports the same all-in-one `grafana/
otel-lgtm:0.36.0` image `compose.yaml`'s `lgtm` service has run since
ch.1 — Tempo, Loki, Mimir, Grafana, and an embedded OpenTelemetry
Collector, co-located in one container — into a single-replica Deployment,
reusing the image tag unchanged. `lgtm-service.yaml` exposes it two ways:
a ClusterIP Service at `lgtm.mea.svc.cluster.local` carrying every signal
port (`4317` OTLP/gRPC, `4318` OTLP/HTTP, `3000` Grafana, `9090`
Prometheus, `3100` Loki, `3200` Tempo) for in-cluster emitters, and a fixed
NodePort on `30300` for host access to the Grafana UI with no
port-forward. One detail in that Service's port naming is worth being
specific about, because it changes whether Istio's own trace export
works at all: the OTLP/gRPC port is named `grpc-otlp`, not the more
natural `otlp-grpc`. Istio's port-protocol auto-detection reads the
segment *before* the first hyphen in a Service port's name and checks it
against a small set of recognized tokens (`grpc`, `http`, `http2`, `tcp`,
`tls`); `otlp` isn't one of them, so a port named `otlp-grpc` gets treated
as opaque TCP, and the `otel` extensionProvider's own OTLP/gRPC export
calls would fail with no HTTP/2 framing underneath them. Putting `grpc`
first in the port name is what makes Istio's own trace export reach this
Service at all.

`deploy/k8s/observability/lgtm-deployment.yaml` gives this pod no
`sidecar.istio.io/inject` label — the LGTM backend stays unmeshed, for the
same reason `postgres` and `kafka` do. A meshed observability backend
would wrap its own OTLP ingest port in mTLS it originates with its own
sidecar, which would collide with two different plaintext OTLP clients
that need to reach it directly: Istio's own `otel` extensionProvider, and
the application-level OTel SDK running inside the three instrumented
services. Keeping the ingest path unmeshed keeps both of those working
without either one needing a sidecar-aware client configuration this
project has no reason to build.

The one addition to the Collector configuration itself,
`deploy/k8s/observability/otelcol-configmap.yaml`, is a second Prometheus
receiver, `prometheus/istio-mesh`, alongside the self-monitoring receiver
`compose.yaml`'s own config already carries. It uses Kubernetes
service discovery (`kubernetes_sd_configs: role: pod`, scoped to `mea`) to
find every pod running an `istio-proxy` container, relabels the scrape
target to that sidecar's stats port (`:15090/stats/prometheus`), and
pulls in `istio_requests_total`, request-duration histograms, and the rest
of Envoy's own metric surface for every meshed pod — the raw material
behind a service graph and per-route golden signals, for all eight
services, regardless of which three carry app-level instrumentation.
That scrape needs its own permission: `deploy/k8s/observability/rbac.yaml`
gives the `lgtm` ServiceAccount a `ClusterRole` that can list/watch pods,
endpoints, and services, bound through a namespace-scoped `RoleBinding`
rather than a `ClusterRoleBinding` — the Collector can discover scrape
targets inside `mea` and nowhere else.

## Mesh breadth, OTel depth

Istio's sidecars give this namespace trace spans and metrics for every
one of its eight services the moment the inject label lands on their
Deployments — no `pyproject.toml` change, no SDK import, no code in any
of those eight services aware the mesh exists. What that span tells a
reader is strictly about the hop: which pod talked to which pod, how
long the request spent between entering one sidecar and the response
leaving the other, and whether it was accepted (and, via
`peer-authentication*.yaml`, how it was authenticated). Nothing about an
Envoy span can say which SQL statement `order-service` ran against
Postgres while handling that request, whether its CQRS write to
`order_view` happened in the same transaction as the aggregate insert, or
which branch of `app/service.py` decided to call `inventory-service` at
all — none of that activity ever reaches the sidecar, because none of it
leaves the application process.

That's the property this chapter names explicitly: **the mesh gives
breadth, OpenTelemetry gives depth.** Breadth, because it costs nothing in
application code and covers every service uniformly. Depth, because it's
the only way to see what a service does with a request after Envoy hands
it off — and depth is exactly what gets lost if a chapter stopped at the
mesh and called the story finished. Resolving that trade-off, this chapter
instruments three services with application-level OpenTelemetry rather than
all eight: `strangler-proxy`,
`order-service`, and `inventory-service` — the three that sit on one
connected, synchronous request path, chosen over an alternative trio built
around the asynchronous Kafka saga hops specifically because that
alternative would need the HTTP request's trace context persisted into an
outbox row and restored by the relay before it could produce one real
trace instead of two disjoint ones. Choosing the synchronous trio side-
steps that gap entirely: `POST /api/orders` produces one connected trace
with no extra propagation work, verifiable from a single capture.

Each of those three services' `pyproject.toml` pins `opentelemetry-
distro==0.66b1` and `opentelemetry-exporter-otlp-proto-grpc==1.45.0`,
plus the exact set of `opentelemetry-instrumentation-*` packages
`uv run opentelemetry-bootstrap -a requirements` resolves for that
service's own dependency set — pinned directly in `pyproject.toml` rather
than left to `opentelemetry-bootstrap -a install` at build time, which
installs nothing into a pip-less `uv` virtualenv. Each Containerfile's
entrypoint is wrapped with `opentelemetry-instrument`: `strangler-proxy`'s
`ENTRYPOINT` becomes `opentelemetry-instrument uvicorn app.main:app ...`
directly, while `order-service` and `inventory-service` wrap the server
process only, after their own `alembic upgrade head` migration step —
`sh -c "alembic upgrade head && exec opentelemetry-instrument uvicorn
app.main:app ..."` — so the migration itself produces no span. That
wrapper is a true no-op everywhere outside this chapter: `.env.example`
ships `OTEL_SDK_DISABLED=true`, which makes `opentelemetry-instrument`
skip OTLP export entirely, so compose and every existing CI path run
unaffected. `deploy/k8s/base/app-config.yaml`'s `mea-app-config` ConfigMap
is the one place that flips to `OTEL_SDK_DISABLED: "false"`, alongside
`OTEL_EXPORTER_OTLP_ENDPOINT: "http://lgtm.mea.svc.cluster.local:4317"`
and `OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"` — active only in this cluster,
for the three Deployments whose own `env:` block additionally sets
`OTEL_SERVICE_NAME` (a value that has to differ per service, so it isn't
in the shared ConfigMap). The other five app services ignore all four keys
outright — their `Settings.from_env()` has no matching field — so nothing
about this instrumentation touches them.

One version-skew detail changes what the resulting DB spans actually show.
`opentelemetry-instrumentation-sqlalchemy==0.66b1`'s own dependency
metadata caps its support at `sqlalchemy<2.1.0`; `order-service` and
`inventory-service` both pin `sqlalchemy[asyncio]==2.1.4` (kept at that
version rather than pinned down to satisfy the instrumentor — this project
upgrades the tool, not the pin, when the two disagree). The instrumentor
loads, finds no SQLAlchemy version it recognizes, and declines to patch —
one `opentelemetry.instrumentation.dependencies` warning line at startup,
no error, no crash. `opentelemetry-instrumentation-asyncpg==0.66b1` carries
no such version cap and instruments the same two services' actual
database driver underneath SQLAlchemy's async engine, so the DB spans in
this chapter's hero trace come from `asyncpg`, not from the ORM layer:
each span names the raw SQL statement `asyncpg` executed, with none of
SQLAlchemy's own ORM-level attributes (mapped class name, relationship
loads) attached to it. The database work itself is fully visible as a
span; the span's own attributes describe the query `asyncpg` ran rather
than the ORM construct that produced it.

The four remaining services with a role in the system's saga —
`notification-`, `payment-`, and `shipping-service`, plus `graphql-
gateway` — stay mesh-only. Their request and response activity is visible
in Kiali's service graph and in Envoy's own spans the moment a request
touches them; what happens inside their own `app/` code during a Kafka
consume-and-react cycle is not. That's a choice carried over from this
book's Java sibling, which deferred Kafka saga-hop tracing in the same
way, not a limitation of Istio or OpenTelemetry — the same outbox-
propagation work described above would close it for a future iteration,
and this chapter names that rather than building it without comment.

## The hero trace

The trace this chapter is built to produce starts at the one entry point
this system has always had: `POST /api/orders` against `strangler-proxy`'s
NodePort. `strangler-proxy`'s own auto-instrumented Starlette server span
opens first, wrapped by Envoy's own ingress span on the same pod — the
PERMISSIVE edge from the mTLS section above is what lets that first hop
exist as plaintext at all. `strangler-proxy`'s `httpx` client call to
`order-service` crosses the mesh as a normal STRICT-mTLS hop, carrying the
OpenTelemetry `traceparent` header that both sidecars propagate
untouched; `order-service`'s own FastAPI server span picks it up, and
underneath it, auto-instrumented `asyncpg` spans record the order
aggregate's insert and the CQRS `order_view` write as two children of that
one server span — the first place in this trace where application depth
shows something the Envoy spans around it can't: two distinct writes
inside what the mesh sees as a single request/response pair. From there,
`order-service`'s `grpcio` client call to `inventory-service`'s `Reserve`
RPC crosses the ACL seam ch.19 built, as another STRICT-mTLS hop with its
own Envoy span wrapping an app-level grpc-client/grpc-server span pair,
closing in a final `asyncpg` span against `inventory-service`'s own
reservation row.

{% include excalidraw.html file="mesh-hero-trace-waterfall" alt="The hero trace as nested spans across three hops: Hop 1, client to strangler-proxy, an Envoy ingress span wrapping an app-level proxy_handler span; Hop 2, strangler-proxy to order-service, an Envoy span wrapping a FastAPI server span with two asyncpg child spans (the order aggregate insert and the order_view CQRS write) and an outbound grpc-client span; Hop 3, order-service to inventory-service over gRPC crossing the ACL seam, an Envoy span wrapping a grpc-server span with its own asyncpg child span reserving the inventory row. Grey boxes are mesh spans present for all 8 services; green boxes are app-level OTel spans present only on the 3 instrumented services." caption="Figure 30.2 — The hero trace: mesh spans (breadth) wrapping app spans (depth), three hops, one connected trace" %}

The figure above shows that nesting as it's built to appear, not as a
rendering of a captured run — the real trace ID, span count, and Tempo
screenshot come from the live capture this chapter's verification footer
points at, not from this diagram. What the shape does establish ahead of
that capture: a single `traceparent` should connect all three hops end to
end in Tempo's trace view, two Envoy spans should bracket the two
application hops, and the asyncpg children should appear nested inside
their parent FastAPI/grpc-server spans rather than as siblings — anything
else in the captured trace (a broken parent-child link, a second root
span, a gap where `order-service`'s outbound call should be) would be a
propagation bug, not a capture artifact.

Golden-signal metrics for this same path come from the `prometheus/
istio-mesh` scrape described above, queryable in Grafana against the
Mimir datasource once a request has driven at least one scrape cycle —
`istio_requests_total{destination_service=~"order-service.*"}` for request
volume and response-code breakdown, the matching `_duration_milliseconds`
histogram for latency, and the same two queries against
`inventory-service` and `strangler-proxy` for the other two hops in the
trace. None of that requires the request to have touched an OTel-
instrumented service at all — it's mesh breadth again, available for
`notification-`, `payment-`, and `shipping-service` exactly as it is for
the three services this chapter also gives app-level depth.

## When render-time checks aren't enough

Chapter 29 drew a careful line between what `kubectl kustomize` and
`kubeconform -strict` can confirm with no cluster at all — that every
manifest in this tree renders and parses against the Kubernetes OpenAPI
schema — and what only a live apiserver and a running kubelet can confirm:
whether a `PersistentVolumeClaim` actually binds, whether an `ImagePull
BackOff` shows up because an image was never loaded, whether a
`PodSecurity` admission rule accepts a `securityContext` block. This
chapter closes that gap for exactly the parts of the system a mesh and an
observability stack add, because none of the three can be answered from
a render.

`deploy/k8s/istio/peer-authentication.yaml` and `telemetry.yaml` render
and pass `kubeconform -ignore-missing-schemas` cleanly — they're
well-formed YAML against the fields Istio's own Go types define — but
`kubeconform` has no bundled schema for either CRD at all, so running it
without that flag reports both as validation errors for a missing schema,
not as confirmation that the policy is well-formed. Whether `STRICT`
mode is actually being enforced, rather than merely declared, is a fact
only a running `istio-proxy` sidecar can report, through `istioctl x
describe pod` against a pod that exists. Whether the `sidecar.istio.io/
inject` label actually triggers injection is a fact only the admission
webhook can produce, visible as a pod running `2/2` instead of `1/1` —
and only after that pod was created *following* `install-istio.sh`,
because the webhook acts on admission, not retroactively, against pods
that already existed. Whether a span actually reaches Tempo depends on
the `lgtm` Service's DNS resolving inside the cluster, the OTLP port
actually being reachable in plaintext from both the mesh and the
application SDK, and the Collector's own pipeline forwarding it to
Tempo's ingest port — none of which a render can observe, because none
of it exists until a request has actually flowed through a running
system.

That's the reason this chapter's own verification status, below, is tied
to a live run rather than to the render and `kubeconform` checks that
cover `deploy/k8s/istio/` and `deploy/k8s/observability/` headlessly in
CI. The render checks confirm the manifests are well-formed before
anyone applies them; the live run is what confirms the mesh, the mTLS
policy, and the trace pipeline this chapter describes actually produce
the behavior described, on a cluster where they've been asked to.

> **ADLC in Action** — Drafting this chapter from the Java sibling's own
> ch.30 alone would have produced a hero trace rooted at `graphql-gateway`,
> because that's where the Java system's synchronous fan-out lives. This
> project's `graphql-gateway` has no comparable role — it's a read-side
> front door added at ch.26, with no outbox, no saga fan-in, and no
> business reason to be one of the three OTel-instrumented services.
> Re-rooting the hero trace at `strangler-proxy` instead meant weighing
> two candidate trios — the synchronous `strangler-proxy`/`order-service`/
> `inventory-service` path chosen here, and an asynchronous
> `strangler-proxy`/`order-service`/`payment-service` alternative that
> would have needed `traceparent` persisted through `order-service`'s
> outbox and restored by its relay before the Kafka hop could join the
> same trace as the HTTP hop before it — and confirming, against
> `order-service`'s own `app/outbox.py`, that the HTTP request and the
> outbox publish are separate transactions today. Choosing the
> synchronous trio instead of reaching for the more distinctive Kafka
> story kept this chapter's single connected trace real without first
> building context-propagation plumbing this project's outbox was never
> designed to carry.
