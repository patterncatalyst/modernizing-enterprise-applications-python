---
title: "The ADLC Safety Net"
order: 7
part: "The Agentic Development Lifecycle (ADLC)"
description: "Tests, contracts, and reconciliation as the guardrails that make agentic generation trustworthy, with a full loop run end-to-end on a trivial change."
---

Chapter 5 named the seven phases and the two gates. Chapter 6 named the
actors that carry each phase out, and the one named gap in this project's
tooling. Neither chapter proved the loop actually holds together under real
work, with a real monolith and a real extraction on the other end of it.
This chapter does. Every example in it is the Review extraction that
produced `examples/01-strangler-proxy/` and `examples/02-review-service/` in
this project — not a staged illustration, but real files and real newman
runs from the loop itself, recorded in `tooling/newman/GOLDEN-BASELINE.md`.
And because the loop ran against a real project rather than getting
narrated in the abstract, it did what a process under real pressure does:
it caught a real defect before it reached a reader. That's this chapter's
actual subject. The ADLC isn't safe because an agent is careful. It's safe
because the loop has a behavior-equivalence suite wired into it as an
automated gate, two places where a human has to stop and decide, and a
habit of writing down what happened even when — especially when — it
didn't match expectations on the first pass.

## Frame: stating intent, on the record

The Frame phase is where a human writes down what "done" means before any
tool touches a keyboard, because a plan that exists only in someone's head
can't be approved, audited, or disagreed with. For this slice of work, the
frame statement wasn't a chapter-sized essay — it was a single decision-log
row that fixed the one fact everything downstream depends on:

```
The Newman behavior-equivalence suite is the CI equivalence gate for every
future extraction, captured against the monolith and re-run unchanged
against each extracted service.
```

Notice what that one row buys. It doesn't say "write good tests" — it names
a specific artifact (one Postman/Newman collection), a specific invariant
(it never gets edited to make a later service pass), and a specific
enforcement point (the same suite, re-pointed, every time). Every later
phase in this chapter is downstream of that sentence. If the Frame phase
had instead said "an agent will judge whether the extraction looks right,"
there would be no automated gate at all — just a model's self-assessment,
precisely the failure mode Chapter 5 warned against.

## Map: reconnaissance before a single line changes

The Map phase answers "what exactly am I touching" before anything gets
generated, and for Review the answer mattered more than it looked. The
monolith's six bounded contexts share one Postgres schema and one Django
deployable; the question Map had to settle was whether Review was actually
independent enough to cut first, or only looked that way. The
reconnaissance — reading the monolith's `review` app, its dependents, and
its data shape — found that Review was REST-only, had no synchronous call
into or out of it from any other context, and shared only an incidental
dependency on the monolith's authentication setup, not a runtime one. That
is what made Review the right slice to cut first rather than an arbitrary
first pick, per the extraction order argued in full in Chapter 4: it let
the very first pass through the loop exercise the
*entire* seam machinery — the strangler proxy, the FastAPI scaffold, the
equivalence gate, the flag-gated cutover — without a second bounded
context's behavior confounding the result.

Map also surfaced a fact that this chapter keeps returning to: Review's
extracted form was scoped to keep sharing the monolith's
existing `reviews` table — true per-context data ownership is deferred to
Chapter 18/19's data-ownership pass, not this extraction's job. While
Review stayed in that shared-schema form, the extracted service and the
monolith it was being peeled away from would keep reading and writing the
*same rows*. File that fact; it's a large part of why this chapter's bug
stayed hidden as long as it did, and why finding it required more than a
response-shape check.

## Plan: the first human gate

Map produces understanding; Plan produces a commitment, and commitments are
where the ADLC inserts its first stop sign. The step plan for Review laid
out the sequence this chapter narrates: build the equivalence suite against
the running monolith, stand up a flag-gated ASGI strangler proxy defaulting
every request to the monolith, build Review as an idiomatic FastAPI
service, then flip the flag and decommission the monolith's copy. Every one
of those steps carried its own acceptance criterion, and none of them began
until a human read the plan and approved it — not a rubber stamp on a diff,
because at this point there was no diff yet to stamp, only a sequence of
intended diffs.

Had the plan instead said "extract Review and give it its own database from
the start," this extraction would have taken longer to reach its first
green equivalence-gate run — and, as the Verify section below shows, it
would also have hidden less of the defect this chapter is actually about.
The plan that was approved deferred schema ownership as a scoping decision,
not an oversight; a human agreeing to that trade-off before any code
existed is exactly the kind of judgment call Chapter 5 argued can't be
delegated to the agent that drafted the plan.

