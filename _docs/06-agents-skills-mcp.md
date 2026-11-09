---
title: "Agents, Skills & MCP Tools in the Loop"
order: 6
part: "The Agentic Development Lifecycle (ADLC)"
description: "The plan, execute, validate relay of model tiers; skills and AGENTS.md as packaged boundaries; the MCP gap in a Python stack; and what substitutes for it."
---

## Learning objectives

By the end of this chapter you can:

- Say what makes an agent more than a prompt: a loop, tools and a stopping condition.
- Run a plan, execute, validate relay in which no tier grades its own work.
- Use skills and an `AGENTS.md` file to make repeated work and project boundaries stable.
- Name what substitutes for a framework-specific MCP server, and what the substitute can't catch.
- Assign each ADLC phase to a human, a tier, a skill or a tool.

## Why this matters

Three building blocks fill the ADLC's phases: **agents** (a model in a loop with tools), **skills** (packaged instructions an agent loads before it acts) and **MCP tools** (servers that give an agent a real toolchain to act against). For this Python stack the third is mostly absent, and the gap changes where the other two have to carry weight.

## Agents: a model in a loop with tools

An agent is not a single clever prompt. It's a model given a **loop** (act, observe, decide the next step without a human re-prompting), a set of **tools** (read a file, run a shell command, call an MCP server, launch another agent) and a **stopping condition** (a task is done, a plan is approved, a gate is passed). Without the loop you have a chatbot that describes what it would do. Without the tools you have a model that can only talk about the codebase.

A single agent, one model with one loop, is the cheapest way to finish a bounded task such as scaffolding a FastAPI service. A second agent on a task that doesn't need one is coordination overhead.

## The relay: plan, execute, validate

**Multi-agent orchestration** coordinates agents with distinct roles and tools so one's output feeds another's input and no agent grades its own work. The Plan and Verify phases run as a relay skill with three roles.

{% include excalidraw.html file="plan-execute-validate-relay" alt="Six boxes in a row: Frame (human, states intent, writes the decision-log entry), Plan tier (Opus, reads Frame plus Map recon, drafts the step plan), Human gate 1 (plan approval, before any diff exists), Execute tier (Sonnet, Generate: scaffolds, writes code and tests, runs them), Validate tier (Opus again, adversarial: re-reads plan and diff against the equivalence suite), Human gate 2 (equivalence sign-off, Verify phase). A dashed line below the row connects the Plan and Validate boxes, labeled: same model tier, now adversarial, not self-vouching." caption="Figure 6.1: The relay. The planning tier drafts, the execution tier builds, the same planning tier validates adversarially, with a human gate on either side of Generate" %}

1. **Plan tier (Opus).** Reads the Frame statement, does the Map reconnaissance and drafts the step plan: a decision-log entry and a row in the build plan. A human approves it before anything else happens. A second model's enthusiasm for the plan doesn't substitute for that sign-off.
2. **Execute tier (Sonnet).** Carries out Generate: scaffolds the FastAPI, aiokafka, grpcio and Strawberry service shape, writes the code and tests, and runs them. It doesn't decide that its own output is correct.
3. **Validate tier (Opus again).** Acts adversarially. It re-reads the approved plan and the diff the execution tier produced, checks them against each other and against the behavior-equivalence suite, then recommends the second human gate. The tier that proposed the plan is the one skeptical enough to doubt it was executed faithfully, which is a different posture from "wrote it, therefore vouches for it."

The planning tier's validating pass isn't peer review between equals. It supervises: it holds authority over whether the execution tier's work is accepted. A plan draft for the Review extraction looks like this, stopped at the first gate:

```
Review-extraction plan draft, the planning tier's output before the first human gate

1  Build the behavior-equivalence suite against the running monolith
   (Newman collection; happy path + out-of-stock + payment-decline).
2  Stand up a flag-gated ASGI strangler proxy, default every request
   to the monolith.
3  Build examples/02-review-service as idiomatic FastAPI + async
   SQLAlchemy; equivalence gate must go green before cutover.
4  Flip STRANGLER_REVIEW_ENABLED; re-run the equivalence suite through
   the proxy; decommission the monolith's review module only after a
   green re-run.

Awaiting human approval before step 3 begins
```

