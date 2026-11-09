---
title: "The Project Ledger"
order: 2
part: "Setting Up"
description: "The ADLC's ledger: the decision log, the build plan, the iteration records, and the reconciliation log that completes it, introduced as the reader's own migration memory."
---

Between the toolchain and the monolith there is one more piece of setup, and it isn't a tool. It's a small set of plain-text files, kept with the project and updated whenever a decision is made or a step finishes. The **project ledger** (the decision log, the build plan and the reconciliation log) became this project's durable memory while it was built, and you can keep the same one on your own migration.

By the end of this chapter you can:

- Say what each ledger file is for and which ADLC phase writes to it.
- Write a decision-log row that records the reason and the rejected alternative.
- Find the current state of a project from the tail of its decision log.
- Tell a clean adaptation from drift in a reconciliation entry.

## Why a ledger

The work in the extraction chapters has one shape: a human states what should happen, an agent does reconnaissance, produces a plan, writes code against it, verifies, rolls out and records the outcome. That is the **Frame, Map, Plan, Generate, Verify, Operate, Reconcile** cycle of the Agentic Development Lifecycle (ADLC). Its last phase, Reconcile, is a few concrete files a human can open and trust.

An agent-assisted modernization is dozens of short conversations over days or weeks, often by different people, sometimes interrupted by a laptop reboot. A Claude Code session has no memory of one from three days ago. A reviewer six weeks out doesn't remember the reasoning behind a week-one choice. An agent picking up a half-finished extraction needs to know what the code looks like and also what was already decided and must not be silently re-decided. Without a durable external record, decisions get reversed because nobody remembered making them, steps get redone because nobody could tell they were done, and steps get skipped because nobody could tell they weren't.

The cost is higher in modernization, which is refactoring under the hardest constraint: the system must keep behaving as it does, in code someone else wrote, for customers who depend on it today. An agent can retry a risky change as often as it likes. It can't decide on its own authority that a retry is safe to ship. That is the job of the two human gates, Plan approval and Verify sign-off, and both need something durable on each side: a record of what was proposed and a record of what was confirmed.

## The decision log

The decision log is append-only, one row per decision, each with a short stable identifier so later work can cite it. A row names the decision, the reasoning and a status:

| Status | Meaning |
|---|---|
| `fixed` | The user set it; nothing downstream relitigates it |
| `accepted` | A synthesis decision a later step could revisit but hasn't |
| `proposed` | A recommended default awaiting confirmation |

Numbering never resets and rows are never deleted. A changed decision gets a new row that says what it supersedes, so the history stays intact.

Three rows show the range. The first is as small as a decision gets, and exactly the kind that gets re-litigated by accident three weeks later:

```
Compose engine = docker-primary, podman-compatible (the project's own
choice). | User-fixed. Docker is the primary engine so the
dev-loop instructions transfer; "podman-compatible" is stated as a
constraint (no Docker-only compose syntax) rather than a second maintained
compose file. | fixed
```

Written down, "I think we picked Docker" becomes a checkable fact with a reason, and nobody wonders why a second compose file was never created.

The second is a correction, caught only once real code existed to check the plan against:

```
Config is a frozen @dataclass Settings.from_env(), NOT pydantic-settings --
this corrects an earlier aspirational claim, not a new design choice. The
build plan's chassis blurb had asserted pydantic-settings as the config
mechanism; as actually built, no service ever adopted it -- 7 of 8 services
follow the frozen-dataclass-with-from_env() shape. This entry is now the
authoritative record. | Accepted -- correction. A planning-stage claim that
was never actually realized in code is exactly the kind of doc-vs-code drift
the reconciliation discipline exists to catch. | accepted -- correction
```

The per-service scorecard in the chassis chapter (`/health` endpoints, structured error handling, retry logic across eight services) starts from the claim about config, so that claim has to be right first. The correction row turns a plan-versus-code discrepancy into a dated, named fact instead of something a reader finds by diffing the plan against `grep`.

The third is a strategy decision, and it governs the highest-stakes moment: the point where the monolith stops being part of the running system.

```
Monolith end-state = fully decommissioned + frozen-not-deleted in-repo: the
monolith stays at examples/00-monolith/ as the golden-baseline referent and
a break-glass fallback, but compose.yaml/scripts/demos no longer start it as
part of the live topology. Learner-reference preservation: a
reference/monolith-before branch plus v0-monolith and stage/01..06 tags,
re-bootable break-glass. Rejected: deleting the monolith entirely (destroys
the equivalence suite's only pre-extraction referent and the "before"
picture). | Fixed -- user decision, approved over full deletion,
explicitly called out as the highest-stakes decision at that gate. | fixed
```

