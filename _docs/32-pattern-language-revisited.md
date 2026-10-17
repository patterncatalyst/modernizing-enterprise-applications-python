---
title: "The Pattern Language, Revisited"
order: 32
part: "Delivering & Reflection"
description: "The microservices pattern catalog re-walked against the completed migration: which patterns earned a lasting role, which were adapted into a narrower shape, which stayed named and scoped out, the anti-patterns of over-decomposition, the chassis in 2026, and the ADLC retrospective."
duration: 35 minutes
---

Thirty-one chapters ago this book opened a single Django monolith with six
apps and five seeded smells. Chapter 26 closed the last extraction: six
independently deployable services plus a data-less GraphQL gateway, reached
through one flagless router with no monolith left to fall back to. Chapters
27 through 31 then did something no single extraction chapter could —
stepped back from any one service and asked what the finished system as a
whole does with the cross-cutting concerns (chassis, contracts, deployment,
mesh, delivery) that no bounded context owns alone. This chapter is the
book's final project: not a new extraction, not a new runnable example, but
a walk back through the entire pattern catalog this project started from —
the same ~45-row matrix in `_plans/build-plan.md` section C that was filled
in one claim at a time, chapter by chapter, across ten iterations — now that
every claim in it can be checked against a finished system instead of a
plan.

The walk uses three verdicts, and only three, because three is what the
matrix actually supports once you read the Note column chapter by chapter
instead of taking the deck's pattern list at face value. **Earned**: the
pattern shipped, in roughly the shape the microservices literature
describes it, and the system would be worse without it — the strangler fig,
the outbox, both saga shapes. **Adapted**: the pattern shipped, but in a
narrower or differently-scoped form than its usual description — a chassis
that is a copied convention instead of a shared library, a schema registry
scoped to one demonstrator instead of every event topic, a service mesh
with observability depth on three services out of eight instead of all of
them. **Named, deferred**: the pattern was never built, and the chapter
that could have built it says so in the same paragraph, with the condition
that would change the answer — full event sourcing, a circuit breaker, a
GitOps operator. A matrix with 45 rows and no deferred column would be
describing a different project than the one this book actually built.

## The pattern language, pattern by pattern

Start with the spine, because everything else in this project only exists
downstream of it. The **Strangler Fig + ASGI reverse-proxy façade** (ch.14)
is the one pattern every other extraction routed through — `STRANGLER_*`
flags toggled per bounded context, the façade itself never carrying domain
logic, only routing decisions. By ch.26 the façade was flagless: every
`*_enabled` boolean and the monolith fallback path were removed, an
unmatched route returns 404 instead of a monolith call, and the monolith
itself sits frozen-not-deleted behind a `reference/monolith-before` branch
and `v0-monolith`/`stage/01..06` tags. **Verdict: earned.** A six-context
migration with one proxy and six flags is a different claim than a
six-context migration with six bespoke reverse-proxy configurations, and
this project only had to write the façade once.

**Content-Based Routing and the Anti-Corruption Layer** (ch.16, ch.19) did
two different jobs at two different seams, which is itself the finding
worth carrying forward: ch.16's router picked a backend by URL path, a
one-dimensional decision; ch.19's `inventory.proto` is the harder case,
a wire contract kept distinct from both the monolith's domain
vocabulary and inventory-service's own, translated at both ends, with a
drift guard (`scripts/check-proto-drift.sh`) that fails the moment the
checked-in `.proto` and the generated stubs disagree. **Verdict: earned,**
and the two instances are evidence the pattern generalizes past its most
common definition (a translation layer against a legacy system) to any
synchronous seam where two services are allowed to evolve their own
vocabulary independently.

**Shared Data → Owned Data**, with Change Data Capture as the bridge
between them (ch.18, ch.19), is the one pattern this book can show at every
stage of its own lifecycle in a single service. The review extraction
stayed on the monolith's shared schema — a named deferral, not an oversight
— while inventory moved to an owned `inventory` schema fed during the
transition window by a Debezium connector tailing Postgres's write-ahead
log, then **retired** once the owned schema was the only reader. The CDC
connector's own runbook (drain, delete connector, drop the replication slot
and publication, disable the flag) is what makes this one adapted rather
than earned outright: Transaction Log Tailing was never meant to be a
permanent fixture, and the project confirms it never became one — `grep`
for Debezium in the CI gates today and it is not there. **Verdict: owned
data is earned; CDC/log tailing is adapted — real, used, and retired on the
schedule it was always supposed to follow.**

