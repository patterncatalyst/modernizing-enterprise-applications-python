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

## Regenerating

```sh
cd assets/diagrams
python3 -I strangler-four-moves.py
python3 -I strangler-proxy-routing.py
python3 -I strangler-cutover-timeline.py
python3 -I review-phase-a-vs-phase-b.py
```

Each spec validates its own output on the way out (`generate_diagram.emit()`
parses the SVG and the Excalidraw JSON before returning). See
`scripts/generate_diagram.py` for the `emit()` API and node styles, and
`_lib.py` for the `node()`/`connect()` helpers used by every spec in this
directory.
