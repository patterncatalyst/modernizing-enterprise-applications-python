#!/usr/bin/env python3
"""ch.07 figure: shared-table-routing-defect -- this project's own pivotal
proof moment: why a response-shape-only equivalence check could not be
trusted to catch the strangler proxy's real routing bug, and what closed
the gap instead.

LEFT panel -- the ambiguity: the ASGI strangler proxy (:8888) can route an
`/api/reviews` request to either the Django monolith (:8000, WSGI) or the
FastAPI review-service (:8001). Because Review's r02 form was scoped to
keep sharing the monolith's existing Postgres schema -- the `reviews` and
`auth_user` tables -- DB ownership is deferred to ch.18/19 (DRQ-028) -- both
backends read and write the exact same rows. A suite that only checks HTTP
response shape (status code, body) cannot tell "served correctly by
review-service" apart from "silently fell through to the monolith," because
for this slice of the walking skeleton both statements describe the same
table.

RIGHT panel -- what actually closed the gap: because the schema is shared,
this suite's real value was never the response shape alone -- it was
exercising a real POST over a real socket against the real WSGI backend and
checking the row that landed in the shared table. That is exactly the
surface where the chunked-body bug (DRQ-026) was hiding: the in-process
routing tests (`httpx.ASGITransport`, a mock transport) passed while the
proxy forwarded every POST's body unread, so `httpx` sent it with
`Transfer-Encoding: chunked` and no `Content-Length` -- which Django's WSGI
stack reads as an empty body. It surfaced only when the Newman suite ran
against the real WSGI server over a real socket (CUTOVER.md's three
baseline/cutover/reverted runs, 58/58 assertions green, post-fix).

Sourced from `_plans/decisions.md` (DRQ-026, DRQ-028) and
`examples/01-strangler-proxy/CUTOVER.md` ("A bug this cutover caught",
"Evidence trail"). No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1440, 780

LEFT_X, RIGHT_X, PANEL_W = 20, 740, 680

left_band = {"x": LEFT_X, "y": 90, "w": PANEL_W, "h": 600,
             "label": "The ambiguity -- a shape-only suite sees the same response either way",
             "fill": "#fafafa"}
right_band = {"x": RIGHT_X, "y": 90, "w": PANEL_W, "h": 600,
              "label": "What closed the gap -- a real POST, a real socket, the shared table",
              "fill": "#eaf4ec"}

# ============================================================================
# LEFT -- both backends share the same reviews/auth_user tables
# ============================================================================
suite_l = node(LEFT_X + 40, 150, 600, 70,
                ["Shape-only equivalence check", "HTTP only -- status code, body shape"], style="sub")
proxy_l = node(LEFT_X + 40, 250, 600, 70,
               ["ASGI strangler proxy :8888", "flag: STRANGLER_REVIEW_ENABLED"], style="accent")
mono_l = node(LEFT_X + 40, 360, 280, 90,
              ["Django monolith :8000 (WSGI)", "answers /api/reviews (path A)"], style="box")
rev_l = node(LEFT_X + 360, 360, 280, 90,
             ["Review service (FastAPI) :8001", "answers /api/reviews (path B)"], style="box")
pg_l = node(LEFT_X + 120, 520, 440, 90,
            ["shared Postgres schema (DRQ-028)", "reviews + auth_user -- read & written by both"], style="accent")

left_nodes = [suite_l, proxy_l, mono_l, rev_l, pg_l]
left_edges = [
    connect(suite_l, proxy_l, label="HTTP request only"),
    connect(proxy_l, mono_l, label="path A"),
    connect(proxy_l, rev_l, label="path B"),
    connect(mono_l, pg_l, amber=True),
    connect(rev_l, pg_l, amber=True, label="same rows either way"),
]

# ============================================================================
# RIGHT -- a real socket + the shared table surfaced the chunked-body bug
# ============================================================================
suite_r = node(RIGHT_X + 40, 150, 600, 70,
               ["Newman, real socket, real WSGI backend", "asserts on the row, not just the response shape"], style="accent")
proxy_r = node(RIGHT_X + 40, 250, 600, 70,
               ["ASGI strangler proxy :8888", "body buffered -- await request.body()"], style="accent")
mock_r = node(RIGHT_X + 40, 360, 280, 90,
              ["In-process test (ASGITransport)", "mock transport -- bug hid here, passed"], style="ghost")
real_r = node(RIGHT_X + 360, 360, 280, 90,
              ["Real WSGI socket (CUTOVER.md)", "bug surfaced here: empty body"], style="accent")
result_r = node(RIGHT_X + 120, 520, 440, 90,
                ["Fixed: buffered body, correct Content-Length", "58/58 assertions green -- baseline, cutover, reverted"], style="box")

right_nodes = [suite_r, proxy_r, mock_r, real_r, result_r]
right_edges = [
    connect(suite_r, proxy_r),
    connect(proxy_r, mock_r, dashed=True, label="passed -- false confidence"),
    connect(proxy_r, real_r, amber=True, label="surfaced the real defect"),
    connect(mock_r, result_r, dashed=True),
    connect(real_r, result_r, amber=True),
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.07 -- the shared-table proof: why response shape alone couldn't tell path A from path B",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "Review's r02 form still shares the monolith's Postgres schema (DRQ-028) -- DB ownership is deferred to ch.18/19",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": LEFT_X + 40, "y": 630,
     "text": "A misrouted request and a correctly routed one can return similarly shaped bodies, because both read and write the same rows.",
     "anchor": "start", "size": 11, "color": "#555555"},

    {"x": RIGHT_X + 40, "y": 630,
     "text": "The in-process mock transport couldn't see the real WSGI stack's chunked-body handling --",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": RIGHT_X + 40, "y": 646,
     "text": "only a real socket run against the real backend, checking the shared table, caught it.",
     "anchor": "start", "size": 11, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/decisions.md (DRQ-026, DRQ-028) and examples/01-strangler-proxy/CUTOVER.md (\"A bug this cutover caught\").",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "shared-table-routing-defect", W, H,
    bands=[left_band, right_band],
    nodes=left_nodes + right_nodes,
    edges=left_edges + right_edges,
    notes=notes,
)
