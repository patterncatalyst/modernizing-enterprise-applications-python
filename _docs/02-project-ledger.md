---
title: "The Project Ledger"
order: 2
part: "Setting Up"
description: "The ADLC's ledger: the decision log, the build plan, the iteration records, and the reconciliation log that completes it, introduced as the reader's own migration memory."
---

Chapter 1 got the toolchain running: uv, Python 3.14, a Docker compose stack
standing in for the services this book's monolith will eventually depend on,
and a green Newman run against the monolith you just started. Everything from
here forward assumes that toolchain works. But before any of it touches the
monolith this book builds in Part 3, there is one more piece of setup, and it
is not a tool at all: it is a small set of plain-text files, kept with the
project and updated continuously, every time a decision gets made or a step
of work finishes. This chapter introduces that **project ledger**: the
decision log, the build plan, and the reconciliation log that became
this project's own durable memory while it was being built, and that you can
keep the same way on your own migration. By the end of this chapter you will
know what each file is for, why an agent-driven modernization effort cannot
safely proceed without them, and where to look if you ever need to pick the
work back up from wherever it was left off.

## Why a ledger, and why now

Every chapter from Part 5 onward in this book narrates the same basic shape of
work: a human states what should happen, an agent does reconnaissance,
produces a plan, writes code against that plan, verifies the result, rolls it
out, and records the outcome. Part 2 names that shape precisely: the
**Frame → Map → Plan → Generate → Verify → Operate → Reconcile** cycle this
book calls the ADLC, the Agentic Development Lifecycle, and Part 2 is where you
will see it defined phase by phase. This chapter is not that explanation. It
exists because the ADLC's last phase, Reconcile, is not an abstraction; it is
a few concrete files that a human can open, read, and trust, and you need to
know those files exist and what they contain before you watch them get used.

Here is the problem a ledger solves, independent of any particular framework
or phase model. An agent-assisted modernization effort is not one long
conversation. It is dozens of short ones, spread across days or weeks, often
by different people, sometimes interrupted by something as mundane as a
laptop reboot. A single Claude Code session has no memory of a session from
three days ago. A human reviewing a pull request six weeks from now has no
memory of the exact reasoning that led to a choice made in week one. And an
agent picking up a half-finished extraction has to somehow know not just what
the code currently looks like, but what was *already decided* and must not be
silently re-decided differently this time. Without a durable, external
record, every one of those gaps becomes an opportunity for drift: a decision
quietly gets reversed because nobody remembered it was made, a step gets
redone because nobody could tell it was already done, or, worse, a step
gets skipped because nobody could tell it was *not* done. A ledger is
the answer to "where does the context live when no single conversation is
long enough to hold it."

This matters more for a modernization project than for most other kinds of
software work, for a reason Part 1 develops in full: a modernization effort is
refactoring under the hardest possible constraint, that the system must keep
behaving the way it already behaves, applied to code someone else wrote, for
reasons nobody fully remembers, that real customers depend on today. An agent
can retry a risky change as many times as it likes with no human watching;
that is exactly what makes agent-assisted work fast. But an agent cannot be
trusted to also decide, on its own authority, that one of those retries is
safe to ship against a production system. That is the job of the two human
gates Part 2 introduces, Plan approval and Verify sign-off, and both gates
only work if there is something durable on each side of them: a record of
what was proposed, and a record of what was actually confirmed. The ledger is
that record.

## The decision log

The first ledger artifact is an append-only decision log, one row per
decision, each with a short, stable identifier so later work can cite it by
name. Every row names the decision, the reasoning behind it, and a status:
`fixed` for something the user set and that nothing downstream is allowed to
relitigate, `accepted` for a synthesis decision a later step could in
principle revisit but hasn't, and `proposed` for a recommended default still
awaiting confirmation. The numbering never resets and rows are never deleted;
if a decision changes, a *new* row records the change and says what it
supersedes, so the history of how the project arrived at its current state
stays intact rather than being overwritten.

Three example rows make the pattern concrete. The first is about as small a
decision as a project makes, and it is exactly the kind of thing that would
otherwise get re-litigated by accident three weeks later:

```
Compose engine = docker-primary, podman-compatible (the project's own
choice). | User-fixed. Docker is the primary engine so the
dev-loop instructions transfer; "podman-compatible" is stated as a
constraint (no Docker-only compose syntax) rather than a second maintained
compose file. | fixed
```

