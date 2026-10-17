# r11 — ch.33 Build Plan: the OpenShift-on-CRC Appendix

**Iteration:** r11 (Phase-1 PLANNER, Opus, lgtm-relay)
**Repo:** `~/Dev/modernizing-enterprise-applications-python` (public, patterncatalyst; Python sibling of `~/Dev/modernizing-enterprise-applications`)
**Target:** ch.33 — the final chapter, `_docs/33-appendix-openshift.md` (stub confirmed; title "Appendix A: Deploying to OpenShift", order 33, part "Appendices"; ch.32 nav points at `/docs/33-appendix-openshift/`).
**Standing convention:** every container project ends with an OpenShift-on-CRC appendix (recorded OpenShift/CRC Appendix Standard). r08/r09/r10 merged on main.
**DRQ range:** DRQ-104 … DRQ-111 (DRQ-102 last real; DRQ-103 reserved-but-not-triggered).
**Status:** awaiting user approval — DRQ-104 (A/B CRC verification) and DRQ-105 (Helm vs overlay) are user gates.

## A. Approach

### A.0 Separation discipline (binding)
OpenShift/CRC/OSSM/Routes/SCC appear in exactly ONE place: the new `openshift/` tree and ch.33. Application code, Containerfiles, the shared env contract, and `deploy/k8s` (the minikube path from ch.29/30) do NOT change and do NOT gain OpenShift dependencies. The **same UBI10 `python-314-minimal` images already run as `USER 1001:0`**, which is exactly what OpenShift's restricted-v2 SCC expects (arbitrary assigned UID, group 0) — so no image rebuild, no Dockerfile edit. OpenShift here is framed as "the same examples on an on-prem Kubernetes distribution," CNCF/vendor-neutral everywhere else. This mirrors datamesh-python's `openshift/` counterpart and the lgtm-crc skill's generic-Kubernetes-is-the-target policy.

### A.1 The `openshift/` deliverables
New tree (all-new files, no edits to existing manifests), modelled on datamesh-python's `openshift/` and the lgtm-crc template layout, adapted to this repo's `examples/<NN>-<svc>/Containerfile` layout and the 8-workload `mea` topology:

```
openshift/
  helm/mea/
    Chart.yaml
    values.yaml            # the 8 services as a data map; image/infra/SCC/Route/mesh/obs knobs
    templates/
      _helpers.tpl         # labels + namespace-portable cluster DNS
      configmap-app.yaml   # shared env contract — SAME keys as deploy/k8s/base/app-config.yaml
      secret-app.yaml      # dev-only Postgres credential — SAME name (mea-postgres-app)
      serviceaccount-infra.yaml  # SA (mea-infra) + nonroot-v2 binding for postgres/kafka
      app-deployment.yaml  # ONE template, range over .Values.services -> 8 Deployments
      app-service.yaml     # -> 8 Services (names identical to minikube)
      route.yaml           # Routes for route:true services (strangler-proxy edge + graphql-gateway)
      postgres.yaml        # Postgres StatefulSet + initdb + Service
      kafka.yaml           # single-broker KRaft Kafka StatefulSet + Service
      bootstrap-job.yaml   # review-service monolith-migrate Job (restricted-v2, idempotent)
      peerauthentication.yaml  # (mesh flag) STRICT default + PERMISSIVE carve-out for Route-facing
      NOTES.txt
  build-and-push.sh        # podman build 8 images + monolith image -> internal registry; --mirror-infra
  install-infra.sh         # project, registry default-route, SCC bindings, (platform) operators
  deploy.sh                # helm upgrade --install + wait on rollout + run bootstrap Job
  capture-evidence.sh      # oc get pods/routes/pa, curl --cacert, trace check -> evidence/ (scrubbed)
  project-checks.sh        # the project's own E2E checkout check
  teardown.sh              # release, project, operators/CSVs/CRDs, leftover check, crc stop
  platform/
    install-platform.sh install-mesh.sh install-observability.sh evidence.sh
    subscriptions/*.yaml   # OSSM3 (servicemeshoperator3), Kiali, RHBOTel — pinned, Manual approval
    mesh/istio.yaml mesh/kiali.yaml   # Sail Istio spec.version v1.30.5; Kiali -> otel-lgtm Prometheus
    observability/         # grafana/otel-lgtm:0.36.0 (anyuid, runAsUser:0 only), otelcol scrape, Instrumentation CR
  evidence/                # output dir (committed only under A/B option A)
  gitops/application.yaml  # illustrative Argo CD Application (not part of the verified deploy)
  README.md                # what changes vs minikube; run order; prerequisites
```

