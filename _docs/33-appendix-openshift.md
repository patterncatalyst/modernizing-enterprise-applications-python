---
title: "Appendix A: Deploying to OpenShift"
order: 33
part: "Appendices"
description: "The finished eight-workload system on OpenShift: a Helm chart, Routes, Security Context Constraints, and the internal registry — built and verified live on OpenShift Local (CRC)."
duration: 40 minutes
---

Every chapter before this one ran this system on something you control from
top to bottom — a `compose.yaml` with every port and volume spelled out, or
the `minikube` cluster ch.29/30 built, where you install exactly the
Kubernetes primitives a chapter asks for and nothing else. OpenShift is a
different kind of target: it ships with its own opinions already baked in —
a default `restricted-v2` admission policy that rejects a hard-coded user
ID, a Route-based ingress layer instead of a raw `NodePort`, an integrated
container registry sitting inside the cluster, and an operator lifecycle
(OLM) governing anything you add beyond the base platform. None of those
opinions are wrong; they're the price of a platform designed to run
workloads it didn't build, from teams it doesn't know, safely by default.
This appendix packages the same eight-workload system — the strangler
proxy, the six extracted bounded contexts, the GraphQL gateway — for that
platform, and `openshift/` is the new, fully additive tree that does it:
a Helm chart in `openshift/helm/mea/`, a handful of lifecycle scripts, and
an opt-in platform tier for service mesh and tracing.

What doesn't change is the point worth sitting with first. The same eight
`ubi10/python-314-minimal` images, the same shared environment contract,
the same `order.placed` Kafka hop between order-service and
notification-service, the same shared-schema dependency review-service has
on the frozen monolith's seed data — none of that is specific to minikube,
and none of it gets rebuilt for OpenShift. `openshift/README.md` states
this directly: everything about the application is identical; OpenShift
changes five things about how it is *deployed*. This chapter walks through
each of those five changes, in the same order the README names them, with
the reasoning the build plan's DRQ-104 through DRQ-111 range captured
behind each one, and closes with the live-cluster claims a headless CI
gate cannot make on its own.

## What stays identical, and what changes

| | minikube (ch.29/30) | OpenShift (this appendix) |
|---|---|---|
| Images | `ubi10/python-314-minimal`, `USER 1001:0` | **identical** — no rebuild, no Containerfile edit |
| ConfigMap keys | `deploy/k8s/base/app-config.yaml` | **identical keys** — `openshift/helm/mea/templates/configmap-app.yaml` is a Helm port of the same contract |
| Service/Secret names | `mea-postgres-app`, per-service Services | **identical names** |
| Edge | `strangler-proxy` is the one REST edge | **identical semantics** — still the one REST edge, now behind a Route |
| OTel trace | strangler-proxy / inventory-service / order-service instrumented | **identical** three services, same `opentelemetry-instrument` wrapper |
| mTLS concept | STRICT mesh-wide, one PERMISSIVE carve-out | **identical concept**, re-expressed for OpenShift's own mesh operator |
| Ingress | NodePort `30888` | **Route** (edge TLS, HTTP→HTTPS redirect) — DRQ-106 |
| Packaging | kustomize `base` + `overlays/minikube` | **Helm chart**, data-driven `services:` map — DRQ-105 |
| Image delivery | `minikube image load` | **podman build → integrated registry push** — DRQ-108 |
| Mesh injection | `istioctl` `IstioOperator`, `sidecar.istio.io/inject` annotation | **Sail `Istio` CR**, `istio.io/rev` pod-template **label** — DRQ-109 |
| Pod identity | no SCC, pinned `runAsUser: 1001` | **three SCC postures**: `restricted-v2` / `nonroot-v2` / `anyuid` — DRQ-107 |
| Shared-schema seed | host port-forward + `manage.py migrate` | **in-cluster bootstrap Job**, idempotent — DRQ-111 |

## Building images for a cluster you don't run a daemon against

Quarkus has `quarkus-openshift`, a Maven profile that turns a `package` into
an in-cluster binary S2I build with no `docker`/`podman` on the host at
all. Python has nothing equivalent — there's no S2I builder image for a
`uv`-managed FastAPI service the way there is for a JAR — so
`openshift/build-and-push.sh` takes the house pattern this project's
own ecosystem already verified on `datamesh-reference-arch-python`'s
`openshift/` counterpart: build with `podman` on the host, push to the
cluster's own integrated registry.

