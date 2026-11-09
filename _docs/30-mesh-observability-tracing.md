---
title: "Mesh, Observability & Distributed Tracing"
order: 30
part: "Operating the Modernized System"
description: "An Istio mesh gives mTLS and a span per hop with no code change; OpenTelemetry on three services adds depth. Both feed a Grafana LGTM stack on minikube."
duration: 40 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain how a sidecar adds mTLS and telemetry with no application change, and why Istio's injection webhook matches a pod-template **label** (`sidecar.istio.io/inject`) and not an annotation.
- Set a namespace-wide `PeerAuthentication` to `STRICT`, add a workload-scoped `PERMISSIVE` exception for `strangler-proxy`'s plaintext NodePort edge, and verify enforcement with `istioctl x describe pod`.
- Say which bugs a render-time check can't catch and a live `kubectl apply -k` reveals.
- Explain why Envoy emits a span for every meshed hop whether or not the application is instrumented, and why the mesh can amplify a trace but never start one or carry business context.
- Instrument a FastAPI service by wrapping its entrypoint with `opentelemetry-instrument` and pinning the resolved packages, with no span-creation code in business logic.
- Read a connected trace across REST, gRPC and Envoy hops through `strangler-proxy`, `order-service` and `inventory-service`.
- Name what the setup does not cover: Loki log shipping and Kafka saga-hop tracing.

## Why this matters

On the cluster, `httpx` still calls `order-service` over plain HTTP and `grpcio` still dials `inventory-service` directly. Nothing between two pods is encrypted, carries a trace header or produces a request metric unless the service's own code does. An Istio mesh across the same eight Deployments changes that without touching application code: every pod-to-pod hop becomes mutual TLS, and a Grafana LGTM backend in the cluster receives two kinds of telemetry, Envoy's spans and metrics for every service and application-level OpenTelemetry spans from three of them. Both are additive on the `base` plus `overlays/minikube` split, with `../../istio` and `../../observability` composed in as sibling directories (`deploy/k8s/overlays/minikube/kustomization.yaml`).

## Why a mesh, and what it buys

A mesh puts a proxy (Envoy) beside every workload as a sidecar and moves cross-cutting concerns out of application code: encryption between services, transport-level retries and timeouts, per-hop metrics and a trace span for every request that crosses it. `order-service`'s gRPC client still dials `inventory-service:9004` unchanged; only the process that terminates each end of the connection differs. When a pod template carries the `sidecar.istio.io/inject` label, Istio's mutating webhook adds an `istio-proxy` container at creation, and every byte on a meshed port passes through it.

That buys three things. Transport security that doesn't depend on each service's own TLS setup: one `PeerAuthentication` covers a namespace. Telemetry that exists whether or not a service was written for observability. And leverage for canary weighting, fault injection and circuit breaking, which this setup doesn't use. What a mesh doesn't buy is insight into a service's own process: a Postgres query, a cache lookup or a branch in business logic never reaches the sidecar. That gap is why the setup doesn't stop at Istio.

## Bringing the mesh up on minikube

The bring-up extends the cluster scripts in place. `setup-profile.sh` still creates the `mea` profile (`--driver=docker --container-runtime=containerd`) and now also publishes NodePort `30300` for Grafana beside `30888` for `strangler-proxy`. A new script runs between profile creation and the image build:

```bash
deploy/k8s/scripts/setup-profile.sh
deploy/k8s/scripts/install-istio.sh      # new: istioctl install, pinned 1.31.2
deploy/k8s/scripts/build-images.sh
deploy/k8s/scripts/deploy.sh             # now also waits on the lgtm Deployment
```

`install-istio.sh` pins `istioctl` to `1.31.2`, because the client installs a control plane of its own version and a mismatched `istioctl` on `PATH` would silently stand up the wrong Istio. It checks the pin with `istioctl version --remote=false`, then runs `istioctl install -y --context mea -f deploy/k8s/istio/istio-install.yaml`. That file is an `IstioOperator`, reconciled by the operator controller instead of applied as a plain object, and its CRD is in no offline validator's schema set. So `deploy/k8s/istio/kustomization.yaml` bundles only the three namespace-scoped resources (`PeerAuthentication` twice, `Telemetry`), and `install-istio.sh` is the only consumer of `istio-install.yaml`.

