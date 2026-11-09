---
title: "Appendix A: Deploying to OpenShift"
order: 33
part: "Appendices"
description: "The finished eight-workload system on OpenShift: a Helm chart, Routes, Security Context Constraints and the internal registry, built and verified live on OpenShift Local (CRC)."
duration: 40 minutes
---

## Learning objectives

By the end of this chapter you can:

- Name the five things that change when the finished system deploys to OpenShift: image delivery, packaging, ingress, pod identity and mesh injection.
- Deliver images with a host-side `podman build` and push to the integrated registry.
- Describe a data-driven Helm chart that renders eight Deployments from one template.
- Assign the right SCC posture (`restricted-v2`, `nonroot-v2`, `anyuid`) to each workload.
- Configure OSSM 3 with STRICT mTLS and a PERMISSIVE carve-out at each Route.
- State what a render-only CI gate proves and what only a live cluster can.

## Why this matters

OpenShift ships with opinions: a default `restricted-v2` admission policy that rejects a hard-coded user ID, Route-based ingress instead of a `NodePort`, an integrated container registry, and an operator lifecycle (OLM) for anything beyond the base platform. They are the price of a platform built to run workloads it didn't write, from teams it doesn't know, safely by default. This appendix packages the same eight workloads (the strangler proxy, six extracted bounded contexts and the GraphQL gateway) for it. `openshift/` is a fully additive tree: a Helm chart in `openshift/helm/mea/`, lifecycle scripts, and an opt-in platform tier for service mesh and tracing.

The application does not change. The same eight `ubi10/python-314-minimal` images, the same environment contract, the same `order.placed` Kafka hop between order-service and notification-service, and the same shared-schema dependency review-service has on the frozen monolith's seed data all carry over. OpenShift changes how the system is deployed, not what it is.

| | minikube | OpenShift |
|---|---|---|
| Images | `ubi10/python-314-minimal`, `USER 1001:0` | **identical**: no rebuild, no Containerfile edit |
| ConfigMap keys | `deploy/k8s/base/app-config.yaml` | **identical keys**: `openshift/helm/mea/templates/configmap-app.yaml` is a Helm port of the same contract |
| Service and Secret names | `mea-postgres-app`, per-service Services | **identical names** |
| Edge | `strangler-proxy` is the one REST edge | **identical semantics**, now behind a Route |
| OTel trace | strangler-proxy, inventory-service, order-service | **identical** three services, same `opentelemetry-instrument` wrapper |
| mTLS concept | STRICT mesh-wide, one PERMISSIVE carve-out | **identical concept**, re-expressed for OpenShift's mesh operator |
| Ingress | NodePort `30888` | **Route** (edge TLS, HTTP to HTTPS redirect) |
| Packaging | kustomize `base` + `overlays/minikube` | **Helm chart**, data-driven `services:` map |
| Image delivery | `minikube image load` | **podman build, then push to the integrated registry** |
| Mesh injection | `istioctl` `IstioOperator`, `sidecar.istio.io/inject` annotation | **Sail `Istio` CR**, `istio.io/rev` pod-template **label** |
| Pod identity | no SCC, pinned `runAsUser: 1001` | **three SCC postures**: `restricted-v2`, `nonroot-v2`, `anyuid` |
| Shared-schema seed | host port-forward + `manage.py migrate` | **in-cluster bootstrap Job**, idempotent |

## Building images without a daemon on the cluster

Quarkus has `quarkus-openshift`, which turns a `package` into an in-cluster binary S2I build. Python has no S2I builder for a `uv`-managed FastAPI service, so `openshift/build-and-push.sh` follows the pattern verified in `datamesh-reference-arch-python`'s `openshift/` tree: build with `podman` on the host, push to the cluster's integrated registry.

