# r05 Build Plan — Payment Extraction (ch.23 Choreographed Saga) + the sync→async checkout flip

**Branch:** `feat/r05-payment` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval.
Extraction 4 of 6. Headline: checkout `POST /api/orders` goes **201 CONFIRMED → 202 PENDING**; payment becomes an async choreographed saga. Payment-service port **:8085**.

## USER-GATE DECISION — shipping-fail handling (planner recommends Option A)
Reacting to `payment.captured` by dispatching shipping means SHIP-FAIL now happens *after* payment capture. Two options:
- **Option A (recommended):** shipping dispatch moves into the `payment.captured` saga reaction; on `ShippingFailed` → compensating gRPC Release + a new terminal `OrderStatus.SHIPPING_FAILED` (TextChoices only, no DB migration). Scenario 4 converts to async (POST tolerant 422|202; bounded-wait → SHIPPING_FAILED; net-zero stock). **Honestly-flagged gap:** the captured payment is NOT refunded on ship-fail (needs a second compensation hop) — **deferred to r06's orchestrated shipping saga**; Scenario 4 asserts net-zero *stock* + terminal status, not a refund. This makes the stranded-payment the motivation for r06 orchestration. (Shipping becomes a saga step r06 can orchestrate.)
- **Option B (minimal-diff):** keep shipping synchronous at checkout inside `transaction.atomic()` so Scenario 4 stays byte-for-byte synchronous 422. Simpler, no new status — but dispatches shipping *before* payment capture (a ship-before-pay smell introduced in a smell-curing chapter) and doesn't make shipping a saga step for r06.
Plan proceeds on **A** unless overridden.

