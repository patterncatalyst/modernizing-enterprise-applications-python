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
```

Each spec validates its own output on the way out (`generate_diagram.emit()`
parses the SVG and the Excalidraw JSON before returning). See
`scripts/generate_diagram.py` for the `emit()` API and node styles, and
`_lib.py` for the `node()`/`connect()` helpers used by every spec in this
directory.
