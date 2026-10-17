---
title: "r10 Build Plan — ch.30 (Mesh, Observability & Tracing) + ch.32 (The Pattern Language, Revisited — the final project)"
description: "Phase-1 (Opus/lgtm-relay) plan for r10: activate the ch.30 Istio + LGTM seam on minikube, add OpenTelemetry additively to 3 services, and author the two back-matter chapters. ch.30 is the one live-env chapter (A/B-2 user-run vs deferred); ch.32 is prose. No code is written until this plan is approved."
status: "awaiting user approval (DRQ-096 is the remaining user gate; DRQ-095/A-B-2 already resolved = A, user-run)"
---

# r10 Build Plan — ch.30 + ch.32

**Planner:** Opus (lgtm-relay Phase 1). **Base:** `main@bfb1340` (r08+r09 merged).
**Scope:** ch.30 (Mesh/Observability/Tracing — Istio + LGTM on minikube, OTel added
additively to 3 services; the ONE live-env chapter) + ch.32 (The Pattern Language,
Revisited — the book's **final project**, prose). Sequenced per the approved
`_plans/backmatter-track-plan.md` r10 row. ch.33 (OpenShift/CRC) is a separate later track.

**USER GATES:** DRQ-095 (A/B-2) is already resolved = **A** (user runs the live sequence and
hands back evidence → `verified-live (user-run)`). DRQ-096 (the 3 OTel services) remains open.

This plan builds ch.30 **fully regardless of the A/B-2 outcome** — the istio +
observability overlays, the OTel instrumentation of 3 services, and the user-runnable
scripts are all authored either way. A/B-2 controls **only** whether the chapter's
verification footer captures live evidence (`verified-live (user-run)`) or is marked
`deferred (requires live minikube/Istio)` with its deferred items named, never faked.

---

## A. Approach

### A.1 ch.30 — Mesh, Observability & Distributed Tracing (the live-env chapter)

**What it is.** ch.29 (r09) shipped `deploy/k8s/base` + `overlays/minikube` rendering clean
headlessly (`kubectl kustomize` 23 resources, `kubeconform -strict` 23/23 Valid), with a
**commented ch.30 seam** in `overlays/minikube/kustomization.yaml` (the `../../istio` +
`../../observability` sibling-overlay references and the `sidecar.istio.io/inject` label
patches, all explicitly deferred). ch.30 **activates that seam**: it makes the 8-service
`mea` namespace a real Istio mesh on a live minikube cluster, adds the Grafana LGTM
observability backend in-cluster, and adds OpenTelemetry app-level instrumentation to 3
chosen services, then tells the trace / metrics / mTLS story the running system produces.

This is a **re-authoring, not a copy**, of the Java sibling's ch.30
(`~/Dev/modernizing-enterprise-applications/_docs/30-*.md` + `deploy/k8s/{istio,observability}`).
The structure is reused; the content is Python-native and the hero trace is this project's own.

**Build surfaces (authored regardless of A/B-2):**

1. **`deploy/k8s/istio/` (new sibling overlay)** — the namespace-scoped CRs that are ordinary
   `kubectl apply -k`-able objects:
   - `peer-authentication.yaml` — `PeerAuthentication` **STRICT** mesh-wide in `mea` (DRQ-098).
   - `peer-authentication-edge.yaml` — a `PERMISSIVE` exception for the one unmeshed hop: the
     NodePort edge (`127.0.0.1:30888` → strangler-proxy), which enters the mesh plaintext from
     outside and must not be rejected by STRICT (mirrors the Java sibling's edge peer-auth).
   - `telemetry.yaml` — mesh-wide `Telemetry` routing Envoy's own spans + access logs to the
     `otel` extensionProvider at 100% sampling (demo sampler, named as not production-appropriate).
   - `kustomization.yaml` — bundles the three CRs only. The `IstioOperator` install itself
     (`istio-install.yaml`, `default` profile: istiod + ingress gateway, `extensionProviders:
     [otel → lgtm.mea.svc.cluster.local:4317]`, `meshConfig.accessLogFile: /dev/stdout`) is
     applied **separately via `istioctl install -f`**, not kustomize (operator-reconciled CRD,
     not a plain apply) — so it is NOT in any kustomization's `resources:` and will NOT and need
     NOT pass `kubeconform` (CRD-schema, cluster-only). Named explicitly in the chapter.

2. **`deploy/k8s/observability/` (new sibling overlay)** — the LGTM backend, **unmeshed**
   (deliberately NO sidecar label — a meshed observability backend would wrap its own OTLP
   ingest in mTLS and collide with the collector) (DRQ-099):
   - `lgtm-deployment.yaml` — one `grafana/otel-lgtm:0.36.0` all-in-one Deployment (Tempo +
     Loki + Mimir + Grafana + an embedded OTel Collector co-located at localhost in the pod),
     reused unchanged in tag from compose's `lgtm` service.
   - `lgtm-service.yaml` — a ClusterIP Service (`lgtm.mea.svc.cluster.local`, port 4317 OTLP for
     in-cluster emitters) + a NodePort for host access to Grafana (publish a second host port at
     profile creation, e.g. `127.0.0.1:30300:30300`; add it to `lib.sh` `NODE_PORTS`).
   - `otelcol-configmap.yaml` — ported from the compose stack's `infra/otelcol/config.yaml`,
     plus ONE addition: a `prometheus/istio-mesh` receiver doing Kubernetes service-discovery of
     `mea` pods and scraping each istio-proxy's Envoy stats (`:15090/stats/prometheus`) so
     `istio_requests_total` + service-graph metrics land in Mimir.
   - `grafana-datasources-configmap.yaml` — Tempo/Mimir/Loki datasources (ported from compose).
   - `rbac.yaml` — the `lgtm` ServiceAccount + ClusterRole/Binding the Prometheus SD scrape needs
     to list/watch pods in `mea`.
   - `kustomization.yaml` — bundles the five above (no `resources: [../../base]`; purely additive).

3. **`deploy/k8s/overlays/minikube/kustomization.yaml` (shared file — single-writer edit)** —
   uncomment/activate the seam: add `../../istio` + `../../observability` to `resources:`, and
   add a `sidecar.istio.io/inject: "true"` **pod-template LABEL** patch (JSON-pointer
   `/spec/template/metadata/labels/sidecar.istio.io~1inject`) to each of the **8 app Deployments**
   — alongside their existing `imagePullPolicy: Never` patches (DRQ-097). **LABEL, not annotation,
   not a namespace-wide `istio-injection=enabled` label**: Istio's sidecar-injection webhook's
   `objectSelector` matches the label on the admitted pod template; the annotation form silently
   injects nothing in an unlabeled namespace (hard-won gotcha from the datamesh reference arch).
   **postgres + kafka StatefulSets are deliberately NOT labelled** — meshing a stateful workload's
   own TLS collides with the injected sidecar's mTLS wrapping.

4. **`deploy/k8s/scripts/install-istio.sh` + extend `setup-profile.sh`/`deploy.sh`/`teardown.sh`**
   — `install-istio.sh` requires `istioctl` pinned to the exact Istio version, requires the `mea`
   profile running, runs `istioctl install -y --context mea -f deploy/k8s/istio/istio-install.yaml`,
   and waits for istiod + ingressgateway rollout. `setup-profile.sh` keeps
   `--driver=docker --container-runtime=containerd` (unchanged; add the Grafana NodePort to the
   published-ports list). `deploy.sh` grows a documented ch.30 path (apply the activated overlay
   after istio is installed); `teardown.sh` removes istio + the observability namespace resources.

5. **OTel instrumentation of exactly 3 services (additive)** — see A.3 + DRQ-096. Per service:
   add `opentelemetry-distro` + `opentelemetry-exporter-otlp-proto-grpc` to `pyproject.toml`,
   run `opentelemetry-bootstrap -a install` (zero-code auto-instrumentation of the detected libs:
   starlette/fastapi, httpx, grpc, asyncpg/sqlalchemy, aiokafka), wrap the Containerfile entrypoint
   with `opentelemetry-instrument uvicorn …` (or the relay/consumer entrypoints), and set
   `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`/`OTEL_TRACES_SAMPLER=always_on` (demo sampler,
   named as such) via `.env.example` + the k8s ConfigMap (additive keys; a no-op where the endpoint
   is unset, so compose + CI stay byte-for-byte unaffected). This is exactly the lgtm-python skill's
   opentelemetry-distro zero-code posture.

**What the ch.30 story demonstrates (prose spine, re-authored structure):**
- Why a service mesh (sidecar data path; app-transparent mTLS, telemetry, traffic mgmt).
- Bringing up the cluster + installing Istio on minikube (docker/containerd driver; the pinned
  istioctl; `default` profile).
- The **mesh opt-in is a label, not an annotation** — the concrete gotcha, with the webhook reason.
- **mTLS across the seam** — PeerAuthentication STRICT, verified with `istioctl x describe pod`
  reporting `Workload mTLS mode: STRICT`; the edge PERMISSIVE exception explained.
- The LGTM stack on Kubernetes (all-in-one image; OTLP ingest; Prometheus SD scrape of sidecars).
- **The limit of mesh-only tracing** — Envoy sidecars give you every hop's span mesh-wide (all 8
  services, for free), but not in-process detail (DB queries, business spans); app-level OTel on
  the 3 chosen services adds that depth. Name the property: **mesh gives breadth, OTel gives depth.**
- **The hero trace** — the connected trace the running system produces (shape depends on DRQ-096;
  see A.3), captured from Tempo; the golden-signal metrics; Kiali/Grafana service graph.
- A **"when dry-run lied"** beat (reused structurally from Java): offline `kubeconform`/`dry-run`
  pass, but a live apply surfaces real admission/scheduling facts (e.g. the un-meshed
  postgres/kafka decision, probe timing under the sidecar, sampler cost) — the gap between
  render-verified and cluster-verified that ch.29 already named and r10 closes (or defers).

### A.2 ch.32 — The Pattern Language, Revisited (the book's final project, prose)

A prose chapter (no new runnable artifact) that re-walks **every pattern the book built** as a
connected *language*, now that the migration is complete (decommission done at r07): Strangler Fig
+ ASGI proxy façade; Transactional Outbox + the dual-write cure; choreographed Saga (payment) vs
orchestrated Saga (shipping, with DB-backed crash-resume); CQRS (order_view) with full Event
Sourcing deliberately deferred; Anti-Corruption Layer + the gRPC `inventory.proto` seam with its
drift guard; Schema Registry (Apicurio, isolated to demo-09); the Microservices Chassis
(convention-not-library, the per-service scorecard, OTel now landed on 3 of 8); Deployment
patterns (kustomize base/overlay); Service Mesh + Observability + Tracing (ch.30); CI/CD +
Supply-chain gates. Each pattern gets a verdict: **earned its place / adapted / deliberately
deferred**, each verdict traceable to the chapter that proved it. Plus: the **anti-patterns of
over-decomposition** (the distributed-monolith trap; the context-aligned "right size" vs
nanoservice sprawl spectrum), the **chassis in 2026**, an **ADLC retrospective** (how the
plan→build→validate relay + the reconciliation ledger actually ran across r01–r10), and
**clearly-scoped further horizons** (named, not hand-waved: pybreaker/bulkhead, full event
sourcing, GitOps operator + canary, Loki log aggregation, Kafka saga-hop app-level tracing).

**§C reconciliation (DRQ-102):** fill the currently-empty **"Service Mesh / Observability /
Tracing (H)"** row Note in `build-plan.md` §C with the r10 result (Istio mesh + mTLS STRICT + LGTM
+ OTel-on-3), and re-confirm every other §C row's "landed rNN" annotation against the shipped
chapters so the matrix is a true checklist with no unlanded pattern. ch.32's own scorecard figure
must match §C exactly.