Orchestration isn't parallelism. The relay is strictly sequential: each phase's output gates the next, and nothing in Generate starts before a human approves Plan. Independent agents do run in parallel where they touch disjoint files, such as authoring separate chapters or generating diagrams, while a shared build artifact or ledger is serialized to one writer. Orchestration is a decision about dependencies between tasks. Tasks with no shared state and no approval gate between them are candidates for parallel agents; Plan before Generate and Generate before Verify are not, however tempting the wall-clock saving.

## Skills: packaged, repeatable instructions

An agent with tools can do almost anything, including solving a well-understood problem in a slightly different, slightly wrong way each time. A **skill** is a named set of instructions an agent loads before acting on a kind of task, with its own triggers and conventions, so the fifth FastAPI scaffold makes the same choices as the first. The project uses five:

| Skill | Job |
| --- | --- |
| **Relay** | The plan, execute, validate tiering that every extraction's Plan and Verify phases run through. |
| **Scaffolding** | The dev toolchain for a new Python service: uv, the Python 3.14 pin, the FastAPI, aiokafka, grpcio and Strawberry service shapes, structured logging, and the pytest, ruff and Testcontainers layout. Every extraction starts from the same baseline instead of a hand-assembled one that drifts. |
| **Diagram generator** | Figures from a short Python spec of boxes and arrows, so diagrams share one visual language. |
| **Local stack** | The local observability substrate (Postgres, Kafka, the LGTM stack) that tests and the equivalence suite run against. |
| **Release** | Release-sync and commit-convention discipline, gated on a human's explicit go-ahead. |

