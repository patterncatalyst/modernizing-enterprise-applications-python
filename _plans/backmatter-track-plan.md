# Back-matter Track Plan — Parts 8–10 (ch.27–32)

**Planner:** Opus (lgtm-relay). Status: awaiting user approval. Strangler fig is complete; these 6 chapters are r01 stubs. ch.33 (OpenShift) is a separate later track.

## Sub-iteration breakdown (grouped by verification class; isolate the one live-env chapter)
- **r08 — Part 8: chassis + registry** — ch.27 (FastAPI Chassis, synthesis/prose) + ch.28 (Contracts & Service Registry, RUNNABLE). Adds `examples/09-schema-registry-demo/` (fastavro + aiokafka + Apicurio v3 REST), `apicurio` to compose, `demos/demo-schema-registry.sh`, a new additive `schema-registry.yml` CI gate (testcontainers Kafka+Apicurio). **CI-verifiable, no live cluster.**
- **r09 — Part 9 deploy + Part 10 supply chain (both CI-verifiable headless)** — ch.29 (Deployment Patterns, `deploy/k8s/` kustomize base+overlays/minikube) + ch.31 (CI/CD + Supply Chain, `examples/10-supply-chain/` syft→grype→policy). New additive `deploy-manifests.yml` (`kubectl kustomize` + client dry-run) + `supply-chain.yml` (anchore sbom+scan). **No cluster.**
- **r10 — mesh (live, user-run) + final project (prose)** — ch.30 (Mesh/Observability/Tracing — Istio + LGTM on minikube, OTel added additively to 3 services) + ch.32 (Pattern Language Revisited, prose). ch.30 **needs the user's live minikube/Istio env** — document-or-user-run verification, no CI gate. ch.32 docs-only.

Rationale: ch.30 structurally depends on ch.29's `deploy/k8s/base`; isolating ch.30 keeps the un-CI-gateable chapter out of any CI-gated merge. (Diverges slightly from §J which lumped 29+30+31.)

## Key reconnaissance (drives honest authoring)
- **ch.27 chassis scorecard is the REAL state (not the build-plan's claims):** config is a frozen `@dataclass Settings.from_env()`, **NOT pydantic-settings** (correct the §C/§A.3 claim in prose); `/health` on **6 of 8** (absent in proxy + review); **no OTel/metrics** anywhere (deferred; ch.30 adds OTel to 3 services); **tenacity only in shipping**, pybreaker/bulkhead deferred; stdlib logging to `logs/`, not structlog; every service has a Containerfile.
- **compose has NO Apicurio yet** (ch.28 adds it).
- **ch.28 Avro client:** DRQ-033 explicitly REJECTED confluent-kafka → use **fastavro + aiokafka + Apicurio v3 REST** (pure-Python; hand-roll the schema-id envelope). Verify the Apicurio v3 REST contract + id-envelope LIVE against the pinned image (Java hit 409→400 status drift across versions).
- **Drift anecdote must be re-derived:** Python's real per-service drift ≠ Java's "notification missing paymentMethod" — read the actual order-service producer payload + payment/notification `schemas.py` and tell Python's true story.
- **CI discipline:** new gates = SEPARATE additive workflows with their own `*-ok` summary; never touch `code-ci.yml`/`contract-gate`/`code-ci-ok` or add `paths:` (a path-filtered required summary job wedges the ruleset).

## USER DECISIONS (A/B) — recommendation in **bold**
1. **ch.28 Avro client:** **(A) fastavro + aiokafka + Apicurio v3 REST** (pure-Python, consistent with DRQ-033) vs (B) confluent-kafka[avro] (pulls librdkafka, contradicts DRQ-033). → **A**.
2. **ch.30 verification (r10):** **(A) you run the minikube/Istio sequence once and hand back the trace/metrics/mTLS evidence → chapter `verified-live (user-run)` with committed evidence** vs (B) document-only, `deferred (requires live minikube/Istio)`, no captured evidence. → **A** (matches the Java/datamesh honest-live posture); B if no cluster this cycle. (Applies at r10.)
3. **Build the runnable demos (examples/09 + examples/10) vs prose-only:** **(A) build both + their CI gates** (artifacts actually run, matches Java) vs (B) prose-only (loses the registry round-trip + SBOM/CVE gate — a regression vs Java). → **A**.
4. **ch.31 supply-chain scope:** scan order-service only (clean "after") vs **order-service + the frozen 00-monolith** (reproduces the before=FAIL / after=PASS thesis-made-measurable). → **include the monolith "before"** (it's frozen-but-present).
5. **Sub-iteration grouping:** **r08=(27,28) / r09=(29,31) / r10=(30,32)** vs r09=(29,30)/r10=(31,32). → **the former** (isolates the live-env chapter).

## Acceptance criteria (per sub-iteration) — see the plan; headline:
- r08: ch.27/28 ≥2000w + figures + ADLC callout + footer; examples/09 round-trip + compatibility tests green (v2 accept, v3 reject with the ACTUAL observed status) via testcontainers; apicurio in compose+.env (blast-radius comment; live JSON flows untouched); schema-registry.yml green; contract-gate untouched/green; demo-schema-registry.sh green.
- r09: ch.29/31 ≥2000w + figures; deploy/k8s renders under kubectl kustomize + client dry-run (headless limit documented honestly); examples/10 demo + supply-chain.yml green (fail-on High); deploy-manifests.yml green; code-ci-ok green.
- r10: ch.30 ≥2000w + figures + manifests + OTel-on-3-services; verification HONEST (user-run evidence OR deferred, deferred items named not faked); ch.32 ≥2000w + §C pattern-matrix reconciled.

## New pins (verify-before-merge; could not skopeo/web from the planner): Apicurio `quay.io/apicurio/apicurio-registry:3.3.3`; fastavro (latest stable, ~1.10.x); opentelemetry-distro + exporter-otlp (3 services, r10); Istio ~1.31.x + istioctl; minikube ~1.39 / k8s ~v1.36.x (r10); syft ~1.44 / grype ~0.112 + anchore sbom-action@v0 / scan-action@v6 (r09); reuse grafana/otel-lgtm 0.36.0, testcontainers 4.15.0, httpx 0.28.1, aiokafka 0.14.0.

## Risks: ch.30 needs user env (author fully, gate on user-run evidence, never fake a trace); Apicurio/Avro REST+id-envelope must be live-verified; grype DB drift (point-in-time); new gates must stay separate from code-ci-ok; single-writer for shared-root files (compose/.env/deploy); re-derive the Python drift story; keep titles aligned with §B.2.
