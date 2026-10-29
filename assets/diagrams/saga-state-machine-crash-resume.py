#!/usr/bin/env python3
"""ch.24 figure: saga-state-machine-crash-resume -- the saga's own status
state machine (RUNNING -> COMPLETED, or RUNNING -> COMPENSATING ->
COMPENSATED), the saga_log row each step appends, and the crash-resume path
that is this service's durability upgrade over the Java sibling's in-memory
Camel Saga coordinator.

Sourced from examples/06-shipping-service/app/orchestrator.py (STEPS,
_advance_one_step, compensate, resume_running_sagas), app/models.py
(SAGA_RUNNING/COMPENSATING/COMPLETED/COMPENSATED, saga_log), MIGRATION.md's
"durability upgrade" section and the live crash-resume proof
(resumedSagaCount: 1, enrich NOT re-invoked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 820

n_running = node(500, 30, 300, 80, ["RUNNING", "step_index advances", "one step per transaction"], style="accent")
n_log = node(880, 30, 380, 80, ["shipping.saga_log", "+1 row per step: step, status,", "detail (JSONB), timestamp"], style="box")
n_completed = node(130, 170, 280, 80, ["COMPLETED", "all 4 steps executed,", "shipment.dispatched emitted"], style="accent")
n_compensating = node(500, 170, 300, 80, ["COMPENSATING", "a step raised;", "only-completed steps unwind"], style="ghost")
n_compensated = node(880, 170, 300, 80, ["COMPENSATED", "shipment.failed emitted,", "same transaction"], style="accent")

n_crash = node(500, 320, 300, 70, ["process crash / kill -9 /", "redeploy mid-step"], style="ghost")
n_restart = node(500, 430, 300, 70, ["app/main.py lifespan:", "resume_running_sagas()"], style="box")
n_scan = node(880, 430, 380, 90,
              ["SELECT sagas WHERE status IN", "(RUNNING, COMPENSATING)", "-- the startup crash-resume scan"], style="accent")
n_pickup = node(500, 560, 300, 90,
                ["advance()/compensate() resumes", "at the PERSISTED step_index", "and context -- not from scratch"], style="accent")
n_proof = node(500, 690, 300, 100,
               ["Live proof: seeded RUNNING,", "step_index=1, docker restart --",
                "enrich NOT re-invoked,", "resumedSagaCount: 1"], style="box")

nodes = [n_running, n_log, n_completed, n_compensating, n_compensated,
         n_crash, n_restart, n_scan, n_pickup, n_proof]

edges = [
    connect(n_running, n_log, dashed=True, label="every step appends"),
    connect(n_running, n_completed, label="step_index == len(STEPS)"),
    connect(n_running, n_compensating, dashed=True, label="step raised"),
    connect(n_compensating, n_compensated, label="reverse-order undo done"),
    connect(n_running, n_crash, dashed=True, amber=True, label="dies mid-step"),
    connect(n_crash, n_restart),
    connect(n_restart, n_scan),
    connect(n_scan, n_pickup),
    connect(n_pickup, n_proof),
]

notes = [
    {"x": W / 2, "y": 16, "text": "a crash leaves the saga in a well-defined, resumable row; nothing is lost, nothing re-runs twice",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 40, "text": "An in-memory Camel-style saga coordinator tracks step progress IN MEMORY -- a pod restart loses it with no documented resume path.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "This saga persists status/step_index/context as a row, so resume is \"trivial\": pick up where the row says, verified by test_crash_resume.py.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "saga-state-machine-crash-resume", W, H,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