The spec uses the `default` profile (`istiod` plus the ingress gateway), not `minimal` (no gateway) or `demo` (which bundles Prometheus, Jaeger and Grafana addons that would duplicate the LGTM stack). `meshConfig.extensionProviders` names an `otel` provider pointed at `lgtm.mea.svc.cluster.local:4317`, and a selector-less `Telemetry` resource (`deploy/k8s/istio/telemetry.yaml`) turns it on for every meshed workload at `randomSamplingPercentage: 100.00`. At mesh scale 100% sampling is a cost and cardinality problem; it is set so one capture is guaranteed to produce the trace below, and it shouldn't reach a production overlay.

`deploy.sh` checks for `istiod` in `istio-system` before `kubectl apply -k deploy/k8s/overlays/minikube` and fails with "run `install-istio.sh` first". The overlay's `PeerAuthentication` and `Telemetry` are Istio custom types, and Kubernetes rejects any object whose CRD it doesn't know yet.

{% include excalidraw.html file="mesh-mtls-topology" alt="The mea namespace with the mesh active: all 8 app Deployments carry the sidecar.istio.io/inject pod-template label and run an injected Envoy sidecar; PeerAuthentication STRICT makes every meshed-to-meshed hop mTLS, with one PERMISSIVE exception on strangler-proxy's plaintext NodePort inbound edge; postgres, kafka and the lgtm backend carry no inject label and stay unmeshed; the three OTel-instrumented services (strangler-proxy, order-service, inventory-service) export app-level OTLP spans to lgtm alongside the mesh-wide Envoy spans and the istio-proxy Prometheus scrape." caption="Figure 30.1: The meshed mea namespace: mTLS STRICT inside, one PERMISSIVE edge, two unmeshed backends" %}

## The opt-in gotcha: a label, not an annotation

Each of the eight app Deployments in `overlays/minikube/kustomization.yaml` already had a JSON-patch operation, `imagePullPolicy: Never`. A second operation adds the inject label:

```yaml
- op: add
  path: /spec/template/metadata/labels/sidecar.istio.io~1inject
  value: "true"
```

`~1` is RFC 6901's escape for a literal `/` in a JSON-pointer segment: the key is the single label `sidecar.istio.io/inject`, not a nested path. What matters more is that it is a pod-template **label**. The injection webhook decides with an `objectSelector`, which matches labels, not annotations and not a namespace marker like `istio-injection: enabled`. Set the key as an annotation and the selector never matches: the pod admits with no sidecar, no error and no event. The `mea` namespace stays unlabelled because injection is opt-in per Deployment, which lets `postgres` and `kafka` opt out.

Neither StatefulSet gets the patch. A sidecar's mTLS layer wrapped around Postgres's or Kafka's own connection conflicts with it instead of composing, so both stay unmeshed and their wire protocol is what it was before the mesh. The sidecar never sees that traffic.

{% include codetabs.html langs="deploy/k8s/istio/peer-authentication.yaml: namespace-wide STRICT|deploy/k8s/overlays/minikube/kustomization.yaml: the inject-label patch|deploy/k8s/scripts/install-istio.sh: the pinned istioctl install" %}

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
  || fail "istioctl is ${client:-unknown}; the project pins ${ISTIO_VERSION}"
