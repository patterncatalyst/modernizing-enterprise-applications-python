#!/usr/bin/env python3
"""ch.01 figure: toolchain-and-repo-layout -- the local toolchain and repo
tree a reader walks through before any pattern gets discussed: uv-managed
Python 3.14 on one side, the docker compose stack (Postgres, Kafka in KRaft
mode, the Grafana LGTM bundle, plus Debezium Connect and Apicurio that come
online for later chapters) on the other, both landing in the same
repository tree underneath.

LEFT band -- "Local toolchain, managed by uv": `uv` itself installs the
Python 3.14 interpreter, creates the venv, and resolves the lockfile --
the one tool every chapter needs. `ruff` (lint) and `pytest` (tests) are
dev-dependency groups `uv sync --group dev` pulls in for every service.
`grpcio-tools` / `scripts/gen-proto.sh` + `check-proto-drift.sh` are drawn
ghosted: real tools in this repo, but scoped to Part 3 (ch.19, the
inventory gRPC seam) onward, not needed for the walking skeleton.

RIGHT band -- "Compose stack": the services `compose.yaml` defines --
Postgres, single-broker KRaft-mode Kafka ("no ZooKeeper"), and the Grafana
LGTM bundle (Loki, Grafana, Tempo, Mimir, plus an embedded OpenTelemetry
Collector) are live from r01. Debezium Connect and the Apicurio schema
registry are drawn ghosted: they exist in the same `compose.yaml`, but
don't matter until ch.19 (CDC) and ch.28 (schema registry).

BOTTOM band -- repository layout, the real top-level directories:
`examples/`, `tooling/`, `demos/`, `infra/`, `scripts/`, `_docs/`.
`examples/`, `tooling/`, and `_docs/` are drawn accent as the three this
chapter calls out by name.

Sourced from `_plans/build-plan.md` ("A. Approach" -- toolchain), `_plans/
decisions.md` (the r01 version matrix), `compose.yaml`, and the repo's own
top-level directory listing. No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1500, 720

# ============================================================================
# LEFT band -- local toolchain, managed by uv
# ============================================================================
band_tool = {"x": 20, "y": 60, "w": 720, "h": 250,
             "label": "Local toolchain -- managed by uv", "fill": "#fafafa"}

uv_node = node(40, 110, 330, 85, ["uv", "installs Python 3.14, venv, lockfile", "required"], style="accent")
ruff_pytest = node(390, 110, 330, 85, ["ruff + pytest", "uv sync --group dev", "required, every service"], style="accent")
grpc_tools = node(40, 205, 330, 85, ["grpcio-tools", "scripts/gen-proto.sh", "scoped to Part 3 (ch.19) onward"], style="ghost")
proto_drift = node(390, 205, 330, 85, ["check-proto-drift.sh", "buf-style breaking-change check", "scoped to Part 3 (ch.19) onward"], style="ghost")

tool_nodes = [uv_node, ruff_pytest, grpc_tools, proto_drift]

# ============================================================================
# RIGHT band -- compose stack (compose.yaml; docker compose)
# ============================================================================
band_podman = {"x": 760, "y": 60, "w": 720, "h": 250,
               "label": "Compose stack -- compose.yaml (docker compose)", "fill": "#eaf4ec"}

postgres = node(780, 110, 213, 95, ["Postgres", "monolith + review DB (shared)"], style="box")
kafka = node(1013, 110, 213, 95, ["Kafka -- KRaft mode", "single broker, no ZooKeeper"], style="box")
lgtm = node(1246, 110, 213, 95, ["Grafana LGTM bundle", "Loki + Tempo + Mimir", "+ OTel Collector"], style="box")
connect_svc = node(780, 215, 320, 85, ["Debezium Connect", "CDC source connectors"], style="ghost")
apicurio = node(1120, 215, 339, 85, ["Apicurio schema registry", "Avro wire-envelope resolution"], style="ghost")

podman_nodes = [postgres, kafka, lgtm, connect_svc, apicurio]

# ============================================================================
# BOTTOM band -- repository layout (repo root)
# ============================================================================
band_repo = {"x": 20, "y": 350, "w": 1460, "h": 250,
             "label": "Repository layout -- repo root", "fill": "#ffffff"}

examples_n = node(40, 410, 220, 130, ["examples/", "00-monolith, 01-strangler-proxy,", "02-review-service, ..."], style="accent")
tooling_n = node(280, 410, 220, 130, ["tooling/", "tooling/newman/ -- behavior-", "equivalence collection"], style="accent")
demos_n = node(520, 410, 220, 130, ["demos/", "demo-final-topology.sh,", "demo-payment-cutover.sh"], style="box")
infra_n = node(760, 410, 220, 130, ["infra/", "db/, debezium/, grafana/,", "otelcol/"], style="box")
scripts_n = node(1000, 410, 220, 130, ["scripts/", "stack-up.sh / stack-down.sh"], style="box")
docs_n = node(1240, 410, 220, 130, ["_docs/", "the chapters --", "01-prerequisites.md is here"], style="accent")

repo_nodes = [examples_n, tooling_n, demos_n, infra_n, scripts_n, docs_n]

# ============================================================================
# edges -- the two explicit cross-references this chapter draws
# ============================================================================
uv_right_y = uv_node["y"] + uv_node["h"] / 2
GUTTER_X, BUS_Y = 726, 385
examples_cx = examples_n["x"] + examples_n["w"] / 2

edges = [
    {"x1": uv_node["x"] + uv_node["w"], "y1": uv_right_y, "x2": GUTTER_X, "y2": uv_right_y, "amber": True},
    {"x1": GUTTER_X, "y1": uv_right_y, "x2": GUTTER_X, "y2": BUS_Y, "amber": True},
    {"x1": GUTTER_X, "y1": BUS_Y, "x2": examples_cx, "y2": BUS_Y, "amber": True,
     "label": "runs & tests -- uv run / uv run pytest, per service"},
    {"x1": examples_cx, "y1": BUS_Y, "x2": examples_cx, "y2": examples_n["y"], "amber": True},

    connect(scripts_n, kafka, amber=True, label="stack-up.sh / stack-down.sh"),
]

bands = [band_tool, band_podman, band_repo]
nodes = tool_nodes + podman_nodes + repo_nodes

notes = [
    {"x": W / 2, "y": 32, "text": "ch.01 -- Toolchain and repo layout: what you install, and where it lands",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": W / 2, "y": 52,
     "text": "uv-managed Python tooling and the docker compose stack both build and back the examples/ tree checked into this repository",
     "anchor": "middle", "size": 11.5, "color": "#555555"},

    {"x": 20, "y": 632,
     "text": "Required for every chapter: uv (manages Python 3.14, the venv, and the lockfile) plus ruff and pytest via uv sync --group dev.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
    {"x": 20, "y": 648,
     "text": "grpcio-tools / proto-drift checking and Debezium Connect / Apicurio are real, but scoped to later parts (ch.19 gRPC seam, ch.28 schema registry).",
     "anchor": "start", "size": 10.5, "color": "#555555"},

    {"x": 20, "y": 684,
     "text": "Sourced from _plans/build-plan.md (\"A. Approach\"), _plans/decisions.md (r01 version matrix), compose.yaml.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "toolchain-and-repo-layout", W, H,
    bands=bands,
    nodes=nodes,
    edges=edges,
    notes=notes,
)
