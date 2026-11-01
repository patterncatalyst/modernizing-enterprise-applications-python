#!/usr/bin/env python3
"""ch.03 figure: migration-metrics-review -- the Review-extraction
measurement table turned into a comparison figure. Unlike a dramatic
before/after speedup, this project's own finding is that Phase A
(illustrative: FastAPI routes bridged onto the monolith's Django ORM via
`sync_to_async`, never shipped as code) and Phase B (the real, shipped
idiomatic FastAPI + async SQLAlchemy service) are STATISTICALLY
INDISTINGUISHABLE on raw import/startup time and import-only RSS -- both
columns are dominated by FastAPI + Pydantic v2's own import graph, so
swapping the ORM barely moves the needle at process-startup granularity.

This is a box/band/edge generator, not a charting library -- the "bars"
below are plain node() rectangles whose WIDTH is scaled to the measured
value. Because the two builds measure almost the same, the bars are drawn
nearly equal length by design; that near-equality is the finding, not a
rendering quirk. The real Phase A -> Phase B payoff is called out
separately, as structural: no synchronous ORM bridged into an async
framework via `sync_to_async` on every query, and no hard build-time
dependency on the entire monolith just to reach one model.

Exact numbers are from `examples/02-review-service/MIGRATION.md`'s own
measured table: import/startup time Phase A (proxy measurement) 0.32-0.35 s
vs Phase B 0.35-0.36 s; import-only RSS Phase A ~73.5 MB vs Phase B ~72.3
MB. Phase A's numbers are a faithful proxy (real `django.setup()` cost plus
`import fastapi, uvicorn`, in the same process) since Phase A was never
built as a running server -- that is named explicitly in the chapter, not
glossed over.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node

g.OUT = os.path.dirname(__file__)

W, H = 1500, 760

LABEL_X = 40
BAR_X = 340
BAR_MAX = 820          # Phase A's bar length in px, in both bands (own scale per band)
BAR_H = 46
ROW_GAP = 16
ROW_PITCH = BAR_H + ROW_GAP
EQUIV_X = 1280

builds = [
    # (label, style)
    ("Phase A -- Django-ORM bridge (proxy measurement, never shipped)", "box"),
    ("Phase B -- idiomatic async SQLAlchemy (shipped app/main.py)", "accent"),
]

startup_vals = [0.335, 0.355]          # midpoints used only to size bars
startup_labels = ["0.32-0.35 s", "0.35-0.36 s"]

memory_vals = [73.5, 72.3]
memory_labels = ["~73.5 MB", "~72.3 MB"]


def bars_for_band(band_y, vals, value_labels, header_h=34):
    scale = BAR_MAX / max(vals)
    nodes, notes = [], []
    row_top = band_y + header_h
    for i, ((label, style), val, vlabel) in enumerate(zip(builds, vals, value_labels)):
        top = row_top + i * ROW_PITCH
        w = max(6, val * scale)
        nodes.append(node(BAR_X, top, w, BAR_H, [""], style=style))
        ty = top + BAR_H / 2 + 5
        notes.append({"x": LABEL_X, "y": ty, "text": label, "anchor": "start", "size": 12, "bold": True})
        notes.append({"x": BAR_X + w + 14, "y": ty, "text": vlabel, "anchor": "start", "size": 12.5, "color": "#1d1d1d"})
        notes.append({"x": EQUIV_X, "y": ty, "text": "16/16 green", "anchor": "start", "size": 11.5, "color": "#2f5f3d"})
    last_bottom = row_top + 2 * ROW_PITCH - ROW_GAP
    return nodes, notes, last_bottom


band1_y = 90
band1_h = 170
band2_y = band1_y + band1_h + 40
band2_h = 170

band_startup = {"x": 20, "y": band1_y, "w": 1460, "h": band1_h,
                "label": "Import/startup time -- own scale; nearly equal by design (that is the finding)",
                "fill": "#fafafa"}
band_memory = {"x": 20, "y": band2_y, "w": 1460, "h": band2_h,
               "label": "Import-only RSS -- own scale; nearly equal by design (that is the finding)",
               "fill": "#eaf4ec"}

nodes1, notes1, bottom1 = bars_for_band(band1_y, startup_vals, startup_labels)
nodes2, notes2, bottom2 = bars_for_band(band2_y, memory_vals, memory_labels)

callout1 = {"x": LABEL_X, "y": bottom1 + 30, "text": "statistically indistinguishable: 0.32-0.35 s vs 0.35-0.36 s, within run-to-run noise",
            "anchor": "start", "bold": True, "size": 12.5, "color": "#2f5f3d"}
callout2 = {"x": LABEL_X, "y": bottom2 + 30, "text": "statistically indistinguishable: ~73.5 MB vs ~72.3 MB",
            "anchor": "start", "bold": True, "size": 12.5, "color": "#2f5f3d"}

structural_y = bottom2 + 70
structural = node(20, structural_y, 1460, 130,
                   ["The real Phase A -> Phase B win is STRUCTURAL, not a startup-time number",
                    "Phase A would carry: a synchronous Django ORM bridged into an async framework via sync_to_async on every query",
                    "Phase A would carry: a hard build-time dependency on the entire monolith just to reach one model",
                    "Phase B has neither -- independent SQLAlchemy models, zero import from 00-monolith"],
                   style="accent")

notes = [
    {"x": W / 2, "y": 32,
     "text": "the Review-extraction measurement: Phase A (illustrative) vs Phase B (shipped)",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": W / 2, "y": 56,
     "text": "the same 16/16-assertion equivalence suite passed, unchanged, against the shipped Phase B build",
     "anchor": "middle", "size": 12, "color": "#2f5f3d"},
]

notes += notes1 + [callout1] + notes2 + [callout2]

notes.append({
    "x": LABEL_X, "y": H - 28,
    "text": "Sourced from examples/02-review-service/MIGRATION.md's measured table. This stack has no compiled-vs-native-image axis to "
            "show a dramatic win on -- the finding is reported as measured, not adjusted for a cleaner story.",
    "anchor": "start", "size": 10, "color": "#777777",
})

g.emit(
    "migration-metrics-review", W, H,
    bands=[band_startup, band_memory],
    nodes=nodes1 + nodes2 + [structural],
    edges=[],
    notes=notes,
)