istioctl install -y --context "$PROFILE" -f deploy/k8s/istio/istio-install.yaml
```

## mTLS: STRICT inside, one PERMISSIVE edge

The namespace-wide `PeerAuthentication` must be named `default` for Istio to treat it as the namespace default, and `mtls.mode: STRICT` covers all of `mea`. The receiving sidecar enforces it, not the API server and not the sender: each meshed pod's `istio-proxy` refuses an inbound connection that isn't wrapped in mTLS from another sidecar's certificate. `postgres` and `kafka` have no sidecar, so the policy doesn't touch them in either direction.

One workload legitimately receives plaintext from outside the mesh: `strangler-proxy`, reached from the host through the NodePort at `127.0.0.1:30888`. An outside client has no sidecar to originate mTLS, so under blanket STRICT the proxy's sidecar would reset every request through that NodePort. `deploy/k8s/istio/peer-authentication-edge.yaml` adds a workload-scoped policy that sets `PERMISSIVE` on that one workload:

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

Istio applies the most specific policy, so the proxy's sidecar accepts plaintext on its inbound side while its outbound calls to `review-`, `notification-`, `inventory-`, `payment-`, `shipping-` and `order-service` are still originated by the sidecar and still mTLS. Everything behind it stays on STRICT. To confirm enforcement, not just configuration, run it against a live pod:

```bash
istioctl x describe pod -n mea <strangler-proxy-pod-name>
```

It reports `STRICT` for most pods and `PERMISSIVE` for `strangler-proxy`'s inbound side. That is the difference between what `kubectl kustomize` renders and what the mesh enforces on a live connection.

## The LGTM stack in the cluster

`deploy/k8s/observability/` runs the same all-in-one `grafana/otel-lgtm:0.36.0` image as `compose.yaml`'s `lgtm` service (Tempo, Loki, Mimir, Grafana and an embedded OpenTelemetry Collector) as a single-replica Deployment. `lgtm-service.yaml` exposes it twice: a ClusterIP Service at `lgtm.mea.svc.cluster.local` carrying `4317` (OTLP/gRPC), `4318` (OTLP/HTTP), `3000` (Grafana), `9090` (Prometheus), `3100` (Loki) and `3200` (Tempo), and a fixed NodePort `30300` for the Grafana UI.

The OTLP/gRPC port is named `grpc-otlp`, not `otlp-grpc`, and that decides whether Istio's trace export works. Istio reads the segment before the first hyphen in a port name and matches it against `grpc`, `http`, `http2`, `tcp` and `tls`. `otlp` isn't one, so `otlp-grpc` is treated as opaque TCP and the `otel` provider's gRPC export fails with no HTTP/2 framing underneath.

The LGTM pod has no inject label. A meshed backend would wrap its OTLP ingest in sidecar mTLS, colliding with two plaintext clients: Istio's `otel` provider and the OTel SDK in the three instrumented services.

`deploy/k8s/observability/otelcol-configmap.yaml` adds a second Prometheus receiver, `prometheus/istio-mesh`, beside the self-monitoring one from `compose.yaml`. It uses `kubernetes_sd_configs` with `role: pod`, scoped to `mea`, to find every pod running `istio-proxy`, relabels each target to the sidecar's stats port (`:15090/stats/prometheus`) and pulls in `istio_requests_total`, request-duration histograms and the rest of Envoy's metrics for all eight services. `rbac.yaml` gives the `lgtm` ServiceAccount a `ClusterRole` to list and watch pods, endpoints and services, bound by a namespace-scoped `RoleBinding` instead of a `ClusterRoleBinding`, so discovery works inside `mea` and nowhere else.

## Mesh breadth, OpenTelemetry depth

The mesh gives trace spans and metrics for all eight services once the label lands, with no `pyproject.toml` change or SDK import. A span says which pod called which, how long the request spent between two sidecars and how it was authenticated. It can't say which SQL statement `order-service` ran, whether the `order_view` write shared a transaction with the aggregate insert, or which branch of `app/service.py` called `inventory-service`, because none of that leaves the process. **The mesh gives breadth, OpenTelemetry gives depth.**

So `strangler-proxy`, `order-service` and `inventory-service` get application-level OpenTelemetry. They sit on one synchronous request path. The alternative trio, built around the asynchronous Kafka saga hops, would need the HTTP request's trace context stored in an outbox row and restored by the relay to produce one trace instead of two disjoint ones. The synchronous trio avoids that: `POST /api/orders` yields one connected trace.

Each of the three pins `opentelemetry-distro==0.66b1` and `opentelemetry-exporter-otlp-proto-grpc==1.45.0` in `pyproject.toml`, plus the exact `opentelemetry-instrumentation-*` packages that `uv run opentelemetry-bootstrap -a requirements` resolves for that service. They are pinned directly because `opentelemetry-bootstrap -a install` installs nothing into a pip-less `uv` virtualenv. Each Containerfile wraps its entrypoint with `opentelemetry-instrument`. `strangler-proxy` runs `opentelemetry-instrument uvicorn app.main:app ...`. `order-service` and `inventory-service` wrap only the server, after migrations: `sh -c "alembic upgrade head && exec opentelemetry-instrument uvicorn app.main:app ..."`, so the migration emits no span.

The wrapper is a no-op elsewhere. `.env.example` ships `OTEL_SDK_DISABLED=true`, so Compose and CI skip OTLP export. Only `mea-app-config` in `deploy/k8s/base/app-config.yaml` flips to `OTEL_SDK_DISABLED: "false"`, with `OTEL_EXPORTER_OTLP_ENDPOINT: "http://lgtm.mea.svc.cluster.local:4317"` and `OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"`. The three Deployments also set `OTEL_SERVICE_NAME` in their own `env:`, since it differs per service. The other five services ignore all four keys: their `Settings.from_env()` has no matching field.