**Synchronous gRPC** (ch.19) is the project's only strongly-typed,
low-latency inter-service call, and it earned that narrow scope rather than
spreading to every seam: order-service's `Reserve` call into
inventory-service is an atomic conditional `UPDATE`, race-tested under
concurrent reservation attempts, with a compensating `Release` issued
*outside* any local transaction — because the moment a reservation crosses
a process boundary, the free rollback a single database transaction used
to provide is gone, and the saga chapters exist precisely to replace it.
**Verdict: earned**, for exactly the one seam where strong typing and a
tight latency budget mattered enough to justify a second wire protocol
alongside REST.

**The Transactional Outbox** (ch.17, ch.20) is the pattern this project
leaned on hardest, and the two chapters that cover it tell different halves
of the same story. Chapter 17 introduces it to cure two smells at once —
a synchronous out-of-process call inside an HTTP request, and a dual-write
race between a database commit and a message publish — by making the
outbox row and the domain write land in the same local transaction; a
declined or failed checkout leaves zero outbox rows, proven by test, not
asserted. Chapter 20 returns to the pattern against a second, more mature
instance (payment-service's own outbox publishing `payment.captured` and
`payment.declined`) and generalizes the shape: one transaction, an
at-least-once relay, and an idempotent consumer on the other end — a check-
then-insert, an upsert, or a status-transition guard, whichever fits the
write. **Verdict: earned**, and earned twice over, since a pattern proven
once in a monolith's own outbox and proven again in a standalone service's
outbox is a stronger claim than either instance alone.

**CQRS** (ch.21, ch.26) and **ACID → ACD** (ch.22) are two sides of the
same architectural cut, so the matrix homes them separately but this walk
treats them together. Breaking one shared Postgres transaction that used
to span order, payment, and shipping into order-service's own local
transaction — spanning only its own `order_svc` schema — is what makes a
`PENDING` order visible and real before payment or shipping has an opinion
on it; `order_view`, a same-database, same-transaction read model updated
by every write path, is what makes that `PENDING` state readable without a
second query touching write tables directly. `rebuild_order_view` proves
the projection is a rebuildable cache, not a second source of truth; a
projection-disabled negative test proves the read side does not silently
fall back to the write tables when the sync stops. **Verdict: earned for
both** — the Isolation gap ACD accepts (a PENDING order visible before its
saga resolves) is a real cost, named as a cost in ch.22, in the open rather
than buried under the pattern's name.

**Event Sourcing** (ch.21) gets its own line because the matrix's own Note
makes a finer claim than "built" or "not built": the chapter teaches the
*outbox-as-event-log* framing against order-service's own `order.placed`
outbox — a durable, ordered, replayable record of what happened — without
building full event-sourced replay (rebuilding current state purely by
folding every historical event). **Verdict: adapted.** The light version
answers the question this project actually had (can a reader audit what
happened to an order); full event sourcing answers a different, harder
question (can the system's current state be reconstructed from nothing but
its event history) that no chapter needed to answer yet.

