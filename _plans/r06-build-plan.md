# r06 Build Plan — Shipping Extraction (ch.24 Orchestrated Sagas + ch.25 Failure Modes & the Resilience Chassis)

**Branch:** `feat/r06-shipping` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval.
Extraction 5 of 6. The deliberate **orchestrated** contrast to r05's choreographed payment saga. Shipping-service HTTP **:8087** (no gRPC; :8086 held by Debezium Connect).

## Key decisions (all settled, DRQ-059..070 — no user A/B)
1. **Orchestrated saga = ADAPT + EMBED the CNDP Example-17 DB-backed orchestrator** (`cloud-native-design-patterns/examples/17-sagas/python/saga-orchestrator/`): keep its logic (STEPS/COMPENSATIONS, `advance()` with row-lock + idempotent guard, reverse-order `compensate()` over completed steps, sagas+saga_log state, **startup crash-resume**) but re-home onto this repo's SQLAlchemy[asyncio]+asyncpg+Alembic stack (`select(Saga).with_for_update()`), embedded in the shipping-service and triggered by a `payment.captured` Kafka consumer. (Rejected: near-verbatim raw-asyncpg lift; a standalone orchestrator service.)
2. **DB-backed orchestrator = a durability UPGRADE** over the Java sibling's `InMemorySagaService` (crash-resumable; teach kill-mid-saga→restart→resume) — ch.24 pedagogy.
3. **Refund hop closes DRQ-054 (the r06 correctness win the Java sibling never built):** payment-service **consumes `shipment.failed`** directly → if it holds a CAPTURED payment for that orderId → transition to new **REFUNDED** status + emit `payment.refunded` via its outbox; idempotent by order_id + status guard. (Rejected: shipping orchestrating the refund [doesn't own payment data]; a monolith command hop; a synchronous refund call.)
4. **Orchestrated-vs-choreographed contrast** = the heart of ch.24: r05 payment stays choreographed (no coordinator); r06 shipping is one named coordinator owning the fulfilment sequence top-to-bottom and the compensation decision. Shown side-by-side in Part 7.
5. **Enrich = REST:** the saga fetches the shipping address (the SHIP-FAIL sentinel lives in the address) via `GET {monolith}/api/orders/{id}` — requires an **additive `shippingAddress` on the monolith `OrderSerializer`** (backward-compatible). Doubles as the ch.25 resilience anchor (a real cross-service call needing timeout+retry).
6. **Reactions live in the existing `order_saga_listener`** (extended to subscribe to `payment.captured`/`payment.declined`/`shipment.dispatched`/`shipment.failed`, group `monolith-order-saga`); delegate to new `handle_shipment_dispatched`/`handle_shipment_failed`.
7. **Lifecycle:** PENDING →(payment.captured)→ **AWAITING_SHIPMENT** →(shipment.dispatched)→ CONFIRMED | →(shipment.failed)→ SHIPPING_FAILED + compensating gRPC Release (order context owns the reserved-line snapshot). `AWAITING_SHIPMENT` = TextChoices addition, no migration. **CONFIRMED now requires a shipment.dispatched.**
8. **ch.25 = conceptual** (mirror Java): document what already runs (gRPC 5s deadline in inventory_client, compensating Release, outbox at-least-once + two-layer idempotency, proxy 502-bridge) + the orchestrator's timeout & crash-resume; **add exactly one concrete mechanism** — a `tenacity` retry-with-timeout on the enrich HTTP call. pybreaker/bulkhead named-but-deferred with reason.
9. **Cutover dimensions:** monolith `SHIPPING_MODE=inprocess|orchestrated` (write) + proxy `STRANGLER_SHIPPING_ENABLED` (reads, transparent pass-through — `ShipmentOut` is byte-portable, no ACL translator). Both reversible; `inprocess` keeps the suite byte-for-byte green.

## Lanes & dependency chain
S1 ledgers/frame → S2 newman baseline (vs in-process monolith) → {S3 event contract ∥ S4 shipping scaffold+reads} → S5 orchestrator core → {S6 monolith lifecycle+enrich field ∥ S6b payment refund} → S7 proxy flag → S8 cutover (gate green both ways + 2 negatives) → S9 decommission in-process dispatch → S10 CI gate → {S11 diagrams ∥ S12 chapters} → S13 reconcile.

- **SHIPPING-SVC** `examples/06-shipping-service/` (:8087, mirror payment-service): own `shipping` schema (sagas, saga_log, shipments, outbox); `app/orchestrator.py` (adapted CNDP engine: with_for_update + idempotent advance + reverse-order compensate + resume scan); `app/steps.py` (enrich→dispatch→book_carrier[SHIP-FAIL throw after Shipment row exists]→emit); `app/enrich_client.py` (httpx + tenacity); `app/consumer.py` (payment.captured, group shipping-service, check-then-create saga by order_id); `app/relay.py` (shipment.dispatched/failed); lifespan runs consumer+relay+**crash-resume scan**; `/health` reports assignment+resume-complete; terminal outbox write atomic with saga state change. REST `GET /api/shipments?orderId=`/`{id}`. Tests incl. **crash-resume** (Testcontainers).
- **MONOLITH-LIFECYCLE** `examples/00-monolith/`: `OrderStatus.AWAITING_SHIPMENT`; `OrderSerializer.shippingAddress` (additive); `SHIPPING_MODE` setting; `handle_payment_captured` branches (inprocess=unchanged r05; orchestrated=PENDING→AWAITING_SHIPMENT, no in-process dispatch); new `handle_shipment_dispatched` (→CONFIRMED) / `handle_shipment_failed` (→SHIPPING_FAILED + Release, status-guarded); `order_saga_listener` subscribes to all 4 topics.
- **PAYMENT-REFUND** `examples/05-payment-service/`: `REFUNDED` status; consume `shipment.failed` → if CAPTURED → REFUNDED + `payment.refunded` outbox (idempotent, status-guarded); relay `_topic_for` += payment.refunded; EVENTS.md.
- **PROXY-FLAG** `STRANGLER_SHIPPING_ENABLED` → :8087 (transparent); routing tests.
- **NEWMAN**: widen Scenario 1 bounded-wait for the extra hop (don't relax terminal CONFIRMED); Scenario 4 → SHIPPING_FAILED + net-zero + **env-guarded REFUNDED assertion**; add Shipping Context Contract folder; baseline green vs in-process monolith; shipping env file.
- **CI** `shipping-equivalence-gate` (clone payment gate: Postgres+Kafka, all services + shipping, SHIPPING_MODE=orchestrated, async suite + reversibility + 2 negatives), wired into `code-ci-ok` (6 gates); `changes` += examples/06-shipping-service/.
- **CHAPTERS** ch.24 (orchestrator pattern, CNDP reuse, orchestration-vs-choreography contrast, saga_log/FOR UPDATE/reverse compensation/crash-resume upgrade, refund hop closing DRQ-054) + ch.25 (failure-mode taxonomy + existing resilience + orchestrator timeout/resume + the one tenacity mechanism; pybreaker/bulkhead deferred); ~5 figures; ≥2000 words each.
- **LEDGERS** DRQ-059..070, §E row 5 done, §C (Orchestrated Saga + resilience landed), r06 reconciliation (CNDP adaptation drift explained).

## Acceptance criteria (headline)
- Shipping saga: normal → COMPLETED (one Shipment DISPATCHED + one shipment.dispatched); SHIP-FAIL → compensate (Shipment CANCELLED + one shipment.failed, no dispatched); redelivery → no second saga; **crash-resume proven** (kill mid-saga → restart → resume from step_index); terminal outbox atomic with state change.
- Monolith: SHIPPING_MODE=inprocess → suite byte-for-byte green (zero regression); orchestrated → AWAITING_SHIPMENT→CONFIRMED|SHIPPING_FAILED+Release(net-zero); no CONFIRMED without shipment.dispatched.
- Refund: SHIP-FAIL order → payment REFUNDED exactly once + payment.refunded; never refunds an uncaptured order.
- Newman: baseline green vs in-process; fully-orchestrated green through proxy (Scenario 1 CONFIRMED, Scenario 4 SHIPPING_FAILED+net-zero+REFUNDED, Shipping Contract); reversibility; both negatives RED (shipping down→stuck AWAITING_SHIPMENT; disable-compensation→stock not net-zero/no refund).
- CI shipping-equivalence-gate green both directions + RED on negatives; code-ci-ok = 6 gates. ch.24/25 at depth; ledgers updated.

## Risks (+ Phase-3 detection)
- Crash-resume not actually working → Testcontainers kill-mid-saga→resume-from-step_index test + CNDP cross-check.
- Refund fires >once / for uncaptured / never → status guard + order_id dedupe + forced-redelivery test (exactly one REFUNDED) + decline-then-no-ship asserts no refund.
- AWAITING_SHIPMENT→terminal race / bounded-wait too short → widen budget w/o relaxing terminal assert; baseline vs in-process first; CI readiness-wait on shipping consumer assignment.
- Compensation mis-ordered / fires for never-completed step / doesn't fire → faithful reverse-order-over-completed; disable-compensation→RED negative proves non-vacuity.
- shipping-down negative masked → dedicated negative (stuck AWAITING_SHIPMENT → bounded-wait exhausts → RED).
- Double-delivery across new shipment.*/payment.refunded → saga order_id unique + reaction status guards + per-consumer redelivery tests.
- CNDP adaptation drift (with_for_update not locking; emit outside saga txn) → reconciliation tracks adaptation; racing-payment.captured concurrency test; assert emit+state commit together.
- Enrich coupling/failure → additive shippingAddress test; tenacity retry+httpx timeout; saga timeout compensates a stuck enrich.

## New pins: **tenacity** (NEW, ch.25 enrich retry — survey current stable + Py3.14 at uv lock); httpx 0.28.1 reused. pybreaker deferred. Everything else reused. Port: shipping :8087.
