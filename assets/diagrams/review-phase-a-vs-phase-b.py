#!/usr/bin/env python3
"""ch.15 figure: review-phase-a-vs-phase-b -- the two-phase extraction
strategy for the Review service, side by side.

Phase A (illustrative, documented but never shipped as code -- see
examples/02-review-service/MIGRATION.md "Why Phase A isn't shipped as code")
lifts the monolith's own Django ORM onto FastAPI behind a `uv` path
dependency and `django.setup()`, paying for every query with
`sync_to_async()` and for the whole monolith's app registry at import time.

Phase B (the live code under examples/02-review-service/app/) replaces that
with idiomatic FastAPI: Pydantic v2 schemas, native async SQLAlchemy 2.x +
asyncpg queries straight to the driver, and Basic-auth verification against
the shared `auth_user` table via passlib's django_pbkdf2_sha256 scheme --
zero Django import anywhere in the service.

Both phases still read/write the SAME shared Postgres schema (ch.18/19 give
review its own database later) -- that line is the same in both panels,
on purpose: this figure is about the code path, not the data topology.

Sourced from examples/02-review-service/MIGRATION.md (the per-component
refactor table and the "why Phase A isn't shipped as code" findings) and
app/db.py, app/models.py, app/auth.py (the real Phase B code).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 620
PANEL_W = 620
LX, RX = 60, 60 + PANEL_W + 60

band_a = {"x": LX, "y": 90, "w": PANEL_W, "h": 460, "label": "Phase A -- illustrative, never shipped", "fill": "#fafafa"}
band_b = {"x": RX, "y": 90, "w": PANEL_W, "h": 460, "label": "Phase B -- live code, app/", "fill": "#eaf4ec"}

# ---- Phase A column ---------------------------------------------------
a_fastapi = node(LX + 30, 130, PANEL_W - 60, 60, ["FastAPI routes", "async def handlers"], style="box")
a_lifespan = node(LX + 30, 210, PANEL_W - 60, 60,
                   ["lifespan: django.setup()", "loads all 6 monolith apps"], style="ghost")
a_orm = node(LX + 30, 290, PANEL_W - 60, 60,
             ["review.models.Review (Django ORM)", "every query via sync_to_async()"], style="box")
a_auth = node(LX + 30, 370, PANEL_W - 60, 60,
              ["DRF BasicAuthentication", "reused from the monolith path dep"], style="box")
a_dep = node(LX + 30, 450, PANEL_W - 60, 50,
             ["uv path dependency on ../00-monolith", "whole monolith becomes a build-time dep"], style="ghost")

a_nodes = [a_fastapi, a_lifespan, a_orm, a_auth, a_dep]
a_edges = [
    connect(a_fastapi, a_lifespan, dashed=True, label="setup, once"),
    connect(a_lifespan, a_orm, dashed=True),
    connect(a_orm, a_auth, dashed=True),
    connect(a_auth, a_dep, dashed=True, label="pulled in by"),
]

# ---- Phase B column -----------------------------------------------------
b_fastapi = node(RX + 30, 130, PANEL_W - 60, 60, ["FastAPI routes (app/routes.py)", "async def handlers"], style="box")
b_schemas = node(RX + 30, 210, PANEL_W - 60, 60,
                  ["app/schemas.py", "Pydantic v2, camelCase via Field(alias=...)"], style="accent")
b_repo = node(RX + 30, 290, PANEL_W - 60, 60,
              ["app/repository.py", "native async/await SQLAlchemy 2.x"], style="accent")
b_auth = node(RX + 30, 370, PANEL_W - 60, 60,
              ["app/auth.py", "passlib django_pbkdf2_sha256 vs auth_user"], style="accent")
b_asyncpg = node(RX + 30, 450, PANEL_W - 60, 50,
                  ["asyncpg driver, no Django import anywhere", "pyproject.toml has no monolith dependency"],
                  style="ink")

b_nodes = [b_fastapi, b_schemas, b_repo, b_auth, b_asyncpg]
b_edges = [
    connect(b_fastapi, b_schemas, label="validate"),
    connect(b_fastapi, b_repo, label="await"),
    connect(b_repo, b_asyncpg, amber=True, label="native async"),
    connect(b_fastapi, b_auth, label="Depends()"),
]

pg = node(LX + (PANEL_W + 60 + PANEL_W) / 2 - 130, 570, 260, 40,
          ["PostgreSQL -- SAME shared schema both phases target"], style="sub")
nodes_all = a_nodes + b_nodes + [pg]
edges_all = a_edges + b_edges + [
    connect(a_orm, pg, label="shared DB"),
    connect(b_repo, pg, label="shared DB"),
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.15 -- Review extraction: Phase A (ORM lift, illustrative) vs Phase B (idiomatic, shipped)",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "startup/RSS were statistically indistinguishable at the proxy level; the real win is structural, not raw speed",
     "anchor": "middle", "size": 11.5, "color": "#555555"},

    {"x": LX, "y": H - 16,
     "text": "Phase A measured via a faithful proxy (real django.setup() + import fastapi,uvicorn) -- never run as a server.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "review-phase-a-vs-phase-b", W, H,
    bands=[band_a, band_b],
    nodes=nodes_all,
    edges=edges_all,
    notes=notes,
)