**Saga, both shapes** (ch.23 choreographed, ch.24 orchestrated), is where
this book makes its sharpest architectural contrast: the same
kind of problem — a multi-step operation across service boundaries that
needs to compensate on partial failure — solved two structurally opposite
ways. Payment's choreographed saga has no box anywhere that knows the whole
sequence; the sequence emerges from three independent event subscriptions
reacting to events, one hop at a time. Shipping's orchestrated saga
re-embeds the reused CNDP Python DB-backed coordinator — `select(...)
.with_for_update()`, an idempotent `advance()`, a reverse-order
`compensate()` — as one process that calls every step and owns the decision
to undo. The orchestrator's `resume_running_sagas()` is itself a durability
upgrade over its own Java sibling's in-memory coordinator: a crash mid-saga
resumes from its last persisted step instead of losing the saga's progress
entirely. **Idempotent Compensation** (also ch.23) closes the gap gRPC's
`Reserve`/`Release` pair opened: a compensating `Release` survives
redelivery at both the Kafka-event layer (a status-transition guard in the
saga listener) and the RPC layer (inventory-service's own
`idempotency_key` ledger), proven live by stock held constant across forced
redelivery on both paths. **Verdict: earned, all three** — a project that
only ever needed choreography, or only ever needed orchestration, would not
have this chapter's contrast to teach from.

**Circuit breakers, service discovery, and health** (ch.25, ch.27) earned a
narrower shape than their Netflix-OSS-era framing suggests. The resilience
this system actually has is concrete and distributed across existing
mechanisms rather than a new named component: a gRPC deadline, the outbox's
at-least-once delivery plus two-layer idempotency, the strangler proxy's
502 fail-safe when a backend is unreachable, the orchestrator's own crash-
resume. The one actually new mechanism r06 added was a `tenacity`
retry-with-timeout wrapping the shipping saga's one outbound HTTP call
(`enrich`). A circuit breaker (`pybreaker`) and a bulkhead were named in
planning prose and never built. **Verdict: adapted** — the mechanisms that
exist are real and load real traffic paths; the two that do not exist are
missing because no second failure mode in this system's eight services has
yet forced the question, not because anyone forgot to ask it.

**The Microservices Chassis** (ch.27) is where "every service does this
the same way" gets its own chapter instead of staying implicit, and its own
scorecard is blunt about the gap between a convention and a library:
config (a frozen `@dataclass` with `from_env()`, 7 of 8 services) and
logging (stdlib `RotatingFileHandler`, 8 of 8) are copied into each service
by hand, not imported from one shared package. `/health` (6 of 8) and
`errors.py` (6 of 8) each have a stated, structural reason for their gap
rather than an unexplained one. **Verdict: adapted** — the chassis exists
and every service runs on it, but "exists" here means eight near-identical
files, not one versioned dependency, a trade-off ch.27 argues is the
correct one for eight services that still redeploy independently of each
other.

**Deployment patterns** (ch.29) landed as kustomize `base` plus a single
`overlays/minikube` tree: 8 app Deployments, a shared `postgres`
StatefulSet with schema-per-service chosen in each service's own code (not
a per-service connection string, a build-plan assumption ch.29's own build
caught and corrected before shipping), and probes that honor each service's
actual health surface — `tcpSocket` for the two services with no `/health`
route, `httpGet /health` for the other six. Both trees render clean under
`kubectl kustomize` and pass `kubeconform -strict`, 23 of 23 resources
Valid in each. **Verdict: earned**, with a headless-render limit stated in
the same chapter it could be read as exceeding: offline rendering and
schema validation are not the same claim as a live cluster admitting and
scheduling the same manifests, and ch.29 says so rather than implying
otherwise.

**Contracts and the Service Registry** (ch.28) is the clearest example in
this project of a pattern scoped to prove a point rather than to cover
every surface it could apply to. `examples/09-schema-registry-demo/`
registers one Avro schema with Apicurio, resolves it by a hand-rolled
global-id wire envelope (no Confluent serde in this pure-Python lane), and
demonstrates both halves of compatibility checking live — a field addition
with a default is accepted, a field retype is rejected with a 400. Every
other event this project publishes still ships as a hand-authored JSON
contract with no registry behind it. **Verdict: adapted** — the mechanism
is real and verified, not simulated, but it answers "can this project use a
registry" rather than "does every event in this project go through one."

