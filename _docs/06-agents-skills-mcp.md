---
title: "Agents, Skills & MCP Tools in the Loop"
order: 6
part: "The AI Development Lifecycle (ADLC)"
description: "The agent-tier relay (plan, execute, validate); the MCP surface for Python tooling; the reusable skill map; when the human must decide."
---

Chapter 5 named the seven phases of the ADLC and the two places a human has
to stop the loop and decide. It also named, in passing, three building
blocks that fill those phases: a tiered model relay, a family of skills, and
an MCP surface this project's stack doesn't fully have. This chapter opens
each of those up. Three building blocks compose into every ADLC phase:
**agents** (a model in a loop with tools, deciding what to do next),
**skills** (packaged, repeatable instructions an agent loads before it
acts), and **MCP tools** (servers that hand an agent a real toolchain to
act against, not just a prompt to reason from) — and this chapter is where
the last of those three gets named directly for what this stack doesn't
have, not just what it does.

## Agents: a model in a loop with tools

An agent, in the sense this book uses the word, is not a single clever
prompt. It's a model given three things a prompt alone doesn't have: a loop
(the model can take an action, observe the result, and decide what to do
next, repeatedly, without a human re-prompting it after every step), a set
of tools (the ability to read a file, run a shell command, call an MCP
server, or launch another agent), and a stopping condition (a task is
"done," a plan is "approved," a gate is "passed"). Strip away the loop and
you have a chatbot that can describe what it would do. Strip away the tools
and you have a model that can only talk about the codebase, never touch it.
The loop plus the tools is what turns "the agent understood the request"
into "the agent produced a passing diff."

The simplest version of this is a single agent: one model, one loop, one
set of tools, working a task start to finish. Much of the mechanical work in
a build like this — scaffolding a FastAPI service, writing a chapter's
prose — runs as a single agent, because a single loop with the right tools
is the cheapest way to get a bounded task done, and adding a second agent to
a task that doesn't need one is pure coordination overhead with no
offsetting benefit.

## The relay: plan, execute, validate

The more interesting case is **multi-agent orchestration**: more than one
agent, each with a distinct role and a distinct set of tools, coordinated so
that one agent's output becomes another's input, and — critically — so that
no single agent is trusted to grade its own work. This project's Plan and
Verify phases are carried out by exactly this pattern, implemented as the
**`lgtm-relay`** skill, under a name worth being precise about: **plan →
execute → validate**.

{% include excalidraw.html file="plan-execute-validate-relay" alt="Six boxes in a row: Frame (human, states intent, writes the decisions.md entry), Plan tier (Opus, reads Frame plus Map recon, drafts the step plan), Human gate 1 (plan approval, before any diff exists), Execute tier (Sonnet, Generate: scaffolds, writes code and tests, runs them), Validate tier (Opus again, adversarial: re-reads plan and diff against the equivalence suite), Human gate 2 (equivalence sign-off, Verify phase). A dashed line below the row connects the Plan and Validate boxes, labeled: same model tier, now adversarial, not self-vouching." caption="Figure 6.1 — The relay: the planning tier drafts, the execution tier builds, the same planning tier validates adversarially, with a human gate on either side of Generate" %}

One model tier — Opus, in the planning role — reads the Frame statement,
does the Map-phase reconnaissance, and drafts a concrete step plan: what
becomes a `decisions.md` entry and a row in `build-plan.md`. That plan sits
in front of a human gate before anything else happens; Chapter 5 called
this the cheapest place in the whole lifecycle to catch a wrong assumption,
and a second model's enthusiasm for its own plan is not a substitute for
that human's sign-off. Once the plan is approved, a second model tier —
Sonnet, in the execution role — carries out Generate: it scaffolds the
FastAPI/aiokafka/grpcio/Strawberry service shape, writes the code, writes
the tests, and runs them. It does not get to decide, on its own authority,
that its own output is correct — that question goes back to the first
tier, now acting in a third, *adversarial* role: it re-reads the approved
plan, re-reads the diff the execution tier actually produced, and checks the
two against each other and against the behavior-equivalence suite before
recommending the second human gate. The same model tier that proposed the
plan is the one skeptical enough to doubt whether its own plan was executed
faithfully — a different posture than "wrote it, therefore vouches for it."