## Generate: a proxy built from first principles, and a service built idiomatic

With the plan approved, Generate produced two things. The first was
`examples/01-strangler-proxy`, the hand-rolled ASGI reverse proxy Chapter 6
introduced: one Starlette catch-all route, a backend-selection function
matching the request's full path, hop-by-hop headers stripped, and — the
detail everything below turns on — the request body read with
`content=request.stream()`, an async generator passed straight through to
`httpx` rather than read into memory first. The second was
`examples/02-review-service`, built per the project's two-phase policy:
Phase A, a thin FastAPI layer reusing the monolith's Django ORM, was
sketched and measured but never shipped as code once two concrete problems
surfaced while sketching it (a synchronous ORM bridged into an async
framework on every query, and a hard build-time dependency on the entire
monolith just to reach one model); Phase B — idiomatic FastAPI, async
SQLAlchemy, zero Django import — is the only code that actually landed,
documented in full in `examples/02-review-service/MIGRATION.md` alongside
the finding that Phase A and Phase B measure as statistically
indistinguishable on raw startup numbers, which Chapter 3 already reported
in full.

Both pieces passed their own local checks before Verify ever saw them: `uv
run pytest` green, `uv run ruff check .` clean, and
`examples/01-strangler-proxy/tests/test_routing.py`'s in-process
pass-through test confirming the proxy forwarded method, path, query
string, headers, and body correctly — against a mock ASGI transport. That
last clause is the whole chapter, and it's worth sitting with before moving
to Verify.

## Verify: the gate that caught a real defect

Verify is where the behavior-equivalence suite actually runs against a live
stack, and it's also where this chapter's real "the net caught it" story
happened. The first full run — Postgres and the monolith live on `:8000`
under gunicorn (WSGI), the review-service on `:8001`, the proxy on `:8888`,
`STRANGLER_REVIEW_ENABLED` unset — did not go green.

```
Captured — newman, the first live run through the proxy, flag OFF
(tooling/newman/GOLDEN-BASELINE.md, "Run A -- flag OFF")

┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
│            test-scripts │                38 │                1 │
│              assertions │                56 │               20 │
└─────────────────────────┴───────────────────┴──────────────────┘
```

Twenty assertions failed, and not only in the new Review folder: every one
of the four pre-existing checkout scenarios failed too, each for the
identical reason. `POST /api/reviews` with a complete, valid JSON body came
back `400 VALIDATION_FAILED`, claiming every field was missing. `POST
/api/orders` came back the same way. The same unedited collection run
directly against the monolith, with no proxy in the path at all, passed
cleanly — 58/58 — so the defect lived specifically in what the proxy did to
a request on its way through.

The root cause traced back to the one line in `proxy_handler` that forwards
the request body: `content=request.stream()`, an async generator. Because
`httpx` can't know the length of a generator ahead of time, it always sends
the upstream request as `Transfer-Encoding: chunked` rather than with a
`Content-Length` header — correct, RFC-compliant behavior on the wire. The
break was on the monolith's side: Django's WSGI handler reads
`environ["CONTENT_LENGTH"]` and falls back to a **zero-length body** when
that header is absent, because it doesn't honor gunicorn's non-standard
`wsgi.input_terminated` signal for chunked requests. Every `POST` the proxy
routed to the monolith arrived empty, no matter what the client actually
sent — reproduced independently of newman and of the collection entirely,
with a bare `httpx` call against `:8000` carrying a chunked body and
getting the identical empty-body failure.

