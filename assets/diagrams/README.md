# Diagram catalogue

Every figure in this book is a paired `name.svg` (committed, embedded via
`{% include excalidraw.html file="..." alt="..." caption="..." %}`) plus
`name.excalidraw` (editable source), generated with
`scripts/generate_diagram.py` (see the `lgtm-diagram-generator` skill), via
a per-diagram `name.py` spec (the editable source of record for layout) that
imports the shared `_lib.py` box-edge-routing helpers in this directory.
This file is the catalogue — one row per diagram, append-only.

| Diagram | Chapter | What it shows |
|---|---|---|
| `strangler-four-moves` | ch.14 | Fowler's strangler fig pattern as four ordered moves (intercept, route, incrementally replace, retire), with the reversibility window spanning moves 1-3 and a ghosted warning about retiring too early. Source: `strangler-four-moves.py`. |
| `strangler-proxy-routing` | ch.14 | The Starlette+httpx strangler proxy's content-based routing, `STRANGLER_REVIEW_ENABLED` OFF vs ON, as two stacked topologies (client -> proxy -> monolith/review-service -> shared Postgres). Source: `strangler-proxy-routing.py`. |
| `strangler-cutover-timeline` | ch.14 | The four-run Newman evidence trail for the Review cutover: baseline OFF, cutover ON, reverted OFF, and the negative check (review-service killed, 502s by design) — plus decommission ghosted as the still-open, irreversible step ahead. Source: `strangler-cutover-timeline.py`. |
| `review-phase-a-vs-phase-b` | ch.15 | The Review service's two-phase extraction: Phase A (illustrative, Django ORM lifted onto FastAPI via `sync_to_async` and a monolith path dependency) vs Phase B (live code: idiomatic FastAPI, Pydantic v2, native async SQLAlchemy/asyncpg, passlib-verified Basic auth), both against the same shared Postgres schema. Source: `review-phase-a-vs-phase-b.py`. |
| `notification-content-based-routing` | ch.16 | The strangler proxy's routing decision generalized past a single URL-path predicate: one topology (client -> proxy -> monolith/review-service/notification-service) with each edge labeled by the real predicate `_select_backend()` evaluates, plus a side panel naming the header- and payload-based dimensions a content-based router could use beyond today's path prefix. Source: `notification-content-based-routing.py`. |
| `acl-contract-seam` | ch.16 | The anti-corruption layer as a contract, not a request: Panel A contrasts review-service's no-ACL direct reach into the monolith's shared Postgres tables (ch.15, a deliberate deferral) against Panel B's notification-service, where the only thing crossing the seam is a frozen Kafka JSON contract translated by the service's own `OrderPlacedEvent` copy into its own owned schema. Source: `acl-contract-seam.py`. |
| `outbox-write-in-transaction` | ch.17 | SMELL #5/#6 before/after inside `place_order()`'s single `@transaction.atomic()`: the before panel ends with a synchronous out-of-process notification send (the dual-write hazard); the after panel ends with one ordinary `OutboxEvent` row, atomic with everything else for free. Source: `outbox-write-in-transaction.py`. |
| `event-driven-notification-topology` | ch.17 | The full pipeline end to end: checkout's outbox row -> `outbox_relay`'s at-least-once Kafka publish -> the `order.placed` topic -> two independent, permanently-running consumer groups (`monolith-notification` and `notification-service`) -> the strangler proxy's `STRANGLER_NOTIFICATION_ENABLED` flag choosing which read path answers `GET /api/notifications`. Source: `event-driven-notification-topology.py`. |
| `idempotent-consumer-dedupe` | ch.17 | What happens when the at-least-once outbox relay redelivers the identical `order.placed` event: application-level check-then-insert handles the common case, a database-level partial unique index on `order_id` backstops the narrow concurrent-race window, and exactly one `Notification` row survives either way. Source: `idempotent-consumer-dedupe.py`. |
| `shared-data-vs-owned-data` | ch.18 | The three data-ownership postures this book builds, stacked: Review stays on the monolith's shared schema (a named deferral), Notification owns its schema from day one (async seam), and Inventory (ch.19) owns its schema too but needs a one-time transaction-log backfill from the still-live monolith table during the cutover window. Source: `shared-data-vs-owned-data.py`. |
| `orderitem-fk-to-snapshot` | ch.18 | The FK-to-snapshot move on `order.OrderItem`: before/after panels contrasting the live `inventory_item` FK against the denormalized `sku`/`item_name`/`unit_price_cents` snapshot, plus the three-step migration sequence (add, backfill, drop FK) that cuts over safely. Source: `orderitem-fk-to-snapshot.py`. |
| `inventory-grpc-proto-acl` | ch.19 | The gRPC proto as the anti-corruption layer for the synchronous order&lt;-&gt;inventory seam: the monolith's domain vocab, `inventory.proto`'s deliberately distinct wire vocab, and inventory-service's own domain vocab, each translated by a client-side and server-side ACL. Source: `inventory-grpc-proto-acl.py`. |
| `cdc-backfill-then-retire` | ch.19 | Transaction-log tailing end to end: Postgres WAL -> replication slot -> Debezium Postgres connector -> Kafka topic -> `InventoryCdcConsumer`'s upsert into the owned schema, with the retire runbook (drain, delete connector, drop slot/publication, disable the flag) ghosted as the step that follows cutover. Source: `cdc-backfill-then-retire.py`. |
| `reserve-release-saga-lite` | ch.19 | Where the free rollback went: before/after panels contrasting the single local `transaction.atomic()` (free rollback, SMELL[ch.22]) against the gRPC `Reserve` committing outside any local transaction, with the compensating `Release` wired explicitly to `PaymentDeclined`/`ShippingFailed`. Source: `reserve-release-saga-lite.py`. |
| `two-cutover-dimensions` | ch.19 | The two independent cutover flags (`INVENTORY_MODE` for reserve/release, `STRANGLER_INVENTORY_ENABLED` for reads) as a 2x2 grid, marking the two exercised, locked-together corners (Run A fully-gRPC, Run B fully-local) against the two split corners that are sound only during the CDC-backfilled transition window. Source: `two-cutover-dimensions.py`. |
| `outbox-relay-at-least-once` | ch.20 | The outbox pattern generalized past ch.17's single case: one DB transaction commits the state row and the outbox row together, a relay polls and publishes at-least-once, and the necessary counterpart is an idempotent consumer in whichever idiom fits the write (check-then-insert, upsert, or a status-transition guard). Source: `outbox-relay-at-least-once.py`. |
| `multi-outbox-saga-topology` | ch.20 | This project's first multi-service outbox choreography: the monolith's `order.placed` outbox feeds payment-service's consumer, which writes its OWN outbox (`payment.captured`/`payment.declined`), which the monolith's `order_saga_listener` consumes in turn — two outboxes chained end to end, no orchestrator anywhere. Source: `multi-outbox-saga-topology.py`. |
| `checkout-sync-to-async-contract` | ch.23 | Before/after panels on `POST /api/orders`: `PAYMENT_MODE=synchronous`'s one round trip ending in a terminal 201/402/422/409, versus `PAYMENT_MODE=choreographed`'s same round trip ending in a 202 PENDING promise the caller must poll `GET /api/orders/{id}` to resolve. Source: `checkout-sync-to-async-contract.py`. |
| `choreographed-payment-saga-sequence` | ch.23 | The full choreographed saga top to bottom, branching into its three terminal outcomes (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) — every arrow is an event one side reacted to, no orchestrator box anywhere, contrasted with ch.24's forward-referenced orchestrated shipping step. Source: `choreographed-payment-saga-sequence.py`. |
| `acid-to-acd-boundary` | ch.22 | What the single `transaction.atomic()` used to span (order + payment + shipping + outbox, full ACID) versus what it spans now (order + outbox only, A/C/D kept) — naming the Isolation gap where a PENDING order is visible and real before payment or shipping have an opinion. Source: `acid-to-acd-boundary.py`. |
| `order-pending-to-terminal-lifecycle` | ch.22 | The state machine the ACD model introduces: PENDING's three idempotent terminal exits (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) plus the honest stuck-PENDING failure mode a bounded-wait poll catches rather than hides. Source: `order-pending-to-terminal-lifecycle.py`. |
| `idempotent-compensation-two-layers` | ch.23 | DRQ-043 closed: a compensating `Release` survives redelivery at both the Kafka-event layer (the saga's status-transition guard) and the RPC layer (inventory-service's `compensations` ledger, `INSERT ... ON CONFLICT DO NOTHING`), proven live by stock held at 94 across both redelivery paths. Source: `idempotent-compensation-two-layers.py`. |
| `orchestrated-shipping-saga-sequence` | ch.24 | The four-step orchestrated saga top to bottom (`enrich -> dispatch -> book_carrier -> emit`), with `app/orchestrator.py`'s single coordinator sequencing every step and owning the reverse-order compensation decision on a `book_carrier` failure. Source: `orchestrated-shipping-saga-sequence.py`. |
| `choreography-vs-orchestration-contrast` | ch.24 | r05's choreographed payment saga and r06's orchestrated shipping saga side by side — same kind of problem, opposite control-flow topology: the left panel has no box that knows the whole sequence, the right panel has exactly one. Source: `choreography-vs-orchestration-contrast.py`. |
| `saga-state-machine-crash-resume` | ch.24 | The saga's own status state machine (RUNNING/COMPENSATING/COMPLETED/COMPENSATED), the `saga_log` row each step appends, and the crash-resume path (`resume_running_sagas()`) that is this service's durability upgrade over the Java sibling's in-memory Camel Saga coordinator — cites the live `resumedSagaCount: 1` proof. Source: `saga-state-machine-crash-resume.py`. |
| `order-lifecycle-awaiting-shipment-refund` | ch.24 | The full order lifecycle once `SHIPPING_MODE=orchestrated` (PENDING -> AWAITING_SHIPMENT -> CONFIRMED/SHIPPING_FAILED) plus the refund hop that closes r05's stranded-payment gap (DRQ-054): the same `shipment.failed` event that drives SHIPPING_FAILED also drives payment-service's CAPTURED -> REFUNDED. Source: `order-lifecycle-awaiting-shipment-refund.py`. |
| `shipping-resilience-chassis` | ch.25 | The resilience chassis: four mechanisms already load-bearing (gRPC deadline, outbox at-least-once + two-layer idempotency, the proxy's 502 fail-safe, saga crash-resume), the one concrete new mechanism (tenacity retry-with-timeout on `enrich`), and pybreaker/`asyncio.Semaphore` named as deliberately deferred. Source: `shipping-resilience-chassis.py`. |
| `order-cqrs-write-read-split` | ch.21 | The CQRS command/query split inside `07-order-service`: the command path reserves over gRPC outside any local transaction, then persists the write aggregate, the `order_view` projection, and the `order.placed` outbox row in ONE transaction; the query path reads `order_view` exclusively, never the write tables. Source: `order-cqrs-write-read-split.py`. |
| `order-view-rebuildable-projection` | ch.21 | The rebuildable read model: aggregate -> projection -> view kept current by every write, `rebuild_order_view` proving it's a cache and not a second source of truth, and the projection-disabled negative test showing exactly what goes stale (and how it's proven, not asserted) when the sync stops. Source: `order-view-rebuildable-projection.py`. |
| `rest-grpc-graphql-protocol-fit` | ch.26 | REST, gRPC, and GraphQL side by side, each labeled with the real seam this project chose it for: REST's request/reply for every service's own surface, gRPC's strongly-typed hot path for order-service's inventory reservation, GraphQL's bounded aggregation for the gateway's one query. Source: `rest-grpc-graphql-protocol-fit.py`. |
| `graphql-gateway-five-source-fanout` | ch.26 | The data-less aggregation gateway fanning one `order(id)` query out to five sources (order/payment/shipping REST, inventory gRPC, review REST per item), each field resolved lazily and nullable, bounded by depth/token limiters fixed in operator config. Source: `graphql-gateway-five-source-fanout.py`. |
| `final-monolith-free-topology` | ch.26 | The end-state topology: six independently deployable services plus the GraphQL gateway, reached through one flagless edge router with no monolith fallback left, and the monolith itself frozen and unwired -- the golden-baseline referent, not deleted. Source: `final-monolith-free-topology.py`. |
| `fastapi-chassis-anatomy` | ch.27 | The cross-cutting concerns inside one FastAPI service, startup to request: config.py's frozen dataclass Settings.from_env(), stdlib RotatingFileHandler logging, the lifespan wiring up db/consumer/relay, errors.py and /health as request-time concerns present on 6 of 8 services, tenacity retry as the one resilience wrapper (shipping only), and OTel/metrics/pybreaker/bulkhead/a shared chassis library named as deferred. Source: `fastapi-chassis-anatomy.py`. |
| `chassis-scorecard` | ch.27 | The used/partial/deferred scorecard across all 8 services, as three stacked bands: used (config, logging, Containerfile -- all or nearly all services); partial (health 6/8, errors.py 6/8, tenacity 1/8, each with a named reason for the gap); deferred (OTel/metrics, pybreaker/bulkhead, a true shared chassis library -- zero footprint today, re-checkable by grep). Source: `chassis-scorecard.py`. |
| `hand-duplicated-vs-registry-schema` | ch.28 | Two panels: today's hand-authored `order.placed` copies (payment-service's 7-field `OrderPlacedEvent` with `paymentMethod`, notification-service's 6-field copy without it -- two independent understandings, no mechanism checking they still agree) versus ch.28's demonstrator, one `order-placed-v1.avsc` registered once with Apicurio and resolved by global id from both a producer and a consumer. Source: `hand-duplicated-vs-registry-schema.py`. |
| `avro-wire-envelope-registry-flow` | ch.28 | The hand-rolled `[1-byte magic][8-byte global id][Avro bytes]` wire envelope (`app/envelope.py`, not Confluent's format -- DRQ-033's pure-Python lane has no serde to supply one) plus the full register/resolve/produce/consume flow against Apicurio's v3 REST API, including the consumer fetching the writer schema by global id rather than trusting its own local copy. Source: `avro-wire-envelope-registry-flow.py`. |
| `avro-compatibility-evolution` | ch.28 | The BACKWARD compatibility proof: v1 registers, v2 (adds `giftMessage` with a default) is ACCEPTED (200), v3 (retypes `totalCents` long -> string) is REJECTED (400, `RuleViolationException`) -- the actual status live-verified against `apicurio-registry:3.3.3`. Source: `avro-compatibility-evolution.py`. |
| `deploy-k8s-namespace-topology` | ch.29 | The `mea` namespace as rendered by `deploy/k8s/base` + `overlays/minikube`: 8 app Deployments/Services, one shared `postgres` StatefulSet (schema-per-service picked in each service's own code, not the connection string), one shared `kafka` StatefulSet, and `strangler-proxy` as the single NodePort (30888) edge -- every other Service, including `graphql-gateway`'s own front door, stays ClusterIP. Marks the probe split (`tcpSocket` on strangler-proxy + review-service, `httpGet /health` on the other six) and the two gRPC-client edges (order-service and graphql-gateway into inventory-service). Source: `deploy-k8s-namespace-topology.py`. |
| `mesh-mtls-topology` | ch.30 | The meshed `mea` namespace: 8 app pods carrying the `sidecar.istio.io/inject` label with Envoy sidecars and STRICT mTLS between them, one PERMISSIVE edge on strangler-proxy's NodePort, and postgres/kafka/lgtm left unmeshed; mesh-breadth (Envoy) vs app-OTLP-depth edges into the lgtm backend. Source: `mesh-mtls-topology.py`. |
| `mesh-hero-trace-waterfall` | ch.30 | The synchronous hero trace as nested spans -- strangler-proxy -> order-service -> inventory-service (gRPC, crossing the ch.19 ACL seam) -- each mesh span wrapping the app span wrapping the asyncpg DB span; labeled as illustrative span nesting, not captured timing. Source: `mesh-hero-trace-waterfall.py`. |
| `supply-chain-gate-pipeline` | ch.31 | Top band: the syft -> grype -> policy-as-code pipeline `examples/10-supply-chain/demo.sh` and `supply-chain.yml` both run, for order-service ("after", `gate: required`) and the frozen monolith ("before", `gate: reported`) side by side -- both produce the identical 265-match/35-High result from their shared UBI base layer; the `.grype.yaml` fixable-only ignore rule routes order-service's 35 not-fixed High findings out of the pass/fail decision, so it passes with 0 fixable High. Bottom band: the four separate, additive GitHub Actions workflows this repo ships (`code-ci.yml`/`contract-gate`, `schema-registry.yml`, `deploy-manifests.yml`, `supply-chain.yml`), each with its own `changes`/gate/`*-ok` summary job and no `paths:` filter, converging on one repository ruleset; `monolith-scan` hangs off `supply-chain.yml`'s `sbom-scan` job but is explicitly excluded from the required check. Source: `supply-chain-gate-pipeline.py`. |

## Regenerating

```sh
cd assets/diagrams
python3 -I strangler-four-moves.py
python3 -I strangler-proxy-routing.py
python3 -I strangler-cutover-timeline.py
python3 -I review-phase-a-vs-phase-b.py
python3 -I notification-content-based-routing.py
python3 -I acl-contract-seam.py
python3 -I outbox-write-in-transaction.py
python3 -I event-driven-notification-topology.py
python3 -I idempotent-consumer-dedupe.py
python3 -I shared-data-vs-owned-data.py
python3 -I orderitem-fk-to-snapshot.py
python3 -I inventory-grpc-proto-acl.py
python3 -I cdc-backfill-then-retire.py
python3 -I reserve-release-saga-lite.py
python3 -I two-cutover-dimensions.py
python3 -I outbox-relay-at-least-once.py
python3 -I multi-outbox-saga-topology.py
python3 -I checkout-sync-to-async-contract.py
python3 -I choreographed-payment-saga-sequence.py
python3 -I acid-to-acd-boundary.py
python3 -I order-pending-to-terminal-lifecycle.py
python3 -I idempotent-compensation-two-layers.py
python3 -I orchestrated-shipping-saga-sequence.py
python3 -I choreography-vs-orchestration-contrast.py
python3 -I saga-state-machine-crash-resume.py
python3 -I order-lifecycle-awaiting-shipment-refund.py
python3 -I shipping-resilience-chassis.py
python3 -I order-cqrs-write-read-split.py
python3 -I order-view-rebuildable-projection.py
python3 -I rest-grpc-graphql-protocol-fit.py
python3 -I graphql-gateway-five-source-fanout.py
python3 -I final-monolith-free-topology.py
python3 -I fastapi-chassis-anatomy.py
python3 -I chassis-scorecard.py
python3 -I hand-duplicated-vs-registry-schema.py
python3 -I avro-wire-envelope-registry-flow.py
python3 -I avro-compatibility-evolution.py
python3 -I deploy-k8s-namespace-topology.py
python3 -I supply-chain-gate-pipeline.py
python3 -I mesh-mtls-topology.py
python3 -I mesh-hero-trace-waterfall.py
```

Each spec validates its own output on the way out (`generate_diagram.emit()`
parses the SVG and the Excalidraw JSON before returning). See
`scripts/generate_diagram.py` for the `emit()` API and node styles, and
`_lib.py` for the `node()`/`connect()` helpers used by every spec in this
directory.