**Service Mesh, Observability, and Distributed Tracing** (ch.30) closes
the deployment story ch.29 opened, and it is the pattern whose verdict
depends most directly on telling apart two different kinds of telemetry.
`deploy/k8s/istio/` makes `mea` a real mesh: `PeerAuthentication` STRICT
mesh-wide, enforced by the receiving Envoy sidecar, with one named
exception — a PERMISSIVE override at the plaintext NodePort edge where
traffic enters from outside the mesh — and the opt-in mechanism is a
pod-template **label**, not an annotation, because the sidecar-injection
webhook's object selector matches labels and an annotation would inject
nothing in an unlabeled namespace. `deploy/k8s/observability/` puts a
`grafana/otel-lgtm` all-in-one backend in-cluster, reachable over OTLP, fed
in part by a Prometheus scrape of every Envoy sidecar's own stats. That
mesh layer gives every one of the eight services request-level telemetry —
spans, mTLS state, a service graph — with zero application code changed. What it cannot give is in-process depth: a database query, a
business-logic branch, a specific SQL statement. That is what app-level
OpenTelemetry auto-instrumentation on exactly three of the eight services —
strangler-proxy, order-service, inventory-service — adds, rooted at the
synchronous `POST /api/orders` → gRPC `Reserve` path precisely because that
path crosses no outbox and needs no extra trace-context plumbing to stay
one connected trace end to end. The Kafka saga hops stay visible at the
mesh layer only; an application-level span crossing a Kafka produce/consume
boundary would need a `traceparent` persisted through the outbox and
restored by the relay before publish, a piece of plumbing this project
named as a condition rather than building speculatively. **Verdict:
adapted** — mesh-wide mTLS and telemetry are earned outright across all
eight services; in-process tracing depth is earned on three of eight by a
stated design choice, not a shortfall discovered too late to fix.

**REST, gRPC, and GraphQL side by side** (ch.26) and the **API Gateway**
evolution it represents landed as one additive, data-less Strawberry
gateway fanning a single `order(id)` query out to five underlying sources
— three REST, one gRPC, one REST-per-item — each field resolved lazily and
nullable, so one failing source degrades a field to `null` and an `errors`
entry instead of failing the whole query. **Verdict: earned** — three
protocols, each kept to the one seam it fits best (REST for every service's
own surface, gRPC for the one hot synchronous path, GraphQL for bounded
aggregation at a gateway with no data of its own), is a stronger claim than
picking one protocol and forcing every seam through it.

**CI/CD and Supply Chain** (ch.31) is where the last new verified result in
this book's build landed, and it landed harder than the plan that preceded
it expected: scanning order-service and the frozen monolith with
syft and grype surfaced 35 High-severity findings in both images, all in
the shared UBI base layer, all `fix-state: not-fixed` — no patched tag
available to re-pin onto, confirmed with `skopeo` rather than assumed. The
resulting gate — fail on fixable findings only — still surfaces every one
of the 35 unfixable Highs in the scan's own `ignoredMatches` output; it
does not lower the bar, it narrows what the bar can hold a merge
responsible for fixing. **Verdict: earned**, and the harder-than-planned
result is itself evidence the gate checks something real rather than
rubber-stamping a known-green scan.

{% include excalidraw.html file="pattern-language-map" alt="Two chained rows of patterns across the book's chapters, colored by verdict. Row one (ch.14-24): Strangler Fig, ACL plus gRPC seam, Transactional Outbox, CQRS, Saga Choreographed, Saga Orchestrated, all accent (earned). Row two (ch.27-31): Contracts and Schema Registry and Microservices Chassis in user-blue (adapted), Deployment in accent (earned), Service Mesh plus Observability in user-blue (adapted, mesh earned/OTel on 3 of 8), CI/CD plus Supply Chain in accent (earned). A ghost row below names five further horizons connected by dashed arrows from the pattern each would extend: full event sourcing from CQRS, pybreaker/bulkhead from the chassis, a GitOps operator plus canary from deployment, Loki log aggregation and Kafka saga-hop tracing both from service mesh plus observability." caption="Figure 32.1 — The pattern language as one connected flow, colored by verdict" %}

## The anti-patterns of over-decomposition

A pattern-coverage matrix this long invites a question the matrix itself
cannot answer: given forty-five rows of patterns this project could have
reached for, why does the finished system have eight services and not
twenty? The answer sits in a row the matrix marks as a trap rather than a
destination — **Modular Monolith with decomposed databases** (ch.13,
ch.18) — and in one more observation: every one of the six real
extractions this book shipped was triggered by a named smell the monolith
already had, not
by a target service count decided in advance.

