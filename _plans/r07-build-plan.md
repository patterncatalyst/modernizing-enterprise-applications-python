# r07 Build Plan — THE FINALE: Order + GraphQL Gateway (ch.26) + ch.21 CQRS — monolith decommissioned

**Branch:** `feat/r07-order-gateway` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval.
Extraction 6 of 6 — the last and hardest. Decommissions the monolith; the strangler-fig completes. Ports: order-service **:8088** (HTTP; gRPC *client* of inventory, no listener), GraphQL gateway **:8090**.

## FIVE user decisions (all with a recommended default)
1. **CQRS shape** — same-DB two-table read model: normalized `orders`/`order_items` aggregate (write) + denormalized `order_view` (read); all reads serve EXCLUSIVELY from `order_view`. *(Rec)* vs a separate read datastore (speculative infra).
2. **Projection timing** — `order_view` upserted in the SAME transaction as the write / each saga transition (read-your-writes, zero extra infra; terminal status still eventually-consistent across the saga hop). *(Rec)* vs async projection off order's own outbox (extra lag/moving part).
3. **GraphQL gateway** — additive, data-less **Strawberry** aggregation gateway with its OWN front door :8090 (REST+gRPC `@Source` resolvers, depth/complexity-bounded, per-field-null+errors[] on downstream failure), never routed through the proxy. *(Rec)* vs via-proxy / order-only / a federation router.
4. **Monolith end-state (HIGHEST STAKES)** — fully **decommissioned + frozen-not-deleted** in-repo as the golden-baseline referent; learner reference preserved via a `reference/monolith-before` branch + `v0-monolith` + `stage/NN` tags (break-glass re-bootable). The monolith's synchronous/local reversibility modes are retired from the running topology but kept frozen in code. *(Rec)* vs delete entirely.
5. **Reversibility** — accept that decommission is the ONE deliberate system-wide irreversible move, de-risked by a pre-cutover reversibility proof + the frozen break-glass monolith + the independently-revertible additive gateway/read-model. *(Rec)*