`openshift/install-infra.sh` does the one-time setup. It creates the `mea` project and, because the registry's external Route isn't exposed on a fresh CRC install, patches `configs.imageregistry.operator.openshift.io/cluster` to set `spec.defaultRoute`. `build-and-push.sh` then logs `podman` into that Route using `oc whoami -t` as a one-time password, never a stored credential, and builds all eight service images plus the frozen monolith image. The monolith is pushed though never deployed as a workload: `openshift/helm/mea/templates/bootstrap-job.yaml` runs it in-cluster to seed review-service's shared schema.

```bash
openshift/build-and-push.sh --mirror-infra   # 8 services + monolith + postgres/kafka
openshift/deploy.sh                          # helm upgrade --install
```

`--mirror-infra` exists because a CRC VM typically has no Docker Hub egress. It pulls `postgres:18.6-alpine` and `apache/kafka:4.3.1` from upstream and re-pushes them into the same registry namespace, so `values.yaml`'s `postgres.image` and `kafka.image` can point at `image-registry.openshift-image-registry.svc:5000/mea/postgres:18.6-alpine`. On a cluster with egress, drop the flag and point those two values at the upstream references.

{% include excalidraw.html file="openshift-image-delivery" alt="A host-side podman build and push pipeline on the left feeding, across the registry Route, ImageStream tags inside the mea project on the right; a mirror-infra branch pulls and re-pushes postgres and kafka images for a CRC VM with no outbound egress; the monolith image and an infra image pull both flow from the same ImageStream tags toward a bootstrap Job and the postgres/kafka StatefulSets respectively." caption="Figure 33.1: Image delivery: podman build and push on the host, pulled in-cluster from the integrated registry" %}

A Docker-strategy `BuildConfig` per service, fed a binary input, was rejected. For eight small FastAPI services with no compiled artifact step it buys nothing a host-side `podman build` doesn't, and it adds a second build surface (the object, its trigger, its log stream) to maintain.

## The Helm chart: one template, data-driven

`openshift/helm/mea/values.yaml` describes the eight services as data, the idiom `datamesh-reference-arch-python`'s chart uses, in place of `deploy/k8s/base`'s one file per service. Each entry carries its port, whether it reads `DATABASE_URL`, which Postgres schema it selects through `search_path`, whether it runs a Kafka consumer group, whether it is one of the two Route-facing edges, and its `resources` block, ported unrounded from the matching `deploy/k8s/base/<svc>.yaml`. `templates/app-deployment.yaml` ranges over the map once and produces all eight Deployments, each with its own probe shape: `tcpSocket` for `strangler-proxy` and `review-service`, which have no `/health` route, and `httpGet /health` for the other six.

{% include codetabs.html langs="openshift/helm/mea/values.yaml: services map (trimmed)|openshift/helm/mea/templates/route.yaml (trimmed)" %}

```yaml
services:
  strangler-proxy:
    port: 8888
    probe: tcp        # no /health route in this service's app code
    route: true        # the system's one REST edge
    otel: true
    resources:
      requests: { cpu: 50m, memory: 128Mi }
      limits:   { cpu: 250m, memory: 256Mi }
  order-service:
    port: 8088
    portEnv: "HTTP_PORT"
    probe: http
    db: true
    schema: "order_svc"
    kafka: true
    consumerGroup: "order-service"
    preStopSleep: 15   # widest fan-in: 4 inbound channels + the outbox relay
    gracePeriodSeconds: 60
```

