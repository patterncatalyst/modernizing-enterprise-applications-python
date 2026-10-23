---
title: "Verification log"
layout: plan
---

Verification-status footers removed from reader-facing chapters (site chrome shows reader content only; banked here, plans collection output:false). One section per chapter, verbatim.

## 00-introduction

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; its claims point at artifacts the `examples/` tree makes checkable elsewhere in this book, from the six-context monolith and its deliberate smells (Part 3) to the behavior-equivalence suite and its gate (Chapters 10 and 7).*

## 01-prerequisites

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — the toolchain and commands it describes are reproducible from the project's own tracked files (`compose.yaml`, `.env.example`, `scripts/stack-up.sh`/`stack-down.sh`, `examples/00-monolith/README.md`); bring the stack up and confirm the Newman run above is green on a fresh clone before continuing to Part 3.*

## 02-project-ledger

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — it describes the project's decision-and-plan ledger; those artifacts are tracked in the repository, and the chapter itself runs no code.*

## 03-modernization-as-engineering

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; the Phase A/B measurements it cites are recorded under `examples/02-review-service/`, and the smells and coupling vocabulary it gestures at are made concrete in Chapters 9 and 13.*

## 04-strategies-and-assessment

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; its extraction-order argument is checkable against `examples/00-monolith/SMELLS.md`, and the strangler mechanics it names are built with running code in Parts 3 and 5.*

## 05-from-sdlc-to-adlc

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; the phases, gates, and ledger artifacts it describes are the ones this project actually uses, and Chapter 7 exercises them against checked-in evidence.*

## 06-agents-skills-mcp

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; the `lgtm-*` skills, the `AGENTS.md` governance pattern (`examples/02-review-service/AGENTS.md`), and the proxy's routing logic (`examples/01-strangler-proxy/app/main.py`) are all checkable in the repository.*

## 07-adlc-safety-net

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — it narrates real, checked-in evidence rather than producing new evidence of its own. The defect it centers on is recorded in the project's own test notes under `tooling/newman/`, and the commands it cites are reproducible against `examples/00-monolith`, `examples/01-strangler-proxy`, and `examples/02-review-service`.*

## 08-designing-the-monolith

*Verification status: <span class="status status--verified">verified</span>.
`examples/00-monolith` runs (`uv sync && manage.py migrate && manage.py seed
&& runserver`); its pytest suite and the Newman contract collection
(`tooling/newman/mea.postman_collection.json`) both pass green against it.
The monolith is now frozen and decommissioned from the live topology
(break-glass only); the pristine pre-extraction state this chapter
describes is preserved on `reference/monolith-before` and tag
`v0-monolith`.*

## 09-deliberate-smells

*Verification status: <span class="status status--verified">verified</span>.
All seven smells are grep-locatable in `examples/00-monolith` via
`grep -rn 'SMELL\[ch\.' .`; the two deterministic failure injections
(`CARD-DECLINE` → 402, `SHIP-FAIL` → 422) are exercised live by `tests/
test_checkout.py`, and the outbox cure is exercised by `tests/
test_outbox.py`. The monolith is frozen/break-glass only; this chapter
describes the pre-extraction "before" preserved on `reference/
monolith-before` and tag `v0-monolith`.*

## 10-testing-the-monolith

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes against `examples/00-monolith`'s real, throwaway
Postgres-backed test database; `tooling/newman/mea.postman_collection.json`
run against the live monolith is recorded green in `tooling/newman/
GOLDEN-BASELINE.md` (14 requests, 42 assertions, two consecutive clean
runs). The monolith is now frozen/break-glass; this chapter describes the
state preserved on `reference/monolith-before` and tag `v0-monolith`.*

## 11-ddd-and-hexagonal

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no new code runs here; every excerpt is quoted verbatim from `examples/00-monolith/` and `examples/02-review-service/`, independently checkable with `grep -rn 'SMELL\[ch\.' examples/00-monolith`.*

## 12-event-storming

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — every excerpt is quoted verbatim from `examples/00-monolith/`, and the `config/settings.py` topic constants are greppable in that tree.*