### A.3 The 3 OTel-instrumented services — recommendation + alternative (DRQ-096, USER-visible)

The mesh gives L7 telemetry (requests, mTLS, service graph, even basic trace spans) for **all 8**
services' sidecars for free. App-level OTel is added to **exactly 3** to give in-process depth and
to produce one connected hero trace. Two viable trios:

- **(A — RECOMMENDED) strangler-proxy + order-service + inventory-service** — the **synchronous**
  request path. Hero trace: `POST /api/orders` enters **strangler-proxy** (edge span, httpx
  client to order), → **order-service** (FastAPI server span + asyncpg spans for the order
  aggregate and the CQRS `order_view` write), → **inventory-service** `Reserve` over **gRPC**
  (grpc-client span on order, grpc-server span on inventory) — crossing the ch.19 ACL seam. Clean
  parent-child distributed trace, **no outbox hazard** (see below), verifiable in one capture. This
  mirrors the Java sibling's synchronous-fan-out hero trace but re-roots it at the strangler-proxy
  edge instead of graphql-gateway. The async Kafka saga hops (order.placed → payment → shipping)
  remain visible at the **mesh layer** in Kiali, and are documented as **app-level-deferred**
  (the same posture the Java sibling took — it deferred Kafka saga-hop tracing too).

- **(B — more distinctive, more risk) strangler-proxy + order-service + payment-service** — the
  **async saga** path. Hero trace would span proxy → order (HTTP) → **Kafka `order.placed`** →
  payment (consume) → capture. This is Python's distinctive story (the Kafka hop Java deferred),
  **but** order-service uses an **Outbox + relay**: the HTTP request writes the outbox row, and a
  *separate* background relay poll publishes to Kafka later — so the HTTP request's trace context
  does **not** reach the Kafka message unless we **persist `traceparent` in the outbox row and
  restore it in the relay** before producing (otherwise aiokafka's instrumentation starts a *new*
  trace at publish time → two disjoint traces, not one). Choosing B therefore pulls in **DRQ-103**
  (build outbox trace-context propagation: an additive nullable `traceparent` column + relay
  restore) to make the single end-to-end trace real rather than faked. If B is chosen without
  DRQ-103, the chapter must show the Kafka hop as a *linked/separate* trace, not a single one.