A version skew changes what the database spans show. `opentelemetry-instrumentation-sqlalchemy==0.66b1` caps support at `sqlalchemy<2.1.0`, and `order-service` and `inventory-service` pin `sqlalchemy[asyncio]==2.1.4`; the project upgrades the tool, not the pin, when the two disagree. The instrumentor finds no version it recognizes and declines to patch, with one `opentelemetry.instrumentation.dependencies` warning at startup. `opentelemetry-instrumentation-asyncpg==0.66b1` has no such cap and instruments the driver under SQLAlchemy's async engine. So the database spans in the trace come from `asyncpg` and name the raw SQL statement executed, without the ORM's mapped class or relationship attributes.

`notification-`, `payment-` and `shipping-service` and `graphql-gateway` stay mesh-only. Their requests show in Kiali's service graph and in Envoy spans, but what their code does during a Kafka consume-and-react cycle does not. Persisting `traceparent` through the outbox would close that gap and is not built.

## The hero trace

The trace starts at the system's one entry point, `POST /api/orders` against `strangler-proxy`'s NodePort. The proxy's Starlette server span opens first, wrapped by Envoy's ingress span on the same pod; the PERMISSIVE edge is what lets that first hop be plaintext. The proxy's `httpx` call to `order-service` crosses the mesh as a STRICT-mTLS hop carrying the `traceparent` header, which both sidecars pass through untouched. `order-service`'s FastAPI server span picks it up, with two `asyncpg` children, the order aggregate insert and the CQRS `order_view` write: application depth showing two writes inside what the mesh sees as one request and response. Its `grpcio` call to `inventory-service`'s `Reserve` RPC crosses the anti-corruption seam as another STRICT hop, an Envoy span around a grpc-client and grpc-server pair, ending in an `asyncpg` span on `inventory-service`'s reservation row.

{% include excalidraw.html file="mesh-hero-trace-waterfall" alt="The trace as nested spans across three hops. Hop 1, client to strangler-proxy: an Envoy ingress span wrapping an app-level proxy_handler span. Hop 2, strangler-proxy to order-service: an Envoy span wrapping a FastAPI server span with two asyncpg child spans (the order aggregate insert and the order_view CQRS write) and an outbound grpc-client span. Hop 3, order-service to inventory-service over gRPC: an Envoy span wrapping a grpc-server span with its own asyncpg child span reserving the inventory row. Grey boxes are mesh spans present for all 8 services; green boxes are app-level OTel spans present only on the 3 instrumented services." caption="Figure 30.2: The expected trace: mesh spans (breadth) wrapping app spans (depth), three hops, one connected trace" %}

The figure shows the expected nesting, not a captured run. In Tempo, one `traceparent` should connect all three hops, two Envoy spans should bracket the two application hops, and the `asyncpg` spans should nest inside their FastAPI or grpc-server parents. A broken parent link, a second root span or a gap where `order-service`'s outbound call belongs is a propagation bug.

Golden-signal metrics for the same path come from the `prometheus/istio-mesh` scrape, queryable in Grafana on the Mimir datasource after one scrape cycle: `istio_requests_total{destination_service=~"order-service.*"}` for volume and response codes, the matching `_duration_milliseconds` histogram for latency, and the same for `inventory-service` and `strangler-proxy`. None of it needs an OTel-instrumented service, so it works for `notification-`, `payment-` and `shipping-service` too.

