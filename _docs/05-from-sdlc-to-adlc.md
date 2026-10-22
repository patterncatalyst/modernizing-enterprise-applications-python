---
title: "From SDLC to ADLC"
order: 5
part: "The Agentic Development Lifecycle (ADLC)"
description: "Why the traditional lifecycle breaks under agent-assisted work; the ADLC phases; which SDLC steps agents replace or augment; the human gates."
---

Part 1 made the case for modernizing this system and chose a strategy for
doing it. This chapter changes a different variable: not *what* gets built,
but *how* the work itself gets done. Every pattern from here forward — the
ASGI strangler proxy, the anti-corruption layer, the saga, the GraphQL
gateway — gets produced through a specific lifecycle, and that lifecycle
isn't the one most of us learned. It's faster, it looks different on a
whiteboard, and it needs its own discipline to stay safe. This chapter names
that lifecycle, shows why the old one doesn't fit agent-assisted work, and
introduces the seven-phase, two-gate model — the **ADLC** — that every
migration chapter from Part 5 onward puts to work.

## The SDLC, and why it looks the way it does

The software development lifecycle most engineering organizations run
today — whatever their flavor of Scrum, Kanban, or stage-gate process —
still traces a recognizable shape: requirements and planning, system
design, implementation, testing and QA, code review, deploy and release,
monitoring, and feedback that loops back to the top. A single pass through
that loop typically costs weeks for a well-scoped feature and months for
anything that touches a shared schema or crosses a team boundary.

That shape isn't an accident of bureaucracy; it's a rational response to a
specific constraint: **writing code is slow relative to the cost of being
wrong.** When a line of code takes minutes of human attention to produce
and hours to properly review, you economize on attempts. You front-load
thinking into requirements and design so you don't discover a wrong
assumption after three sprints of implementation. You specialize roles — an
analyst gathers requirements, an architect designs, a developer implements,
a tester verifies, a reviewer gates, an operator deploys — because no one
person can hold the whole stack of concerns in their head at production
quality. You insert a code-review stage not because developers write bad
code but because a second pair of eyes is cheap insurance against a mistake
that's expensive to ship. And you document the handoffs — tickets, design
docs, test plans — because the handoffs themselves are where knowledge gets
lost, and an audit trail is how an organization proves the work was
actually done.

Every one of those stages is a queue with a context switch at both ends. A
requirements doc sits in a backlog until a designer picks it up; a design
sits in review until an architect signs off; a pull request sits until a
reviewer has a free hour. None of those delays reflect laziness — they
reflect that each role is a scarce, specialized resource being time-sliced
across many pieces of work at once. That's why a modernization effort under
the traditional SDLC is measured in quarters per extracted service: not
because the code is hard to write, but because the code has to pass through
several expensive, serially-scheduled human gates to be trusted.

## What agentic coding tools change

A coding agent — a tool that can read a codebase, reason about a change,
write the code, write the tests, and explain what it did, inside a single
conversational session — doesn't remove any of those conceptual stages. It
collapses the *time* each one takes, and it moves several of them inside
one continuous loop instead of across a chain of separate people.
"Requirements and planning" becomes **expressing intent** to the agent in a
sentence or a paragraph. "System design" and "implementation" become the
agent **reading the surrounding code and proposing a change** in the same
breath, because for an agent there's no handoff cost between designing a
function and writing it. "Testing and QA" and "code review" become the
agent **writing and running tests alongside the code**, with a human
reviewing a finished diff rather than an abstract plan. What used to take
weeks because of queueing delay between specialized roles now takes minutes
to hours because one engineer, working with one model, carries the work
through every stage without waiting for anyone else's calendar.