Design choices embedded, each a reserved DRQ:

- **Helm chart, not an OpenShift kustomize overlay (DRQ-105).** `values.yaml` carries a `services:` map (keys = the 8 workloads) with per-service `port/probe/size/db/kafka/route/grpcPort/migrate` fields; `app-deployment.yaml` ranges over it (datamesh-python idiom). Opt-in `mesh.enabled` / `observability.otlp.enabled` default **off** so a plain `helm install` renders the live-core topology. minikube stays on kustomize (ch.29/30) — the two paths never cross.

- **Routes instead of NodePort (DRQ-106).** `strangler-proxy` is the system's single REST edge (:8888, `component: edge-router`) — it gets the primary edge-TLS Route (`insecureEdgeTerminationPolicy: Redirect`), replacing minikube's NodePort 30888. `graphql-gateway` (:8090) gets a second Route as the query edge. strangler-proxy has NO `/health` route (confirmed in `app/main.py`) → probes stay `tcpSocket`, and the Route needs no health annotation it can't serve. **OSSM 3 provisions no ingress gateway — the Route IS the edge;** the mesh governs only sidecar-to-sidecar traffic.

- **SCC posture (DRQ-107).** 8 app pods → default SA under **restricted-v2**, NO `runAsUser` (UBI10-1001 images already satisfy it; a fixed UID would be rejected as "UID not in range"). Postgres/Kafka hardcode UIDs (70 / 1000) → dedicated SA `mea-infra` bound to **nonroot-v2**. otel-lgtm → **anyuid** with **only** `runAsUser: 0` (no seccompProfile — adding one flips admission back to restricted-v2 and Grafana can't write /data).

- **Image delivery into CRC (DRQ-108).** Python has no `quarkus-openshift` S2I path, so the house Python pattern (datamesh-python `build-and-push.sh`) is used: **podman build on host → push to the exposed internal registry** (`default-route-openshift-image-registry.apps-crc.testing/mea/<svc>:v1`, `podman login` with `oc whoami -t`, `--tls-verify=false`). Build the 8 service images **plus the frozen monolith image** (needed by the bootstrap Job). `--mirror-infra` mirrors `postgres`/`kafka` upstream images into the registry (the CRC VM has no Docker Hub egress). Chart `image.pullPolicy: IfNotPresent`. Rejected alternative recorded: in-cluster BuildConfig (Docker strategy, binary input) — more moving parts across 8 Python services and no host-engine benefit here; noted as the no-host-engine fallback in the README.

- **OSSM / mesh + LGTM on OpenShift (DRQ-109).** OSSM 3 via the Sail operator (`servicemeshoperator3`), `Istio` CR `spec.version: v1.30.5` (exact, never `-latest`). Injection by the **`istio.io/rev: default` pod-template LABEL**, NOT the classic `sidecar.istio.io/inject` annotation the minikube path uses (Sail's revisioned webhook ignores the annotation). Namespace-wide **STRICT** `PeerAuthentication` + a **PERMISSIVE** carve-out scoped to the two Route-facing services (the router isn't in the mesh and arrives as plaintext — would 502). LGTM = the same `grafana/otel-lgtm:0.36.0` all-in-one already used in ch.30, redeployed via the platform tier; its embedded Prometheus scrapes sidecars on :15020 and **Kiali points at it** (no cluster Prometheus on CRC). The same 3 services instrumented in ch.30 (strangler-proxy, order-service, inventory-service, via `opentelemetry-distro`) point `OTEL_EXPORTER_OTLP_ENDPOINT` at otel-lgtm; RHBOTel's `Instrumentation` CR is the OpenShift-native alternative noted but the existing distro wiring is reused to keep the app contract identical.

- **review-service monolith-migrate bootstrap on CRC (DRQ-111, conditional).** On minikube, `deploy.sh` runs the frozen monolith's `manage.py migrate`/`seed` from the host through a port-forward to seed the shared `public` schema (reviews/customers/inventory_items/auth_user) that review-service reads. On CRC the clean, no-host-egress form is an **idempotent bootstrap Job** running the monolith image in-cluster with `DATABASE_URL` → the in-cluster Postgres Service, guarded by the same `to_regclass('public.reviews')` check. `oc rsh`/port-forward is the documented fallback.

- **Headless CI gate (DRQ-110).** Add ONE additive workflow `openshift-chart.yml`: `helm template openshift/helm/mea --set mesh.enabled=true --set observability.otlp.enabled=true | kubeconform -strict -ignore-missing-schemas -summary`, with its own `openshift-chart-ok` summary job, **no `paths:`**, cluster-free — mirroring `mesh-manifests.yml` exactly. `-ignore-missing-schemas` lets Route/PeerAuthentication/Istio CRs through unchecked. NEVER touch `code-ci.yml`/`contract-gate`/`code-ci-ok`/`schema-registry.yml`/`deploy-manifests.yml`/`supply-chain.yml`/`mesh-manifests.yml`.

### A.2 ch.33 prose spine (≥2000 words)
Peer-to-peer register, no confessional voice. Structure (adapt from the grpc sibling's STRUCTURE, never copy its gRPC-specific content):

1. **Intro** — every prior chapter ran on something you control end-to-end (compose, minikube). OpenShift adds opinions — SCCs, Routes, an integrated registry, OLM operators — and a chart has to be built around them. The deployment target changes nothing about the application: same 8 images, same env contract, same `order-placed` Kafka hop, same review-service shared-schema dependency.
2. **What stays identical vs what changes** (a table/figure). Identical: the UBI10-1001 images, ConfigMap keys, Secret/Service names, the strangler-proxy edge semantics, the 3-service OTel trace, STRICT mesh mTLS as a concept. Changes: NodePort→Route, kustomize→Helm, `minikube image load`→podman push to internal registry, istioctl `IstioOperator`→Sail `Istio` CR with `istio.io/rev` label, annotation→label injection, no-SCC→restricted-v2/nonroot-v2/anyuid, host-port-forward migrate→in-cluster bootstrap Job.
3. **Building images inside/for the cluster** — the podman→internal-registry loop; why Python has no S2I quarkus path; the infra-mirror for the egress-less CRC VM.
4. **The Helm chart** — the data-driven services map; restricted-v2 securityContext; wait-for-postgres init; the two Routes; the bootstrap Job.
5. **SCC: three postures** — restricted-v2 (apps), nonroot-v2 (infra), anyuid-runAsUser-0 (otel-lgtm), each with why.
6. **OSSM 3: STRICT mTLS, a PERMISSIVE carve-out, Route-is-the-edge** — Sail injection by label; why the router needs the carve-out; Kiali→otel-lgtm Prometheus.
7. **A traced checkout, live** — the E2E checkout through the strangler-proxy Route → order-service → Kafka → notification, and the trace in Grafana.
8. **What CI validates and what it does not** — the headless kubeconform render; the live-cluster claims it cannot prove.
9. **ADLC-in-Action callout** (blockquote `> **ADLC in Action** — …`, the house style from ch.31) — the agent-assisted loop that re-homed the topology (read the real minikube manifests + datamesh-python precedent + lgtm-crc gotchas rather than assuming symmetry).
10. **Decision callout** (`<div class="callout callout--safe">`) — when to reach for Routes vs mesh, Helm vs overlay, podman-push vs BuildConfig.
11. **What you learned** + **On the wire** (the run sequence).
12. **COMPACT footer** (see §C).

Figures (paired SVG + .excalidraw via lgtm-diagram-generator): (A.1) CRC topology — app pods restricted-v2, infra pods nonroot-v2, otel-lgtm anyuid, internal registry, two edge Routes; (A.2) image delivery podman→registry→Deployment; (A.3) STRICT mTLS + PERMISSIVE carve-out with the Route as the edge; optionally (A.4) the traced checkout path.

### A.3 Rejected (one line each)
- OpenShift kustomize overlay — entangles the minikube overlay or duplicates base; no opt-in-flag mechanism (use Helm).
- In-cluster BuildConfig S2I — extra moving parts for 8 Python images, no host-engine win (use podman push; note as fallback).
- Reusing `sidecar.istio.io/inject` annotation on OpenShift — Sail ignores it; silently no injection (use `istio.io/rev` label).
- Fixed `runAsUser` on app pods — rejected by restricted-v2 (let the platform assign).
- A full operator-based Postgres/Kafka (CNPG/Strimzi CRs) — not assumed installed; plain StatefulSets keep the core self-contained (operators are platform-tier/appendix).
- Touching any existing CI workflow or `deploy/k8s` — forbidden; `openshift/` is purely additive.
- `--insecure` curl for Route verification — use the cluster ingress CA (`--cacert`).
- Faking any CRC output — forbidden; A/B gate controls evidence, never fabrication.

## B. Steps (ordered, parallel-safe waves; single-writer per file)

**Wave 1 — scaffold `openshift/` (1 agent).** All-new files, no contention. Invoke the **lgtm-crc skill** (binding conventions) adapted to Python: substitute `__PROJECT__=mea`, services = the 8 workloads, Route on strangler-proxy + graphql-gateway, Postgres/Kafka as plain StatefulSets, bootstrap Job for review-service. Write chart + scripts + platform tier. Offline-validate: `bash -n` every script, `helm lint`, `helm template` with all flags on.

**Wave 2 — chapter + diagrams (2 agents, parallel on fixed figure specs).**
- Agent 2a: write `_docs/33-appendix-openshift.md` (single writer) per §A.2; ≥2000 words; compact footer templated for both A/B outcomes (final badge set at the user gate).
- Agent 2b: lgtm-diagram-generator → the 3–4 paired SVG+excalidraw figures into `assets/`.

**Wave 3 — CI gate + ledgers (parallel, 1 writer per file).**
- `.github/workflows/openshift-chart.yml` (new, additive).
- `_plans/decisions.md` — append DRQ-104…DRQ-111.
- `_plans/reconciliation.md` — r11 note.
- `_plans/build-plan.md` — §J r11 row + check the §B.2 ch.33 line.

**Wave 4 — validation + USER gate.**
- Run `lgtm-professional-voice` scan (0 ban-tier required), `helm lint` + `helm template | kubeconform -strict -ignore-missing-schemas`, `bash -n` all scripts, `bundle exec jekyll build` (exit 0), nav 32→33 check (33 terminal).
- Then the **A/B user gate (DRQ-104):** user chooses (A) live CRC run + evidence → footer `verified`, commit scrubbed `openshift/evidence/`; or (B) document-only → footer `unverified`. Set the compact footer badge accordingly. Never fabricate output.

Branch → PR → squash-merge. Upstream pins surveyed at plan time (§E), re-checked at build time and before any live run.

**Agent count:** 3–4 Sonnet execution agents across the waves; Opus validates in Phase 3.

## C. Acceptance criteria (checkable)
- [ ] `_docs/33-appendix-openshift.md` ≥ 2000 words, front-matter intact (order 33, part Appendices), stub line removed.
- [ ] ≥ 3 figures, each a committed paired SVG + `.excalidraw`, referenced in-text.
- [ ] One **ADLC-in-Action** callout (house blockquote style) + one Decision callout.
- [ ] **COMPACT** footer in the PR#11 style: `*Verification status: <span class="status status--verified">verified</span>. <note>*` (or `status--unverified`) — classes `status--verified`/`status--unverified` ONLY; not the old verbose form.
- [ ] `helm lint openshift/helm/mea` clean; `helm template … --set mesh.enabled=true --set observability.otlp.enabled=true | kubeconform -strict -ignore-missing-schemas` → 0 invalid (CRs skipped-missing-schema).
- [ ] `bash -n` passes on every `openshift/*.sh` and `openshift/platform/*.sh`.
- [ ] `openshift-chart.yml` is additive, headless, has `openshift-chart-ok`, has NO `paths:`, and no existing workflow is modified.
- [ ] CRC verification honest per A/B: option A → evidence committed under `openshift/evidence/` (scrubbed, no secrets), footer `verified`; option B → footer `unverified` with the live-CRC-required items named, nothing faked.
- [ ] Voice: 0 ban-tier hits (`\bhonest\b`/"honestly"/"for honesty"/"not hidden"/"not faked"/"stated plainly"; no "capstone").
- [ ] `jekyll build` exits 0; nav ch.32 → ch.33 intact and ch.33 is the last chapter (no next link).
- [ ] No change to app code, Containerfiles, `deploy/k8s`, or protected CI workflows.
- [ ] DRQ-104…DRQ-111 recorded in `_plans/decisions.md`; §J r11 row added.

## D. Risks + Phase-3 detection
- **CRC resource weight** — platform tier needs 12 vCPU / 32 GiB, 80 GB disk; a plain core run needs 6/20. *Detect:* `require_crc_size` guard; README states sizing; A/B-A pre-flight checks `crc config`.
- **restricted-v2 rejecting a pod** — any stray `runAsUser`/fixed UID on app pods ("UID not in range"). *Detect:* grep chart templates for `runAsUser` on app Deployments (should appear only on otel-lgtm anyuid); `helm template` + `oc get pod -o jsonpath` scc check in evidence.
- **OSSM provides no ingress gateway → Route-is-edge** — assuming a mesh gateway, or STRICT 502-ing every Route request. *Detect:* assert PERMISSIVE PeerAuthentication exists for both Route-facing services; prose states the Route is the edge.
- **Image-into-CRC delivery** — registry default-route not exposed / `podman login` TLS / egress-less VM for infra images. *Detect:* `build-and-push.sh` preconditions documented; `--mirror-infra` path; evidence shows ImageStreams present.
- **Injection by annotation (Sail ignores it)** — reusing the minikube `sidecar.istio.io/inject` pattern → no sidecars. *Detect:* chart uses `istio.io/rev` label; evidence shows 2/2 ready meshed pods.
- **Shared-namespace / leftover operators from sibling appendices** — a foreign CRC left dirty. *Detect:* `install-infra.sh` inventories `oc get sub,csv -A` + non-system namespaces, flags foreign, removes only with user approval; `teardown.sh` returns CRC to empty then `crc stop`.
- **Pin drift** — CSVs can't be known without a cluster; upstream moved since 2026-10-09. *Detect:* Phase-2 re-runs the lgtm-crc `oc get packagemanifest` survey and `skopeo list-tags` before any live run; deliberate holds recorded with reason.
- **Monolith image omitted** — bootstrap Job can't seed the shared schema. *Detect:* `build-and-push.sh` builds the monolith image; Job idempotency guard on `to_regclass('public.reviews')`.
- **review-service health** — it has no `/health` route; an httpGet probe or health-annotated Route would fail. *Detect:* chart uses `tcpSocket` probe for strangler-proxy + review-service; verified in `helm template`.

## E. New pins (surveyed at plan time; Phase-2 re-checks upstream + on-cluster)
Source of truth = the lgtm-crc `references/versions.md` (dated 2026-10-09, a verified live CRC run), confirmed current by web survey on 2026-10-17:
- **CRC (OpenShift Local):** 2.64.0 (web-confirmed newest). Bundles **OpenShift 4.22.14**, **Kubernetes 1.35.6**.
- **OSSM 3 (Sail):** `servicemeshoperator3` channel `stable-3.4`, CSV `servicemeshoperator3.v3.4.3`; **Istio `spec.version: v1.30.5`** (exact).
- **Kiali:** `kiali-ossm` `stable`, CSV `kiali-operator.v2.27.5`.
- **Red Hat build of OpenTelemetry:** `opentelemetry-product` `stable`, CSV `opentelemetry-operator.v0.158.0-2`.
- **Helm:** v4.3.1 (2026-10-15, web-confirmed newest stable; datamesh-python authored against helm v4). Pin v4.x.
- **otel-lgtm:** reuse `docker.io/grafana/otel-lgtm:0.36.0` (same as ch.30).
- **App/infra images:** reuse the project's existing UBI10 `python-314-minimal` (USER 1001:0) service images; Postgres/Kafka = the images the minikube StatefulSets already use (mirror into the internal registry).
- **kubeconform:** the version already used by `mesh-manifests.yml`.
- All operators: `installPlanApproval: Manual`, exact `startingCSV`, approve only the named InstallPlan. Operator CSVs MUST be re-checked on the cluster (`oc get packagemanifest`) before a live run.

## F. DRQ allocations (start DRQ-104; DRQ-102 last real, DRQ-103 reserved-but-not-triggered)
- **DRQ-104** — A/B CRC-verification gate (live-run+evidence `verified` vs document-only `unverified`). *User gate.*
- **DRQ-105** — Helm chart vs OpenShift kustomize overlay → Helm chart.
- **DRQ-106** — Routes-as-edge: strangler-proxy (primary) + graphql-gateway, edge-TLS Redirect, replacing NodePort; OSSM provides no ingress gateway.
- **DRQ-107** — SCC posture: restricted-v2 (apps), nonroot-v2 (postgres/kafka infra SA), anyuid+runAsUser:0-only (otel-lgtm).
- **DRQ-108** — image delivery: podman build → exposed internal registry, `--mirror-infra` for egress-less VM, monolith image included; BuildConfig fallback recorded.
- **DRQ-109** — OSSM-on-CRC: Sail `Istio` v1.30.5, `istio.io/rev` label injection, STRICT + PERMISSIVE carve-out, Kiali→otel-lgtm Prometheus.
- **DRQ-110** — headless CI gate: additive `openshift-chart.yml` (`helm template | kubeconform -strict -ignore-missing-schemas`, `openshift-chart-ok`, no `paths:`), protected workflows untouched.
- **DRQ-111** (conditional) — review-service monolith-migrate bootstrap: in-cluster idempotent Job vs `oc rsh`/port-forward.
