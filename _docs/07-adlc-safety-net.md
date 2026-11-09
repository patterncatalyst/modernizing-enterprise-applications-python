---
title: "The ADLC Safety Net"
order: 7
part: "The Agentic Development Lifecycle (ADLC)"
description: "Tests, contracts and reconciliation as the guardrails that make agentic generation trustworthy, shown by running the full loop on the Review extraction and the defect it caught."
---

## Learning objectives

By the end of this chapter you can:

- Walk the seven ADLC phases on one real extraction and name the artifact each one leaves behind.
- Explain why a behavior-equivalence suite is the automated gate and what it must never be edited to do.
- Find a defect that in-process tests cannot see by running the equivalence suite over a real socket against the real backend.
- State what the two human gates decide that the equivalence suite can't.
- Say what a negative check proves and why an equivalence gate needs one.

## Why this matters

The loop is safe for three reasons, and an agent being careful isn't one of them. A behavior-equivalence suite runs as an automated gate. A person stops the work twice to decide. And what happened gets written down, especially when it didn't match the plan. The Review extraction, which produced `examples/01-strangler-proxy/` and `examples/02-review-service/`, ran the loop against the real monolith, and the loop caught a defect before it reached a reader. The runs are recorded in `tooling/newman/GOLDEN-BASELINE.md`.

## Frame: state intent on the record

Frame is where a human writes down what "done" means before any tool runs, because a plan that exists only in someone's head can't be approved, audited or disagreed with. For this work the frame was one decision-log row:

```
The Newman behavior-equivalence suite is the CI equivalence gate for every
future extraction, captured against the monolith and re-run unchanged
against each extracted service.
```

The row names an artifact (one Postman/Newman collection), an invariant (it is never edited to make a later service pass) and an enforcement point (the same suite, re-pointed, every time). If Frame had said "an agent will judge whether the extraction looks right," there would be no automated gate, only a model grading its own work.

## Map: reconnaissance before anything changes

Map answers "what exactly am I touching." The monolith's six bounded contexts share one Postgres schema and one Django deployable. Reading the `review` app, its dependents and its data shape showed that Review was REST-only, had no synchronous call into or out of it from any other context, and shared only the monolith's authentication setup. That made it the right first slice rather than an arbitrary pick: the first pass through the loop could exercise the whole seam machinery (strangler proxy, FastAPI scaffold, equivalence gate, flag-gated cutover) without a second context's behavior confounding the result.

Map also fixed a scoping fact. The extracted Review service keeps sharing the monolith's `reviews` table, and per-context data ownership is a later extraction's job. While the schema is shared, the monolith and the extracted service read and write the same rows. That is a large part of why the defect below stayed hidden as long as it did.

## Plan: the first human gate

Plan turns understanding into a commitment, and the ADLC puts its first stop sign there. The plan for Review had four steps: build the equivalence suite against the running monolith, stand up a flag-gated ASGI strangler proxy that defaults every request to the monolith, build Review as an idiomatic FastAPI service, then flip the flag and decommission the monolith's copy. Each step had an acceptance criterion, and none began until a human approved the plan. There was no diff to review yet, only a sequence of intended diffs.

The approved plan deferred schema ownership. Giving Review its own database from the start would have delayed the first green equivalence run. A human accepting that trade-off before any code existed is the kind of judgment the agent that drafted the plan can't make for itself.

## Generate: a proxy from first principles, a service in the idiom

Generate produced two things.

- `examples/01-strangler-proxy`: a hand-rolled ASGI reverse proxy with one Starlette catch-all route, a backend-selection function that matches the full request path, and hop-by-hop headers stripped. The request body was forwarded with `content=request.stream()`, an async generator handed straight to `httpx` instead of being read into memory.
- `examples/02-review-service`: built in two phases, per the project's migration template. Phase A, a thin FastAPI layer reusing the monolith's Django ORM, was sketched and measured but never shipped. It bridged a synchronous ORM into an async framework on every query and made the whole monolith a build-time dependency just to reach one model. Phase B, idiomatic FastAPI with async SQLAlchemy and no Django import, is the code that landed. `examples/02-review-service/MIGRATION.md` records that the two phases measure as statistically indistinguishable on raw startup numbers.

Both passed their local checks before Verify saw them: `uv run pytest` green, `uv run ruff check .` clean, and an in-process pass-through test confirming the proxy forwarded method, path, query string, headers and body through a mock ASGI transport. Remember that last check.

## Verify: catching a real defect

Verify runs the equivalence suite against a live stack: Postgres and the monolith on `:8000` under gunicorn (WSGI), the review-service on `:8001`, the proxy on `:8888`, `STRANGLER_REVIEW_ENABLED` unset. The first run did not go green.