## When render-time checks aren't enough

`kubectl kustomize` and `kubeconform -strict` confirm that manifests render and parse against the Kubernetes OpenAPI schema. They can't confirm whether a volume binds, an image was loaded or `PodSecurity` accepts a `securityContext`. The mesh and observability additions add more that a render can't answer:

- **The CRDs have no schema.** `peer-authentication.yaml` and `telemetry.yaml` pass `kubeconform -ignore-missing-schemas`, which only means they match Istio's field names. Without the flag, `kubeconform` reports both as missing-schema errors, not as confirmation.
- **STRICT is declared, not enforced.** Only a running sidecar reports its mode, through `istioctl x describe pod`.
- **Injection happens at admission.** A pod shows `2/2` instead of `1/1` only if it was created after `install-istio.sh`; the webhook doesn't act on existing pods.
- **Spans reaching Tempo.** That needs `lgtm` DNS resolving in the cluster, the OTLP port reachable in plaintext from both the mesh and the SDK, and the Collector forwarding to Tempo, none of which exists until a request flows through a running system.

The render checks run headlessly in CI over `deploy/k8s/istio/` and `deploy/k8s/observability/`. Whether the mesh, the mTLS policy and the trace pipeline behave as described takes a live run.

> **ADLC in Action**
>
> Drafting from an assumed topology would have rooted the trace at `graphql-gateway`, the natural root when synchronous fan-out lives there. This gateway is a read-side front door with no outbox, no saga fan-in and no reason to be instrumented. Re-rooting at `strangler-proxy` meant weighing two trios: the synchronous `strangler-proxy`, `order-service`, `inventory-service` path used here, and an asynchronous `strangler-proxy`, `order-service`, `payment-service` path that would need `traceparent` persisted through the outbox and restored by the relay. Reading `order-service`'s `app/outbox.py` confirmed the HTTP request and the outbox publish are separate transactions today. The synchronous trio kept the trace real without building propagation the outbox was never designed to carry.

> **Decision**
>
> Mesh every service for breadth, since it costs no code. Add OpenTelemetry only where you need to see inside the process, and choose the instrumented path by whether trace context can flow along it without new plumbing. Keep stateful backends and the telemetry backend out of the mesh, and verify enforcement on a live pod, not in the YAML.

> **🤖 Explore with your agent**
>
> "In deploy/k8s, confirm every app Deployment in overlays/minikube carries the sidecar.istio.io/inject label patch and check the PeerAuthentication rule: STRICT in mea, PERMISSIVE only for strangler-proxy's NodePort edge, postgres, kafka and lgtm unmeshed. Then report which of the eight services have OpenTelemetry instrumentation in their Containerfile and which are mesh-only."
>
> Check: after the deploy, `kubectl -n mea get pods` shows `2/2` for the eight app pods and `1/1` for postgres, kafka and lgtm, and `istioctl x describe pod -n mea <strangler-proxy-pod>` reports PERMISSIVE on its inbound side.

## Build, run, observe

With the `mea` profile from the cluster scripts, run the sequence above (`setup-profile.sh`, `install-istio.sh`, `build-images.sh`, `deploy.sh`). Grafana is at `127.0.0.1:30300` and the strangler edge at `127.0.0.1:30888`. Send `POST /api/orders` through the edge, then open the trace in Tempo through Grafana and the request metrics on the Mimir datasource. `deploy/k8s/scripts/capture-ch30-evidence.sh` drives a few checkouts against the live mesh and writes the trace, the `istioctl` mTLS description and the `istio_requests_total` query to `deploy/k8s/observability/evidence/`; a step that finds nothing writes a `*.MISSING.txt` and the script exits non-zero.

- **Set the inject key as an annotation instead of a label:** the pod admits with no sidecar, no error and no event.
- **Create an app pod before running `install-istio.sh`:** it stays `1/1` with no sidecar.
- **Remove the `PERMISSIVE` edge policy:** `strangler-proxy`'s sidecar resets plaintext requests arriving through the NodePort.
- **Rename the OTLP port `otlp-grpc`:** Istio treats it as opaque TCP and the mesh's trace export fails.