{% include excalidraw.html file="sdlc-vs-adlc" alt="Two parallel eight-step cycles. Left, the traditional SDLC: requirements and planning (days-weeks), system design (weeks), implementation and coding (weeks-months), testing and QA (days-weeks), code review (days), deploy and release (days), monitoring and observability (ongoing), feedback and iteration (continuous) — looping back to step one. Right, the agentic SDLC: express intent (minutes), agent understands (seconds), agent implements (minutes), agent tests and docs (minutes), human review (minutes-hours), deploy and ship (minutes), monitoring and observability (continuous), learn and iterate (ongoing) — looping back to step one. A transformation arrow connects the two loops, with a Key Differences table below." caption="Figure 5.1 — The traditional SDLC (weeks to months, handoff-driven) and the agentic SDLC it's becoming (hours to days, human-guides/agent-executes)" %}

Read the "Key Differences" table in Figure 5.1 carefully, because it says
more than "faster." **Sequential handoffs become fluid agent flow** — the
queueing delay between stages mostly disappears because one actor (human
plus agent) now owns several stages at once. **Human codes everything
becomes human guides, agent executes** — the engineer's job shifts from
typing every line to stating intent, setting constraints, and judging
output, a different skill than the one most of us were trained in. **Docs
as afterthought becomes docs generated inline** — because an agent that
just wrote the code can narrate it as it goes. And **manual incident
response becomes agent-assisted remediation** — when something breaks, the
same tool that wrote the code can read the logs, propose a fix, and draft
the patch.

None of this removes risk — it relocates it. The traditional SDLC's
slowness was also, incidentally, where a lot of its safety lived: several
serial human gates are a crude but real form of error-correction. Collapse
the stages without replacing that error-correction with something else, and
you've simply made it faster to ship a wrong answer. That's the problem
this book's lifecycle exists to solve.

## The ADLC: the agentic SDLC, disciplined

The agentic SDLC in Figure 5.1 describes what becomes *possible* once a
coding agent is in the loop. It doesn't, by itself, say where human
judgment re-enters, what gets checked before a change is trusted, or how a
team keeps a traceable record of why a given change was made — the things
the old SDLC's slowness used to provide implicitly. This book's answer is
the **Agentic Development Lifecycle (ADLC)**: a disciplined instance of the
agentic SDLC with seven named phases and exactly two places where a human
must stop the loop and decide.

1. **Frame** — a human states the outcome and acceptance criteria for this
   step of work, as a short statement of intent plus an entry in the
   project's decision log. This is "express intent," made
   concrete and recorded rather than said once and forgotten.
2. **Map** — reconnaissance: classify the legacy Django module in play,
   map its dependencies, and locate the seam this step will cut along. No
   code changes yet; this phase answers "what exactly am I touching."
3. **Plan** — a concrete step plan and a decision-log entry describing
   the approach get drafted. **Human gate: the plan is approved before any
   code is written.** This is the point where a wrong assumption is
   cheapest to catch — before it's embodied in a diff.
4. **Generate** — the code and its tests get scaffolded and written
   against the approved plan.
5. **Verify** — a second, more skeptical pass runs the test suite, checks
   the change against the **behavior-equivalence suite**, and runs a
   security scan. **Human gate: a human signs off on equivalence** before
   the change is trusted. This is the second and last point where the
   change depends on a human's judgment.
6. **Operate** — the change rolls out behind a feature flag, observed
   through the stack's telemetry, with the human controlling what
   percentage of traffic sees it and how fast that percentage grows.
7. **Reconcile** — the decision log, the build plan, and the
   reconciliation log get updated with the outcome, including any drift
   from what was planned. Nothing here is thrown away; it becomes the next
   step's Map input.

{% include excalidraw.html file="agentic-sdlc-to-adlc" alt="Two stacked bands. Top band: agentic SDLC (8 steps): express intent, agent understands, agent implements, agent tests and docs, human review, deploy and ship, monitoring and observability, learn and iterate. Bottom band: ADLC (7 phases): Frame, Map, Plan, Generate, Verify, Operate, Reconcile. Dashed lines map each top step down to the phase or phases it corresponds to — express intent to Frame, agent understands to Map, agent implements spanning both Plan and Generate, agent tests and docs to Generate, human review to Verify, deploy and ship and monitoring and observability both to Operate, learn and iterate to Reconcile. Two gate markers sit between the bands: plan approval, and equivalence sign-off." caption="Figure 5.2 — Mapping the agentic SDLC's eight steps onto this book's seven-phase ADLC, with the two human gates marked where they land" %}