```
A review-extraction plan draft -- the planning tier's output, before the
first human gate

S1  Build the behavior-equivalence suite against the running monolith
    (Newman collection; happy path + out-of-stock + payment-decline).
S2  Stand up a flag-gated ASGI strangler proxy, default every request
    to the monolith.
S3  Build examples/02-review-service as idiomatic FastAPI + async
    SQLAlchemy; equivalence gate must go green before cutover.
S4  Flip STRANGLER_REVIEW_ENABLED; re-run the equivalence suite through
    the proxy; decommission the monolith's review module only after a
    green re-run.

-- awaiting human approval before S3 begins --
```

Why call this "orchestration" rather than just "two models talking to each
other"? Because the planning tier's validating pass is not a peer review
between equals — it supervises, in the specific sense of holding authority
over whether the execution tier's work is accepted. The walkthrough in
Chapter 7 shows exactly what that relay caught, and what it didn't catch on
the first pass, on the Review extraction.

One more distinction matters here: *orchestration* is not the same thing
as *parallelism*. The plan → execute → validate relay is strictly
sequential — each phase's output gates the next, and the whole point is
that nothing in Generate starts before a human has approved Plan.
Elsewhere, independent agents *do* run in parallel — authoring separate
chapter files or generating diagrams can be parallelized because they touch
disjoint files, while a shared build artifact or ledger is serialized to
one writer at a time under a single-writer rule. Multi-agent orchestration,
in other words, is a design decision about *dependencies between tasks*,
not a blanket instruction to use more agents. A task with no shared state
and no approval gate between its pieces is a good candidate for parallel
agents; a task where one piece's output must be approved before the next
begins — Plan before Generate, Generate before Verify — is not, no matter
how tempting it is to save wall-clock time by running them together.

## Skills: packaged, repeatable instructions

An agent with tools can do almost anything; that's also its biggest
liability, because "almost anything" includes solving a well-understood
problem in a slightly different, slightly wrong way every single time it's
asked. A **skill**, in the sense this project uses the term, is a packaged,
named set of instructions an agent loads before it acts on a particular
kind of task — not a suggestion buried in a long system prompt, but a
discrete, invocable unit with its own name, its own triggers, and its own
worked conventions, so that the fifth time an agent scaffolds a FastAPI
service it makes the same choices the first time did.

This project runs on a family of skills with a shared naming convention,
the **`lgtm-*`** family, and naming them concretely is more useful than
describing skills in the abstract:

- **`lgtm-relay`** is the plan → execute → validate tiering described
  above — the mechanism every extraction's Plan and Verify phases run
  through.
- **`lgtm-python`** scaffolds the dev toolchain for a new Python service —
  uv, the Python 3.14 interpreter pin, the FastAPI/aiokafka/grpcio/
  Strawberry service shapes, the structured logging convention, the
  pytest/ruff/Testcontainers test layout — so every service extraction in
  this book starts from the same known-good baseline instead of a
  hand-assembled one that drifts service to service.
- **`lgtm-diagram-generator`** generates figures from a short Python spec
  of boxes and arrows, so the diagrams across many chapters share one
  visual language instead of each chapter inventing its own — every figure
  in this book, including this one, is built this way.
- **`lgtm-docker-stack`** stands up the local observability substrate —
  Postgres, Kafka, the LGTM stack — that every extraction's tests and
  behavior-equivalence suite run against.
- **`lgtm-github`** carries the release-sync and commit-convention
  discipline for pushing a finished iteration upstream, gated, per this
  project's own standing rule, on a human's explicit go-ahead.

A skill is not only a packaged *task*; it's also a packaged *boundary*.
The second kind of skill this project leans on hardest is project
governance through a context file, `AGENTS.md`, that lives inside each
generated service directory and constrains every agent that works on it
afterward, whether or not that agent remembers how the project started.
`examples/02-review-service/AGENTS.md` states the pattern directly: it
records the module's two-phase migration history, pins the exact dependency
versions in use, and tells an agent picking the module up later not to go
looking for a Phase A implementation that was never committed as code —
only measured and written up in `MIGRATION.md`. Read that for what it
actually does: it doesn't trust an agent's memory of how a prior session
left things, and it doesn't make a future agent re-derive context from a
transcript nobody kept. That's a governance file doing exactly the job a
style guide or an architecture review board does in a traditional SDLC —
except it travels with the repository, applies to every agent that opens
it rather than to whichever reviewer is on call, and costs nothing to
re-read on the hundredth feature the way it did on the first.

