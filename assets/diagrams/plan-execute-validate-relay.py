#!/usr/bin/env python3
"""ch.06 figure: plan-execute-validate-relay -- this chapter's central
concept, the plan -> execute -> validate relay: three model tiers plus two
human gates, Frame-to-Verify.

TIER 1 -- Opus, planning role: reads the Frame statement and the Map-phase
reconnaissance (manual, plus the `lgtm-python` skill -- there is no
Quarkus-Agent-MCP / Camel-MCP equivalent for this stack, DRQ-020), drafts
the step plan that becomes a `decisions.md` entry and a `build-plan.md`
row. Sits in front of HUMAN GATE 1 (plan approval) -- the cheapest place in
the whole lifecycle to catch a wrong assumption.

TIER 2 -- Sonnet, execution role: carries out Generate -- scaffolds the
FastAPI/aiokafka/grpcio/Strawberry service shape, writes the code, writes
the tests, runs them. It does not get to decide, on its own authority, that
its own output is correct.

TIER 3 -- Opus again, now in the ADVERSARIAL role: re-reads the approved
plan, re-reads the diff Sonnet actually produced, checks the two against
each other and against the Newman behavior-equivalence suite, before
recommending HUMAN GATE 2 (equivalence sign-off). The same model tier that
proposed the plan is the one skeptical enough to doubt whether its own plan
was executed faithfully.

Frame itself stays entirely human.

Tier names (Opus plan -> Sonnet execute -> Opus validate) and the phase
table are sourced from `_plans/build-plan.md` section F.1's phase table
(Plan: "Opus produces the step plan... GATE: human approves plan before any
code"; Generate: "Sonnet scaffolds + writes code + tests"; Verify: "Opus
validates: run pytest/Newman, check the equivalence gate, security scan...
GATE: human signs off on equivalence") -- the same artifacts `_docs/06-
agents-skills-mcp.md` is scoped to name directly (`decisions.md`,
`build-plan.md`). No codenames; generic/public names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1600, 560

ROW_Y, ROW_H = 190, 130

frame = node(40, ROW_Y, 200, ROW_H,
             ["Frame -- human", "states intent, writes", "the decisions.md entry"], style="user")
plan = node(260, ROW_Y, 230, ROW_H,
            ["Plan tier -- Opus", "reads Frame + manual recon,", "drafts the step plan"], style="accent")
gate1 = node(510, ROW_Y, 200, ROW_H,
             ["Human gate 1", "plan approval --", "before any diff exists"], style="user")
execute = node(730, ROW_Y, 230, ROW_H,
               ["Execute tier -- Sonnet", "Generate: scaffolds FastAPI", "service + tests, runs them"], style="accent")
validate = node(980, ROW_Y, 240, ROW_H,
                ["Validate tier -- Opus", "adversarial: re-reads plan + diff", "against the Newman suite"], style="accent")
gate2 = node(1240, ROW_Y, 200, ROW_H,
             ["Human gate 2", "equivalence sign-off --", "Verify phase"], style="user")

nodes = [frame, plan, gate1, execute, validate, gate2]

edges = [
    connect(frame, plan),
    connect(plan, gate1, amber=True),
    connect(gate1, execute, amber=True),
    connect(execute, validate),
    connect(validate, gate2, amber=True),
]

# ---- the bus lane: Plan and Validate are the same model tier -------------
BUS_Y = 420
validate_bottom_x = validate["x"] + validate["w"] / 2
plan_bottom_x = plan["x"] + plan["w"] / 2
row_bottom = ROW_Y + ROW_H

edges += [
    {"x1": validate_bottom_x, "y1": row_bottom, "x2": validate_bottom_x, "y2": BUS_Y, "dashed": True},
    {"x1": validate_bottom_x, "y1": BUS_Y, "x2": plan_bottom_x, "y2": BUS_Y, "dashed": True, "bidir": True,
     "label": "same model tier -- now adversarial, not self-vouching"},
    {"x1": plan_bottom_x, "y1": BUS_Y, "x2": plan_bottom_x, "y2": row_bottom, "dashed": True},
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.06 -- the relay: Plan -> Execute -> Validate, gated by two human sign-offs",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "Opus plans and, later, validates adversarially; Sonnet builds in between -- the tier that drafted the plan is the one that checks it was executed faithfully",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from _plans/build-plan.md (section F.1's phase table) and _docs/06-agents-skills-mcp.md.",
     "anchor": "start", "size": 10.5, "color": "#555555"},
]

g.emit(
    "plan-execute-validate-relay", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