Nothing about that row is dramatic, which is the point. Without it written
down, a later contributor, human or agent, reaching for container tooling
has no way to know that one engine was the project's chosen primary rather
than an accident of whoever set up their machine first, or why a second
compose file was never created to match it. The row is what turns
"I think we picked Docker" into a checkable fact with a reason attached.

The second row is a correction, and it is the kind that matters precisely
because nobody caught it until real code existed to check the plan against:

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

That correction matters well beyond one config file. Chapter 27 builds a
per-service scorecard of exactly what each of the eight services actually
uses (`/health` endpoints, structured error handling, retry logic), and
that scorecard depends on the chassis chapter's own starting claim about
*config* being correct first. A plan that says "pydantic-settings" and code
that actually ships a frozen `@dataclass` are not a contradiction to paper
over; that correction row is what makes the discrepancy a dated, named fact
instead of something a reader discovers by diffing the plan against `grep`.

The third row is a strategy decision, and it is the one that shapes the
project's single highest-stakes moment: the point where the monolith stops
being part of the running system:

```
Monolith end-state = fully decommissioned + frozen-not-deleted in-repo: the
monolith stays at examples/00-monolith/ as the golden-baseline referent and
a break-glass fallback, but compose.yaml/scripts/demos no longer start it as
part of the live topology. Learner-reference preservation: a
reference/monolith-before branch plus v0-monolith and stage/01..06 tags,
re-bootable break-glass. Rejected: deleting the monolith entirely (destroys
the equivalence suite's only pre-extraction referent and the book's own
"before" picture). | Fixed -- user decision, approved over full deletion,
explicitly called out as the highest-stakes decision at that gate. | fixed
```

This is a case where a decision row does real design work, not just
record-keeping. It commits the project to a specific, reversible-feeling but
actually-irreversible move, retiring the monolith from the live system
while keeping it runnable in-repo as history, and it records the rejected
alternative in the same breath, so a later contributor tempted to "clean up"
by deleting `examples/00-monolith/` entirely can read exactly why that was
considered and turned down.

## The build plan

If the decision log is the project's memory of *what was decided*, the build
plan is its memory of *what is being built and in what order*. This
project's build plan is a single long document that covers the chosen
approach and the alternatives it rejected, the full chapter-by-chapter site
architecture, the reference monolith's design (including every flaw
planted in it and which later chapter cures each one), the strangler-fig
decomposition sequence service by service, the ADLC's own phase table, and an
iteration-by-iteration release plan with explicit risks and how each is
detected.

The section of the build plan most directly relevant to this chapter's
argument is its phase table, because it is where the ADLC's seventh phase,
Reconcile, gets tied explicitly to the ledger you are reading about right
now:

```
| 7. Reconcile | Append decision outcomes, update build-plan status, record
drift | -- | the three ledger artifacts | change log / traceability |
```

Part 2 will unpack what "Reconcile" means as a phase in the loop a human and
an agent run together. What matters here is narrower and more concrete: the
table names its mechanism, and the mechanism is these files. Reconcile is not
a separate ceremony bolted onto the end of a step; it *is* the act of
writing an outcome into the decision log, updating a status line in the
build plan, and appending a section to the reconciliation log. The phase
and the artifact are the same thing, which is exactly why this chapter
precedes Part 2 rather than following it: you need to recognize these files
on sight before you watch a chapter narrate the loop that writes to them.

The same table's second row is also worth sitting with, because this book's
own ADLC has a gap in exactly the place that table
names: Map has no framework-aware MCP server to lean on for
this stack, so that cell reads **manual reconnaissance plus the
scaffolding skill** instead of a live, framework-aware tool. Chapter 6
explains why that gap exists and what it costs in practice; this chapter's
job is only to show you where the gap is recorded, in the same phase table
that names every other phase's tooling, in plain sight rather than tucked
into a footnote.

## Per-iteration plans and the resume record

The decision log and the build plan both operate at the scale of the whole
project. Day to day, the unit of work is one iteration, and this project
gives each iteration its own plan file. Each one lays out that iteration's
approach, its steps grouped into parallel-safe lanes with explicit
dependencies between them, a per-lane acceptance checklist, the risks
specific to that iteration and how to detect them, and, where a choice
couldn't be made in advance, an explicit list of open decisions for the user
to resolve before the work that depends on them proceeds.

What takes the place of a separate status file, the thing that tells the
next session where to resume, is a short narrative appended to the tail of
the decision log at the close of each iteration. The most recent one, written
when the project's last chapter landed, says exactly where things stand and
names what is not yet done rather than implying the project is finished: it
records that the final chapter is built and committed, that no further
appendix chapters remain, and that what is left is not an open verification
gate but scope the approved plans always treated as separate future work.

