# Deploying the modernized system to OpenShift

This directory is the **OpenShift counterpart** to [`deploy/k8s/`](../deploy/k8s/).
`deploy/k8s/` runs the eight-workload topology on vanilla Kubernetes (minikube,
ch.29/30); this tree runs the same topology on OpenShift, packaged as a **Helm
chart** (`helm/mea/`). ch.33, "Appendix A: Deploying to OpenShift," walks through
it end to end; this README is the quick reference.

## What's here

```
openshift/
├── lib.sh                    # crc-admin context guard, service list
├── build-and-push.sh         # podman build + push: 8 services + the monolith image
├── install-infra.sh          # project, registry Route, SCC binding, foreign-operator check
├── deploy.sh                 # helm upgrade --install + rollout status + bootstrap Job wait
├── capture-evidence.sh       # verification -> evidence/<date>/ (scrubbed)
├── project-checks.sh         # the happy-path checkout, through the strangler-proxy Route
├── teardown.sh                # release, project, operators/CSVs/CRDs, leftover check, crc stop
├── evidence/                  # output directory (empty until a live run lands here)
├── gitops/application.yaml   # illustrative Argo CD Application (not part of the verified deploy)
├── helm/mea/                 # one Helm chart, the whole live-core topology
│   ├── Chart.yaml
│   ├── values.yaml           # the 8 services as data; image/infra/mesh/observability knobs
│   └── templates/
│       ├── _helpers.tpl          # labels + namespace-portable cluster DNS
│       ├── configmap-app.yaml    # shared env contract (same keys as deploy/k8s/base/app-config.yaml)
│       ├── secret-app.yaml       # dev-only Postgres credential
│       ├── serviceaccount-infra.yaml  # SA + SCC binding for postgres/kafka
│       ├── app-deployment.yaml   # ONE template, ranged over values.services -> 8 Deployments
│       ├── app-service.yaml      # -> 8 Services
│       ├── route.yaml            # Routes for strangler-proxy + graphql-gateway
│       ├── postgres.yaml         # Postgres StatefulSet (+ Service)
│       ├── kafka.yaml            # single-broker KRaft Kafka StatefulSet (+ Service)
│       ├── bootstrap-job.yaml    # review-service's shared-schema seed (idempotent)
│       ├── peerauthentication.yaml  # mesh.enabled: STRICT + PERMISSIVE carve-out
│       └── NOTES.txt
└── platform/                 # opt-in: service mesh + tracing
    ├── install-platform.sh install-mesh.sh install-observability.sh evidence.sh
    ├── subscriptions/        # OSSM 3, Kiali, Red Hat build of OpenTelemetry (pinned)
    ├── mesh/                 # Sail Istio v1.30.5 + Kiali
    └── observability/        # grafana/otel-lgtm:0.36.0 (anyuid) + its otelcol config
```

## What changes from `deploy/k8s/` -> OpenShift

Everything about the application is identical: the same 8 UBI10
`python-314-minimal` images (`USER 1001:0`), the same shared env contract, the
same per-service Postgres schema wiring (chosen in each service's own code via
`search_path`, not by the connection string), the same `order.placed` Kafka hop,
the same review-service shared-`public`-schema dependency, the same graceful
shutdown windows and health probes. OpenShift changes five things about how it
is *deployed*:

1. **Security Context Constraints (SCC), not a pinned UID.** `deploy/k8s/base`
   pins `runAsUser: 1001`. OpenShift's default `restricted-v2` SCC assigns each
   pod a UID from the namespace's allocated range and rejects a hardcoded one --
   so the 8 app Deployments here drop `runAsUser` entirely (the UBI10 image
   already runs as an arbitrary UID with group 0, which is exactly what
   restricted-v2 expects). Postgres and Kafka *do* need specific UIDs (70 /
   1000), so they run under a dedicated ServiceAccount (`mea-infra`) bound to
   `nonroot-v2`. The one further exception is otel-lgtm (platform tier) under
   `anyuid`, with only `runAsUser: 0` set -- no `seccompProfile`, or admission
   flips back to restricted-v2 and its root-owned writes fail again.
2. **Routes, not a NodePort.** `strangler-proxy` -- the system's one REST edge --
   and `graphql-gateway` get edge-TLS Routes (HTTP redirected to HTTPS),
   replacing `deploy/k8s`'s NodePort 30888 and graphql-gateway's in-cluster-only
   reach. OpenShift Service Mesh 3 provisions no ingress gateway of its own here:
   the Route IS the edge.