The distributed-monolith trap is what happens when a team splits a
database along service boundaries before splitting the code that owns it,
or splits the code before anything forces a database split at all: the
result looks decomposed — multiple schemas, multiple deployables — but
every one of those pieces still has to change in lockstep, because nothing
about the split removed the coupling that made them one system in the
first place. It is strictly worse than the monolith it replaced: the
monolith's single transaction at least gave atomic consistency without
asking; the decomposed version gives up that consistency and gets
independence in return for nothing, because the services still cannot deploy, migrate, or
fail independently of each other. Chapter 18 names this trap directly
rather than let a reader discover it by building it. Every real extraction
in this project earned its database split by a different, concrete
mechanism each time — notification's event-driven seam needed no shared
schema at all from day one; inventory's CDC backfill gave it a bridge
across a live cutover window before retiring; order's CQRS projection gave
it a read path that never touches another service's write tables. None of
the six extractions split a schema first and found a reason for the split
afterward.

The context-aligned "right size" this project settled on is six bounded
contexts plus a gateway with no data of its own — not a number chosen in
advance, but a number that happened to fall out of following the smell
list to its end. A nanoservice-sprawl architecture for the same problem
domain — a `create-order-id` service, a `validate-sku` service, a
`send-confirmation-email` service — would have the same forty-five-pattern
catalog available to reach for and would reach for most of it for the
wrong reason: more services to coordinate, more network calls per request,
more places a single business rule can drift out of sync with its sibling
copies, with no corresponding gain in independent deployability, because
services that only make sense called together are not actually independent
no matter how many separate repositories they live in. The test this
project applied at every extraction decision, explicitly, was whether a
named smell in the existing monolith demanded the split — a sync-send
inside a transaction, a shared-table race, a God object doing five jobs at
once — not whether a textbook diagram suggested a boundary existed. Six
extractions against five smells is evidence the test was applied
consistently rather than invoked once and abandoned.

## The chassis in 2026

Revisit ch.27's own scorecard with ch.30's result folded in, and the
chassis picture this book leaves behind is a convention, copied by hand
into eight codebases, with one new row that moved from zero coverage to
partial coverage this iteration. Config and logging remain the two rows
every service shares identically — a frozen `@dataclass` with `from_env()`
in 7 of 8, stdlib `RotatingFileHandler` logging in all 8 — proof that the
cheapest cross-cutting concerns to keep synchronized by hand are the ones
with the least behavioral surface area to drift. `/health` and `errors.py`
sit at 6 of 8, each absence tied to a stated structural reason rather than
an unexplained gap. `tenacity` retry sits at 1 of 8, exactly where ch.25
put it and nowhere it was not needed. OpenTelemetry, which ch.27 reported
at zero footprint across the whole tree, now has a footprint on exactly 3
of 8 — strangler-proxy, order-service, inventory-service — the same
targeted, don't-build-ahead-of-need posture every other row in this
scorecard already modeled: three services instrumented for one connected
hero trace, not eight services instrumented because a complete-looking
column reads better than a true partial one.

{% include excalidraw.html file="book-pattern-scorecard" alt="Three stacked bands matching build-plan.md section C. EARNED (8 cards): Strangler Fig, Content-Based Routing plus ACL, Shared to Owned Data plus sync gRPC, Transactional Outbox plus event-driven, CQRS plus ACID to ACD, Saga Choreographed plus Orchestrated, Deployment via kustomize, CI/CD plus Supply Chain. ADAPTED (5 cards): Microservices Chassis, Contracts and Schema Registry, Service Mesh plus Observability (mesh earned, OTel on 3 of 8), CDC and Transaction Log Tailing (transition-only, retired), Event Sourcing (light, outbox-as-log framing). NAMED, DEFERRED (6 ghost cards): full event sourcing, pybreaker and bulkhead, a GitOps operator plus canary, Loki log aggregation, Kafka saga-hop tracing, and Caching (demoted to Appendix H)." caption="Figure 32.2 — The book-wide pattern scorecard, matching build-plan.md section C" %}