**Planner recommendation: A** — it delivers a genuine connected distributed trace that is
capturable in one live run with no outbox surgery, keeps the r10 blast radius additive, and still
roots the trace at the strangler-proxy edge. **Present A/B to the user as DRQ-096.** (If the user
wants the Kafka-saga-hop one-up over Java, choose B **and** accept DRQ-103's outbox work.)

### A.4 What I reject, and why (one line each)
- **Namespace-wide `istio-injection=enabled` label** — rejected: `mea` deliberately stays
  unlabelled; per-Deployment `sidecar.istio.io/inject` label is the precise, documented opt-in.
- **Injection via pod annotation** — rejected: the webhook `objectSelector` matches labels;
  annotation silently injects nothing (the hard-won gotcha).
- **Meshing postgres + kafka** — rejected: sidecar mTLS collides with their own TLS; keep stateful
  infra unmeshed (matches Java + datamesh precedent).
- **`demo` Istio profile** — rejected: it bundles addons (its own Prometheus/Jaeger/Grafana) that
  duplicate the LGTM stack; use `default` (istiod + ingress gateway) with LGTM as the only backend.
- **Instrumenting all 8 services with app-level OTel** — rejected: the mesh already covers all 8 at
  L7; 3 app-instrumented services is the deliberate breadth-vs-depth teaching split.
- **A required CI gate that applies the mesh** — rejected: it needs a live cluster, cannot run
  headless, and would wedge the ruleset (see §D).
- **confluent-kafka / any vendor-cloud / OpenShift specifics** — rejected: generic minikube is the
  r10 target (OpenShift is ch.33); CNCF/vendor-neutral only (Istio, OTel, Grafana LGTM all qualify).
- **"capstone" framing for ch.32** — rejected: ban-tier register; ch.32 is the book's **final
  project**.

---

## B. Steps (ordered, parallel-safe waves; single-writer on shared-root files)

Shared-root single-writer files: `deploy/k8s/overlays/minikube/kustomization.yaml`,
`deploy/k8s/scripts/lib.sh`, `_docs/30-*.md`, `_docs/32-*.md`, `_plans/*`, `build-plan.md`,
each `examples/<svc>/pyproject.toml`+`Containerfile`, `.env.example`, any new CI workflow.

**Wave 0 — gate + foundations (serial; 1 planner-executor).**
- Resolve the open user gate at the plan gate before any build: **DRQ-096** (DRQ-095/A-B-2 already
  = A). Freeze DRQ-097/098/099/100/101/102.
- Survey-confirm pins (DRQ-100) and correct the track-plan placeholders.
- Author `deploy/k8s/istio/*` + `deploy/k8s/observability/*` (new files, no contention).
- Single-writer edit of `deploy/k8s/overlays/minikube/kustomization.yaml` (activate seam + 8
  injection-label patches) and `deploy/k8s/scripts/*` (install-istio.sh + Grafana NodePort +
  deploy/teardown ch.30 paths) + `lib.sh` NODE_PORTS.
- **Housekeeping sweep (folded in):** rename lingering "capstone" → "final project" in the existing
  `_plans/*` files (and any "complete project" from the prior interim convention → "final
  project"); tighten the leftover `MINIKUBE_DRIVER=podman` opt-in out of the deploy/k8s minikube
  path (docker+containerd is the only driver; podman may remain only as a build-engine option).

**Wave 1 — parallel build (4 agents, each single-writer on disjoint paths).**
- **Agent A (OTel):** instrument the 3 chosen services — `pyproject.toml` deps,
  `opentelemetry-bootstrap -a install`, Containerfile `opentelemetry-instrument` entrypoint wrap,
  additive `.env.example` + k8s ConfigMap OTEL_* keys. One agent for idiom consistency across the
  3 disjoint `examples/<svc>/` dirs. (If DRQ-096=B+DRQ-103: also the additive outbox `traceparent`
  column + Alembic migration + relay restore in order-service.)
- **Agent B (ch.30 prose):** author `_docs/30-*.md` (≥2000w, ≥2 figures, ADLC-in-Action callout,
  verification footer scaffold with placeholders for the A/B-2 evidence fill-in).
- **Agent C (ch.32 prose + §C):** author `_docs/32-*.md` (≥2000w, ≥2 figures, ADLC retrospective,
  footer) + reconcile `build-plan.md` §C (fill the Mesh/Observability row; re-confirm all "landed"
  cells). Final-project framing; no "capstone".
- **Agent D (CI, per DRQ-101):** `.github/workflows/mesh-manifests.yml` — a NEW, SEPARATE,
  additive gate: `changes` (no `paths:`) → `render` (`kubectl kustomize` the activated
  istio+observability-inclusive overlay, piped to `kubeconform -strict`; the `IstioOperator` +
  Istio CRD-schema objects are excluded/skipped as not-headless-schemable) → `mesh-manifests-ok`
  summary (`if: always()`). Must go green **without a cluster**. Never touches code-ci.yml /
  contract-gate / code-ci-ok / schema-registry.yml / deploy-manifests.yml / supply-chain.yml.

**Wave 2 — the A/B-2 live step (serial; USER-run, DRQ-095=A).**
- The USER runs, once, on their cluster:
  `setup-profile.sh` → `install-istio.sh` → `build-images.sh` → `deploy.sh` (activated overlay) →
  drive traffic (N synchronous checkouts / reads) → capture evidence into
  `deploy/k8s/observability/evidence/`: the hero trace JSON (`ch30-hero-trace.json`), the mTLS
  proof (`ch30-istioctl-mtls.txt` from `istioctl x describe pod`), the metrics
  (`ch30-metrics.txt`), and hands back the artifacts + the trace ID + pod-ready facts. An executor
  then wires those exact filenames + figures into ch.30's footer and flips status to
  `verified-live (user-run)`. (Fallback only if the cluster is unavailable at run time: mark
  `deferred (requires live minikube/Istio)` with items named, no fabricated evidence.)

**Wave 3 — validate + reconcile (serial; 1 Opus validator).**
- Voice pass (`lgtm-professional-voice`): **0 ban-tier** across `_docs/30`, `_docs/32`, new
  READMEs, scripts prose (no "honest/honestly/not hidden/not faked/stated plainly/to be
  honest/capstone").
- `lgtm-idiomatic-review` on the OTel instrumentation code.
- `kubeconform -strict` on the istio + observability overlay render (headless) — the exact command
  the gate runs; the istioctl-only `istio-install.yaml` documented as cluster-only, not a failure.
- Jekyll build exit 0; nav **29→30→31** and **31→32→(33)** intact.
- Append `reconciliation.md` r10 section (CLEAN/DRIFT verdicts; the Java-sibling re-authoring; the
  A/B-2 outcome; any bug found live). Update `decisions.md` (DRQ-095..103) + `build-plan.md` §J r10
  row + §C. Correct the track-plan pin placeholders.

**Agent count: 4 in Wave 1** (A OTel, B ch.30, C ch.32+§C, D CI), plus serial Wave-0 foundations
and a serial Wave-3 validator; Wave 2 is user-run.

---

## C. Acceptance criteria (checkable)

- [ ] `_docs/30-*.md` ≥2000 words, ≥2 figures, one **ADLC-in-Action** callout, a
      verification-status footer.
- [ ] `_docs/32-*.md` ≥2000 words, ≥2 figures, ADLC retrospective, footer; framed as the book's
      **final project** (zero occurrences of "capstone").
- [ ] `deploy/k8s/istio/` + `deploy/k8s/observability/` overlays render under
      `kubectl kustomize` **and** pass `kubeconform -strict` **headless** (the istioctl-only
      `istio-install.yaml` is excluded as cluster-only and documented as such — not a gate failure).
- [ ] `deploy/k8s/overlays/minikube/kustomization.yaml` still renders clean with the seam active;
      the 8 app Deployments carry the `sidecar.istio.io/inject: "true"` **label** (not annotation);
      postgres/kafka carry none.
- [ ] OTel wired into **exactly 3** services — **name them in the chapter + decisions.md**
      (recommended: `01-strangler-proxy`, `07-order-service`, `04-inventory-service`; or the
      DRQ-096=B trio). Additive only: compose + every existing CI gate stay byte-for-byte green.
- [ ] ch.30 verification is honest per **A/B-2** (= A): `verified-live (user-run)` with the
      committed evidence files cited in the footer — and **no fabricated trace/span/metric/
      screenshot**. (Fallback: `deferred` with items named, never faked.)
- [ ] ch.32 reconciles `build-plan.md` **§C** — the Mesh/Observability/Tracing (H) row Note is
      filled; every "landed rNN" cell re-confirmed against shipped chapters; the ch.32 scorecard
      figure matches §C.
- [ ] Voice: **0 ban-tier** hits across new prose.
- [ ] Jekyll build exit 0; nav **29→30→31** and **31→32→(33)** intact.
- [ ] If a new CI workflow exists (DRQ-101): it is separate/additive, `*-ok`, no `paths:`, goes
      **green without a cluster**, and does not touch any protected workflow.

---

## D. Risks + Phase-3 detection

| Risk | Phase-3 detection |
|---|---|
| **Live-env dependency** (minikube docker/containerd driver, resources: LGTM all-in-one is memory-heavy — 8g/4cpu floor already in `setup-profile.sh`) | The user-run step either produces evidence or it doesn't; no evidence ⇒ fall back to deferred honestly. Pre-flight: `setup-profile.sh` resource checks; Grafana NodePort added to `NODE_PORTS`. |
| **Istio injection via label-not-annotation** (annotation injects nothing silently) | Verify pods reach `2/2 Ready` (app + istio-proxy) in the user-run; `istioctl x describe pod` must show the sidecar. If `1/1`, the label is wrong/missing. |
| **mTLS STRICT rejects the plaintext NodePort edge** | The edge `PeerAuthentication` PERMISSIVE exception; detection = a `200/202` through `127.0.0.1:30888` after STRICT is applied. |
| **OTLP endpoint wiring** (wrong `OTEL_EXPORTER_OTLP_ENDPOINT`, wrong port 4317, LGTM unmeshed-but-unreachable) | No spans in Tempo in the user-run ⇒ check the ConfigMap endpoint + that lgtm Service resolves; headless: assert the env keys are present in the rendered ConfigMap. |
| **Outbox breaks trace-context** (only if DRQ-096=B without DRQ-103) | If B: the capture shows two disjoint traces ⇒ either build DRQ-103 (traceparent column + relay restore) or document the Kafka hop as linked/separate honestly. |
| **Overlay renders-but-wouldn't-apply** (admission/webhook/scheduling only live) | ch.30 states the render-verified vs cluster-verified gap (ch.29 already named it); the live apply (A) closes it. The "when dry-run lied" section is the teachable. |
| **Pin availability** (istioctl must match the Istio pin exactly; opentelemetry-distro is beta-channel `0.xxbN`; grafana/otel-lgtm 0.36.0 pull) | `install-istio.sh` asserts `istioctl version` == pin; `uv lock` resolves the OTel pins at execution; `skopeo`/pull-check the lgtm + istio images before the user-run. Re-survey at execution (pins move). |
| **Never fake a trace** (the crux) | Validator confirms every trace/metric/mTLS claim in ch.30 is backed by a committed evidence file (A) or marked deferred; grep the footer for fabricated-looking IDs with no evidence file. |
| **CI wedge** (a required gate that can't run headless) | The only new gate is kubeconform-on-overlays, `*-ok`, no `paths:`, cluster-free; confirm code-ci-ok/contract-gate/schema-registry/deploy-manifests/supply-chain untouched. |

---

## E. New pins (surveyed at plan time 2026-10-17; correcting the track-plan placeholders)

| Component | r10 pin | Track-plan placeholder → correction | Where |
|---|---|---|---|
| Istio + istioctl | **1.31.2** (published 2026-10-16, current stable) | "~1.31.x" → 1.31.2 | `deploy/k8s/scripts/install-istio.sh`, `deploy/k8s/istio/*`, ch.30 |
| opentelemetry-distro | **0.66b1** (OTel Python instrumentation is a beta-channel line `0.xxbN` — this *is* its stable channel) | "opentelemetry-distro (latest)" → 0.66b1 | 3 services' `pyproject.toml` |
| opentelemetry-exporter-otlp-proto-grpc | **1.45.0** (core line) + matching `opentelemetry-instrumentation` 0.66b1 via `bootstrap -a install` | "exporter-otlp" → opentelemetry-exporter-otlp-proto-grpc 1.45.0 | 3 services' `pyproject.toml` |
| grafana/otel-lgtm | **0.36.0** (REUSE, unchanged from compose / DRQ-077) | reuse 0.36.0 | `deploy/k8s/observability/lgtm-deployment.yaml` |
| minikube | floor **v1.33.0** (`MINIKUBE_MIN`, already set); current stable ~1.37.x — survey at execution | "~1.39" → floor-not-exact; the project pins a floor, not an exact minikube | `deploy/k8s/scripts/lib.sh` |
| Kubernetes | **v1.37.1** (REUSE from DRQ-093) | "~v1.36.x" → v1.37.1 reused | `deploy/k8s/scripts/lib.sh` |
| kubeconform | **v0.8.0** (REUSE from DRQ-093) | — | the new headless gate |

Driver/runtime (not a version pin, but binding): **`minikube start --driver=docker
--container-runtime=containerd`** — already as-built in `setup-profile.sh`/`lib.sh`; the earlier
"podman" guidance is **superseded**.

---

## F. DRQ allocations (r10 — decisions.md continues from DRQ-094)

- **DRQ-095 — A/B-2 (RESOLVED = A):** ch.30 verification mode = **A** — user runs the minikube+
  Istio+LGTM sequence once and hands back trace/metrics/mTLS evidence → `verified-live (user-run)`
  with committed evidence. Build is identical to the (B) document-only path; this only controls the
  footer + whether evidence is captured.
- **DRQ-096 — the 3 OTel-instrumented services (OPEN, USER GATE):** **(A, recommended)** strangler-
  proxy + order-service + inventory-service (synchronous gRPC hero trace, no outbox hazard); vs
  **(B)** strangler-proxy + order-service + payment-service (async Kafka saga hop — requires DRQ-103).
- **DRQ-097 — injection mechanism:** per-Deployment pod-template **label** `sidecar.istio.io/
  inject: "true"` on the 8 app Deployments; postgres/kafka excluded; namespace unlabelled.
- **DRQ-098 — mTLS mode:** `PeerAuthentication` **STRICT** mesh-wide in `mea`, with a PERMISSIVE
  edge exception for the plaintext NodePort → strangler-proxy hop.
- **DRQ-099 — observability overlay shape:** single `grafana/otel-lgtm:0.36.0` all-in-one
  Deployment + ClusterIP(OTLP 4317) & NodePort(Grafana) Services + otelcol ConfigMap (compose port
  + the istio-mesh Prometheus-SD scrape receiver) + grafana-datasources ConfigMap + scrape RBAC;
  unmeshed (no sidecar label).
- **DRQ-100 — r10 pins:** Istio/istioctl 1.31.2; opentelemetry-distro 0.66b1 +
  opentelemetry-exporter-otlp-proto-grpc 1.45.0 (+ instrumentation 0.66b1); reuse grafana/otel-lgtm
  0.36.0, k8s v1.37.1, kubeconform v0.8.0; minikube floor v1.33.0. Corrects the track-plan guesses.
- **DRQ-101 — ch.30 CI posture:** NOT CI-gateable live; add a SINGLE separate additive
  `mesh-manifests.yml` (kubeconform-on-istio+observability-overlays, `*-ok`, no `paths:`,
  cluster-free). *Planner recommendation: add the kubeconform gate* (mirrors deploy-manifests.yml;
  keeps the overlays render-verified headlessly).
- **DRQ-102 — ch.32 §C reconciliation:** fill the Mesh/Observability/Tracing (H) row; re-confirm
  all "landed rNN" cells; ch.32 scorecard figure == §C; final-project framing.
- **DRQ-103 — (conditional, only if DRQ-096=B):** outbox trace-context propagation — additive
  nullable `traceparent` column on order-service's outbox + relay restore before aiokafka produce,
  so the Kafka-saga hero trace is one real trace; else document it as linked/separate.

---

## G. Gate for the orchestrator (present to the user before Phase 2)

1. **DRQ-095 / A/B-2 — RESOLVED = A** (user runs the live sequence and hands back evidence).
2. **DRQ-096 (OPEN)** — OTel trio **A** (proxy + order + inventory, synchronous, no outbox risk —
   *recommended*) or **B** (proxy + order + payment, async Kafka saga hop, pulls in DRQ-103)?
