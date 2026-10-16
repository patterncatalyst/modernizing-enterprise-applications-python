# r04 Build Plan — Inventory Extraction (ch.18 Shared→Owned Data + ch.19 CDC & gRPC)

**Branch:** `feat/r04-inventory` · **Planner:** Opus (lgtm-relay). Status: awaiting user approval.
First synchronous **gRPC** seam + first **Debezium CDC** (transition-only). Checkout stays 201 (async 202 is r05).

## Key design decisions (all settled, confirmed vs the Java sibling — DRQ-041..048)
1. **Inventory service** `examples/04-inventory-service/` (mirror notification-service): FastAPI REST reads (:8084) + a `grpc.aio` server (:9004) started from the FastAPI lifespan (one process, two listeners). Own `inventory` Postgres schema via Alembic, reaching its end state by **own migration + own-seed** of the 3 SKUs (NOT by a running Debezium).
2. **proto = the ACL** — author `inventory.proto` FIRST (`CheckStock`/`Reserve`/`Release`/`GetStock`); both service + monolith generate stubs from one canonical proto; a checksum drift-guard keeps the two copies identical. Wire vocab deliberately distinct from the domain so the ACL earns its keep.
3. **Reserve/Release semantics:** `Reserve` = single conditional `UPDATE … SET qty=qty-:q WHERE sku=:sku AND qty>=:q` (rowcount 1=ok/0=insufficient — concurrency-safe on the row lock); `Release` = compensating `UPDATE … +:q`. Idempotency/over-restore is a documented limitation deferred to the saga chapter (mirrors Java).
4. **Monolith gRPC client + local-txn interaction (the crux):** remote `Reserve` happens **BEFORE and OUTSIDE** `transaction.atomic()` (the remote decrement is in another DB — Django rollback can't undo it). Flow: resolve customer → remote Reserve per line (accumulate reserved + snapshot fields; insufficient→release-already-reserved→409) → `with atomic():` create Order/OrderItems(snapshotted)/payment/shipping/outbox → on any failure inside (402/422) catch OUTSIDE, remote `Release` every reserved line (net-zero), re-raise. `RemoteInventoryClient` (`order/inventory_client.py`) is the client-side ACL.
   - *Rejected:* wrapping remote Reserve inside the local txn (phantom decrements on rollback; holding a DB txn across an RPC).
5. **FK→snapshot:** `order_items` drops the `inventory_item` FK, adds `sku`+`item_name` snapshot columns (`unit_price_cents` already snapshotted), filled from the `StockReply` at checkout. Serializer `sku`→`source="sku"`; drop the `items__inventory_item` prefetch. Wire contract unchanged.
6. **Two cutover dimensions:** (1) READS — proxy `STRANGLER_INVENTORY_ENABLED` routes `/api/inventory*` GETs to :8084; (2) RESERVE/RELEASE (internal monolith→:9004, not via proxy) — monolith `INVENTORY_MODE=local|grpc`. Independent but moved together (fully-local = pre-extraction baseline; fully-gRPC = owned DB). Mixed state breaks Newman stock capture — flip both together.
7. **CDC = transition-only, NOT in CI.** Debezium Connect added to compose + connector/scripts to backfill the owned schema from `public.inventory_items` (snapshot+stream), then **retired** (documented runbook). The CI `inventory-equivalence-gate` tests the **post-cutover end state** (Postgres + inventory gRPC service self-seeded + monolith `INVENTORY_MODE=grpc` + proxy flag ON; NO Debezium, NO Kafka) — confirmed this is exactly how the Java gate works. CDC correctness proven out-of-band by `scripts/verify-cdc.sh`.

## Lanes & dependency chain
PROTO (first, blocks SVC+CLIENT) → (INVENTORY-SVC-GRPC ∥ MONOLITH-GRPC-CLIENT+SNAPSHOT) ∥ (CDC-BACKFILL ∥ PROXY-FLAG ∥ CHAPTERS) → NEWMAN → CI → LEDGERS.

- **PROTO** — canonical `examples/04-inventory-service/proto/.../inventory.proto`; `scripts/gen-proto.sh`; byte-identical vendored copy in `examples/00-monolith/order/proto/`; drift-guard; commit generated stubs both sides.
- **INVENTORY-SVC-GRPC** — pyproject (grpcio 1.84.0, grpcio-tools 1.84.0 dev, protobuf 7.36.2, + the notification-service stack); `app/{config,db,models,schemas,repository,service,routes,errors,grpc_server,main}.py`; Alembic `0001_create_inventory_schema` + `0002_seed_inventory`; `app/cdc_consumer.py` (flag-gated `INVENTORY_CDC_ENABLED`, transition-only, aiokafka); Containerfile; MIGRATION.md; CUTOVER.md; unit tests incl. a **concurrency Reserve race** (two racers, last unit, exactly one wins). `/health` reports `grpcServerListening`.
- **MONOLITH-GRPC-CLIENT+SNAPSHOT** — add grpcio/protobuf; `order/inventory_client.py` ACL; settings `INVENTORY_MODE`+`INVENTORY_GRPC_TARGET`; rework `place_order` (reserve-outside-atomic, dispatch on mode, compensating Release); `order/models.py` FK→snapshot + migration (backfill then drop FK); serializer + prefetch updates; keep `local` path green (reversible).
- **CDC-BACKFILL** — compose `connect` (`quay.io/debezium/connect:3.7.0.Final`, heap 256m/768m, mem 1536m, host 8086→8083, BOOTSTRAP kafka:9094); Postgres `wal_level=logical` + replication slots; `.env.example` CONNECT_* ; `infra/debezium/inventory-connector.json` (pgoutput, topic.prefix meap, table public.inventory_items, slot/publication meap_inventory_*); `scripts/{register,retire,verify}-debezium.sh`.
- **PROXY-FLAG** — `STRANGLER_INVENTORY_ENABLED` + base URL; route `/api/inventory*`; routing test.
- **NEWMAN** — add guarded "Inventory Context Contract" folder (list/get/404, `--env-var inventoryContractEnabled=true`); confirm the 4 checkout scenarios' stock-capture stays correct reading via the proxy + reserve/release over gRPC; README/GOLDEN-BASELINE two-dimension note.
- **CI** — `inventory-equivalence-gate` (Postgres only, NO Kafka/Connect): uv sync monolith+proxy+inventory; monolith migrate+seed; inventory alembic upgrade head (own-seed); monolith `INVENTORY_MODE=grpc`; inventory :8084/:9004; proxy flag ON; run newman fully-gRPC (Inventory+Smoke+4 scenarios), then reversibility fully-local, then negative (kill inventory → RED). Extend `changes`; wire into `code-ci-ok`.
- **CHAPTERS** — ch.18 (shared→owned data, DB-per-service tradeoffs, FK→snapshot, read-models fwd-ref) + ch.19 (gRPC proto-as-ACL seam, transaction-log tailing & why you retire it, reserve-outside-local-txn crux, atomic reserve/compensating release, FK→snapshot, two-flag cutover, green gRPC CI gate); 5 figures; voice+idiomatic+jekyll clean.
- **LEDGERS** — DRQ-041..048; §E row 3 done; §C (Simple CDC / synchronous gRPC / ACL / owned-data) landed; §J r04; r04 reconciliation.

## Acceptance criteria (per lane) — see each lane; headline:
- Reserve atomic + concurrency-safe (race test); checkout `INVENTORY_MODE=grpc` decrements the owned DB, 201; decline/ship-fail → compensating Release → net-zero (Newman Scenarios 3/4 in fully-gRPC); `order_items` FK gone + snapshots filled; reads route via proxy flag; CDC register/verify/retire works on compose; `inventory-equivalence-gate` green fully-gRPC AND fully-local, RED on inventory-down; ch.18/19 at depth; ledgers updated.

## Risks (+ Phase-3 detection)
- Reserve race/oversell → concurrency test + confirm single conditional UPDATE.
- Cross-boundary rollback (decline/ship-fail leaves stock down) → Newman net-zero in fully-gRPC + confirm Release fires outside atomic.
- Remote call inside local txn → review Reserve precedes atomic; test one Release per reserved line on decline.
- Debezium creeping into CI → confirm the gate has NO connect/Kafka.
- gRPC proto drift → checksum guard + regenerate-and-diff.
- CDC duplicate redelivery → idempotent upsert by id + verify-cdc event count.
- grpc.aio not bound before newman → `/health` gates on grpcServerListening.
- Py3.14: use standard cp314 (grpcio 1.84.0 has it), NOT free-threaded cp314t.
- Mixed cutover state → gate flips both dimensions together.

## New pins (survey/re-verify at lock): grpcio 1.84.0, grpcio-tools 1.84.0 (dev), protobuf 7.36.2 (both sides), quay.io/debezium/connect:3.7.0.Final; reuse aiokafka 0.14.0 (CDC consumer only). Ports: inventory HTTP 8084 / gRPC 9004; connect host 8086. No new CI tooling (Postgres service + newman only).