`openshift/install-infra.sh` does the one-time setup that step depends on —
creating the `mea` project and, because the registry's external Route
isn't exposed by default on a fresh CRC install, patching
`configs.imageregistry.operator.openshift.io/cluster` to turn
`spec.defaultRoute` on. Once that Route exists, `build-and-push.sh` logs
`podman` into it using `oc whoami -t` as a one-time password — never a
stored credential — and builds all eight service images plus the frozen
monolith image, which is pushed too even though it is never deployed as
its own workload: `openshift/helm/mea/templates/bootstrap-job.yaml` runs it
in-cluster to seed review-service's shared schema, which the next section
covers.

```bash
openshift/build-and-push.sh --mirror-infra   # 8 services + monolith + postgres/kafka
openshift/deploy.sh                          # helm upgrade --install
```

`--mirror-infra` exists because a CRC VM typically has no Docker Hub
egress: the flag pulls `postgres:18.6-alpine` and `apache/kafka:4.3.1` from
upstream and re-pushes them into the same registry namespace the eight
service images landed in, so `values.yaml`'s `postgres.image` and
`kafka.image` can point at `image-registry.openshift-image-registry.svc:
5000/mea/postgres:18.6-alpine` instead of the public registry. On a
cluster that does have egress, the flag is unnecessary — drop it and point
those two values fields at the upstream references directly.

{% include excalidraw.html file="openshift-image-delivery" alt="A host-side podman build and push pipeline on the left feeding, across the registry Route, ImageStream tags inside the mea project on the right; a mirror-infra branch pulls and re-pushes postgres and kafka images for a CRC VM with no outbound egress; the monolith image and an infra image pull both flow from the same ImageStream tags toward a bootstrap Job and the postgres/kafka StatefulSets respectively." caption="Figure 33.1 — Image delivery: podman build and push on the host, pulled in-cluster from the integrated registry" %}

The rejected alternative — a Docker-strategy `BuildConfig` per service,
triggered from a binary input the way the Quarkus sibling's S2I build
works — is recorded rather than silently dropped, because it's the
question anyone porting a Java `openshift/` tree to a Python one will ask
first. For eight small FastAPI services with no compiled artifact step,
an in-cluster `BuildConfig` buys nothing a host-side `podman build` doesn't
already have, and it adds a second build surface (the `BuildConfig`
object, its trigger, its own log stream) to maintain for no benefit. It's
named in `openshift/README.md`'s "what changes" list only as the path not
taken.

## The Helm chart: one template, data-driven

`openshift/helm/mea/values.yaml` describes the eight services as data, not
as eight hand-written manifests — the same idiom
`datamesh-reference-arch-python`'s own chart uses, and a real departure
from `deploy/k8s/base`'s one-file-per-service layout. Each entry carries
exactly the fields that service actually needs: its port, whether it reads
`DATABASE_URL`, which Postgres schema it selects via `search_path`,
whether it runs a Kafka consumer group, whether it's one of the two
Route-facing edges, and its exact `resources` block, ported without any
size-tier rounding from the matching `deploy/k8s/base/<svc>.yaml`.
`templates/app-deployment.yaml` ranges over that map once, producing all
eight Deployments and inheriting each service's own probe shape along the
way — `tcpSocket` for `strangler-proxy` and `review-service`, which have no
`/health` route in their own application code, `httpGet /health` for the
other six.

{% include codetabs.html langs="openshift/helm/mea/values.yaml — services map (trimmed)|openshift/helm/mea/templates/route.yaml (trimmed)" %}

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
# OpenShift Route — the platform-native ingress, replacing NodePort 30888.
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

Two flags in `values.yaml` — `mesh.enabled` and
`observability.otlp.enabled` — are both off by default, so a plain `helm
upgrade --install` renders only the live-core topology: eight app
Deployments, the two Postgres/Kafka StatefulSets, the shared ConfigMap and
Secret, and the two Routes. `openshift/platform/install-mesh.sh` and
`install-observability.sh` flip each flag independently with their own
`deploy.sh --set`, and because `deploy.sh` always runs with
`--reset-then-reuse-values`, turning one flag on never clobbers the other.

