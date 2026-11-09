---
title: "From SDLC to ADLC"
order: 5
part: "The Agentic Development Lifecycle (ADLC)"
description: "Why the traditional lifecycle breaks under agent-assisted work, the seven ADLC phases, and the two human gates that replace the old lifecycle's slowness."
---

## Learning objectives

By the end of this chapter you can:

- Explain why the traditional SDLC's stages are queues, and what an agent collapses.
- Name the seven ADLC phases and the two human gates.
- Map each agentic SDLC step onto the phase that carries it.
- Choose between local and hosted agent execution without changing what Verify checks.
- Say which two judgments never move to an agent.

## Why this matters

Every pattern in the migration (the ASGI strangler proxy, the anti-corruption layer, the saga, the GraphQL gateway) is produced through a lifecycle, and it isn't the one most engineers learned. It's faster, it looks different on a whiteboard, and it needs its own discipline to stay safe. Collapse the old stages without replacing their error-correction and you ship a wrong answer faster.

## The SDLC and the constraint behind it

Most organizations run a loop of requirements and planning, system design, implementation, testing and QA, code review, deploy and release, monitoring, and feedback to the top. One pass costs weeks for a well-scoped feature and months for anything that touches a shared schema or crosses a team boundary.

That shape answers one constraint: **writing code is slow relative to the cost of being wrong.** When a line takes minutes of attention to write and hours to review, you economize on attempts. You front-load thinking into requirements and design. You specialize roles because no one person holds every concern at production quality. You add code review because a second pair of eyes is cheap insurance, and you document handoffs because that's where knowledge gets lost.

Every stage is also a queue with a context switch at both ends. A requirements doc waits for a designer, a design waits for an architect, a pull request waits for a reviewer's free hour. Each role is a scarce resource time-sliced across work, which is why modernization under the SDLC is measured in quarters per extracted service. The code isn't hard to write; it has to clear several serially scheduled human gates to be trusted.

## What agentic coding tools change

A coding agent reads a codebase, reasons about a change, writes the code and the tests, and explains what it did in one session. It removes no stage; it collapses the time each takes and moves several inside one loop.

| SDLC stage | With an agent |
| --- | --- |
| Requirements and planning | **Express intent** in a sentence or paragraph. |
| System design and implementation | The agent **reads the surrounding code and proposes a change** in one step; there's no handoff between designing a function and writing it. |
| Testing and QA, code review | The agent **writes and runs tests alongside the code**; a human reviews a finished diff, not an abstract plan. |

Work that took weeks of queueing takes minutes to hours, because one engineer with one model carries it through every stage.

{% include excalidraw.html file="sdlc-vs-adlc" alt="Two parallel eight-step cycles. Left, the traditional SDLC: requirements and planning (days-weeks), system design (weeks), implementation and coding (weeks-months), testing and QA (days-weeks), code review (days), deploy and release (days), monitoring and observability (ongoing), feedback and iteration (continuous), looping back to step one. Right, the agentic SDLC: express intent (minutes), agent understands (seconds), agent implements (minutes), agent tests and docs (minutes), human review (minutes-hours), deploy and ship (minutes), monitoring and observability (continuous), learn and iterate (ongoing), looping back to step one. A transformation arrow connects the two loops, with a Key Differences table below." caption="Figure 5.1: The traditional SDLC (weeks to months, handoff-driven) and the agentic SDLC (hours to days, human guides and agent executes)" %}

Figure 5.1's differences table says more than "faster."

- **Sequential handoffs become fluid agent flow.** One actor, human plus agent, owns several stages at once.
- **Human codes everything becomes human guides, agent executes.** The engineer states intent, sets constraints and judges output.
- **Docs as afterthought becomes docs generated inline.** The agent that wrote the code narrates it.
- **Manual incident response becomes agent-assisted remediation.** The tool that wrote the code reads the logs and drafts the patch.

None of this removes risk; it relocates it. Serial human gates were a crude but real form of error-correction, and speed without a replacement just makes it faster to ship a wrong answer.

## The ADLC: the agentic SDLC, disciplined

The agentic SDLC says what becomes possible. It doesn't say where human judgment re-enters, what gets checked before a change is trusted, or how to keep a record of why a change was made. The **Agentic Development Lifecycle (ADLC)** has seven named phases and exactly two places where a human must stop the loop and decide.

1. **Frame**: a human states the outcome and acceptance criteria as a short statement of intent plus a decision-log entry.
2. **Map**: reconnaissance. Classify the legacy Django module in play, map its dependencies and locate the seam. No code changes; this answers "what exactly am I touching."
3. **Plan**: draft a step plan and a decision-log entry. **Human gate: the plan is approved before any code is written.** A wrong assumption is cheapest to catch here, before it's embodied in a diff.
4. **Generate**: scaffold and write the code and its tests against the approved plan.
5. **Verify**: a more skeptical pass runs the tests, checks the change against the **behavior-equivalence suite** and runs a security scan. **Human gate: a human signs off on equivalence** before the change is trusted.
6. **Operate**: roll out behind a feature flag, watched through the stack's telemetry, with the human controlling what percentage of traffic sees the change and how fast it grows.
7. **Reconcile**: update the decision log, the build plan and the reconciliation log with the outcome, including drift from the plan. Nothing is thrown away; it becomes the next step's Map input.

{% include excalidraw.html file="agentic-sdlc-to-adlc" alt="Two stacked bands. Top band: agentic SDLC (8 steps): express intent, agent understands, agent implements, agent tests and docs, human review, deploy and ship, monitoring and observability, learn and iterate. Bottom band: ADLC (7 phases): Frame, Map, Plan, Generate, Verify, Operate, Reconcile. Dashed lines map each top step down to the phase or phases it corresponds to: express intent to Frame, agent understands to Map, agent implements spanning both Plan and Generate, agent tests and docs to Generate, human review to Verify, deploy and ship and monitoring and observability both to Operate, learn and iterate to Reconcile. Two gate markers sit between the bands: plan approval, and equivalence sign-off." caption="Figure 5.2: Mapping the agentic SDLC's eight steps onto the seven-phase ADLC, with the two human gates marked where they land" %}