## 13-coupling-and-modular-monolith

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — `examples/00-monolith/` is unchanged from Chapter 10; every coupling score and excerpt above is drawn from that tree's source and `SMELLS.md`, both checkable with `grep -rn 'SMELL\[ch\.' examples/00-monolith`.*

## 14-strangler-fig-pattern

*Verification status: <span class="status status--verified">verified</span>.
The proxy's pytest suite and the live Newman equivalence run
(`tooling/newman/GOLDEN-BASELINE.md`) both pass against a real stack:
58/58 assertions green with the flag off, on, and reverted, and the
review-service-down negative check fails loudly as required, then recovers
once restarted.*

## 15-extraction-1-review-service

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes 11/11 against a real, throwaway Postgres container,
`ruff check` passes clean, and a live run on `:8001` was driven end to end
with `curl` covering list, filter, get, and both auth-failure and
authenticated-create paths. The flag cutover itself is verified separately
at the proxy/Newman level (ch.14); the Phase A numbers here are a measured
proxy, since Phase A code was never built, by design.*

## 16-content-based-routing-acl

*Verification status: <span class="status status--verified">verified</span>.
`tests/test_routing.py` (8 tests, including the two-flag independence case)
and `ruff check` both pass, and the live two-flag toggle was driven end to
end with `curl` against the real stack. The full Kafka-backed cutover
evidence for the notification flag specifically is ch.17's own
verification record; this chapter's own scope is the routing
generalization and the ACL concept, confirmed above.*

## 17-extraction-2-notification-service

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes 8/8 against a real, throwaway Postgres container
plus a Testcontainers integration test proving redelivery-yields-one-row
against a real Kafka broker; `ruff check` is clean and `alembic upgrade
head` creates the schema cleanly. The full async cutover is verified live
end to end in `tooling/newman/GOLDEN-BASELINE.md`'s NEWMAN-ASYNC lane:
66/66 assertions green in both flag states, and the negative check (service
killed) fails strictly then recovers to green on restart.*

## 18-shared-data-to-owned-data

*Verification status: <span class="status status--verified">verified</span>.
This is a planning and analysis chapter with no new code of its own; every
artifact it cites — `order/models.py::OrderItem`, its migration, and the
prior services' own shared-vs-owned docs — is real, already-built code,
confirmed via `manage.py migrate`/`sqlmigrate`. The extraction this chapter
plans is verified built and cut over in ch.19's own verification record.*

## 19-cdc-and-extraction-3-inventory

*Verification status: <span class="status status--verified">verified</span>.
`uv run pytest` passes 16/16 in `examples/04-inventory-service` (REST and
gRPC, including a concurrency race test stable across 5 repeated runs),
`ruff check` is clean, and `alembic upgrade head` seeds correctly. The full
cutover is verified live in `tooling/newman/GOLDEN-BASELINE.md`'s
NEWMAN-GRPC lane: 71/71 assertions green across both configurations,
net-zero stock confirmed by direct query, and a negative check that fails
strictly then recovers on restart. The Debezium CDC path is transition-only
infrastructure, exercised manually against the compose stack rather than by
the pytest/Newman CI gates.*

## 20-outbox-pattern-done-right

*Verification status: <span class="status status--verified">verified</span>. Every mechanism this chapter describes is live, already-shipped code exercised by the live cutover run in `tooling/newman/` against a real Postgres and Kafka broker — the redelivery and negative-check numbers cited above are quoted directly from that run's output. The ordering/cleanup/poison-message gaps are documented limitations confirmed by reading the relay code's own exception handling, not claims requiring a further run.*

## 21-event-sourcing-and-cqrs

*Verification status: <span class="status status--verified">verified</span>. The CQRS mechanism is live, already-shipped code exercised by the CQRS contract run in `tooling/newman/` against a real Postgres instance (50 requests/133 assertions, 0 failed, repeated across 4 runs); the projection-disabled negative quoted above is taken directly from that run's output. The CQRS-versus-event-sourcing scoping argument is analysis of already-verified behavior, not an independent claim.*

## 22-acid-to-acd

*Verification status: <span class="status status--verified">verified</span>. The synchronous-mode free-rollback claim is the same direct-query proof ch.19 already recorded. The ACD-mode claims — the PENDING window's real latency, the reachable stranded-payment deferral, and the isolation-anomaly analogs — are quoted from the live cutover run in `tooling/newman/` and the order service's own docstring, not re-derived here; the PACELC framing is analysis of that already-verified behavior.*

## 23-saga-and-extraction-4-payment

*Verification status: <span class="status status--verified">verified</span>. The full choreographed topology — monolith, payment/inventory/review/notification services, the strangler proxy, and a real Kafka broker — was brought up live for the cutover run in `tooling/newman/`: 95/95 and 89/89 assertions green across the forward and reversed runs, the negative check fails strictly then self-heals on restart, and double-delivery idempotency is proven independently at both the saga and inventory layers. No integration bug surfaced; the known stranded-payment-on-ship-fail gap (ch.22) remains open by design, deferred to the next extraction (ch.24).*

## 24-extraction-5-shipping-service

*Verification status: <span class="status status--verified">verified</span>. The full topology — monolith, inventory/payment/shipping services, the strangler proxy, and a real Kafka broker — was brought up live for the cutover run in `tooling/newman/`: the happy and ship-fail paths resolve correctly, reversibility and crash-resume are reproduced against a live restarted container, and the negative check fails as required. 6 consecutive stable runs followed the poll-script fix ch.25 covers; no application-code bug surfaced, only a test-harness one.*

## 25-failure-modes-and-resilience

*Verification status: <span class="status status--verified">verified</span>.
Every mechanism this chapter inventories is cited against a live run
already recorded in a prior chapter or `tooling/newman/GOLDEN-BASELINE.md`:
the gRPC deadline/503 translation, the two-layer outbox idempotency, the
proxy's 502 bridge, and the saga crash-resume proof. The new `tenacity`
retry in `enrich_client.py` is unit- and integration-tested, but its
retry-on-transient-failure branch was not independently fault-injected
against a live, killed-and-restarted monolith — that run remains the
highest-value thing a future iteration should confirm.*

## 26-communication-and-extraction-6-order

*Verification status: <span class="status status--verified">verified</span>. Every artifact cited is real, already-shipped code exercised end to end by `tooling/newman/`'s contract suite: the reversibility proof, the flagless proxy rewrite, a GraphQL contract bug found and fixed, the monolith-free contract suite (50 requests/133 assertions, 0 failed, repeated across two stability windows), and three negative checks each restored to 0 failed. Numbers are quoted directly from that evidence, not re-derived for this chapter.*

## 27-quarkus-microprofile-chassis

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no new runnable example; its scorecard is read directly from the services' own source (`config.py`/`main.py`/`errors.py` and the dependency declarations across the services), checkable with `grep -rl tenacity examples/*/pyproject.toml` and the matching checks for OpenTelemetry, Prometheus, and `pydantic_settings`.*

## 28-contracts-and-service-registry

*Verification status: <span class="status status--verified">verified</span>.
The drift claim is read directly from the payment- and
notification-service event schemas against `examples/07-order-service/
EVENTS.md`'s reference shape. Every registry claim is proven in
`examples/09-schema-registry-demo` under Testcontainers-managed Kafka and
Apicurio: a field-for-field round trip and a compatibility suite confirming
v2 accepted (`200`) and v3 rejected (`400`, `RuleViolationException`);
`demos/demo-schema-registry.sh` reproduces the identical progression
standalone.*

## 29-deployment-patterns

*Verification status: <span class="status status--verified">verified</span>. Both the base and the minikube overlay render with `kubectl kustomize` (23 resources each) and pass `kubeconform -strict` with zero invalid. Applying to a live cluster is out of scope for this chapter — the exact limit its own "Verifying without a cluster" section describes — not a manifest defect.*

## 30-mesh-observability-tracing

*Verification status: <span class="status status--verified">verified</span>.
`deploy/k8s/scripts/capture-ch30-evidence.sh` ran green on a live minikube
cluster (docker driver + containerd, Istio v1.30.5, the LGTM stack): all eight
app pods join the mesh 2/2, `istioctl x describe pod` reports `Workload mTLS
mode: STRICT`, `istio_requests_total` returns live series from Mimir, and the
hero trace resolves end to end in Tempo as **one connected trace** rooted at
`strangler-proxy`'s `POST` server span, spanning `order-service` (FastAPI
server span + two asyncpg writes) and `inventory-service`'s gRPC `Reserve` —
Envoy mesh spans wrapping the app-level OTel spans, exactly as Figure 30.2
describes. The scrubbed capture is committed under
`deploy/k8s/observability/evidence/` (`ch30-hero-trace.json`,
`ch30-istioctl-mtls.txt`, `ch30-metrics.txt`); every query runs in-cluster, no
port-forward.*

