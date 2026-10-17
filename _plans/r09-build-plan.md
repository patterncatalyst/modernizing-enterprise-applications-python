# r09 Build Plan — Part 9 (ch.29 Deployment Patterns) + Part 10 (ch.31 CI/CD & Supply Chain)

**Planner:** Opus (lgtm-relay Phase 1). **Status:** awaiting user approval (one OPEN decision: A/B-4). **Scope:** the two CI-verifiable, headless back-matter chapters per `_plans/backmatter-track-plan.md`. ch.30 (mesh, live) + ch.32 (Pattern Language Revisited) remain grouped at r10. **No live cluster at r09.**

This is the Python sibling of `~/Dev/modernizing-enterprise-applications` r09. The Java tree is a **structure reference to re-author, never copy** — the Python reality diverges in several ways that matter (see "Grounded reconnaissance").

## Grounded reconnaissance (binding facts this plan is built on)

- **8 services + their real ports** (from each `Containerfile`'s `EXPOSE`): `01-strangler-proxy` :8888 (edge), `02-review-service` :8001, `03-notification-service` :8002, `04-inventory-service` :8084 **+ :9004 gRPC**, `05-payment-service` :8085, `06-shipping-service` :8087, `07-order-service` :8088 (gRPC **client** of inventory, no second port), `08-graphql-gateway` :8090.
- **Health asymmetry is real and must be honored (DRQ-082):** `/health` exists on **6 of 8** services — **absent on `01-strangler-proxy` and `02-review-service`**. Deployments for those two use **`tcpSocket`** readiness/liveness probes; the other six use `httpGet /health`. Do not fake `/health` on proxy/review.
- **Config = env vars read by `Settings.from_env()` (DRQ-083)**, not Quarkus properties. The ConfigMap keys are this project's own names: `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `INVENTORY_GRPC_TARGET`, `HTTP_PORT`, and the topic names (`ORDER_PLACED_TOPIC`, etc.). Postgres creds go in a Secret. Each service owns its own Postgres **schema** on the one shared instance.
- **Migrations run on container start:** order-service's `CMD` is `sh -c "alembic upgrade head && exec uvicorn ..."`; the sibling services follow the same shape. In k8s this stays as the container command at r09 (documented); an `initContainer` split is noted as the production-grade alternative but not required for a render-only iteration.
- **Images:** every service builds from a `Containerfile` (UBI10 `python-314-minimal`, multi-stage, non-root `USER 1001:0`). The **monolith uses `Dockerfile`** (Django + gunicorn, `:8000`), not `Containerfile` — relevant to the A/B-4 "before" build.
- **compose.yaml / .env.example are infra-only and FROZEN at r09** — no app process runs as a compose service; r09 adds **no** new compose infra (Apicurio was the r08 addition). `deploy/k8s` is a *parallel* deployment surface, not a change to compose.
- **CI discipline (DRQ-086 precedent):** new gates are separate additive workflows with their own `*-ok` summary and **no `paths:` filter** (a path-filtered required summary job wedges the ruleset). `code-ci.yml`/`contract-gate`/`code-ci-ok` and `schema-registry.yml` are never touched. The Java `supply-chain.yml` violates both rules (has `paths:`, no `*-ok`) — the Python version **corrects** this to the `schema-registry.yml` shape.
- **Figures:** paired SVG + `.excalidraw` + `.py` under `assets/diagrams/` via `lgtm-diagram-generator`, house amber/Red-Hat-font style, matching r08's `chassis-scorecard.*` / `avro-*` figures. Chapters end with a `*Verification status:*` footer citing exact files (r08 ch.27/28 pattern).

## Approach

### ch.29 — Deployment Patterns (`deploy/k8s/`)
**Chosen:** a kustomize `base` + a single `overlays/minikube` overlay.
- `base/` — `namespace.yaml` (ns `mea`), `app-config.yaml` (ConfigMap `mea-app-config`, Python env names + per-service `*_DATABASE_URL`/schema + `KAFKA_BOOTSTRAP_SERVERS=kafka:9092` + `INVENTORY_GRPC_TARGET=inventory-service:9004`), `app-secret.yaml` (Postgres creds), eight `*-service.yaml` (Deployment+Service each, per-service ports/probes/resources/graceful-shutdown matching each service's actual shape; order-service has the 4-channel saga fan-in note + widest `terminationGracePeriodSeconds`), `infra/postgres-statefulset.yaml`, `infra/kafka-statefulset.yaml` (single-node, mirroring compose's KRaft env), `kustomization.yaml`.
- `overlays/minikube/kustomization.yaml` — `resources: [../../base]`, `images:` retag each `mea/<svc>` to `:1.0`, patch every app Deployment to `imagePullPolicy: Never` (no in-cluster registry; images `minikube image load`-ed), patch `strangler-proxy` Service to `NodePort` 30888 (the single off-cluster edge; everything else stays ClusterIP). The ch.30 Istio sidecar-inject labels + `../../istio`/`../../observability` sibling overlays are written as a **commented SEAM** with a one-line "wired in r10" note — **not active at r09**, so the overlay renders clean now.
- `scripts/` (`lib.sh`, `build-images.sh`, `setup-profile.sh`, `deploy.sh`, `teardown.sh`) + `README.md` — the live minikube path, documented and user-runnable, **not** exercised by CI.
- **Rejected:** Helm (that's the ch.33 OpenShift/CRC appendix's tool; kustomize is the generic-k8s choice here). **Rejected:** one flat manifest dir with no overlay (loses the base/overlay teaching point and the environment-specialization story). **Rejected:** per-service namespaces (the book's topology is one `mea` namespace, schema-per-service in one DB).

### ch.31 — CI/CD & Supply Chain (`examples/10-supply-chain/`)
**Chosen:** syft→grype→policy, scanning **container images** (the real deployable form — catches both Python-dependency and UBI base-layer CVEs, which a `uv.lock`-only scan would miss).
- `policy.yaml` — `fail-on: High` + `targets:` (order-service `after`, and — pending A/B-4=B — monolith `before`).
- `demo.sh` — for each target: build the image (`Containerfile`/`Dockerfile`), `syft <image> -o cyclonedx-json`, `grype sbom:<file>`, tally by severity, apply `fail-on`. Writes `evidence/` (SBOM + grype JSON + `summary.txt`). Same three steps as CI so "green locally" == "green in CI". On B, the monolith is expected to FAIL (message says so).
- `evidence/` — committed sample SBOM + grype JSON + `summary.txt` as point-in-time artifacts; `.gitignore` for regenerated runs.
- `README.md` — prereqs (syft/grype on PATH), the before/after thesis, the grype-DB-drift caveat.
- **Rejected:** scanning the source tree / `uv.lock` only (misses OS-layer CVEs, the whole point of supply-chain). **Rejected:** Trivy/Snyk (grype is the CNCF-adjacent, vendor-neutral, offline-DB choice consistent with the Java sibling and the "maintained OSS, no vendor-cloud" constraint). **Rejected:** SPDX format (CycloneDX matches the Java sibling + wide tool support).

### Workflows (both NEW, both the `schema-registry.yml` shape)
- `deploy-manifests.yml` — `changes` (no `paths:`) → `render` (pin kubectl v1.37.1; `kubectl kustomize deploy/k8s/base` and `.../overlays/minikube`; pipe into `kubeconform -strict` for **offline** schema validation and `kubectl apply --dry-run=client -f -` for client-side structural validation) → `deploy-manifests-ok` summary (`if: always()`, all-success-or-skipped).
- `supply-chain.yml` — `changes` (no `paths:`) → `sbom-scan` (checkout; build order-service image; `anchore/sbom-action@v0` syft CycloneDX; `anchore/scan-action@v7` grype `fail-build: true severity-cutoff: high`); **[A/B-4=B]** a separate `continue-on-error`/non-gating step builds + scans the monolith image and reports its findings without blocking → `supply-chain-ok` summary. **Explicitly corrects the Java sibling**'s `paths:`-filtered, `*-ok`-less shape.
- **Never touched:** `code-ci.yml`, `contract-gate`, `code-ci-ok`, `pages.yml`, `schema-registry.yml`.

## Steps (ordered, grouped into parallel-safe waves)

**GATE 0 (before Wave 1):** orchestrator resolves A/B-4 with the user. Default assumption for drafting = **B**.

### Wave 1 — build artifacts (3 parallel executors, disjoint trees)
- **W1-a (writer of `deploy/k8s/**` only):** create `base/` (namespace, app-config, app-secret, 8 service manifests with ports/probes matching each service — `tcpSocket` for proxy+review, `httpGet /health` for the six — resources, graceful shutdown, non-root securityContext; order-service saga fan-in), `base/infra/` (postgres + kafka StatefulSets), `base/kustomization.yaml`, `overlays/minikube/kustomization.yaml` (images/NodePort/`Never`, ch.30 seam commented), `scripts/*`, `README.md`. **Dep:** none. **Self-check:** `kubectl kustomize deploy/k8s/base` and `.../overlays/minikube` render.
- **W1-b (writer of `examples/10-supply-chain/**` only):** `policy.yaml`, `demo.sh`, `README.md`, `evidence/` samples + `.gitignore`. Reflect A/B-4 outcome in `policy.yaml` targets + `demo.sh`. **Dep:** none (references existing `Containerfile`/`Dockerfile`). **Self-check:** `shellcheck demo.sh`; local run if syft/grype present.
- **W1-c (writer of `.github/workflows/` — new files only):** `deploy-manifests.yml` + `supply-chain.yml` in the `changes`/gate/`*-ok` shape, pins above. **Dep:** none; must not edit any existing workflow. **Self-check:** `actionlint`.

### Wave 2 — author chapters (2 parallel executors)
- **W2-a (writer of `_docs/29-deployment-patterns.md` + `assets/diagrams/deploy-k8s-*` only):** ≥2000w re-authored in house voice, citing W1-a files by path; sections ≈ compose→cluster, the deploy tree, images (UBI10 non-root), config-as-data (ConfigMap/Secret with the real env names), liveness/readiness (**the 6/8 asymmetry explained** — proxy and review have no `/health`, so they use `tcpSocket`), resources, rolling update + graceful shutdown (order-service fan-in), the strangler as the single ingress, in-cluster infra, **"Verifying without a cluster"** (what offline validation covers: `kubectl kustomize` renders offline, `kubeconform`/`--dry-run=client` validate offline; server dry-run / admission / webhooks need a live cluster — deferred to the user's minikube / r10 ch.30), ADLC callout, verification footer. One figure (`lgtm-diagram-generator`). **Dep:** W1-a.
- **W2-b (writer of `_docs/31-cicd-gitops-supply-chain.md` + `assets/diagrams/supply-chain-*` only):** ≥2000w; the pipelines this repo actually ships (`code-ci.yml` equivalence/contract gates, `schema-registry.yml`, the new `deploy-manifests.yml`/`supply-chain.yml`), the flag-gated progressive delivery the strangler already did, SBOM→scan→policy-as-code, the **before=FAIL/after=PASS** evidence (per A/B-4), GitOps named-and-scoped, ADLC callout, verification footer. One figure. **Dep:** W1-b, W1-c.

### Wave 3 — validate + reconcile (1 serial executor; Phase-3 territory)
- `lgtm-professional-voice` scan (0 ban-tier) across `_docs/29`,`_docs/31`.
- `lgtm-idiomatic-review` over the YAML/kustomize + bash + workflow YAML.
- Headless proofs: `kubectl kustomize` both dirs + `kubeconform -strict`; `examples/10-supply-chain/demo.sh` (expect after=PASS, before=FAIL-reported on B).
- `bundle exec jekyll build` exit 0 + nav/`_parts` intact.
- Ledger updates (**writer of `_plans/` only**): `decisions.md` DRQ-088..093; `reconciliation.md` new r09 section + r10 forward-ref; `build-plan.md` status row for r09. Correct the Java-shape note on `supply-chain.yml`.

**Executor count:** 3 (W1) + 2 (W2) + 1 (W3) = 6 slots across 3 waves.

## Acceptance criteria (checkable)
1. `_docs/29-*.md` and `_docs/31-*.md` each **≥2000 words**, with **≥1 figure** (SVG+excalidraw+py committed), an **ADLC callout**, and a **verification footer** citing exact files.
2. `kubectl kustomize deploy/k8s/base` **and** `deploy/k8s/overlays/minikube` render with **exit 0**; output passes `kubeconform -strict` and `kubectl apply --dry-run=client -f -`. The headless limit (no server dry-run / admission without a cluster) is stated in ch.29 and `deploy/k8s/README.md`, scoped to what offline validation actually covers.
3. `deploy/k8s/overlays/minikube` renders clean with the **ch.30 Istio/observability seam left commented** (no dangling `../../istio` reference at r09).
4. Probes honor reality: `tcpSocket` for strangler-proxy + review-service; `httpGet /health` for the other six.
5. `examples/10-supply-chain/demo.sh` runs syft→grype→policy and writes `evidence/`; **order-service (after) = PASS**; **[B]** monolith (before) = FAIL, reported as expected.
6. `supply-chain.yml` is **green** on the gating target (fail-on High on order-service); **[B]** monolith scanned non-gating/reported; shape = `changes`/gate/`supply-chain-ok`, **no `paths:`**.
7. `deploy-manifests.yml` **green**; shape = `changes`/render/`deploy-manifests-ok`, **no `paths:`**.
8. `code-ci.yml`, `contract-gate`, `code-ci-ok`, `pages.yml`, `schema-registry.yml`, `compose.yaml`, `.env.example` **unchanged** (`git diff` empty for these).
9. `lgtm-professional-voice` = **0 ban-tier**; `lgtm-idiomatic-review` clean on new YAML/bash.
10. `jekyll build` exit 0; Part 9 / Part 10 nav intact; `_plans` ledgers updated (DRQ-088..093, r09 reconciliation section).

## Risks (and how Phase-3 detects each)
- **grype DB drift / point-in-time.** A High CVE in the UBI base or a Python dep can appear *after* the evidence was committed and turn a green gate red (or vice-versa). *Detect:* `demo.sh` prints `grype db status` (built date); README + ch.31 footer state the committed `evidence/` is point-in-time; CI uses the live DB, so a failure is read as a real new finding, not a regression. Mitigation if a transient High blocks the gating "after": pin/triage via a documented grype ignore with a justification, never by silently lowering `fail-on`.
- **Renders-but-wouldn't-apply.** `kubectl kustomize` + `kubeconform` validate structure/schema, not cluster admission (defaults, webhooks, RBAC, PVC binding). *Detect:* ch.29 + README state this limit explicitly; the live minikube path is user-runnable via `scripts/` and deferred to r10 ch.30, not claimed as CI-verified.
- **New gate wedges the ruleset.** A `paths:`-filtered required summary job reports nothing on unrelated PRs and blocks merges. *Detect:* both new workflows copy the `schema-registry.yml` `changes`→gate→`*-ok` shape with **no `paths:`**; `actionlint` + a review check that `*-ok` is `if: always()` and all-success-or-skipped.
- **Monolith "before" image build (A/B-4=B).** The Django/gunicorn `Dockerfile` must build in CI for the non-gating scan; a build break there must **not** block the gating "after". *Detect:* monolith build+scan is a `continue-on-error` step; `supply-chain-ok` depends only on the order-service result; demo.sh builds the monolith in its own subshell.
- **Pin availability.** syft/grype/anchore-actions/kubectl/kubeconform tags can move. *Detect:* exact pins recorded in DRQ-093 and in each workflow comment with the survey date; Phase-3 re-resolves on failure. Note scan-action is **v7** (Java used v6) and syft/grype are far ahead of the track plan's placeholders.
- **Accidental edit to a protected file.** *Detect:* acceptance #8 — `git diff` must be empty for `code-ci.yml`/`contract-gate`/`code-ci-ok`/`pages.yml`/`schema-registry.yml`/`compose.yaml`/`.env.example`.
- **Health-probe authenticity.** Copying Java's uniform smallrye-health probes would fake `/health` on proxy+review. *Detect:* review each Deployment's probe type against the 6/8 reality.

## New pins (surveyed upstream latest-stable 2026-10-17; track-plan placeholders corrected)
| Tool | r09 pin | Track-plan placeholder | Note |
|---|---|---|---|
| syft | **v1.54.1** | ~1.44 | corrected (released 2026-10-06) |
| grype | **v0.120.1** | ~0.112 | corrected (released 2026-10-06) |
| anchore/sbom-action | **@v0** (v0.24.3) | @v0 | confirmed |
| anchore/scan-action | **@v7** (v7.4.2) | @v6 | **corrected: v6→v7** |
| kubectl (for `kubectl kustomize` + dry-run) | **v1.37.1** | (unspecified) | latest stable k8s; bundles kustomize v5.7.x |
| kustomize (standalone ref) | **v5.8.3** | (unspecified) | reference only; CI uses `kubectl kustomize` |
| kubeconform | latest stable | (unspecified) | offline schema validation in `deploy-manifests.yml` |

minikube / live-k8s version stays an r10 (ch.30) concern. No new Python package pins at r09 (deploy + supply-chain are tooling, not app deps). compose/.env pins unchanged.

## DRQ allocations (reserve; last existing id = DRQ-087)
- **DRQ-088** — A/B-4 resolution: supply-chain scan scope = **order-service + frozen `00-monolith` "before"** (recommended B), monolith non-gating/reported, order-service hard-gated. *[pending user]*
- **DRQ-089** — deploy topology: kustomize `base` + single `overlays/minikube`; one `mea` namespace, schema-per-service; probes matching each service (6/8 `httpGet /health`, tcpSocket for proxy+review); NodePort only on the strangler edge; ch.30 Istio/observability left as a commented seam.
- **DRQ-090** — supply-chain policy: `fail-on: High`, policy-as-code in committed `policy.yaml`; SBOM target = **container image** (CycloneDX), not source tree.
- **DRQ-091** — `deploy-manifests.yml`: new separate additive gate, `changes`/render/`deploy-manifests-ok`, no `paths:`; offline render + `kubeconform`/`--dry-run=client`.
- **DRQ-092** — `supply-chain.yml`: new separate additive gate, `changes`/`sbom-scan`/`supply-chain-ok`, no `paths:`; **corrects the Java sibling's `paths:`-filtered, `*-ok`-less shape**; anchore sbom-action@v0 + scan-action@v7.
- **DRQ-093** — r09 pins: syft v1.54.1, grype v0.120.1, scan-action v7, kubectl v1.37.1, kubeconform latest (survey 2026-10-17).