```yaml
# OpenShift Route: the platform-native ingress, replacing NodePort 30888.
# OSSM 3 provisions no ingress gateway of its own: the Route IS the edge.
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {% raw %}{{ $name }}{% endraw %}
spec:
  to: { kind: Service, name: {% raw %}{{ $name }}{% endraw %}, weight: 100 }
  port: { targetPort: http }
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

`mesh.enabled` and `observability.otlp.enabled` are off by default, so a plain `helm upgrade --install` renders the core topology: eight Deployments, the Postgres and Kafka StatefulSets, the shared ConfigMap and Secret, and the two Routes. `openshift/platform/install-mesh.sh` and `install-observability.sh` flip each flag independently with `deploy.sh --set`. Because `deploy.sh` always runs with `--reset-then-reuse-values`, turning one on never clobbers the other.

The chart's one Job, `templates/bootstrap-job.yaml`, replaces the host-run `manage.py migrate` and `manage.py seed` against a port-forward in `deploy/k8s/scripts/deploy.sh`. It runs the frozen monolith's image in-cluster behind the same idempotency check, `SELECT to_regclass('public.reviews')`. If the relation exists the Job exits; if not, it migrates and seeds, leaving review-service's shared `public` schema (`reviews`, `customers`, `inventory_items`, `auth_user`) in place. It is a Helm `post-install,post-upgrade` hook with `before-hook-creation` and not `hook-succeeded`, so the completed Job stays visible to `deploy.sh`'s `oc wait --for=condition=complete` and to `capture-evidence.sh`.

## SCC: three postures, one reason each

`restricted-v2` assigns every pod a UID from a namespace-allocated range with group `0` and rejects a pod that asks for a specific UID. That collides with `runAsUser: 1001` on minikube only on paper: the UBI10 `python-314-minimal` images already run as `USER 1001:0`, which is what `restricted-v2` expects. The fix for the eight app Deployments is to drop `runAsUser`. `templates/app-deployment.yaml` sets `runAsNonRoot: true`, drops all capabilities and sets `seccompProfile: RuntimeDefault`, with no `runAsUser`.

| Workload | SCC | Reason |
|---|---|---|
| Eight app pods | `restricted-v2` | Images run as `1001:0`; any assigned UID works. |
| Postgres, Kafka | `nonroot-v2` | Upstream images hardcode UIDs (`70`, `1000`) that a random UID would break, along with data directory ownership. `templates/serviceaccount-infra.yaml` creates the `mea-infra` ServiceAccount and a `RoleBinding` to `system:openshift:scc:nonroot-v2`. |
| `otel-lgtm` | `anyuid` | Grafana's all-in-one image writes to `/data` as root. |

The `anyuid` grant is as narrow as the problem. `platform/observability/lgtm-serviceaccount.yaml` binds the `lgtm` ServiceAccount to `anyuid`, and the Deployment sets `runAsUser: 0` and nothing else. In particular it sets no `seccompProfile`: setting one flips admission back to `restricted-v2` and reintroduces the write failure. `install-infra.sh` creates that ServiceAccount up front, because it belongs to the platform's raw manifests and not to the Helm release, and pre-creating it avoids Helm refusing to adopt an object it didn't create.

## OSSM 3: STRICT mTLS, a PERMISSIVE carve-out, and the Route as the edge

`openshift/platform/install-mesh.sh` installs OpenShift Service Mesh 3 (the Sail operator) and pins the control plane to an exact release, `spec.version: v1.30.5`, never a floating tag.

A pod joins this mesh differently than on minikube. The Istio path there injects `istio-proxy` from a `sidecar.istio.io/inject` pod-template **annotation**. Sail's webhook is revisioned and ignores that annotation, so reusing it produces no sidecar and no error. `app-deployment.yaml` sets the pod-template **label** `istio.io/rev: default`, matching the `Istio` resource named `default` that `install-mesh.sh` applies.

{% include codetabs.html langs="openshift/platform/mesh/istio.yaml (trimmed)|openshift/helm/mea/templates/peerauthentication.yaml (trimmed)" %}

```yaml
apiVersion: sailoperator.io/v1
kind: Istio
metadata:
  name: default
spec:
  version: v1.30.5      # exact; never a floating vX.Y-latest
  namespace: istio-system
```

```yaml
# Namespace-wide STRICT, plus one PERMISSIVE override per Route-facing
# service, otherwise every Route request 502s against its own sidecar.
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
spec:
  mtls: { mode: STRICT }
---
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: {% raw %}{{ $name }}{% endraw %}-edge
spec:
  selector: { matchLabels: { app.kubernetes.io/name: {% raw %}{{ $name }}{% endraw %} } }
  mtls: { mode: PERMISSIVE }