The decision not to collapse eight copies of a fifteen-line
`_configure_logging()` function into one shared internal package was made
once, in ch.27, and this chapter's own chassis review found no new reason
to revisit it: a shared library versioned independently of eight services
is a coordination cost — a second dependency every service has to bump,
test, and roll out on its own schedule — and this project's services have
spent thirty-one chapters proving they can evolve, break, and redeploy
without coordinating a release with each other. That cost should wait for
the same trigger a circuit breaker waits for: drift across the eight
copies causing a real, observed bug, not a stylistic preference for fewer
files. No such bug has appeared. The chassis in 2026, for this project, is
eight files that happen to agree, re-checkable with the same `grep`
commands ch.27 ran the first time, not a ninth artifact underneath them.

## The ADLC retrospective

This book was built by an agentic development lifecycle, not written
straight through, and the mechanism is itself worth a verdict of its own
now that it has run for ten iterations: a planner drafts an approach and
names every open design question as an explicit, numbered decision before
a line of code exists; a builder implements against that plan, one
iteration at a time; a validator checks the result against the plan's own
acceptance criteria and writes down what it found, correct or not, in
`_plans/reconciliation.md`. The relay's value was never that the plan was
always right the first time — it rarely was, in the way that matters — it
was that every place the plan and the as-built code disagreed got written
down in the same pass that found it, instead of surfacing later as an
unexplained inconsistency a reader would have to track down alone.

Three corrections carried across the ten iterations make the pattern
concrete. At r08, the plan's own build-plan table claimed every service's
configuration ran on `pydantic-settings` — a reasonable guess, written
before a single service existed — and ch.27's own research phase, which
meant grepping all eight `app/config.py` files directly rather than taking
the plan's wording at face value, found a plain `dataclasses.dataclass` in
every one of them and no `pydantic_settings` import anywhere in the tree.
At r09, the plan described the deployment ConfigMap as carrying one
database connection string per service; building `app-config.yaml` against
the real `config.py` modules showed the actual shape is one shared
`DATABASE_URL` with schema selection happening in each service's own code
— a different claim, caught and corrected in the shipped manifest rather
than shipped wrong and fixed later. At r09 again, the supply-chain gate's
own risk section expected a transient CVE that a base-image re-pin could
clear; the real scan found 35 unfixable Highs in a base layer with no newer
patched tag to re-pin onto, confirmed with `skopeo`, and the gate shipped
against that harder, real finding instead of the plan's easier anticipated
one. None of these three is a failure of the planning phase — a plan
written before any code exists cannot know what the code will turn out to
be — they are evidence the validation phase did the one job it exists to
do: read the actual files, not the plan's description of what the files
should contain.

`_plans/reconciliation.md`'s per-iteration record is the artifact that
makes this retrospective possible at all. Each entry states what shipped,
names any divergence from the plan that preceded it, and renders a
CLEAN-or-DRIFT verdict with the reasoning attached — the same discipline
this chapter applies to forty-five patterns, applied instead to ten
iterations of the process that built them. A reader who wants to check any
claim in this book against the code it describes has two places to start:
the chapter's own verification footer, and the reconciliation entry for
the iteration that shipped it.

> **ADLC in Action** — This chapter's own section C reconciliation is a
> last example of the same discipline, run one more time before the ledger
> closes. The Service Mesh / Observability / Tracing row sat with an empty
> Note through nine iterations, because ch.30 — the chapter that would fill
> it — was the last one built. Filling it meant reading `deploy/k8s/istio/`
> and `deploy/k8s/observability/` directly (confirming `PeerAuthentication`
> STRICT, the injection label mechanism, and which three services actually
> carry an `opentelemetry-distro` dependency in their `pyproject.toml`),
> not inferring the row's content from this chapter's own plan — the same
> check ch.27 ran against eight `config.py` files and ch.29 ran against
> the ConfigMap's real shape. A matrix whose last row was filled by
> paraphrasing the plan that proposed it, rather than by reading the code
> that plan produced, would be exactly the kind of drift this retrospective
> spends its own length arguing against.