Read that resume note as what it actually is: not documentation written after
the fact to describe a finished piece of work, but the kind of note a
dedicated status file would carry, placed instead at the point in the
decision log where the iteration's last decision was recorded. It names
exactly what is done, exactly what still depends on a human running
something live, and exactly what was always out of scope rather than merely
forgotten, including, notably, the very chapter you are reading now. Nobody
has to re-read the whole project's history to find the current state; the
tail of the decision log is where it lives.

{% include excalidraw.html file="ledger-files-to-adlc-phases" alt="The ledger's files mapped onto the ADLC's seven phases: the build plan and each iteration's own plan are produced during Plan, those same files are what Generate and Verify execute and check against, and the decision log plus the reconciliation log are written during Reconcile, which also loops back to update the build plan's own status line. Plan and Verify are marked as the two human-gate phases." caption="Figure 2.1: The ledger's files, mapped onto the ADLC's phases, and how an interrupted session resumes from them" %}

## Governing the agents: `AGENTS.md`

The three artifacts above govern the *project*: what was decided, what is
being built, where things stand. A different kind of file in this project's
example directories governs something narrower and more immediate: how an
agent is supposed to behave while it is actually working inside a given
piece of code. `examples/00-monolith/`, for instance, carries its own
`AGENTS.md`, opening with exactly what the module is, what state it is
frozen in as of this project's last extraction, and an explicit instruction
not to "fix" any of its six planted smells without first reading
`SMELLS.md`, because the smells are planted teaching material, not bugs.
It goes on to pin the toolchain an agent must use inside that one directory:
uv only, never a bare `pip install` or `python -m venv`, and the exact
dependency versions in play.

None of that is decision history; it is standing operating procedure,
scoped to this one codebase, that every agent session working in that
directory inherits automatically rather than having to be re-explained each
time. It is a narrower kind of ledger than the decision log or the
build plan, but it is the same underlying idea: write the thing down
once, durably, so it does not have to live only in one person's memory or one
session's context window.

## The ledger and the two human gates

Part 2 names two points in the ADLC where a human, not an agent, has to stop
the loop and decide: approving a plan before any code gets written against
it, and signing off that a verification result is sufficient evidence to
trust a change before it ships. Both gates are only meaningful if there is
something concrete for a human to look at, and the ledger is that something.
A plan-approval gate without a written plan is just a conversation nobody can
audit afterward; this project's gate is a human reading an iteration's plan
file, its lanes and acceptance criteria, before a single line of that
iteration's code was written, and, at several points across this project's
own history, reading a short list of open decisions and picking one
explicitly, with the choice and the reason both recorded as a new decision
row rather than assumed. A verify-sign-off gate without a recorded result is
just trust on faith; this project's gate is a human reading a decision row or
a reconciliation-log section that says, concretely, which suite ran and what
it reported, not merely that an agent claims it passed.

## Reconcile, and the artifact that is already live

The phase table names a third ledger artifact alongside the decision log and
the build plan: the reconciliation log, an append-only record that tracks
every piece of code or design this project reused or adapted from another
source, including for one service a
database-backed saga orchestrator reused from a separate pattern catalog,
against exactly what diverged and why. Each extraction's reconcile pass
appends a new section naming the source, what was kept, what changed, and a
verdict: a **clean adaptation** if every divergence is named and traced to an
accepted decision, or **drift** if something changed without being recorded,
which has to be resolved before that extraction counts as done.
This project built all three ledger artifacts together from its very first
iteration, and the reconciliation log has been live and growing ever
since: by the time this project's last chapter was authored, it carried a
dedicated section for nearly every iteration this book's extractions went
through, each one a concrete record of what was borrowed, what was changed,
and why the change was fine.

## What's next

Part 1, "Why Modernize," picks up a different question before any ledger
entry gets written against this project's own monolith: not how the work
gets recorded, but why a modernization effort, strangling a monolith into
services one seam at a time, counts as disciplined engineering
rather than following fashion, and when it does not. Part 2, "The Agentic
Development Lifecycle (ADLC)," is where the phase model this chapter has only
gestured at (Frame, Map, Plan, Generate, Verify, Operate, and the Reconcile
phase that writes to the files you just read about) gets defined properly,
with this project's own ledger as its running, working example rather than a
diagram. Chapter 3, "Modernization as Engineering, Not Fashion," is next.