```

The namespace-wide `default` PeerAuthentication sets `mtls.mode: STRICT`, so every meshed sidecar refuses a connection without another sidecar's mTLS on the far end. That is right for every hop between the eight services and wrong for the one hop that can't originate mTLS: the OpenShift router isn't a mesh member, and OSSM 3 provisions no ingress gateway on this cluster, so every Route request reaches `strangler-proxy` or `graphql-gateway` as plain traffic from outside the mesh. Under STRICT alone it is refused at the edge meant to receive it. A second, workload-scoped PeerAuthentication per Route-facing service (`strangler-proxy-edge`, `graphql-gateway-edge`) set to `PERMISSIVE` accepts both mTLS and plaintext on that workload's inbound side, while every hop behind it, including its own outbound calls to the other six services, stays STRICT.

{% include excalidraw.html file="openshift-mesh-mtls-edge" alt="The mea namespace with OSSM 3 active: every service pairs with an istio-proxy sidecar joined by the istio.io/rev label; a namespace-wide STRICT PeerAuthentication governs every sidecar-to-sidecar hop; strangler-proxy and graphql-gateway each carry a workload-scoped PERMISSIVE PeerAuthentication because Route traffic arrives from outside the mesh with no sidecar on the client side; postgres and kafka carry no istio.io/rev label and stay unmeshed; Kiali reads otel-lgtm's own bundled Prometheus instead of a cluster Prometheus, which CRC does not run." caption="Figure 33.2: STRICT mesh-wide, a PERMISSIVE carve-out at each Route, the Route itself as the one unmeshed edge" %}

Kiali needs a Prometheus to read mesh metrics from, and OpenShift Local runs no user-workload Prometheus. `install-observability.sh` finishes by patching the live `Kiali` resource so `external_services.prometheus.url` points at `otel-lgtm`'s bundled Prometheus (`http://lgtm.mea.svc.cluster.local:9090`). The same all-in-one image is the OTLP trace backend and Kiali's metrics source, so no second Prometheus is needed.

## A traced checkout, live

The "Scenario 1 - Happy-Path Checkout" payload in `tooling/newman/mea.postman_collection.json` drives through the Route here instead of the minikube NodePort: customer `1`, `SKU-WIDGET-001`, `CARD-VISA`, and a shipping address that doesn't match the `SHIP-FAIL` sentinel. `openshift/project-checks.sh`, sourced by `capture-evidence.sh`, POSTs it to `https://<strangler-proxy Route host>/api/orders` with `curl --cacert` against the cluster's ingress CA and not `--insecure`, then polls the order every two seconds until it reaches a terminal status (`CONFIRMED`, `PAYMENT_DECLINED` or `SHIPPING_FAILED`) or the script fails.

The request path is the same as on minikube. `strangler-proxy` forwards to `order-service` over plain HTTP inside the mesh, or over mTLS once `mesh.enabled` is on, and `order-service` publishes `order.placed` to the topic `notification-service` consumes. Only the destination of the trace changes. With `observability.otlp.enabled` on, the three `opentelemetry-instrument`-wrapped services export spans to `otel-lgtm` at `lgtm.mea.svc.cluster.local:4317`, an in-cluster Service DNS name built by the chart's `_helpers.tpl`.

## What CI validates, and what it can't

A GitHub Actions runner has no OpenShift cluster, so the `openshift-chart.yml` gate is scoped to what rendering can prove: `helm lint openshift/helm/mea`, then `helm template openshift/helm/mea --set mesh.enabled=true --set observability.otlp.enabled=true | kubeconform -strict -ignore-missing-schemas`. Every optional flag is on, so the render includes the Route, the PeerAuthentication pair and the bootstrap Job. `kubeconform` has no schema for a `Route`, an `Istio` resource or a `PeerAuthentication`, and `-ignore-missing-schemas` passes them through unchecked, as the manifest gate already does for Istio's CRDs on the minikube path.