## Further horizons

Five extensions did not make it into this book, and each one has a
specific, checkable condition attached rather than a vague gesture at
future work. **A `pybreaker` circuit breaker and an `asyncio`-based
bulkhead** would earn their place the moment two of this system's eight
services start failing in a way the existing mechanisms — the gRPC
deadline, the outbox's at-least-once delivery, the proxy's 502 fail-safe —
do not already catch; that second failure mode has not yet appeared. **Full
event sourcing**, replaying an aggregate's current state from nothing but
its historical events, would replace the outbox-as-log framing ch.21
teaches the moment a reader needs point-in-time state reconstruction (an
audit of an order as it looked three saga steps ago) rather than just an
ordered record of what happened. **A GitOps operator with a canary
rollout** — Argo CD or Flux reconciling the cluster against a Git
repository, promoting a new version gradually while watching an error-rate
signal — would extend the flag-gated progressive delivery this project
already practices (`STRANGLER_*` and `*_MODE` flags, toggled and verified
one Newman run at a time) into the deployment layer itself, once a second
cluster or a staged rollout target exists to promote into. **Loki log
aggregation** is the one piece of the LGTM stack ch.30's own backend ships
but does not yet wire into: Tempo carries this project's traces today;
centralizing all eight services' stdout into Loki, queryable alongside
those traces, is the next concrete step once a reader needs to correlate a
log line with the span that produced it rather than `kubectl logs`-ing one
pod at a time. **Application-level tracing across a Kafka saga hop** — a
`traceparent` persisted in an outbox row and restored by the relay before
publish — would turn the saga's event chain into one connected trace
instead of mesh-visible-but-separate hops, and is scoped exactly as far as
that one piece of plumbing: the trio chosen for ch.30 avoided it on
purpose, because the synchronous path proves the same breadth-versus-depth
point without it.

## What you learned

- **A verdict needs three outcomes, not two** — a pattern-coverage matrix
  that only tracks built-versus-not-built cannot represent a schema
  registry that works but covers one event out of a dozen, or a chassis
  that is real but copied by hand; earned, adapted, and named-deferred are
  the three claims this project's actual state supports.
- **Every real extraction traces to a named smell, not a target
  architecture** — six bounded contexts emerged from following five
  documented problems in the original monolith to their end, not from
  deciding on six services in advance and finding work to fill them.
- **A distributed monolith is a database split with no corresponding code
  split** — it gives up the one thing a monolith has without asking (atomic
  consistency across the split tables) and gets independent deployability
  in return for nothing, because the split pieces still cannot change
  without each other.
- **A chassis can be real without being a library** — eight copies of a
  small, stable file, re-checkable by `grep`, cost less to keep in sync by
  hand than a ninth shared package costs to version, test, and roll out
  independently, for a system of this size.
- **Mesh and application tracing answer different questions** — a service
  mesh gives every hop breadth (spans, mTLS, a service graph) with zero
  application code changed; application-level OpenTelemetry on a chosen
  few services adds the in-process depth a mesh cannot see, and choosing
  which three services get that depth is itself a design decision, not an
  oversight on the other five.
- **A reconciliation ledger is what makes a retrospective checkable** —
  three real plan-versus-code corrections surfaced across ten iterations
  (a configuration mechanism, a ConfigMap's real shape, a harder-than-
  expected CVE scan result) because each validation pass read the actual
  files the plan described, and wrote down what it found whether or not it
  matched.

Appendix A, next, puts this same finished system on OpenShift — a
different platform, the same eight services and the same manifests this
chapter's scorecard already accounts for.

---

*Verification status: <span class="status status--unverified">unverified</span>.
This is a conceptual, docs-only chapter with no new runnable example; its
job is reconciling `_plans/build-plan.md` section C against chapters
already shipped, not producing new evidence. Every verdict cites the
chapter that proved it (ch.14 through ch.31), and this iteration's
reconciliation was re-confirmed against each cited chapter rather than
assumed carried-forward.*