3. **Helm, not a kustomize overlay.** `values.yaml` describes the 8 services as
   data (port/probe/schema/route/grpcPort); `mesh.enabled` and
   `observability.otlp.enabled` are opt-in flags, both off by default, so a
   plain `helm install` renders only the live-core topology.
4. **Images pushed to the integrated registry, not loaded into a local one.**
   Python has no `quarkus-openshift`-style S2I path, so `build-and-push.sh`
   builds each service with `podman` on the host and pushes to OpenShift's
   exposed internal registry, instead of `minikube image load`.
5. **An in-cluster bootstrap Job, not a host port-forward.** `deploy/k8s/scripts/
   deploy.sh` seeds review-service's shared `public` schema by running the
   frozen monolith's `manage.py migrate`/`seed` from the host through a
   port-forward. On OpenShift that becomes `helm/mea/templates/bootstrap-job.yaml`:
   the same idempotent `to_regclass('public.reviews')` guard, run as a Job
   against the in-cluster Postgres, no local Python toolchain or tunnel needed.

## Prerequisites

- A Fedora or RHEL host with **OpenShift Local (CRC)** 2.64.0+ (bundles OpenShift
  4.22.14), `oc` (`eval "$(crc oc-env)"`), `helm` v4.x, `podman`, and a free Red
  Hat account for the CRC pull secret (`crc setup` prompts for it; it is never
  stored in this repo). Stop any running minikube profile first -- one local
  cluster at a time.
- Sizing: `crc config set cpus 6; crc config set memory 20480` for the live-core
  topology; `crc config set cpus 12; crc config set memory 32768` once the
  platform tier (service mesh + tracing) is added.
- The scripts use the `crc-admin` kubeconfig context `crc start` writes
  (override with `OCP_CONTEXT`) and refuse any API server other than
  `api.crc.testing`.

## Install

```sh
crc start; eval "$(crc oc-env)"
./openshift/install-infra.sh                 # project, registry Route, SCC binding
./openshift/build-and-push.sh --mirror-infra # podman build+push: 8 services + monolith + postgres/kafka
./openshift/deploy.sh                        # helm upgrade --install + rollout status
```

`--mirror-infra` copies `postgres:18.6-alpine` and `apache/kafka:4.3.1` into the
same registry namespace for a CRC VM with no Docker Hub egress; on a cluster
that does have egress, drop the flag and point `postgres.image`/`kafka.image` in
`values.yaml` at the upstream refs instead.

Reach the system through its Routes, verifying TLS with the cluster's ingress CA:

```sh
oc --context crc-admin get configmap default-ingress-cert -n openshift-config-managed \
  -o jsonpath='{.data.ca-bundle\.crt}' > /tmp/ingress-ca.crt
curl -s --cacert /tmp/ingress-ca.crt https://strangler-proxy-mea.apps-crc.testing/api/inventory
curl -s --cacert /tmp/ingress-ca.crt https://graphql-gateway-mea.apps-crc.testing/health
```

## Optional: the platform tier

```sh
./openshift/platform/install-platform.sh     # mesh, then tracing (needs 12 vCPU / 32 GiB)
```

or run `platform/install-mesh.sh` / `platform/install-observability.sh`
individually. Both install pinned OperatorHub subscriptions (Manual approval,
exact `startingCSV`) and are undone by the same `teardown.sh`.

## Verify

```sh
./openshift/capture-evidence.sh              # writes openshift/evidence/<date>/
```

Runs the happy-path checkout (`project-checks.sh`) through the strangler-proxy
Route with the same payload `tooling/newman/mea.postman_collection.json`'s
"Scenario 1" uses (customer 1, `SKU-WIDGET-001`, `CARD-VISA`, a non-`SHIP-FAIL`
address), polls the order to its terminal `CONFIRMED` status, and -- when the
mesh/observability tiers are installed -- checks STRICT mTLS, the PERMISSIVE
Route carve-out, and a captured trace. Every check fails the script on a miss;
nothing here invents a result it could not produce.

## Uninstall

```sh
./openshift/teardown.sh                      # release, project, operators/CSVs/CRDs, then crc stop
```