The render proves every template parses as a valid Kubernetes object, every {% raw %}`{{ }}`{% endraw %} reference resolves, and the chart doesn't regress to invalid YAML. It can't prove that `restricted-v2` admits the eight app pods without a stray `runAsUser`, that a Route's edge TLS terminates and redirects, that the bootstrap Job's guard behaves against a real Postgres, or that a checkout through the Route produces the trace. Those are live-cluster facts.

> **ADLC in Action**: The plan started from an assumption of symmetry with the minikube mesh path: same Istio concepts, same PeerAuthentication shape, a different installer. Reading the real artifacts found three places the symmetry breaks and would have shipped broken. Sail's revisioned webhook ignores the `sidecar.istio.io/inject` annotation, which surfaces as "no sidecar, no error" and passes a render-only check. OSSM 3 installs no ingress gateway on this cluster, so the Route has to be the mesh's one legitimately plaintext edge. And `restricted-v2`'s UID-range rejection meant the fix was to remove `runAsUser`, not pick a new value, which the `datamesh-reference-arch-python` precedent and an OpenShift/CRC skill's accumulated gotchas both flagged. A chart drafted from the assumption alone, without reading `app-deployment.yaml`, `peerauthentication.yaml` and the Sail operator's CRD behavior, would render clean under `kubeconform` and still fail to admit a pod or carry a Route request past the mesh edge.

> **Decision**
>
> Use a Route, not a mesh ingress gateway, when OSSM provisions none (always, on OpenShift Local): treat the Route as the one plaintext edge with a scoped PERMISSIVE PeerAuthentication. Use a Helm chart over a kustomize overlay when several platform knobs (SCC posture, Route, mesh, observability) must toggle independently. Use host-side `podman build` and push over a `BuildConfig` when the runtime has no S2I builder and the images are small; keep `BuildConfig` for runtimes like Quarkus, where in-cluster building is the documented path.

## Build, run, observe

```bash
crc start; eval "$(crc oc-env)"
./openshift/install-infra.sh                   # project, registry Route, SCC binding
./openshift/build-and-push.sh --mirror-infra   # 8 services + monolith + postgres/kafka
./openshift/deploy.sh                          # helm upgrade --install + rollout + bootstrap Job
./openshift/platform/install-mesh.sh           # optional: OSSM 3, STRICT + PERMISSIVE
./openshift/platform/install-observability.sh  # optional: otel-lgtm, Kiali -> its Prometheus
./openshift/capture-evidence.sh                # writes openshift/evidence/<date>/
./openshift/teardown.sh                        # release, project, operators/CRDs, then crc stop
```

{% include excalidraw.html file="openshift-crc-topology" alt="The mea project on OpenShift Local: strangler-proxy and graphql-gateway each behind their own Route under restricted-v2, the other six services under restricted-v2 with no external exposure, postgres and kafka under the mea-infra ServiceAccount bound to nonroot-v2, and otel-lgtm under anyuid with only runAsUser 0 set." caption="Figure 33.3: The mea project on OpenShift Local: three SCC postures, two Routes as the only edge" %}

The recorded run in `openshift/evidence/2026-10-17/` shows the checkout through the `strangler-proxy` Route answering `202` with a `PENDING` order that reached `CONFIRMED` on the second poll, the `default` PeerAuthentication at STRICT with `strangler-proxy-edge` and `graphql-gateway-edge` at PERMISSIVE, plaintext from an unmeshed pod to review-service refused, and `otel-lgtm` running under `anyuid` as UID 0 with no seccomp profile.

- Put `sidecar.istio.io/inject` on a pod template instead of the `istio.io/rev` label: no sidecar is injected and nothing reports an error.
- Remove a `-edge` PeerAuthentication: Route requests to that service are refused by its own sidecar.
- Add a `seccompProfile` to the `otel-lgtm` Deployment: admission reverts to `restricted-v2` and the write to `/data` fails.
- Add `runAsUser` back to an app Deployment: `restricted-v2` rejects the pod.