**Why the in-process tests never saw this.** `test_routing.py`'s
pass-through test drove the proxy entirely through `httpx.ASGITransport` —
an in-process mock transport that never puts a real chunked-encoded request
on a real TCP connection against a real WSGI server. ASGI servers (the
review-service's own uvicorn included) decode chunked bodies correctly
regardless of framing, so the same defect, run against `:8001` instead of
`:8000`, produced no symptom at all. The gap was invisible to every check
that had already passed, for a structural reason — WSGI's handling of
`CONTENT_LENGTH`, not a flaky-test reason a re-run would fix — and it was
invisible specifically *because* the fast, in-process test suite never
touched a real socket.

> **ADLC in Action** — This defect's discovery and its fix happened as two
> separate, dated passes, not one continuous session, and the project's own
> ledger keeps both: the newman run that found it was scoped to
> `tooling/newman/` only, and the acceptance criterion it left open —
> "full suite green through the proxy in both flag states" — was recorded
> as still-open rather than quietly patched around under deadline pressure.
> A follow-up pass, written up as its own section of
> `tooling/newman/GOLDEN-BASELINE.md`, closed it. Writing down "this is
> blocked, here is exactly why" as its own checkpoint — instead of folding
> a half-fixed state into the same commit that claimed the extraction was
> done — is what let the next session start from an accurate map instead of
> rediscovering the same root cause from scratch.

The fix buffered the body instead of streaming it unread:

```python
# app/main.py, proxy_handler() -- before:
content=request.stream(),
# after:
body = await request.body()
content=body,
```

Forwarding `bytes` instead of a stream lets `httpx` compute a correct
`Content-Length` for the upstream request; the hop-by-hop header set
already stripped the inbound `Content-Length` and `Transfer-Encoding`
headers, so no other change was needed. A new regression test,
`test_post_body_forwarded_with_content_length_not_chunked`, captures the
actual outbound request the proxy builds via `httpx.MockTransport` and
asserts directly on its framing: a `Content-Length` header present and
correct, no `Transfer-Encoding: chunked`, and the exact body bytes intact.
Run against the pre-fix code, it fails exactly as expected —
`AssertionError: assert None == '75'`, where `None` is the missing
`Content-Length` the broken code never set. Run against the fix, it passes,
and the full local suite goes to 8/8.

With the fix in place, the same live stack, the same unedited collection,
ran clean in every state the cutover cares about:

```
Captured — newman, post-fix, flag OFF / flag ON / flip-back
(tooling/newman/GOLDEN-BASELINE.md)

Run A  (flag false, monolith)         58/58 assertions, 0 failed
Run B  (flag true,  review-service)   58/58 assertions, 0 failed
Run C  (flag false, flip-back)        58/58 assertions, 0 failed

Negative -- flag true, review-service killed:
  6/6 assertions FAILED, newman exit code 1, every request a real 502
Recovered -- review-service restarted:
  16/16 assertions, 0 failed
```

Run A and Run B are byte-identical in shape — same 19 requests, same 38
test-scripts, same 58 assertions, 0 failed in both — which is exactly the
cutover proof this extraction needed: the same collection, the same
environment, only the proxy's own flag changed, and the response contract
held on both sides of that flip. The negative check matters just as much as
the two positive ones: with the flag on and the review-service process
killed, every request came back a real `502`, never a silently-swallowed
`200`. An equivalence gate that can't fail isn't actually asserting
anything, and this one — tested here by taking the backend it depends on
offline — demonstrably can.

## The second human gate: what "equivalent" actually covers here

{% include excalidraw.html file="shared-table-routing-defect" alt="Two panels. Left: the ASGI strangler proxy can route an /api/reviews request to either the Django monolith or the FastAPI review-service, and because Review's extraction kept sharing the monolith's existing Postgres schema, both backends read and write the exact same rows — a suite that only checks HTTP response shape cannot tell a correctly-served request apart from one that silently fell through, because for this slice both statements describe the same table. Right: what actually closed the gap — exercising a real POST over a real socket against the real WSGI backend, which is exactly the surface where the chunked-body bug was hiding, invisible to the in-process mock-transport tests and caught only once the suite ran against a live socket." caption="Figure 7.1 — Why a response-shape-only check needed a real socket to be trusted here" %}

Finding and fixing the chunked-body bug didn't, by itself, close the Verify
phase. The ADLC's second gate sits exactly here: a human has to look at
"58/58 green" and decide that's sufficient evidence to trust the cutover,
rather than treating a green suite run as self-certifying. That distinction
isn't cosmetic, and Review's shared-schema scoping is exactly why.
Because the monolith and the review-service read and write the *same*
`reviews` rows while the cutover window is open, a suite that only checked
the HTTP response's shape — status code, body — could not, on its own, tell
"served correctly by review-service" apart from "silently fell through to
the monolith and happened to return the same data anyway." For this
extraction specifically, those two outcomes are not just hard to
distinguish — for most of the read traffic, they are observationally
identical, because both backends are looking at the same table. The suite's
real power here was never the response-shape check alone; it was that a
live, real-socket POST against the real WSGI backend is also the exact
surface where a backend that silently received an empty body would fail
differently than one that received the request correctly — which is
precisely the surface the chunked-body bug was hiding on. Signing off on
equivalence meant a person taking responsibility for the judgment that a
real-socket run against both backends, in both flag states, with a negative
check thrown in, was the right coverage for a cutover this entangled — not
merely confirming that an exit code was zero.

## Operate: flipping the flag

With Verify's sign-off recorded, Operate is where `STRANGLER_REVIEW_ENABLED`
actually controls production traffic rather than a test run. The flag's
behavior is exactly what Run A, Run B, and the flip-back proved: `false`
routes `/api/reviews*` to the monolith, `true` routes it to the
review-service, and flipping it back is a config change and a restart, not
a redeploy — the reversibility window Chapter 14 names stays open right up
until the monolith's `review` module is finally decommissioned. No
irreversible step happened during this extraction; that step doesn't arrive
until the final seam, in Chapter 26.

## Reconcile: the ledger closes the loop

Reconcile is the phase most lifecycles skip, and it's the one that makes
this chapter's story legible to anyone who wasn't in the room when it
happened. Nothing about the chunked-body bug was left as a verbal
anecdote: `tooling/newman/GOLDEN-BASELINE.md` carries the dated record of
both passes — the run that found it, left unfixed in that same commit
because the fix was scoped to a separate follow-up, and the repair
pass that closed it — and the project's decision log records the root
cause, the fix, and the regression test in one place a reader can check
against the code directly. Both records also note what stayed *out of
scope* for this extraction: Review's shared-schema
scoping stayed in place, even though giving Review its own schema
from the start would have narrowed the blast radius of a routing mistake —
because true per-context data ownership is Chapter 18/19's subject, not
this one's, and reopening that scope here would have meant re-litigating a
decision the approved plan had already made. That's a real, named deferral,
not a problem papered over.

## The lesson: necessary, not sufficient

{% include excalidraw.html file="adlc-safety-net-layers" alt="Three stacked layers. Layer 1, automated: the Newman behavior-equivalence suite, re-run against every candidate build over a real socket, which caught the chunked-body bug that an in-process mock-transport suite structurally could not see; removing this layer lets every POST through the proxy keep silently arriving empty. Layer 2, adversarial verification: checking the suite's result against what actually persisted in the shared table, not just the HTTP response shape; removing this layer lets a shape-only green run get trusted even when both backends happen to look similar for different reasons. Layer 3, the two human gates: plan approval before any diff exists, and equivalence sign-off judging whether the suite's specific coverage is the right coverage for the stakes; removing this layer means a green suite run gets trusted as self-certifying." caption="Figure 7.2 — The safety net's three layers, and what each one stops" %}

Pull back from the specifics and the shape is simple enough to state in one
sentence: the ADLC is only as safe as its safety net, and that net has
three layers, not one. The behavior-equivalence suite is the automated
layer — cheap enough to re-run after every candidate change, which is what
caught the chunked-body defect the instant it ran against a real socket
instead of a mock transport. Checking the suite's result against what the
shared table actually held, not just the response shape, is the layer that
compensates for the first layer's specific blind spot in a schema this
entangled. And the two human gates — plan approval and equivalence sign-off
— are the layer that decides, on work an agent produced, whether the first
two layers' coverage was actually the right coverage for what was at
stake. Remove the equivalence gate and the chunked-body regression ships
silently, every checkout and every review write arriving empty at the
monolith. Remove the willingness to ask what a shared schema could be
hiding, and a future, subtler version of the same shape of bug — one that
doesn't announce itself with a loud `400` — could pass a response-shape
check without anyone noticing it was never really testing what they thought
it was.

That's also the concrete answer to a question Chapter 5 left open: what,
precisely, does "verify" mean once the suite has already run? It means a
human or a reasoning-model validator asking whether the suite's specific
coverage could be fooled by the specific shape of *this* change — here, a
hand-rolled proxy forwarding a body it never read — and, when the answer is
"maybe," reaching for the real-socket, real-WSGI run that actually
disambiguates it. That's a skill, not a checklist item, and it's the reason
the second gate sits with a person rather than inside the suite itself.

## What's next

This chapter ran the loop once, on real work, and showed its net catch a
real defect before it reached a reader. Part 3 builds the system this loop
goes on to strangle across every chapter that follows — the reference
monolith, its six
bounded contexts, and the deliberate smells planted into it, so every later
pattern arrives because the monolith actually needs it, not because a
chapter outline said so. Part 4 then goes looking for the seams those
smells mark, using domain-driven design and event storming to decide where
the next cut goes before the ADLC runs this same loop again, at rising
difficulty, five more times.

---

*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — it narrates real, checked-in evidence rather than producing new evidence of its own. The defect it centers on is recorded in the project's own test notes under `tooling/newman/`, and the commands it cites are reproducible against `examples/00-monolith`, `examples/01-strangler-proxy`, and `examples/02-review-service`.*