A skill is also a packaged *boundary*. Each generated service directory carries an `AGENTS.md` that constrains every agent that works on it later. The review service's `AGENTS.md` records the module's two-phase migration history, pins the dependency versions in use, and tells a future agent not to look for a Phase A implementation (FastAPI over the monolith's own Django ORM), which was never committed as code, only measured and written up in `MIGRATION.md`. Phase B, idiomatic FastAPI with async SQLAlchemy, is the final state. It doesn't rely on an agent's memory of how a prior session ended, and nobody re-derives context from a transcript nobody kept. It does the job of a style guide or an architecture review board, except it travels with the repository and applies to every agent that opens it.

## The MCP gap

Skills say how to approach a task; they don't give an agent anything new to act on. Without tools it describes a library from training data that may be a year stale, with no way to check it against the running version. The **Model Context Protocol (MCP)** closes that gap: an MCP server exposes a fixed set of callable functions with structured inputs and outputs that an agent calls mid-loop for ground truth.

**There is no framework-specific MCP server for this stack.** Nothing serves live, version-matched FastAPI documentation, scaffolds an aiokafka consumer or validates a Starlette route's structure before deploy, the way an integration-framework-aware server validates a route definition. Three substitutes fill the gap:

1. **A scaffolding skill's conventions** stand in for a live scaffolding tool.
2. **Manual reconnaissance** stands in for a dependency-mapping tool: read the Django app's models, views and URL configuration before drafting a plan. Map's output is only as good as this reading is thorough.
3. **The generic MCP surface** (filesystem, shell, web fetch) still grounds an agent in the project's version-pinned `pyproject.toml` and `uv.lock`. An agent that reads `pyproject.toml` before writing an import beats one working from memory of what usually ships.

### What the gap costs: the proxy

Where an integration framework ships a content-based router as a component, `examples/01-strangler-proxy/` builds the equivalent from first principles.

{% include excalidraw.html file="asgi-strangler-proxy-flow" alt="A client request hits the strangler proxy's one catch-all route, mounted at the application root. A backend-selection function matches the full request path against six fixed prefixes, each mapped to one operator-configured backend base URL; no match returns a real 404. The matched request is rebuilt: hop-by-hop headers are stripped, the body is buffered so the outbound request carries a correct Content-Length instead of falling back to chunked encoding, and the request streams to the backend. A reachable backend's response streams back to the client verbatim; an unreachable backend becomes a real 502, never a swallowed 200. A callout names the trap: the full request path must be matched, not a route-pattern-relative value with the mount prefix already stripped." caption="Figure 6.2: The strangler proxy, a Python content-based router built without an integration framework" %}

It's one Starlette catch-all route and a backend-selection function that matches the request's full path against six fixed prefixes. It handles the two things a hand-rolled proxy must get right and a mature framework would guarantee:

- **Hop-by-hop headers are stripped**, so a value computed for one hop isn't forwarded to the next.
- **The request body is buffered**, so the outbound call carries a correct `Content-Length` instead of falling back to chunked transfer encoding.

The trap is in the matching: use the request's *full* path, never a route-pattern-relative value with the mount prefix already stripped. A refactor that gets this wrong fails silently, because every request falls through to nothing.

{% include excalidraw.html file="structural-vs-behavioral-gates" alt="Two stacked panels. Top: the structural gate, here necessarily weaker and more manual than a live route-validator MCP tool would be: ruff check plus Python's own import-time wiring, where a Starlette or FastAPI app that fails to construct raises immediately rather than deploying silently. It catches a malformed route registration or a typo'd dependency signature, but has no opinion about whether a routing predicate matches the right requests once real traffic flows. Bottom: the behavioral gate, the Newman equivalence suite and its adversarial follow-up, run during Verify against a running service. This is the layer that caught the strangler proxy's real chunked-body bug: the in-process routing tests passed while the proxy silently sent every POST upstream with no body, because only a real socket run surfaces that class of defect." caption="Figure 6.3: The structural gate (ruff and import-time wiring) and the behavioral gate (the equivalence suite) are different layers, and this stack's structural layer is weaker than a framework-aware MCP tool's would be" %}

`ruff check` and Python's import-time wiring (a Starlette or FastAPI app that fails to construct raises immediately) catch a malformed route registration, an unresolved import or a typo'd dependency signature. They have no opinion on whether a routing predicate matches the right requests under real traffic. With no live structural validator to narrow the search, the behavioral gate does more work here: the Newman equivalence suite and its adversarial follow-up, run during Verify against a running service. In the Review extraction the in-process routing tests passed cleanly, because neither import-time checks nor a mock ASGI transport could see that the proxy's outbound request carried no body. Only a real socket against a real WSGI backend could.

## How the three compose

| Phase | Who or what carries it |
| --- | --- |
| **Frame** | Entirely human. No agent, skill or tool replaces a person stating intent and writing the decision-log entry. |
| **Map** | Manual reconnaissance plus the scaffolding skill's conventions, in place of an MCP-driven dependency map. |
| **Plan** | The relay's planning tier, informed by Map, producing the plan for the first gate. |
| **Generate** | The execution tier, using the scaffolding skill and the per-service `AGENTS.md` files to produce the diff: a hand-rolled ASGI proxy, a FastAPI service, an aiokafka consumer. |
| **Verify** | The planning tier again, adversarial, checking the diff against the approved plan and the equivalence suite. It carries more weight than it would behind a stronger structural layer. |
| **Operate, Reconcile** | Mostly `AGENTS.md` and ledger work: `AGENTS.md` keeps constraining any agent that touches the running service, and the three ledger artifacts record what happened. |

> **Decision**
>
> Use one agent for a bounded task with no gate inside it. Use the relay when a human approval sits between pieces of work, and never let the tier that wrote the code validate it. Where no MCP server exists, put the missing checks in the behavioral gate.

> **🤖 Explore with your agent**
>
> "Review `examples/01-strangler-proxy/app` as the validation tier would. Check that backend selection matches the full request path, that hop-by-hop headers are stripped and that the request body is buffered before the outbound call. Report each check as pass or fail with the file and line, and change nothing."
>
> Check: the reply cites file and line for each of the three checks, and `uv run pytest` in `examples/01-strangler-proxy` still passes.