Figure 5.2 is worth reading phase by phase against Figure 5.1. "Express
intent" is Frame. "Agent understands" is Map. "Agent implements" is where
the plan gate sits — it spans both Plan and Generate because the first pass
at implementing *is* the plan, and nothing past that pass happens until a
human has read and approved it. "Agent tests and docs" lands inside
Generate. "Human review" is where the equivalence gate sits, inside
Verify — not a rubber stamp on a diff, but a check against a concrete,
re-runnable suite. "Deploy and ship" and "monitoring and observability"
both land in Operate, because rollout and the telemetry that watches it are
one continuous activity, not two. "Learn and iterate" is Reconcile.

The three ledger artifacts this book keeps — the decision log, the
build plan, and the reconciliation log — are the ADLC's substitute for
the SDLC's heavyweight design document, test plan, and traceability
matrix. They do the same job those documents did — recording *why* a
decision was made, *what* was planned, and *whether* the outcome matched
the plan — but they're lightweight, append-only, and largely
agent-maintained, so keeping them current costs almost nothing compared to
the ceremony they replace.

## The tooling realization — and the one gap worth naming

Every phase in that loop needs an actor to carry it out, and this project
names its actors concretely rather than describing the loop in the
abstract. The **`lgtm-relay`** skill supplies three of the seven phases as
a single tiered relay: one model tier plans, a second executes, and the
first tier returns, now adversarial, to validate — the mechanics of that
relay, and why the same tier that proposed the plan is the one that
doubles back to doubt it, are Chapter 6's subject in full. The
**`lgtm-python`** skill supplies the scaffold conventions Generate draws
on — FastAPI service shapes, `pytest`/`pytest-django` layout, the
Containerfile pattern every extracted service follows.

{% include excalidraw.html file="adlc-tooling" alt="A seven-phase cycle, each phase annotated with the real tool role for this project's stack: Frame — human, intent plus PRD; Map — manual reconnaissance plus the lgtm-python skill, no MCP equivalent; Plan — lgtm-relay, Opus plans; Generate — lgtm-relay, Sonnet executes, plus lgtm-python scaffolds; Verify — lgtm-relay, Opus validates, pytest plus Newman plus a security scan; Operate — lgtm-docker-stack or lgtm-minikube-stack plus feature flags; Reconcile — the three ledger files." caption="Figure 5.3 — The ADLC's seven phases, annotated with the real tool at each one — including where the tooling runs out" %}

Figure 5.3 names a gap directly rather than papering over it: Map has no
MCP server standing behind it the way a framework-specific migration
toolchain might. There is no live, version-matched migration assistant for
this project's stack to query the way an equivalent tool exists for
other ecosystems — Map substitutes careful manual reading of the Django
app plus the `lgtm-python` skill's scaffold conventions. This is named
explicitly, not implied away, because a reader following this book's loop
in their own Python project shouldn't expect a tool that doesn't exist to
show up later. Chapter 6 returns to this gap and names what actually
substitutes for it in day-to-day use.

## Local versus hosted execution

One design choice changes the shape of a team's workflow independently of
which phase is running: *where* the coding agent actually executes — on an
engineer's own machine, or inside a managed, shared execution environment.

{% include excalidraw.html file="adlc-local-vs-hosted" alt="A shared outer path (express intent, learn and iterate, monitoring and observability, deploy and ship) flanked by two parallel inner bands covering agent understands through human review. The local band runs each step through a local coding agent plus uv, pytest, and Testcontainers against Docker Engine. The hosted band runs the same steps through a hosted AI platform, with agent tests and docs landing in GitHub Actions' code-ci.yml. Both bands converge back onto the shared deploy-and-ship step." caption="Figure 5.4 — The same agentic loop, run two ways: a local execution path (uv plus Docker Engine) versus a hosted path (a hosted AI platform plus GitHub Actions)" %}

