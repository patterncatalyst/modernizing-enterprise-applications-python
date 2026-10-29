#!/usr/bin/env python3
"""ch.25 figure: shipping-resilience-chassis -- what already runs in this
system (gRPC deadline, outbox at-least-once + two-layer idempotency, the
proxy's 502 fail-safe, the saga timeout/crash-resume) plus the ONE concrete
new mechanism r06 adds (tenacity retry-with-timeout on the enrich call), with
pybreaker (circuit breaker) and asyncio.Semaphore (bulkhead) named as
deferred.

Sourced from examples/00-monolith/order/inventory_client.py (DEFAULT_TIMEOUT_
SECONDS=5.0, grpc.RpcError -> InventoryServiceUnavailable), examples/06-
shipping-service/app/enrich_client.py (tenacity retry/wait_exponential/
stop_after_attempt), examples/01-strangler-proxy/app/main.py (httpx.HTTPError
-> 502), app/orchestrator.py (resume_running_sagas), MIGRATION.md/CUTOVER.md
(idempotency + crash-resume), ch.25 prose (pybreaker/Semaphore deferral).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1340, 760

band = {"x": 20, "y": 50, "w": 1300, "h": 560, "label": "Already running in this system", "fill": "#fafafa"}

n_client = node(560, 10, 220, 40, ["Client: POST /api/orders"], style="box")

n_deadline = node(60, 110, 280, 100,
                   ["gRPC deadline: 5.0s", "order.inventory_client.py", "RpcError -> 503, compensating Release"], style="box")
n_outbox = node(380, 110, 300, 100,
                 ["Transactional outbox", "at-least-once + 2-layer idempotency", "(status guard + unique-index ledger)"], style="box")
n_proxy = node(720, 110, 280, 100,
                ["Strangler proxy 502 bridge", "unreachable upstream -> real 502,", "never a swallowed 200"], style="box")
n_sagatimeout = node(1040, 110, 240, 100,
                      ["Saga crash-resume", "resume_running_sagas()", "picks up at step_index"], style="box")

n_retry = node(380, 280, 300, 120,
                ["NEW: tenacity retry-with-timeout", "enrich_client.py -- 3 attempts,", "exponential backoff, TRANSIENT only",
                 "(contract errors raised immediately)"], style="accent")

n_breaker = node(60, 450, 300, 110,
                  ["DEFERRED: pybreaker", "circuit breaker -- no sustained-", "failure load to justify it yet"], style="ghost")
n_bulkhead = node(400, 450, 300, 110,
                   ["DEFERRED: asyncio.Semaphore", "bulkhead -- one saga's enrich call", "can't yet starve another's"], style="ghost")
n_honesty = node(760, 450, 480, 110,
                  ["Verification discipline: stuck-* negative checks", "make failures VISIBLE (RED, not a false green) --", "the AWAITING_SHIPMENT poll-script bug, found live"], style="accent")

nodes = [n_client, n_deadline, n_outbox, n_proxy, n_sagatimeout,
         n_retry, n_breaker, n_bulkhead, n_honesty]

edges = [
    connect(n_client, n_deadline),
    connect(n_client, n_outbox),
    connect(n_client, n_proxy),
    connect(n_client, n_sagatimeout),
    connect(n_outbox, n_retry, dashed=True, label="shipping's enrich step"),
    connect(n_retry, n_breaker, dashed=True, label="not yet needed"),
    connect(n_retry, n_bulkhead, dashed=True, label="not yet needed"),
    connect(n_retry, n_honesty, label="made visible"),
]

notes = [
    {"x": W / 2, "y": 30, "text": "the resilience chassis: four mechanisms already in use, one new one, two deferred",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 40, "y": H - 40, "text": "Deferral is a decision, not an oversight: pybreaker/Semaphore solve problems this system doesn't have yet (sustained failure, contention).",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "6/6 consecutive stable runs after the poll-script fix -- a resilience lesson about the TEST SUITE, not just the system under test.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "shipping-resilience-chassis", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