Read Figure 5.2 against Figure 5.1. "Express intent" is Frame and "agent understands" is Map. "Agent implements" spans Plan and Generate, because the first pass at implementing is the plan and nothing past it happens until a human approves it. "Agent tests and docs" lands in Generate. "Human review" is the equivalence gate inside Verify, not a rubber stamp on a diff but a check against a re-runnable suite. "Deploy and ship" and "monitoring and observability" both land in Operate, because rollout and the telemetry watching it are one activity. "Learn and iterate" is Reconcile.

Three ledger artifacts (the decision log, the build plan and the reconciliation log) replace the SDLC's design document, test plan and traceability matrix. They record why a decision was made, what was planned and whether the outcome matched. They're append-only and largely agent-maintained, so keeping them current costs almost nothing.

## Tooling for each phase

The **relay** skill supplies three of the seven phases as one tiered relay: one model tier plans, a second executes, and the first returns, now adversarial, to validate. The **scaffolding** skill supplies the conventions Generate draws on: FastAPI service shapes, `pytest` and `pytest-django` layout, and the Containerfile pattern every extracted service follows.

{% include excalidraw.html file="adlc-tooling" alt="A seven-phase cycle, each phase annotated with the tool role for this stack: Frame: human, intent plus PRD; Map: manual reconnaissance plus a scaffolding skill, no MCP equivalent; Plan: the relay, Opus plans; Generate: the relay, Sonnet executes, plus a scaffolding skill scaffolds; Verify: the relay, Opus validates, pytest plus Newman plus a security scan; Operate: a local-stack skill or a cluster-stack skill plus feature flags; Reconcile: the three ledger files." caption="Figure 5.3: The ADLC's seven phases, annotated with the tool at each one, including where the tooling runs out" %}

Figure 5.3 names a gap. Map has no MCP server behind it of the kind a framework-specific migration toolchain provides. There's no live, version-matched migration assistant for this stack, so Map substitutes careful manual reading of the Django app plus the scaffolding skill's conventions. Don't expect a tool that doesn't exist to appear in your own Python project.

## Local versus hosted execution

Where the agent runs is a separate choice from which phase is running: on the engineer's machine, or in a managed, shared environment.

{% include excalidraw.html file="adlc-local-vs-hosted" alt="A shared outer path (express intent, learn and iterate, monitoring and observability, deploy and ship) flanked by two parallel inner bands covering agent understands through human review. The local band runs each step through a local coding agent plus uv, pytest, and Testcontainers against Docker Engine. The hosted band runs the same steps through a hosted AI platform, with agent tests and docs landing in GitHub Actions' code-ci.yml. Both bands converge back onto the shared deploy-and-ship step." caption="Figure 5.4: The same agentic loop run two ways, local (uv plus Docker Engine) and hosted (a hosted AI platform plus GitHub Actions)" %}

| Path | Runs | Gives you | Costs you |
| --- | --- | --- | --- |
| **Local** | `uv run pytest` and Testcontainers against a local Docker Engine | Full visibility into every file touched and command run | Loop speed bound to one machine |
| **Hosted** | The same steps in a managed AI platform, with `code-ci.yml` standing in for "agent tests and docs" | A reproducible check that doesn't depend on a laptop | Less direct visibility into each step |

Both paths converge on the same "deploy and ship" step and the same equivalence gate. Where Generate and Verify execute doesn't change what Verify checks, so neither is the "real" workflow.

## Why the gates matter for modernization

A greenfield feature has no existing behavior to preserve, so a failed equivalence check breaks nothing a user depended on. A strangler-fig extraction's premise is that a request through the new FastAPI service behaves identically to the same request on the Django monolith, for every caller, including the ones nobody thought to ask about. The Plan gate catches "this step quietly changes behavior nobody signed off on" before a diff exists. The Verify gate turns "I believe this behaves the same" into "this produced 58 identical assertions against the real backend, over a real socket." Drop either gate and the migration gets a confident wrong answer in minutes instead of weeks.

> **ADLC in Action**: Both gates stopped the Review extraction and waited on a human. The Plan gate approved a five-step extraction sequence before any FastAPI code existed. The Verify gate caught a real defect that every in-process test had missed: a request body silently arriving empty at the monolith. The automated suite caught it only because it ran against a real socket instead of an in-process stand-in. Skipping the Verify gate would have shipped it.

## Where humans stay in control

Two decisions never move to an agent, however capable the tooling.

- **What "equivalent" means for this step.** An agent can run the equivalence suite and report the result. Deciding that its coverage fits the stakes of this extraction is a judgment, not a retrievable fact.
- **Whether to proceed past a gate when the evidence is ambiguous.** A green run is evidence that a change is probably safe, not proof. Trusting it anyway, or reaching for an adversarial check, belongs to someone who can be held accountable for being wrong. In the Review extraction every assertion passed while a defect hid underneath.

> **Decision**
>
> Run every extraction through the seven phases and keep both human gates: approve the plan before any code is written, and sign off on equivalence before any traffic moves.

> **🤖 Explore with your agent**
>
> "Take the Review extraction in `examples/02-review-service` and write the Frame, Map and Plan entries for extracting the notification context next: acceptance criteria, the monolith modules and dependencies you'd map, and a numbered step plan. Stop at the plan and wait for my approval before writing any code."
>
> Check: the reply stops after the plan and writes no files under `examples/`.