The **local** path in Figure 5.4 keeps the agent on the developer's own
machine, running `uv run pytest` and Testcontainers against a local Docker
Engine. It gives the engineer full visibility into every file the agent
touches and every command it runs, at the cost of tying the loop's speed to
whatever that one machine can do. The **hosted** path runs the equivalent
steps inside a managed AI platform, with `code-ci.yml` standing in for
"agent tests and docs" as the hosted, reproducible equivalent of the same
check. Both paths converge back onto the same "deploy and ship" step and
the same equivalence gate — the choice of where Generate and Verify
*execute* doesn't change what Verify *checks*, which is exactly why this
book treats the two paths as interchangeable rather than naming one as the
"real" workflow and the other as a convenience.

## Why this matters specifically for modernization

A greenfield feature and a strangler-fig extraction look similar in the
ADLC's phase list, but they are not equally forgiving of a skipped gate.
Greenfield code has no existing behavior to preserve — if Verify's
equivalence check fails, there's no "before" state a user was depending on.
A strangler-fig extraction's entire premise is that a request routed
through the new FastAPI service behaves identically to the same request
hitting the Django monolith it replaces, for every caller, including the
callers nobody thought to ask. That premise is exactly what the Plan gate
and the Verify gate exist to protect: Plan is where a human catches "this
step quietly changes behavior nobody signed off on changing" before a diff
exists to review line by line; Verify is where the behavior-equivalence
suite — Chapter 10 builds it, every extraction chapter from Chapter 15
onward runs it — turns "I believe this behaves the same" into "this
produced 58 identical assertions against the real backend, over a real
socket." Collapse the ADLC's speed without keeping both gates, and a
migration doesn't get safer along with getting faster — it gets a
confident wrong answer shipped in minutes instead of weeks.

> **ADLC in Action** — The two gates this chapter names aren't a
> theoretical safeguard added for this book's narrative; they're the exact
> two points where this project's own Review extraction (Chapter 7's
> subject) actually stopped and waited on a human. The Plan gate approved a
> five-step extraction sequence before any FastAPI code existed. The Verify
> gate caught a real defect — a request body silently arriving empty at the
> monolith — that every in-process test had missed, because the automated
> suite that caught it had to run against a real socket instead of an
> in-process stand-in to see it at all. Chapter 7 narrates exactly what each gate
> caught and what would have shipped if either one had been skipped.

## The limits: where humans stay in control

Two decisions in this lifecycle never move to an agent, regardless of how
capable the tooling gets, and naming them here sets up Chapter 6's claim
that no amount of tooling changes who holds the authority to approve. The
first is **what "equivalent" means for this specific step** — an agent can
run a suite and report its result, but deciding that suite's coverage is
the right coverage for the stakes of this particular extraction is a
judgment call, not a retrievable fact. The second is **whether to proceed
past a gate when the evidence is ambiguous** — a green suite run is
evidence that a change is probably safe, not proof that it is, and the
decision to trust that evidence anyway, or to reach for an adversarial
check instead, has to be made by someone who can be held accountable for
being wrong. Chapter 7 shows exactly what that second judgment call looked
like in practice, on a real extraction, with a suite that passed every
assertion while hiding a real defect underneath.

## What's next

This chapter named the lifecycle — seven phases, two gates, three ledger
artifacts — without yet naming who or what actually carries each phase out
day to day. **Chapter 6, "Agents, Skills & MCP Tools in the Loop,"** opens
that up: the `lgtm-relay` tiering in full, the skill map this project
draws on, and a plain accounting of what substitutes for the MCP surface
this project's stack doesn't have. **Chapter 7** then runs the whole loop
once, end to end, on real work, and shows exactly what its safety net
caught.

---

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; the phases, gates, and ledger artifacts it describes are the ones this project actually uses, and Chapter 7 exercises them against checked-in evidence.*