The chart's one Job — `templates/bootstrap-job.yaml` — replaces
`deploy/k8s/scripts/deploy.sh`'s host-run `manage.py migrate`/`manage.py
seed` against a port-forward with an in-cluster run of the frozen
monolith's own image, guarded by the identical idempotency check: `SELECT
to_regclass('public.reviews')`. If that relation already exists, the Job
exits immediately; if it doesn't, it runs the real migrate-then-seed and
leaves review-service's shared `public` schema (`reviews`, `customers`,
`inventory_items`, `auth_user`) in place for every later `helm upgrade` to
find already seeded. The Job is wired as a Helm `post-install,post-upgrade`
hook with `before-hook-creation` — not `hook-succeeded` — specifically so
the completed Job stays visible to `deploy.sh`'s own
`oc wait --for=condition=complete` check and to `capture-evidence.sh`
afterward, rather than being deleted the moment it succeeds.

## SCC: three postures, one reason each

OpenShift's default `restricted-v2` Security Context Constraint assigns
every pod a UID from a namespace-allocated range and group `0`, and it
rejects a pod that asks for a specific UID outright. That collides head-on
with `deploy/k8s/base`'s `runAsUser: 1001` — but only on paper, because the
UBI10 `python-314-minimal` images were already built to run as `USER
1001:0`, an arbitrary assigned UID with group `0`. That's exactly what
`restricted-v2` expects by default, so the fix for the eight app
Deployments is to drop `runAsUser` entirely rather than add anything:
`openshift/helm/mea/templates/app-deployment.yaml` sets
`runAsNonRoot: true`, drops all capabilities, and sets
`seccompProfile: RuntimeDefault`, with no `runAsUser` key at all.

Postgres and Kafka are the opposite case: their upstream images hardcode
non-root UIDs (`70` and `1000`) that `restricted-v2`'s random-UID
assignment would silently overwrite, breaking the data directory ownership
both images assume on startup. `templates/serviceaccount-infra.yaml`
creates a dedicated ServiceAccount, `mea-infra`, and a `RoleBinding` to the
cluster role OpenShift auto-generates for the `nonroot-v2` SCC
(`system:openshift:scc:nonroot-v2`) — letting exactly those two
StatefulSets keep the UID their own images need, without loosening
anything for the eight app pods that don't need it.

The third posture belongs to `otel-lgtm`, the platform tier's tracing
backend, and it's the one place this chart reaches for `anyuid`. Grafana's
own all-in-one image writes to `/data` as root, and the fix here is as
narrow as the problem: `platform/observability/lgtm-serviceaccount.yaml`
binds the `lgtm` ServiceAccount to `anyuid`, and the Deployment sets
`runAsUser: 0` and nothing else — specifically no `seccompProfile`.
Setting one flips admission back to `restricted-v2` for that pod, which
reintroduces the exact write failure the `anyuid` grant exists to avoid.
`install-infra.sh` provisions that ServiceAccount up front, before the
platform tier is ever installed, because — unlike `mea-infra` — it belongs
to the platform's raw manifests rather than to the Helm release, and
pre-creating it there avoids Helm later refusing to adopt an object it
didn't create itself.

## OSSM 3: STRICT mTLS, a PERMISSIVE carve-out, and the Route as the edge

`openshift/platform/install-mesh.sh` installs OpenShift Service Mesh 3 —
the Sail operator — and pins the control plane to an exact release,
`spec.version: v1.30.5`, never a floating tag. The first thing worth
correcting here, because it's the mistake a reader coming from the
minikube chapter would make without checking, is how a pod actually joins
the mesh. ch.30's Istio path injects `istio-proxy` by watching a
`sidecar.istio.io/inject` pod-template **annotation**. Sail's webhook is
revisioned, and it ignores that annotation entirely — reusing it here
would produce no sidecar at all, with no error to point at the cause.
`app-deployment.yaml` instead sets the pod-template **label**
`istio.io/rev: default`, which matches the `Istio` custom resource named
`default` that `install-mesh.sh` applies.

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
# service — otherwise every Route request 502s against its own sidecar.
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

`peerauthentication.yaml`'s namespace-wide `default` resource sets
`mtls.mode: STRICT`, which means every meshed sidecar refuses a connection
that doesn't arrive with another sidecar's own mTLS on the other end.
That's correct for every hop between the eight services — and wrong for
the one hop that can't originate mTLS at all: the OpenShift router isn't a
mesh member, and OSSM 3 provisions no ingress gateway of its own on this
cluster, so every Route request arrives at `strangler-proxy` or
`graphql-gateway` as plain traffic from outside the mesh. Under a
namespace-wide STRICT policy alone, that traffic would be refused at the
very edge meant to receive it. The fix is a second, workload-scoped
`PeerAuthentication` per Route-facing service — `strangler-proxy-edge`,
`graphql-gateway-edge` — set to `PERMISSIVE`, which accepts both mTLS and
plaintext on that one workload's inbound side while every hop *behind* it,
including that same workload's own outbound calls to the other six
services, stays fully STRICT.

{% include excalidraw.html file="openshift-mesh-mtls-edge" alt="The mea namespace with OSSM 3 active: every service pairs with an istio-proxy sidecar joined by the istio.io/rev label; a namespace-wide STRICT PeerAuthentication governs every sidecar-to-sidecar hop; strangler-proxy and graphql-gateway each carry a workload-scoped PERMISSIVE PeerAuthentication because Route traffic arrives from outside the mesh with no sidecar on the client side; postgres and kafka carry no istio.io/rev label and stay unmeshed; Kiali reads otel-lgtm's own bundled Prometheus instead of a cluster Prometheus, which CRC does not run." caption="Figure 33.3 — STRICT mesh-wide, a PERMISSIVE carve-out at each Route, the Route itself as the one unmeshed edge" %}

Kiali needs its own Prometheus to read mesh metrics from, and OpenShift
Local runs no user-workload Prometheus of its own. `install-observability.
sh`'s last step patches the live `Kiali` custom resource to point
`external_services.prometheus.url` at `otel-lgtm`'s bundled Prometheus —
`http://lgtm.mea.svc.cluster.local:9090` — the same all-in-one image ch.30
already uses on minikube, here doubling as both the OTLP trace backend and
Kiali's metrics source, rather than standing up a second Prometheus just
for mesh observability.

