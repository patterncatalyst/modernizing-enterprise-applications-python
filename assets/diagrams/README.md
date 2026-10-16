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
```

Each spec validates its own output on the way out (`generate_diagram.emit()`
parses the SVG and the Excalidraw JSON before returning). See
`scripts/generate_diagram.py` for the `emit()` API and node styles, and
`_lib.py` for the `node()`/`connect()` helpers used by every spec in this
directory.
