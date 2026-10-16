# CUTOVER.md — Review strangler-fig cutover evidence trail (r02)

This file records the evidence for the single most load-bearing claim in r02:
that `STRANGLER_REVIEW_ENABLED` behind this proxy is a **safe, reversible
cutover switch**. The full run logs live in
`tooling/newman/GOLDEN-BASELINE.md`; this file is the narrative summary.

All runs below used the unedited Postman/Newman collection
(`tooling/newman/mea.postman_collection.json`) through the proxy on `:8888`
(`tooling/newman/proxy.postman_environment.json`, `baseUrl=http://localhost:8888`),
against a live stack: Postgres 18.6-alpine, the monolith on `:8000` (gunicorn/WSGI),
and `examples/02-review-service` on `:8001`. Only `STRANGLER_REVIEW_ENABLED` and
whether a backend is up changed between runs.

## The flag

`STRANGLER_REVIEW_ENABLED`, read by `app/config.py` from the environment.
Routing matches the **full** request path against `/api/reviews` (see README's
"The full-path-prefix lesson").

| Flag | Backend for `/api/reviews*` | Backend for everything else |
|---|---|---|
| `false` (default) | monolith `:8000` | monolith `:8000` |
| `true` | review-service `:8001` | monolith `:8000` |

## A bug this cutover caught (and why it matters)

The in-process routing tests (`tests/test_routing.py`, via `httpx.ASGITransport`)
passed while a real defect hid underneath: the proxy forwarded the request body
as an unread async stream, so httpx sent it upstream with
`Transfer-Encoding: chunked` and no `Content-Length`. The monolith is Django/WSGI,
which reads `CONTENT_LENGTH` and treats a missing one as an empty body — so every
`POST` routed to the monolith **through the proxy** arrived empty. It surfaced only
when the Newman suite ran against the real WSGI server over a real socket. Fixed by
buffering the body (`content = await request.body()`) so bounded requests carry a
correct `Content-Length`; a regression test now asserts the outbound upstream
request is non-chunked with the body intact. This is the strangler-fig lesson in
miniature: equivalence must be proven against the real thing, not a mock.

## Evidence trail (all green, post-fix)

### 1. Baseline — flag OFF (reversibility window)
Full suite through the proxy, reviews served by the monolith:
**19 requests / 38 test-scripts / 58 assertions, 0 failed (exit 0).**

### 2. Cutover — flag ON
Same unedited suite, `STRANGLER_REVIEW_ENABLED=true`, reviews now served by
`examples/02-review-service`, everything else still the monolith:
**19 / 38 / 58, 0 failed (exit 0)** — byte-identical in shape to run 1.

### 3. Reversibility — flip back to OFF
Restart the proxy with the flag off; monolith serves reviews again:
**19 / 38 / 58, 0 failed (exit 0).** The reversibility window is genuinely open —
flipping back is a config change plus a restart, right up until the monolith's
Review app is deliberately decommissioned (a later iteration).

### 4. Negative check — review-service down, the Review folder MUST go RED
Flag ON, `examples/02-review-service` killed, run only the `Review Context
Contract` folder: every `/api/reviews*` request gets the proxy's real `502`
(upstream unavailable), not a soft pass. **5 requests, 6/6 assertions failed,
newman exit code 1** (status-code and JSON-body assertions both fail). Restart
the review-service and re-run the same folder: **16 assertions, 0 failed (exit 0).**
The equivalence gate does not quietly pass when the extracted service is down.

## Summary of the suite runs

| # | Flag | Review served by | Everything else | Result |
|---|---|---|---|---|
| 1 | `false` | monolith | monolith | 58/58 green |
| 2 | `true` | review-service | monolith | 58/58 green |
| 3 | `false` (reverted) | monolith | monolith | 58/58 green |
| 4a | `true`, review-service **down** | *(nothing — 502)* | monolith | RED, exit 1 (as required) |
| 4b | `true`, review-service restarted | review-service | monolith | 16/16 green |

See `tooling/newman/GOLDEN-BASELINE.md` for the verbatim newman tables, and
`examples/00-monolith/SMELLS.md` (#7) for the smell this cutover begins to cure.
