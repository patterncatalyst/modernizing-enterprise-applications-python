# CUTOVER.md — Review strangler-fig cutover evidence trail (r02)

**Status: TEMPLATE.** This file records the evidence trail for the single
most load-bearing claim in the r02 walking skeleton: that
`STRANGLER_REVIEW_ENABLED` behind this proxy is a **safe, reversible cutover
switch**. It mirrors the shape of the Java proxy's `CUTOVER.md`
(`modernizing-enterprise-applications/examples/01-strangler-proxy/CUTOVER.md`)
and the full-path-prefix lesson documented in this directory's `README.md`.

This file is a **template with placeholders** — the PROXY lane (this build)
has verified the routing logic itself in-process
(`tests/test_routing.py`, 7/7 green, both flag states + pass-through
fidelity + a real 502 on upstream-down). It has NOT run the live
behavior-equivalence suite against the real monolith + review-service
processes — that is the NEWMAN lane's job, using the Postman/Newman
collection against the actual running stack. Fill in every `TODO` below with
real run output before treating this as a completed evidence trail; do not
edit the narrative structure, only the placeholders.

See also: `README.md` in this directory (the proxy and its routing rule),
and `examples/00-monolith/SMELLS.md` for the smell this cutover cures.

## The flag

`STRANGLER_REVIEW_ENABLED`, read by `app/config.py` from the environment.
Routing matches the **full** request path against `/api/reviews` (see
README's "The full-path-prefix lesson").

| Flag | Backend for `/api/reviews*` | Backend for everything else |
|---|---|---|
| `false` (default) | monolith `:8000` | monolith `:8000` |
| `true` | review-service `:8001` | monolith `:8000` |

## Evidence trail (to be filled in by the NEWMAN lane)

### 1. Baseline — flag OFF (reversibility window)

With `STRANGLER_REVIEW_ENABLED=false` (or unset) and the monolith's Review
app still mounted, run the full behavior-equivalence suite, unmodified,
through the proxy:

```bash
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json \
    --env-var "baseUrl=http://localhost:8888"
```

**Result: TODO — `<passed>/<total>` assertions green, 0 failed.** Review
served by the monolith, reached through the proxy; the proxy should
introduce zero observable difference.

### 2. Cutover — flag ON

With `STRANGLER_REVIEW_ENABLED=true` and `examples/02-review-service`
running on `:8001`, re-run the same suite, unmodified:

```bash
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json \
    --env-var "baseUrl=http://localhost:8888"
```

**Result: TODO — `<passed>/<total>` assertions green, 0 failed.** Review
now served by `examples/02-review-service`; everything else still the
monolith.

**Stronger proof than a status-code-only suite pass** (closing the exact
false-equivalence gap the Java proxy's CUTOVER.md §2 documents — a shared
backing store can make the wrong backend look right): with the monolith
stopped, confirm Review still answers through the proxy and nothing else
does:

```
GET http://localhost:8888/api/reviews?sku=<TODO-sku>  -> TODO (expect 200, served by review-service; monolith is down)
GET http://localhost:8888/api/orders                   -> TODO (expect 5xx; still targets the dead monolith, as expected)
```

### 3. Reversibility — flip back to OFF

Restart the proxy with `STRANGLER_REVIEW_ENABLED=false` (monolith back up,
Review app still present), re-run the full suite once more, unmodified:

```bash
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json \
    --env-var "baseUrl=http://localhost:8888"
```

**Result: TODO — `<passed>/<total>` assertions green, 0 failed.** This
demonstrates the reversibility window is still genuinely open: flipping the
flag back is a config change and a restart, nothing more — right up until
the monolith's Review app is deliberately decommissioned (out of scope for
this proxy build; see the monolith/review-service lanes' own plans for that
step).

### 4. Negative check — review-service down, the Review folder MUST go RED

With `STRANGLER_REVIEW_ENABLED=true` and the review-service process killed,
re-run only the Review folder of the suite:

```bash
newman run tooling/newman/mea.postman_collection.json \
    --environment tooling/newman/local.postman_environment.json \
    --env-var "baseUrl=http://localhost:8888" \
    --folder "TODO-review-folder-name"
```

**Result: TODO — expect RED, newman exit code 1.** Expected failure mode:
`GET /api/reviews*` returns the proxy's own `502` (connection refused,
forwarded as a plain-text body by `app/main.py`'s upstream-failure handler)
instead of `200` with a JSON body — the assertions on status code and
`Content-Type: application/json` should both fail. Record the exact failing
assertions here:

```
TODO — paste newman's failure output
```

This is the discipline the Java proxy's CUTOVER.md names explicitly: the
suite must not quietly pass when the extracted service is down. A
soft/degraded pass here would mean the equivalence gate is testing the
wrong thing.

Restart review-service and re-run the same folder to confirm it goes GREEN
again:

```
TODO — paste newman's recovery output (expect GREEN, exit code 0)
```

## Summary of the suite runs

| # | Flag | Review served by | Everything else served by | Result |
|---|---|---|---|---|
| 1 | `false` | monolith | monolith | TODO |
| 2 | `true` | review-service | monolith | TODO |
| 3 | `false` (reverted) | monolith | monolith | TODO |
| 4a | `true`, review-service **down** | *(nothing — 502)* | monolith | TODO — expect RED |
| 4b | `true`, review-service restarted | review-service | monolith | TODO — expect GREEN |

The Postman/Newman collection itself must stay unedited across every run in
this table — only `--baseUrl`, `STRANGLER_REVIEW_ENABLED`, and whether
review-service/the monolith are up should change between rows.