## The MCP surface — and the gap this stack doesn't paper over

Skills tell an agent *how* to approach a task; they don't, by themselves,
give it anything new to act on. An agent without tool access can still
describe a library's configuration from training data that may be a year
stale, with no way to check that claim against the version actually
running. The **Model Context Protocol (MCP)** closes that gap for the
ecosystems that have it: an MCP server is a small, purpose-built service
that exposes a fixed set of callable tools — not a chat interface, a set of
functions with real inputs and real, structured outputs — that an agent can
call mid-loop to get ground truth instead of a guess.

Here is where this chapter has to say something the Java sibling's
equivalent chapter doesn't: **there is no framework-specific MCP server for
this project's stack.** No tool exposes live, version-matched FastAPI
documentation the way a Quarkus-aware MCP server exposes Quarkus
documentation; no tool scaffolds an aiokafka consumer or validates a
Starlette route's structure the way an integration-framework-aware MCP
server validates a route definition before it's deployed. This is named
explicitly, per `_plans/decisions.md` (DRQ-020), rather than implied away —
a reader following this book's loop in their own Python project shouldn't
expect a tool that doesn't exist to show up later.

Three substitutes fill that gap in this project's day-to-day practice, and
naming them concretely is more useful than leaving "manual reconnaissance"
as an unexplained phrase:

1. **The `lgtm-python` skill's scaffold conventions** stand in for a live
   scaffolding tool — the same job `quarkus_create`-style scaffolding does
   elsewhere, done by a skill's packaged conventions instead of an MCP
   call against a running service.
2. **Manual reconnaissance** — actually reading the Django app's models,
   views, and URL configuration before drafting a plan — stands in for a
   dependency-mapping tool. Map's output is only as good as this reading
   is thorough, which is exactly why Chapter 7's Map section narrates what
   that reading actually found on the Review extraction, not just that it
   happened.
3. **The generic MCP surface** — a filesystem, a shell, a web-fetch
   tool — still grounds an agent in the real, version-pinned
   `pyproject.toml` and `uv.lock` a project actually carries, even without
   a framework-specific server layered on top. An agent that reads
   `pyproject.toml` before writing an import is already doing better than
   one working from memory of what version "usually" ships.

{% include excalidraw.html file="asgi-strangler-proxy-flow" alt="A client request hits the strangler proxy's one catch-all route, mounted at the application root. A backend-selection function matches the full request path against six fixed prefixes, each mapped to one operator-configured backend base URL; no match returns a real 404. The matched request is rebuilt: hop-by-hop headers are stripped, the body is buffered so the outbound request carries a correct Content-Length instead of falling back to chunked encoding, and the request streams to the backend. A reachable backend's response streams back to the client verbatim; an unreachable backend becomes a real 502, never a swallowed 200. A callout names the trap: the full request path must be matched, not a route-pattern-relative value with the mount prefix already stripped." caption="Figure 6.2 — The Python analog of a content-based router, built from first principles instead of an integration framework" %}

That absence of a framework-specific router also shapes what Generate
actually produces for this project's own strangler seam. Where a full
integration framework ships a content-based router as a built-in component,
this project's `examples/01-strangler-proxy/` builds the equivalent from
first principles: one Starlette catch-all route, a backend-selection
function that matches the request's full path against six fixed prefixes,
and explicit, commented handling of the two things a hand-rolled proxy has
to get right that a mature framework would otherwise guarantee — stripping
hop-by-hop headers so a value computed for one hop isn't blindly forwarded
to the next, and buffering the request body so the outbound call carries a
correct `Content-Length` instead of silently falling back to chunked
transfer encoding. The module's own docstring names the trap explicitly:
match the request's *full* path, never a route-pattern-relative value with
a mount prefix already stripped, because a future refactor that gets this
wrong fails silently — every request falls through to nothing. Building
this proxy without a framework-aware MCP tool to validate its structure is
exactly the gap named above made concrete; Chapter 14 builds the proxy in
full, and Chapter 7 narrates the real defect that single design decision
was hiding before a real-socket test caught it.