This row does design work. It commits the project to a move that feels reversible and isn't, retiring the monolith from the live system while keeping it runnable as history, and it records the rejected alternative, so a contributor tempted to clean up by deleting `examples/00-monolith/` can read why that was turned down.

## The build plan

The decision log remembers what was decided. The build plan remembers what is being built and in what order. Here it is one long document covering the chosen approach and the alternatives rejected, the site architecture by chapter, the reference monolith's design (every planted flaw and the extraction that cures it), the strangler-fig sequence service by service, the ADLC phase table, and an iteration-by-iteration release plan with its risks and how each is detected.

The phase table ties Reconcile to the ledger:

```
| 7. Reconcile | Append decision outcomes, update build-plan status, record
drift | -- | the three ledger artifacts | change log / traceability |
```

Reconcile is not a ceremony bolted onto a finished step. It is writing an outcome into the decision log, updating a status line in the build plan and appending a section to the reconciliation log. The phase and the artifact are the same thing.

The table also records a gap. Map has no framework-aware MCP server for this stack, so that cell reads **manual reconnaissance plus the scaffolding skill**, written in the same table that names every other phase's tooling.

## Per-iteration plans and the resume record

The decision log and build plan work at the scale of the whole project. Day to day the unit is one iteration, and each gets a plan file: the approach, steps grouped into parallel-safe lanes with explicit dependencies, a per-lane acceptance checklist, the iteration's risks and how to detect them, and, where a choice couldn't be made in advance, a list of open decisions for the user to resolve before dependent work starts.

There is no separate status file. At the close of each iteration, a short narrative is appended to the tail of the decision log. The latest says the final chapter is built and committed, that no appendix chapters remain, and that what's left is scope the approved plans always treated as separate future work, not an open verification gate. It names what is done, what still depends on a human running something live, and what was always out of scope rather than forgotten. Nobody re-reads the project history to find the current state; the tail of the decision log is where it lives.

{% include excalidraw.html file="ledger-files-to-adlc-phases" alt="The ledger's files mapped onto the ADLC's seven phases: the build plan and each iteration's own plan are produced during Plan, those same files are what Generate and Verify execute and check against, and the decision log plus the reconciliation log are written during Reconcile, which also loops back to update the build plan's own status line. Plan and Verify are marked as the two human-gate phases." caption="Figure 2.1: The ledger's files mapped onto the ADLC phases, and how an interrupted session resumes from them" %}

## Governing the agents: `AGENTS.md`

The three artifacts above govern the project. A different file governs how an agent behaves inside one piece of code. `examples/00-monolith/` carries its own `AGENTS.md`. It says what the module is, that it's frozen after the last extraction, and that no agent may "fix" any of the six planted smells without first reading `SMELLS.md`, because the smells are teaching material, not bugs. It pins the toolchain for that directory: uv only, never a bare `pip install` or `python -m venv`, and the dependency versions in play.

This is standing operating procedure scoped to one codebase, inherited by every agent session in that directory instead of re-explained each time. It's the same idea as the decision log: write it down once, so it doesn't live in one person's head or one session's context.

## The ledger and the two human gates

Plan approval and Verify sign-off are only meaningful if a human has something concrete to look at. A plan approval without a written plan is a conversation nobody can audit. The Plan gate is a human reading an iteration's plan file, with its lanes and acceptance criteria, before any code is written, and often a short list of open decisions where the human picks one explicitly, with the choice and reason recorded as a new decision row. A sign-off without a recorded result is trust on faith. It is a human reading a decision row or a reconciliation-log section that says which suite ran and what it reported, not an agent's claim that it passed.

## Reconciliation

The reconciliation log is the third artifact: an append-only record of every piece of code or design the project reused or adapted from another source, such as the database-backed saga orchestrator one service reuses from a separate pattern catalog, set against exactly what diverged and why. Each extraction's reconcile pass appends a section naming the source, what was kept, what changed, and a verdict:

| Verdict | Meaning |
|---|---|
| **Clean adaptation** | Every divergence is named and traced to an accepted decision |
| **Drift** | Something changed without being recorded; resolve it before the extraction counts as done |

All three artifacts were built together from the first iteration, and the reconciliation log has a section for nearly every iteration the extractions went through.

> **Decision**
>
> Record every decision as an append-only row with its reason and rejected alternative, and every borrowed or adapted piece of code in the reconciliation log. If a step's outcome isn't in the ledger, it isn't done.

## For deeper coverage

The next part makes the case for why strangling a monolith into services counts as disciplined engineering and when it doesn't. The one after defines the phase model, Frame through Reconcile, with this project's ledger as the working example.