```
Captured: newman, first live run through the proxy, flag OFF
(tooling/newman/GOLDEN-BASELINE.md, "Run A -- flag OFF")

┌─────────────────────────┬───────────────────┬──────────────────┐
│                         │          executed │           failed │
├─────────────────────────┼───────────────────┼──────────────────┤
│                requests │                19 │                0 │
│            test-scripts │                38 │                1 │
│              assertions │                56 │               20 │
└─────────────────────────┴───────────────────┴──────────────────┘
```

Twenty assertions failed, and not only in the new Review folder. The four checkout scenarios that predated Review failed for the same reason: `POST /api/reviews` and `POST /api/orders` with complete, valid JSON came back `400 VALIDATION_FAILED`, claiming every field was missing. The same unedited collection run straight against the monolith, with no proxy in the path, passed 58/58. The defect was in what the proxy did to a request on its way through.

The cause was `content=request.stream()`. `httpx` can't know a generator's length, so it sends the upstream request as `Transfer-Encoding: chunked` with no `Content-Length`, which is correct on the wire. Django's WSGI handler reads `environ["CONTENT_LENGTH"]` and falls back to a zero-length body when it is absent, because it ignores gunicorn's non-standard `wsgi.input_terminated` signal for chunked requests. Every `POST` the proxy routed to the monolith arrived empty. A bare `httpx` call to `:8000` with a chunked body reproduced it without newman or the collection.

The in-process test never saw it. It drove the proxy through `httpx.ASGITransport`, which never puts a chunked request on a real TCP connection against a real WSGI server. ASGI servers, uvicorn in the review-service included, decode chunked bodies correctly, so the same request sent to `:8001` showed no symptom. Re-running wouldn't have helped: the fast in-process checks never touched a socket.

> **ADLC in Action**: The discovery and the fix were two separate, dated passes, and the project ledger keeps both. The newman run that found the defect was scoped to `tooling/newman/` only, and the acceptance criterion it left open, "full suite green through the proxy in both flag states," was recorded as open instead of patched around under deadline pressure. A follow-up pass, written up as its own section of `tooling/newman/GOLDEN-BASELINE.md`, closed it. Recording "blocked, and here is exactly why" as its own checkpoint let the next session start from an accurate map instead of rediscovering the root cause.

The fix buffers the body:

```python
# app/main.py, proxy_handler() -- before:
content=request.stream(),
# after:
body = await request.body()
content=body,
```

With `bytes`, `httpx` computes a correct `Content-Length` for the upstream request. The hop-by-hop header set already strips the inbound `Content-Length` and `Transfer-Encoding`, so nothing else changed. A regression test captures the outbound request through `httpx.MockTransport` and asserts on its framing: `Content-Length` present and correct, no `Transfer-Encoding: chunked`, body bytes intact. Against the pre-fix code it fails with `AssertionError: assert None == '75'`, where `None` is the missing header. Against the fix it passes, and the local suite goes to 8/8.

With the fix, the same live stack and the same unedited collection ran clean in every state the cutover cares about:

```
Captured: newman, post-fix, flag OFF / flag ON / flip-back
(tooling/newman/GOLDEN-BASELINE.md)

Run A  (flag false, monolith)         58/58 assertions, 0 failed
Run B  (flag true,  review-service)   58/58 assertions, 0 failed
Run C  (flag false, flip-back)        58/58 assertions, 0 failed

Negative -- flag true, review-service killed:
  6/6 assertions FAILED, newman exit code 1, every request a real 502
Recovered -- review-service restarted:
  16/16 assertions, 0 failed
```

Runs A and B have the same shape: 19 requests, 38 test-scripts, 58 assertions, 0 failed, with only the proxy flag changed. The negative check matters as much. With the flag on and the review-service killed, every request came back a real `502`, never a swallowed `200`. A gate that can't fail asserts nothing, and this one was shown to fail by taking its backend offline.

## The second human gate: what "equivalent" covers

{% include excalidraw.html file="shared-table-routing-defect" alt="Two panels. Left: the proxy routes /api/reviews to either the Django monolith or the FastAPI review-service, and because both read and write the same Postgres rows, a check on response shape alone can't tell a correct response from one that fell through. Right: a real POST over a real socket against the real WSGI backend is the surface where the chunked-body bug was hiding." caption="Figure 7.1: Why a response-shape check needed a real socket to be trusted" %}

Fixing the bug didn't close Verify. At the second gate a person looks at "58/58 green" and decides whether that is enough evidence to trust the cutover. A green run doesn't certify itself, and Review's shared schema is why. While both backends read and write the same `reviews` rows, a suite that checks only status code and body can't tell "served by review-service" from "fell through to the monolith and returned the same data." For most read traffic the two are observably identical. A live POST over a real socket against the real WSGI backend is different: a backend that received an empty body fails differently from one that received the request. Sign-off meant a person taking responsibility for the judgment that real-socket runs against both backends, in both flag states, with a negative check, were the right coverage for a cutover this entangled.

