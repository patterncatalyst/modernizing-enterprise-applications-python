# r03 Build Plan — Notification Extraction (ch.16 Content-Based Routing & ACL + ch.17 Going Event-Driven)

**Branch:** `feat/r03-notification` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval.
Checkout stays **synchronous 201 CONFIRMED** at r03 (async 202 is r05/payment).

## PIVOTAL DECISION (confirm at gate) — who writes the monolith's notification read-model after the synchronous send is removed
SMELLS.md #6's cure requires `place_order()` to stop writing a `Notification` row / calling the dispatcher and write **only** the `order.placed` outbox row. That leaves the flag-OFF monolith `/api/notifications` surface empty unless something repopulates it.
- **Recommended: the monolith becomes a consumer of its own event** — a Django `order_placed_consumer` management command (group `monolith-notification`) idempotently writes the `Notification` row from `order.placed`. This IS the "going event-driven"/decorating-collaborator lesson of ch.17, makes the bounded-wait genuinely async on BOTH flag states, and makes the notification-service a true like-for-like replacement (same consume→record→serve shape; only schema + process differ). The proxy flag chooses who *serves the read*; both sides consume the topic in different groups during the strangle window.
- **Fallback (DRQ-038, simpler):** keep an in-transaction `Notification` row write in checkout, drop only the external dispatch. Keeps flag-OFF Kafka-free, but contradicts SMELLS #6, and the bounded-wait is never exercised flag-OFF. Chosen only if you want less machinery.

