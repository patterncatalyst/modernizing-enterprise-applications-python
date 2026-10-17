#!/usr/bin/env python3
"""ch.31 figure: supply-chain-gate-pipeline -- two bands.

Top band: the actual syft -> grype -> policy-as-code pipeline
examples/10-supply-chain/demo.sh runs for BOTH targets in policy.yaml,
side by side -- order-service ("after", gate: required) on top,
00-monolith ("before", gate: reported) below it, both producing the
IDENTICAL 265-match / 0 Critical / 35 High / 153 Medium / 77 Low result
(evidence/summary.txt, 2026-10-17) because both images pin the same
ubi10/python-314-minimal base layer. The fixable-only ignore rule in
.grype.yaml (fix-state: not-fixed) is what turns order-service's 35 raw
High findings into 0 fixable High -> PASS, while the monolith's
`gate: reported` verdict is measured on the RAW count (35 High) and
reports FAIL without ever blocking the pipeline.

Bottom band: the CI gate map -- the four separate, additive workflows
this repo actually ships (code-ci.yml/contract-gate, schema-registry.yml,
deploy-manifests.yml, supply-chain.yml), each with its own changes/gate/
`*-ok` summary job and no `paths:` filter, converging on one repository
ruleset. monolith-scan is drawn hanging off supply-chain.yml's sbom-scan
node, explicitly NOT feeding supply-chain-ok -- it is continue-on-error
and absent from that job's `needs:` list (supply-chain.yml).

Sourced from: examples/10-supply-chain/policy.yaml, .grype.yaml,
demo.sh, README.md ("The captured result"), evidence/summary.txt;
.github/workflows/code-ci.yml, schema-registry.yml, deploy-manifests.yml,
supply-chain.yml.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 920

band_pipeline = {"x": 20, "y": 50, "w": 1360, "h": 340,
                  "label": "examples/10-supply-chain/demo.sh == supply-chain.yml: build -> syft SBOM -> grype scan -> fixable-only policy gate (DRQ-088/090/092)",
                  "fill": "#f1f5f9"}
band_gates = {"x": 20, "y": 420, "w": 1360, "h": 460,
              "label": "Four separate, additive required checks -- same changes / gate / *-ok summary-job shape, no paths: filter (DRQ-091/092)",
              "fill": "#fafafa"}

# ---- Band 1, row A: order-service, the "after", gate: required ------------
a_build = node(50, 95, 190, 95, ["Build image", "order-service", "Containerfile (UBI10)"], style="accent")
a_sbom = node(270, 95, 190, 95, ["syft v1.54.1", "CycloneDX JSON SBOM", "5720 components"], style="box")
a_scan = node(490, 95, 210, 95, ["grype v0.120.1", "DB built 2026-10-16", "265 matches: 0C/35H/153M/77L"], style="box")
a_ignore = node(730, 95, 230, 95, [".grype.yaml ignore rule", "fix-state: not-fixed", "-> ignoredMatches (35 High)"], style="ghost")
a_gate = node(990, 95, 190, 95, ["policy.yaml gate", "fail-on: High, fixable only", "fixable = 0 High / 0 Crit"], style="accent")
a_pass = node(1210, 95, 150, 95, ["gate: required", "PASS", "exit 0"], style="user")

# ---- Band 1, row B: 00-monolith, the "before", gate: reported -------------
b_build = node(50, 225, 190, 95, ["Build image", "00-monolith (frozen)", "Dockerfile (UBI10)"], style="accent")
b_sbom = node(270, 225, 190, 95, ["syft", "CycloneDX JSON SBOM", "5690 components"], style="box")
b_scan = node(490, 225, 210, 95, ["grype, same DB", "SAME base layer", "265 matches: 0C/35H/153M/77L"], style="box")
b_raw = node(730, 225, 230, 95, ["gate: reported", "measured on RAW count", "(not filtered to fixable)"], style="sub")
b_fail = node(990, 225, 190, 95, ["fail-on: High", "raw High = 35 > 0", "reported FAIL"], style="ghost")
b_excl = node(1210, 225, 150, 95, ["continue-on-error", "never blocks", "the pipeline"], style="ghost")

pipeline_nodes = [a_build, a_sbom, a_scan, a_ignore, a_gate, a_pass,
                  b_build, b_sbom, b_scan, b_raw, b_fail, b_excl]

pipeline_edges = [
    connect(a_build, a_sbom),
    connect(a_sbom, a_scan),
    connect(a_scan, a_ignore),
    connect(a_ignore, a_gate, label="fixable matches only"),
    connect(a_gate, a_pass, amber=True),
    connect(b_build, b_sbom),
    connect(b_sbom, b_scan),
    connect(b_scan, b_raw),
    connect(b_raw, b_fail),
    connect(b_fail, b_excl, dashed=True),
]

# ---- Band 2: the four CI gates, each its own changes/gate/*-ok -----------
g1 = node(60, 460, 290, 95, ["code-ci.yml", "contract-gate", "full Newman suite, no monolith"], style="accent")
g1ok = node(60, 580, 290, 70, ["code-ci-ok"], style="box")

g2 = node(390, 460, 290, 95, ["schema-registry.yml", "schema-registry-gate", "Avro round trip + BACKWARD compat"], style="accent")
g2ok = node(390, 580, 290, 70, ["schema-registry-ok"], style="box")

g3 = node(720, 460, 290, 95, ["deploy-manifests.yml", "render", "kubectl kustomize + kubeconform -strict"], style="accent")
g3ok = node(720, 580, 290, 70, ["deploy-manifests-ok"], style="box")

g4 = node(1050, 460, 290, 95, ["supply-chain.yml", "sbom-scan (order-service)", "fixable-only grype gate"], style="accent")
g4ok = node(1050, 580, 290, 70, ["supply-chain-ok"], style="box")

monolith_scan = node(1050, 680, 290, 70, ["monolith-scan", "continue-on-error: true", "absent from needs: -- never gates"], style="ghost")

ruleset = node(420, 790, 540, 95, ["Repository ruleset", "4 required checks, each if: always()",
                                    "a new gate = a new additive workflow, old ones untouched"], style="user")

gate_nodes = [g1, g1ok, g2, g2ok, g3, g3ok, g4, g4ok, monolith_scan, ruleset]

gate_edges = [
    connect(g1, g1ok),
    connect(g2, g2ok),
    connect(g3, g3ok),
    connect(g4, g4ok),
    connect(g4, monolith_scan, dashed=True, label="built + scanned, never gates"),
    connect(g1ok, ruleset),
    connect(g2ok, ruleset),
    connect(g3ok, ruleset),
    connect(g4ok, ruleset),
    connect(a_pass, g4, dashed=True, label="same 3 steps as demo.sh"),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.31 -- the supply-chain gate pipeline (top) and the four additive, separately-gated CI checks it joins (bottom)",
     "anchor": "middle", "bold": True, "size": 16},
    {"x": 40, "y": H - 46, "text": "Both images inherit the SAME 35 High CVEs from the shared ubi10/python-314-minimal base layer -- none from either service's own Python dependencies.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "gate-on: fixable (.grype.yaml) scopes the block to what a re-pin or a dependency bump could actually fix; point-in-time against the grype DB (built 2026-10-16) and the pinned base-image tag.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "supply-chain-gate-pipeline", W, H,
    bands=[band_pipeline, band_gates],
    nodes=pipeline_nodes + gate_nodes,
    edges=pipeline_edges + gate_edges,
    notes=notes,
)