## Operate: flip the flag

With sign-off recorded, `STRANGLER_REVIEW_ENABLED` controls real traffic. `false` routes `/api/reviews*` to the monolith and `true` routes it to the review-service. Flipping back is a config change and a restart, not a redeploy. That reversibility window stays open until the monolith's `review` module is decommissioned, and no irreversible step happened during this extraction. The irreversible step arrives with the final seam, the order extraction.

## Reconcile: the ledger closes the loop

Reconcile is the phase most lifecycles skip. `tooling/newman/GOLDEN-BASELINE.md` carries the dated record of both passes: the run that found the defect, left unfixed in that commit because the fix was a separate follow-up, and the repair pass that closed it. The decision log records the root cause, the fix and the regression test in one place, where a reader can check them against the code. Both records also name what stayed out of scope. Review's shared-schema scoping stayed in place, even though a schema of its own would have narrowed the blast radius of a routing mistake, because reopening a decision the approved plan had made would have been re-litigation. That is a named deferral, not a hidden problem.

## The three-layer safety net

{% include excalidraw.html file="adlc-safety-net-layers" alt="Three stacked layers. Automated: the Newman equivalence suite, re-run against every candidate over a real socket, which caught the chunked-body bug an in-process mock suite couldn't see. Adversarial verification: checking the result against what actually persisted in the shared table, not only the response shape. Human gates: plan approval before any diff exists, and equivalence sign-off on whether the suite's coverage fits the stakes." caption="Figure 7.2: The safety net's three layers, and what each one stops" %}

The ADLC is as safe as its net, and the net has three layers.

| Layer | What it does | What removing it lets through |
|---|---|---|
| Behavior-equivalence suite | Re-runs unchanged against every candidate over a real socket; cheap enough to run after every change | The chunked-body regression ships, and every checkout and review write arrives empty at the monolith |
| Checking the shared table, not only the response shape | Compensates for the equivalence suite's blind spot in an entangled schema | A subtler bug that doesn't announce itself with a loud `400` passes a shape-only check |
| Two human gates (plan approval, equivalence sign-off) | Decides whether the first two layers' coverage fits what's at stake | A green run is trusted as self-certifying |

"Verify" therefore means asking whether the equivalence suite's coverage could be fooled by the specific shape of this change, here a hand-rolled proxy forwarding a body it never read, and when the answer is maybe, running the real-socket, real-WSGI check that settles it. That judgment sits with a person or a reasoning-model validator, not inside the equivalence suite.

> **Decision**
>
> Trust a cutover only when the unedited equivalence suite is green over a real socket against both backends in both flag states, a negative check goes red when a backend is killed, and a person has judged that this coverage can't be fooled by this change.

> **🤖 Explore with your agent**
>
> "In `examples/01-strangler-proxy`, read `proxy_handler` in `app/main.py` and `tests/test_routing.py`. List which request-framing properties the tests assert and which they don't, pick one they don't, and write a test that would fail over a real socket against a WSGI backend but pass through `httpx.ASGITransport`. Say what the equivalence suite in `tooling/newman` would and wouldn't catch for it."
>
> Check: `cd examples/01-strangler-proxy && uv run pytest` passes, and the reply names a gap the in-process transport can't observe.

## Build, run, observe

The proxy's local checks run without a stack:

```sh
cd examples/01-strangler-proxy
uv run pytest
uv run ruff check .
```

The live runs above belong to the flag-gated proxy at the `stage/01-review` tag (`git checkout stage/01-review`); the proxy on `main` is flagless and no longer routes to the monolith. They need Postgres, the monolith on `:8000` under gunicorn, the review-service on `:8001` and the proxy on `:8888`. Point the collection at the proxy:

```sh
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/proxy.postman_environment.json
```

`tooling/newman/GOLDEN-BASELINE.md` lists the expected counts for each run above. Experiments:

- Restore `content=request.stream()` in `proxy_handler()`. The framing regression test fails on the missing `Content-Length`; at `stage/01-review`, a live `POST` through the proxy to the monolith also comes back `400 VALIDATION_FAILED`.
- At `stage/01-review`, kill the review-service with `STRANGLER_REVIEW_ENABLED=true`. Every review request comes back a real `502` and newman exits 1; it recovers when the service restarts.

## For deeper coverage

`tooling/newman/GOLDEN-BASELINE.md` has the full run record, `examples/01-strangler-proxy/CUTOVER.md` has the reversibility evidence for each seam, and `examples/02-review-service/MIGRATION.md` has the Phase A and Phase B comparison.