## Key design (DRQ-071..081)
- **Order service** `examples/07-order-service/` (:8088, mirror shipping template, idiomatic-from-day-one): CQRS command side (`place_order` = validate customer [owned `customers` table] → reserve inventory over gRPC OUTSIDE any DB tx → persist aggregate PENDING + `order_view` PENDING + `order.placed` outbox row in ONE local tx; compensating Release on failure, net-zero) + read model (`order_view`, projected same-tx, rebuildable via `rebuild_order_view`, reads view-only). **Lifts the four saga reactions** (payment.captured/declined, shipment.dispatched/failed) into `app/consumer.py` (group `order-service`) → `handle_*` with idempotent status guards + compensating gRPC Release (stable key `{order_id}:{sku}:release`) + refund-on-ship-fail preserved. Own outbox relay produces `order.placed` (forward-fill, no CDC). Customer FK→snapshot (`customer_id` value + `customer_email` snapshot; owns `customers`). Checkout 202 PENDING.
- **GraphQL gateway** `examples/08-graphql-gateway/` (:8090, Strawberry 0.335.0): `Query.order(id): OrderView` stitching order(REST)+payments/shipments/reviews(REST)+per-item stock(gRPC) via field resolvers (httpx + grpc.aio, bounded timeouts); data-less; depth/complexity limits (Strawberry `QueryDepthLimiter`/`MaxTokensLimiter`, no extra dep); partial-failure = per-field null + `errors[]`, not a 500; `/graphql`+`/sdl`+`/health`.
- **Decommission + flagless edge router:** add `STRANGLER_ORDER_ENABLED` for cutover, prove reversibility, then the irreversible move — remove the monolith's order app/relay/saga-listener from the running topology; collapse the proxy `_select_backend` to unconditional per-context routing (unmatched→404, drop monolith fallback); rewrite `test_routing.py` flagless. **Re-point shipping-service enrich from MONOLITH_BASE_URL → order-service read surface** (order read model MUST serve `shippingAddress`). Freeze `examples/00-monolith/`; cut `reference/monolith-before` branch + tags BEFORE decommission. **Strike SMELL #2 (god service) + #3 (one-ACID-txn) — ACID→ACD for ALL contexts.**
- **Equivalence → contract/acceptance suite:** capture the FINAL monolith-anchored baseline BEFORE cutover; convert assertions to "meets captured contract"; re-point `{{baseUrl}}` to the proxy edge + gateway; drop live-monolith dependency; keep all 4 scenarios + 6 context contracts + GraphQL folder + 3 negatives (consumer-down, compensation-disabled, **projection-disabled→stale-read→RED**) green against the monolith-free mesh.
- **CI:** new `order-gateway-contract-gate` (Postgres+Kafka + inventory+payment+shipping+order+gateway+proxy-as-edge, NO live monolith, contract suite + GraphQL check, red-then-green by disabling compensation/projection); `monolith-equivalence-gate` reframed as frozen-baseline/contract gate (or retired); rewire `code-ci-ok`.
- **Chapters:** ch.21 (Event Sourcing & CQRS — the `order_view` projection as the concrete example, rebuildable read models, outbox-as-event-log) + ch.26 (REST vs gRPC vs GraphQL, the data-less aggregation gateway, the final extraction + decommission, SMELL #2/#3 struck). Final-topology diagram.

## Lanes & dependency chain
S1 ledgers/frame → {S2 newman FINAL baseline, S3 order scaffold} ; S3→S4 (command+reactions+outbox+gRPC client)→S5 (read model+projection)→S6 (gateway) ; S4→S7 (proxy flag + enrich re-point + reversibility proof)→S8 (irreversible decommission + flagless router + freeze + strike smells)→{S9 contract-suite convert→S10 CI} ; {S5,S6}→S11 chapters ; all→S12 reconcile+final project.

## Acceptance criteria (headline)
- Order-service: 202 PENDING; reads from `order_view` incl. shippingAddress; 4 reactions drive the lifecycle with net-zero + refund preserved; redelivery no-op, Release ≤once; `order.placed` via own outbox; one local tx spans only `order` schema; view rebuildable; projection-disabled negative RED.
- Gateway: `order(id)` stitches 5 sources (REST+gRPC); data-less; downstream-down→per-field null+errors[] not 500; depth-bomb rejected; contract folder green.
- Decommission: reversibility proven BEFORE the irreversible step; after → proxy flagless (every /api/* → owner, unknown→404, no monolith backend); shipping enrich re-pointed + Scenario 4 green; monolith frozen + reference branch/tags; SMELL #2/#3 struck.
- Contract suite green against the monolith-free mesh; 3 negatives each RED when broken.
- order-gateway-contract-gate green (no live monolith) + red-then-green; code-ci-ok rewired. ch.21+26 at bar. Ledgers + final project.

## Risks (+ Phase-3 detection)
- CQRS read-your-writes / projection correctness → projection-disabled negative must go RED; grep read path for aggregate fallback (must be none).
- Doubled write-then-project latency → tune budget, don't relax terminal assert; run suite ≥2× stable.
- Lifted reactions regress r05/r06 (idempotent compensation + refund) → unit re-assert guards + at-most-once Release before e2e; Scenarios 3/4 + redelivery green.
- Shipping enrich break (points at dead monolith) → S7 re-point + integration assert order-service serves shippingAddress.
- order.placed producer flip → exactly one producer post-decommission (Scenario 1 CONFIRMED + notification checks); consumers idempotent.
- GraphQL N+1/depth-bomb/partial-failure → depth+complexity test; partial-failure per-field-null test; bounded timeouts.
- Decommission breaks suite / loses baseline (biggest) → reversibility proven before S8; frozen `v0-monolith` break-glass; 3 negatives prove non-vacuity after the referent is gone.
- Flagless router mis-routes → rewritten test_routing asserts every prefix→owner + unknown→404, no monolith backend.
- DRQ numbering: a Java *reference* "DRQ-077" appears in r01 docs as a pin ref — use genuinely-free Python IDs from DRQ-071 and footnote the collision.

## New pin: **strawberry-graphql 0.335.0** (Py3.14-OK; past the 0.312.3 CVE baseline — verify at uv lock). Depth/complexity limiter is in-package (no extra dep). Everything else reused. Ports: order :8088, gateway :8090.