## A traced checkout, live

The same payload `tooling/newman/mea.postman_collection.json`'s "Scenario
1 — Happy-Path Checkout" drives through minikube's NodePort drives through
the Route here instead: customer `1`, `SKU-WIDGET-001`, `CARD-VISA`, a
shipping address that doesn't match the `SHIP-FAIL` sentinel.
`openshift/project-checks.sh` — sourced by `capture-evidence.sh`, not run
standalone — `POST`s that payload to `https://<strangler-proxy
Route host>/api/orders` with `curl --cacert`, against the cluster's own
ingress CA rather than `--insecure`, and polls the resulting order every
two seconds until it reaches its terminal `CONFIRMED` status or the script
fails outright.

Nothing about that request path changes shape between minikube and
OpenShift: `strangler-proxy` still forwards to `order-service` over plain
HTTP inside the mesh (or over mTLS, once `mesh.enabled`), `order-service`
still publishes `order.placed` to the same Kafka topic
`notification-service` consumes, and the terminal state check is the same
`CONFIRMED`/`PAYMENT_DECLINED`/`SHIPPING_FAILED` state machine ch.23's
saga built. What's new to this environment is only *where* the trace that
request produces ends up: when `observability.otlp.enabled` is on, the
same three `opentelemetry-instrument`-wrapped services — `strangler-proxy`,
`inventory-service`, `order-service` — export their spans to
`otel-lgtm` over `lgtm.mea.svc.cluster.local:4317`, identical wiring to
ch.30's minikube backend, just reached over the in-cluster Service DNS
this chart's `_helpers.tpl` builds rather than a `NodePort`.

## What CI validates, and what it can't

A GitHub Actions runner has no OpenShift cluster behind it, so the gate
this appendix adds is scoped narrowly to what rendering alone can
prove: `helm lint openshift/helm/mea`, followed by
`helm template openshift/helm/mea --set mesh.enabled=true --set
observability.otlp.enabled=true | kubeconform -strict
-ignore-missing-schemas`, with every optional flag turned on so the render
includes the Route, the `PeerAuthentication` pair, and the bootstrap Job
along with the always-on Deployments and Services. `kubeconform` has no
schema for a `Route`, an `Istio` custom resource, or a `PeerAuthentication`
— `-ignore-missing-schemas` lets those pass through unchecked rather than
failing the whole pipe on a CRD no offline validator ships with, the same
accommodation ch.29's `deploy-manifests.yml` already makes for Istio's own
CRDs on the minikube path.

What that render can prove: every template parses as a syntactically valid
Kubernetes object, every {% raw %}`{{ }}`{% endraw %} reference resolves, and the chart doesn't
regress into producing invalid YAML the next time someone edits
`values.yaml`. What it cannot prove is any claim this chapter makes about
a *running* cluster — that `restricted-v2` actually admits the eight app
pods without a stray `runAsUser` creeping back in, that a Route's edge TLS
actually terminates and redirects, that the bootstrap Job's idempotency
guard behaves correctly against a real Postgres, or that a checkout
through the Route produces the trace this chapter describes. Those are
live-cluster facts, and the verification note at the end of this appendix
names exactly which of them a real run has, and hasn't yet, confirmed.