{% include excalidraw.html file="structural-vs-behavioral-gates" alt="Two stacked panels. Top: the structural gate, here necessarily weaker and more manual than a live route-validator MCP tool would be — ruff check plus Python's own import-time wiring, where a Starlette or FastAPI app that fails to construct raises immediately rather than deploying silently. It catches a malformed route registration or a typo'd dependency signature, but has no opinion about whether a routing predicate matches the right requests once real traffic flows. Bottom: the behavioral gate, the Newman equivalence suite and its adversarial follow-up, run during Verify against a running service. This is the layer that caught the strangler proxy's real chunked-body bug: the in-process routing tests passed while the proxy silently sent every POST upstream with no body, because only a real socket run surfaces that class of defect." caption="Figure 6.3 — The structural gate (what ruff and import-time wiring catch) and the behavioral gate (what the equivalence suite catches) are different layers, and this stack's structural layer is weaker than a framework-aware MCP tool's would be" %}

That weaker structural layer is worth being precise about, because it's the
direct consequence of the MCP gap named above. `ruff check` and Python's
own import-time wiring — a Starlette or FastAPI app that fails to construct
raises immediately rather than deploying silently — catch a malformed route
registration, an unresolved import, or a typo'd dependency signature: the
class of defect that would otherwise surface as a confusing traceback. They
have no opinion about whether a routing predicate matches the right
requests once real traffic flows through it. That gap is exactly where the
behavioral gate — the Newman equivalence suite and its adversarial
follow-up, run during Verify against a running service — has to do more
work in this project than it would if a live structural validator existed
to narrow the search space first. Chapter 7's chunked-body bug is the
concrete proof: the in-process routing tests passed cleanly, because
nothing about Python's import-time checks or a mock ASGI transport could
see that the proxy's outbound request silently carried no body. Only a
real socket, against a real WSGI backend, could.

## How the three compose, phase by phase

None of the three building blocks in this chapter does anything alone; the
ADLC's seven phases are where they combine.

- **Frame** stays entirely human — no agent, skill, or tool substitutes
  for a person stating intent and writing the decision-log entry.
- **Map** is where the gap named above shows up first: manual
  reconnaissance plus the `lgtm-python` skill's conventions ground the
  agent's understanding of the Django app's shape before any plan gets
  drafted, in place of a live MCP-driven dependency map.
- **Plan** is the planning tier of the relay, informed by whatever Map
  turned up, producing the step plan that sits in front of the first human
  gate.
- **Generate** is the execution tier, using the project's skills
  (`lgtm-python`, the per-service `AGENTS.md` governance files) to produce
  the actual diff — a hand-rolled ASGI proxy, a FastAPI service shape, an
  aiokafka consumer, whatever the step calls for.
- **Verify** returns to the planning tier in its adversarial role, checking
  the diff against the approved plan and the behavior-equivalence suite —
  carrying more of the weight here than it would with a stronger
  structural layer behind it, per the previous section.
- **Operate** and **Reconcile** are mostly governance-file and ledger
  work — `AGENTS.md` keeps constraining any agent that touches the running
  service, and the same three ledger artifacts Chapter 5 introduced record
  what actually happened.

## What's next

This chapter named the actors — the relay's two tiers in a supervisor
relationship, the `lgtm-*` skills and the `AGENTS.md` governance layer, and
the plain accounting of what substitutes for an MCP surface this stack
doesn't have — without yet proving any of it holds together under real
pressure. That proof is Chapter 7's entire job: it runs this exact
machinery once, end to end, on the Review extraction, and narrates a real
Python-shaped defect the safety net caught before it reached a reader.

---

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — no runnable example of its own; the `lgtm-*` skills, the `AGENTS.md` governance pattern (`examples/02-review-service/AGENTS.md`), and the proxy's routing logic (`examples/01-strangler-proxy/app/main.py`) are all checkable in the repository.*