## Settled decisions (DRQ-049..058)
- **201→202 suite conversion (headline):** ONE collection; each checkout POST tolerant of `201|402|202`; the load-bearing assertion becomes a **bounded-wait poll of `GET /api/orders/{id}` to a strict terminal status** + strict side-effects (stock delta / net-zero), reusing the notification folder's `setNextRequest` idiom. Must baseline GREEN against the unmodified synchronous monolith (polls match on attempt 1) — proves non-vacuity. The **negative check** (consumer down → stuck PENDING → RED) is the honesty guarantee. (Rejected: forked async collection; "accept any 2xx"; 201-with-PENDING dishonest contract.)
- **Payment = choreographed** (no orchestrator; payment-service reacts to `order.placed`, monolith reacts to `payment.captured/declined`). Deliberate contrast to r06 shipping = orchestrated.
- **Idempotent compensation (closes DRQ-043):** server-side idempotency in the inventory-service **Release** via a `(order_id, sku)` compensation ledger + an `idempotency_key` field added to `ReleaseRequest` in `inventory.proto` (repeated Release = no-op). Plus a client-side status-transition guard in the saga reaction (defense-in-depth; the server ledger covers the crash-window the client guard can't).
- **Saga reaction location:** a Django management command `order/management/commands/order_saga_listener.py` (group `monolith-order-saga`), structurally like `order_placed_consumer`/`outbox_relay`. (Rejected: AppConfig thread; Celery.)
- **Payment REST reads move behind a proxy flag** `STRANGLER_PAYMENT_ENABLED` → payment-service :8085. So two cutover dimensions: monolith `PAYMENT_MODE=synchronous|choreographed` (write/capture) + proxy `STRANGLER_PAYMENT_ENABLED` (reads). Flip together; reversible.
- **`order.placed` gets an additive optional `paymentMethod` field** (emitted for the PENDING order in choreographed mode; backward-compatible). Also fix the Notification N1 folder's stale 201/CONFIRMED assumption to be async-tolerant.
- **Chapter scope:** author **ch.20 (Outbox Pattern, Done Right)** + **ch.22 (ACID→ACD)** + **ch.23 (payment/choreographed saga)** this iteration (payment is the concrete material for all three). **ch.21 (Event Sourcing & CQRS) defers to r07** (order extraction).
- **No new dependency pins** — everything reused (aiokafka 0.14.0 etc.); payment-service deliberately has **no grpcio** (the MONOLITH issues the compensating Release, not payment-service).

## Lanes & dependency chain
S1 ledgers/frame → {S2 NEWMAN baseline (gates behavior), S3 PAYMENT-SVC, S4 IDEMPOTENT-COMPENSATION (proto+ledger)} → S5 MONOLITH-SAGA+ASYNC-CHECKOUT → S6 PROXY-FLAG → S7 CUTOVER (full topology, reversibility, negative, double-delivery) → S8 DECOMMISSION → S9 CI-KAFKA (payment-equivalence-gate) → S10 CHAPTERS → S11 LEDGERS.

- **PAYMENT-SVC** `examples/05-payment-service/` (:8085, clone 03-notification): own `payment` schema (Alembic); aiokafka consumer of `order.placed` → capture (deterministic DECLINE rule, never throws) → persist Payment + outbox row atomically (idempotent by unique order_id); own outbox relay publishes `payment.captured`/`payment.declined`; REST `GET /api/payments?orderId=`/`{id}` camelCase; lifespan runs consumer+relay; `/health` partition-assignment; Testcontainers round-trip test. No FK into monolith (order_id value). Null paymentMethod → captures (not declines).
- **IDEMPOTENT-COMPENSATION** `examples/04-inventory-service/`: add `idempotency_key` to `ReleaseRequest`, regenerate stubs both sides (drift guard green); `inventory.compensations` ledger (unique on order_id,sku,kind); Release handler = no-op if key seen else re-increment + ledger insert in one txn; concurrency/replay test.
- **MONOLITH-SAGA+ASYNC-CHECKOUT** `examples/00-monolith/`: `PAYMENT_MODE` setting; `OrderStatus.SHIPPING_FAILED` (Option A); `place_order` choreographed branch (reserve gRPC outside atomic → persist PENDING + order.placed outbox(+paymentMethod) → 202, no in-process charge/confirm/ship); view returns 202 for PENDING / 201 for CONFIRMED; `order_saga_listener` command (payment.captured→dispatch shipping→confirm | ShippingFailed→Release(idempotency_key)+SHIPPING_FAILED; payment.declined→PAYMENT_DECLINED+Release); synchronous branch byte-for-byte unchanged (zero-regression baseline). `payment.captured`/`payment.declined` event shapes defined + mirrored.
- **PROXY-FLAG** `STRANGLER_PAYMENT_ENABLED` + base URL + routing test.
- **NEWMAN-ASYNC** convert Scenarios 1/3/4 to 202-tolerant bounded-wait-to-terminal + net-zero; add guarded "Payment Context Contract" folder; fix N1; baseline green vs synchronous monolith.
- **CI-KAFKA** `payment-equivalence-gate` (Postgres + Kafka service, proto-drift, monolith+saga-listener+payment-svc+inventory-svc+proxy, full async suite, red-then-green by disabling the Release reaction, consumer-down negative), wired into `code-ci-ok`; `changes` += examples/05-payment-service/.
- **CHAPTERS** ch.20 + ch.22 + ch.23 (≥2000 words each, diagrams, footers), + ~5 figures (choreographed sequence, sync→async, PENDING→terminal lifecycle, compensation+idempotency ledger, ACID→ACD).
- **LEDGERS** DRQ-049..058, §E row 4 done, §C (saga/outbox/ACID landed), §J r05, r05 reconciliation.

## Acceptance criteria (headline)
- NEWMAN adapted suite green vs the SYNCHRONOUS monolith (non-vacuity) AND through the proxy in choreographed mode (bounded-wait→terminal); Scenario 3 PENDING→PAYMENT_DECLINED + net-zero; Scenario 4 → SHIPPING_FAILED + net-zero (Option A); Scenario 2 synchronous 409.
- Payment-service idempotent (redelivery → one payment + one outbox); inventory Release idempotent (replay → no over-restore, ledger-proven).
- `PAYMENT_MODE=synchronous` → suite byte-for-byte green (zero regression); choreographed → 202+PENDING→saga→terminal, reactions idempotent.
- payment-equivalence-gate green; red-then-green (no-Release → Scenario 3 RED); consumer-down negative RED-then-green; code-ci-ok requires it.
- ch.20/22/23 at depth; jekyll + voice + idiomatic clean. Ledgers updated.

## Risks (+ Phase-3 detection)
- PENDING→terminal race / bounded-wait flakiness → readiness-gate on both consumers' /health; budget mirrors notification (~15-20×750ms); rerun gate 3×.
- At-least-once double-capture/double-release → payment unique order_id + inventory (order_id,sku) ledger; crash-window (Release ok, status commit fails, redelivery) covered by SERVER ledger not just client guard; replay tests + CI red-then-green.
- Suite stops being honest across 201→202 → S2 baseline green vs synchronous monolith; negative check (stuck PENDING → RED) required; reject any bounded-wait that passes on PENDING.
- Compensation idempotency silently wrong (stock drifts up) → exact before/after numbers + strict net-zero equality + replay no-op test.
- Stuck-PENDING-on-consumer-down must go RED not hang → bounded budget + strict terminal assertion (fails, not waits).
- ACID→ACD stranded-payment-on-ship-fail (Option A) → documented deferral to r06; Scenario 4 asserts net-zero stock + terminal only.
- Synchronous-baseline regression from the new consumer → PAYMENT_MODE=synchronous byte-for-byte green keeps the new path dormant when off.

## New pins: NONE (all reused). Payment-service port :8085 (flag at gate if you'd prefer :8003).