> **ADLC in Action** — The build plan behind this appendix started from a
> working assumption of symmetry with ch.30's minikube mesh path: same
> Istio concepts, same `PeerAuthentication` shape, just a different
> installer. Reading the real artifacts instead of trusting that
> assumption turned up three places where the symmetry breaks in a way
> that would have shipped broken: Sail's revisioned webhook ignores the
> `sidecar.istio.io/inject` annotation the minikube path relies on
> entirely, which only surfaces as "no sidecar, no error" rather than a
> failure anyone would notice in a render-only check; OSSM 3 installs no
> ingress gateway of its own on this cluster, which means the Route itself
> has to be treated as the mesh's one legitimately-plaintext edge rather
> than assuming a gateway resource would exist to carry that traffic in;
> and `restricted-v2`'s UID-range rejection meant the correct fix for the
> eight app Deployments was to *remove* `runAsUser` rather than pick a new
> value, something `datamesh-reference-arch-python`'s own `openshift/`
> precedent and the `lgtm-crc` skill's accumulated gotchas both called out
> directly. An agent drafting this chapter from the plan's working
> assumption alone, without reading `app-deployment.yaml`,
> `peerauthentication.yaml`, and the Sail operator's own CRD behavior
> first, would have produced a chart that renders clean under
> `kubeconform` and still fails to admit a single pod, or to carry a
> single Route request past the mesh's own edge.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Reach for a <strong>Route</strong>, not a mesh ingress gateway, whenever OSSM provisions none on the target cluster — on OpenShift Local that's always, and treating the Route as the one legitimately-plaintext edge (with a scoped PERMISSIVE <code>PeerAuthentication</code>) is simpler than standing up a gateway resource the platform doesn't give you. Reach for a <strong>Helm chart</strong> over an OpenShift kustomize overlay when more than one platform-specific knob (SCC posture, Route, mesh, observability) needs to toggle independently without forking the manifest tree — <code>values.yaml</code>'s data-driven <code>services:</code> map is what let this chart stay one template for eight workloads instead of eight hand-edited copies. Reach for <strong>host-side <code>podman build</code> and push</strong> over an in-cluster <code>BuildConfig</code> when the runtime has no S2I builder image and the images are small enough that a host build costs nothing extra — reserve a <code>BuildConfig</code> for a runtime (Quarkus's own S2I path is the example two chapters over) where building inside the cluster is the supported, documented path rather than a workaround.</p></div>

## What you learned

- **OpenShift's opinions are about *how* a system deploys, not what it
  is** — the same eight images, ConfigMap keys, Service names, and
  three-service OTel trace carry over unchanged; Routes, Helm, the
  integrated registry, Sail's label-based injection, and three SCC
  postures are the only things this chapter actually changes.
- **A UBI image built for Kubernetes is usually already right for
  `restricted-v2`** — `USER 1001:0` satisfies the SCC's arbitrary-UID,
  group-0 expectation with no edit; the fix for the eight app Deployments
  was removing `runAsUser`, not choosing a new one.
- **Sail injects by a pod-template label, not the classic inject
  annotation** — reusing ch.30's `sidecar.istio.io/inject` pattern here
  would silently produce zero sidecars; `istio.io/rev: default` is the
  real mechanism.
- **OSSM 3 on OpenShift ships no ingress gateway** — the Route is the
  mesh's one legitimately-plaintext edge, and a workload-scoped
  `PeerAuthentication` set to `PERMISSIVE` is what keeps a namespace-wide
  `STRICT` policy from 502-ing every Route request.
- **A render-only CI gate proves syntax, not cluster behavior** —
  `helm template | kubeconform -strict -ignore-missing-schemas` catches a
  broken chart before it ever reaches a cluster, but admission,
  connectivity, mTLS, and trace capture are live-cluster claims a headless
  pipeline cannot make on its own.

## On the wire

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

{% include excalidraw.html file="openshift-crc-topology" alt="The mea project on OpenShift Local: strangler-proxy and graphql-gateway each behind their own Route under restricted-v2, the other six services under restricted-v2 with no external exposure, postgres and kafka under the mea-infra ServiceAccount bound to nonroot-v2, and otel-lgtm under anyuid with only runAsUser 0 set." caption="Figure 33.2 — The mea project on OpenShift Local: three SCC postures, two Routes as the only edge" %}

---

*Verification status: <span class="status status--unverified">unverified</span>.
Verification is pending the headless CRC run (DRQ-104); when
`openshift/project-checks.sh` plus the mesh/mTLS/trace checks pass on a
live CRC cluster, this status flips to verified, with the captured
`openshift/evidence/` files cited directly. No Route hostname, pod status,
trace ID, or mTLS line in this chapter is drawn from an uncaptured run.*