## Other design decisions (settled, recorded as DRQs)
- **Outbox relay = Django management-command polling relay** (`manage.py outbox_relay`): poll `published_at IS NULL` (partial index), publish to Kafka keyed by `orderId`, stamp on ack. (Rejected: AppConfig thread = N racing relays; APScheduler/Celery = scope creep. Debezium/CDC is r04.)
- **Kafka client = aiokafka 0.14.0 both sides** (one client; realizes DRQ-019). (Rejected: confluent-kafka C dep; kafka-python laggy on Kafka 4.x.)
- **Kafka-in-CI = GitHub Actions service container** (KRaft `apache/kafka:4.3.1`, health via `kafka-broker-api-versions.sh`, `--health-start-period 30s`, advertise `PLAINTEXT://localhost:9092`). Testcontainers used only for the service's own idempotency pytest.
- **Own schema = separate Postgres SCHEMA `notification` in the same instance**, owned+migrated by the service via **Alembic** (first owned schema; deliberate contrast with Review's shared schema, DRQ-028).
- **WebSocket push = DEFERRED** (DRQ-037).
- **Async equivalence = env-guarded bounded-wait** (busy-wait-on-retry, self-`setNextRequest`, strict terminal assert; folder skip-guarded by `notificationContractEnabled`, on only in the Kafka gate).
- **`order.placed` contract (DRQ-036):** `{orderId, customerId, customerEmail, totalCents, confirmationMessage, placedAt}`, topic `order.placed`, key `orderId`. Hand-maintained (no registry until ch.28/Apicurio).

## Lanes & dependency chain
STEP 0 (freeze `order.placed` contract) → (MONOLITH-OUTBOX ∥ NOTIFICATION-SVC ∥ PROXY-FLAG) → NEWMAN-ASYNC → CI-KAFKA gate green → CHAPTERS → LEDGERS.

- **MONOLITH-OUTBOX** (`examples/00-monolith/`): `OutboxEvent` model + migration (partial index); `place_order()` writes the outbox row in-txn instead of the sync send (cures #5/#6); delete `send_order_confirmation`/`_dispatch...`; `notification/services.py::record_order_placed` idempotent; `common/management/commands/outbox_relay.py` (aiokafka producer); `notification/management/commands/order_placed_consumer.py` (group `monolith-notification`, `earliest`); settings `KAFKA_BOOTSTRAP_SERVERS`; add aiokafka; SMELLS.md #5/#6 cured.
- **NOTIFICATION-SVC** (`examples/03-notification-service/`, :8002, mirror 02-review-service): FastAPI + async SQLAlchemy + aiokafka consumer (group `notification-service`, `earliest`) in lifespan task; own `notification` schema via Alembic; `GET /api/notifications?customerId=` (400 on missing param, camelCase); uniform errors; idempotent by `order_id` (DB partial-unique backstop); Containerfile :8002; MIGRATION.md (two-phase, honest); Testcontainers idempotency test.
- **PROXY-FLAG** (`examples/01-strangler-proxy/`): add `STRANGLER_NOTIFICATION_ENABLED` + base URL; route `/api/notifications*` when ON; routing tests (flag on/off + service-down→502); CUTOVER note.
- **NEWMAN-ASYNC** (`tooling/newman/`): add env-guarded "Notification Context Contract" folder — N1 `POST /api/orders`→201 CONFIRMED (capture customerId/orderId); N2 bounded-wait poll `GET /api/notifications?customerId=` until the orderId appears, assert camelCase + channel EMAIL + message; collection vars (20×750ms=15s budget). Guard off in Kafka-free gates. README/GOLDEN-BASELINE updated.
- **CI-KAFKA** (`.github/workflows/code-ci.yml`): extend `changes`; new `notification-equivalence-gate` = Postgres + **Kafka** service containers, uv sync (monolith/proxy/notification), migrate+seed + `alembic upgrade head`, start monolith/relay/monolith-consumer/notification-svc/proxy(flag ON), consumer-readiness wait, run the Notification folder flag ON then flag OFF, consumer-down negative check (invert exit code → RED required). Wire into `code-ci-ok`. Existing two gates stay Kafka-free + green.
- **CHAPTERS**: ch.16 (content-based routing generalized, the ACL as a contract, decorating-collaborator) + ch.17 (transactional outbox, aiokafka consume + idempotency, own-schema contrast, Django-relay-vs-FastAPI-consumer, two-flag cutover, async false-equivalence trap, at-least-once); paired SVG+Excalidraw figures; jekyll + voice + idiomatic scans clean.
- **LEDGERS**: DRQ-032..040; §E row 2 done; §J r03; §C rows (Outbox/Content-based Routing/ACL/Event-driven) landed; r03 reconciliation.

## Acceptance criteria (per lane)
- **MONOLITH-OUTBOX:** checkout still 201 CONFIRMED with no Kafka; `order.placed` row lands in the SAME txn (a DECLINE/SHIP-FAIL checkout leaves zero new outbox rows — tested); sync send gone; relay publishes + stamps; monolith consumer writes exactly one Notification per order on redelivery.
- **NOTIFICATION-SVC:** `alembic upgrade head` creates the `notification` schema+table+partial-unique index; consumer idempotent (duplicate→one row, Testcontainers-proven); `GET /api/notifications?customerId=` camelCase + 400 on missing param; container serves :8002.
- **PROXY-FLAG:** flag ON→:8002, OFF→monolith; others unaffected; service-down→502; tests green.
- **NEWMAN-ASYNC:** Notification folder green through proxy flag OFF (monolith serves, monolith-consumer populated) AND ON (service serves); bounded-wait hits within budget; existing folders stay green; folder inert in Kafka-free gates.
- **CI-KAFKA:** notification-equivalence-gate green (Kafka up, flag ON then OFF); consumer-down negative check RED (inverted step passes); code-ci-ok requires+green; two existing gates stay Kafka-free+green.
- **CHAPTERS:** ch.16/17 replace stubs at house depth + figures; jekyll clean; voice+idiomatic clean.
- **LEDGERS:** DRQ-032..040; §E/§J/§C updated; r03 reconciliation present.

## Risks (+ Phase-3 detection)
- At-least-once duplicates → idempotency test + CI "exactly one row per order" assert.
- Relay lag vs bounded-wait budget → relay poll ~1s, budget 15s; check green margin; widen before narrowing.
- Consumer-group readiness race in CI → `auto_offset_reset=earliest` + explicit assignment-readiness wait (grep log, not timing).
- KRaft single-broker health in CI → health-start-period + api-versions health-cmd; optionally pre-create the topic.
- Dual-write cure not atomic → test: DECLINE/SHIP-FAIL leaves zero new outbox rows.
- Event-schema drift (no registry) → field/type assertion in the service test + "duplicated by hand until ch.28" note (DRQ-036).
- Async suite flakiness → rerun the gate / inspect timing margins before merge.
- aiokafka wheel on Py3.14 → `uv sync --locked` in CI; fallback confluent-kafka.
- Skip-guard mis-wired → the two Kafka-free gates must stay green with no Kafka.

## New pins (surveyed 2026-10-16, all list Py3.14): aiokafka 0.14.0 (monolith + service), alembic 1.20.0 (service), testcontainers 4.15.0 (dev, service). No new CI action. Reused unchanged: fastapi/uvicorn/sqlalchemy/asyncpg/pydantic/pytest(+asyncio)/httpx/ruff; apache/kafka 4.3.1, postgres 18.6-alpine, newman 6.2.2, node 22, uv 0.13.1.