## 31-cicd-gitops-supply-chain

*Verification status: <span class="status status--verified">verified</span>.
`examples/10-supply-chain/demo.sh` was run live with `syft`/`grype` against
both the order-service and monolith Containerfiles: it generated both
CycloneDX SBOMs, scanned both with the project's grype policy, and exited
`0`. The required order-service gate passed clean (0 fixable Critical/
High); the reported-only monolith gate failed as expected, without
affecting the script's exit code.*

## 32-pattern-language-revisited

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — a docs-only reconciliation with no new runnable example; every verdict cites the chapter that proved it (Chapters 14 through 31), re-confirmed against each rather than assumed.*

## 33-appendix-openshift

*Verification status: <span class="status status--verified">verified</span>.
`openshift/capture-evidence.sh` ran all six checks green on a live OpenShift
Local 2.64.0 cluster (OpenShift 4.22.14): nine `:v1` ImageStream tags; every
app pod Ready under restricted-v2, Postgres/Kafka under nonroot-v2, otel-lgtm
under anyuid; both edge-TLS Routes answering; a happy-path checkout through the
strangler-proxy Route reaching `CONFIRMED`; OSSM 3 (Istio v1.30.5) with STRICT
mTLS rejecting a plaintext caller (exit 56) and Kiali reporting the namespace
`MTLS_ENABLED`; and OTLP traces for the instrumented services in otel-lgtm's
Tempo. The scrubbed run is committed under `openshift/evidence/2026-10-17/`.*
