---
title: "Failure Modes & the Resilience Chassis"
order: 25
part: "Coordinating Across Services"
description: "Partial-failure taxonomy; timeouts, retry + jitter, circuit breaker, bulkhead, load shedding; the FastAPI resilience chassis."
duration: 35 minutes
---

Every chapter since ch.14 has quietly been building a resilience mechanism
without calling it that: a bounded gRPC timeout here, an at-least-once outbox
there, a proxy that fails loud instead of swallowing an error. This chapter
is where those mechanisms get named as a single taxonomy, inventoried
against what this system already does and does not do, and extended with one
concrete new piece — a retry policy around the one outbound HTTP call ch.24's
saga makes. It is also where this chapter draws its scope most narrowly: two
well-known resilience patterns, a circuit breaker and a bulkhead, are named
and **not** built, because nothing in this system yet produces the failure
condition either one exists to solve.

The code already covered in ch.19, ch.20, ch.23, and ch.24 is the evidence
base for this chapter — there is no new `examples/` directory. The one new
file this chapter walks in full is `examples/06-shipping-service/app/enrich_client.py`.

## A failure-mode taxonomy for a distributed saga

A monolith inside one process has, broadly, two failure modes: the request
raises, or it doesn't. Once a business operation spans a Kafka topic, a gRPC
call, an HTTP call to a sibling service, and a saga that can be interrupted
mid-sequence, the taxonomy gets considerably longer, and naming each kind
precisely matters because the right mitigation for one kind is often useless
— or actively wrong — against another:

- **Total unavailability.** The callee is simply not there: connection
  refused, DNS failure, a process that crashed. The correct response is to
  fail fast and either retry (if the call is idempotent and the outage might
  be transient) or surface a clear error — never wait indefinitely.
- **Slow but alive.** The callee answers, eventually, but far past any
  useful budget — a GC pause, a saturated connection pool, a downstream
  dependency of the callee that is itself struggling. This is the failure
  mode a **timeout** exists for specifically; without one, a slow callee
  silently becomes an unbounded wait, which is worse than an outright
  crash because nothing observes it as a failure until something times out
  somewhere else, later, for an unrelated reason.
- **Transient blips.** A single dropped packet, a momentary connection reset,
  one request that happened to lose a race. The callee is fine; this one
  call wasn't. **Retry** is the correct tool here, and only here — retrying
  a call that is failing for a structural reason (bad request, broken
  contract) just repeats the same failure three times instead of once.
- **Sustained degradation.** The callee is up but consistently failing or
  consistently slow for an extended window — not one blip, a pattern. A
  **circuit breaker** exists for this case specifically: stop calling a
  dependency that has demonstrated it will not succeed, so the caller
  fails fast instead of burning threads/connections on calls that are
  statistically certain to fail anyway.
- **Resource exhaustion from one dependency starving another.** One slow or
  saturated downstream call consumes a shared pool of threads/connections
  that an unrelated call path also needed. A **bulkhead** — a hard cap per
  dependency, independent of every other dependency's cap — exists to keep
  that starvation contained to the one path that caused it.
- **Process-level interruption.** The caller itself — not the callee — dies
  mid-operation: a crash, a `kill -9`, a redeploy. Timeouts, retries,
  breakers, and bulkheads are all about *calls*; this failure mode is about
  *state*, and the mitigation is durability — persisting enough to resume,
  which is exactly what ch.24's saga does.
- **A broken verifier.** Not a failure in the system under test at
  all, but a failure in the thing *checking* it — an assertion that reports
  green when the real answer is unknown, or red for a reason that has
  nothing to do with the code it's supposed to be testing. This chapter's
  closing section is about exactly this kind of failure, because this
  book's own equivalence suite hit one.

{% include excalidraw.html file="shipping-resilience-chassis" alt="The resilience chassis: four mechanisms this system already depends on, one new mechanism this chapter adds, and two patterns named as deferred, with the reason" caption="Figure 25.1 — What already runs, what's new, and what's not built yet" %}

## What already runs: four mechanisms, built before this chapter had a name for them

Before writing a single new line, it's worth a measured inventory of what
this book's system already does about several of those failure modes,
because the answer is "more than a reader might expect" — each mechanism
was built in service of a specific extraction's correctness, not as part of
a resilience initiative, which is exactly how production resilience usually
accumulates.

**A gRPC deadline, since ch.19.** `order.inventory_client.py`'s
`RemoteInventoryClient` has carried a bounded timeout from the moment
checkout started calling inventory-service over gRPC:

```python
# order/inventory_client.py
DEFAULT_TIMEOUT_SECONDS = 5.0

def __init__(self, target=None, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    self._timeout = timeout
    ...

def _call(self, rpc, request):
    try:
        return rpc(request, timeout=self._timeout)
    except grpc.RpcError as exc:
        # translated to InventoryServiceUnavailable (503) --
        # never confused with a logical "insufficient stock" outcome
        ...
```

Five seconds is the "slow but alive" failure mode's mitigation: a hung or
overloaded inventory-service can delay checkout by at most five seconds, not
indefinitely, and `grpc.RpcError` on any outcome — timeout, `UNAVAILABLE`,
anything else gRPC's channel reports — is translated to a distinct
`InventoryServiceUnavailable`, never silently conflated with a legitimate
"insufficient stock" business outcome. That distinction matters precisely
because the caller's next action differs: insufficient stock is a terminal
`422` the customer needs to see; a timed-out RPC is a `503` the customer
should be told to retry, and internally it's also the trigger for this
book's compensating `Release` path whenever the timeout happens after an
earlier line in the same checkout already reserved stock.

**At-least-once delivery plus two-layer idempotency, since ch.17/ch.20/ch.23.**
Every outbox relay in this project — the monolith's, payment-service's,
shipping-service's — publishes, then stamps a row as published, as two
separate operations. A crash between those two steps republishes the
identical payload on the next poll rather than losing it, which is the
correct trade for this kind of failure (lose a message, or risk a duplicate)
when the alternative is building distributed exactly-once delivery, a
problem Kafka itself does not solve for you. The necessary counterpart on
every receiving side is an idempotent consumer, and this book has used three
different idioms for that across its chapters depending on what the write
actually is: check-then-insert-plus-unique-index for a new row (ch.17's
notification dedupe, ch.24's saga-by-order-id dedupe), a status-transition
guard for an existing row's lifecycle (ch.22/ch.23's `_is_pending`, ch.24's
`_is_awaiting_shipment`), and `INSERT ... ON CONFLICT DO NOTHING` against a
stable key for a compensating action that must never double-apply (ch.23's
`Release` ledger). ch.23's Figure 23.3 already walked the two-layer version
of this in detail for inventory's compensating `Release`; it is the same
discipline, applied consistently, every time this book introduces a new
at-least-once hop.

**The strangler proxy's 502 fail-safe, since ch.14.** The proxy's
`proxy_handler` treats an unreachable or broken upstream as a real failure,
never a swallowed success:

```python
# examples/01-strangler-proxy/app/main.py
except httpx.HTTPError as exc:
    # Bridge semantics: an unreachable/broken upstream is a real 502,
    # never a swallowed 200.
    return Response(status_code=502, ...)
```

This is a small piece of code with an outsized role in this book's testing
discipline: it is what makes every negative check in this book's equivalence
suite — "kill this service and confirm the caller sees a real failure" —
actually mean something. A proxy that caught `httpx.HTTPError` and returned
a cached or default `200` would make every "service X down" scenario in
this project's Newman collection pass vacuously, which is the single worst
outcome a resilience mechanism can produce: looking resilient while hiding
the failure from the one system positioned to notice it.

**Saga timeout and crash-resume, as of ch.24.** The last of the four is the
one this book just finished building: `resume_running_sagas()`'s
startup scan, which turns a crashed-mid-saga process from a silent loss into
a resumable condition. It belongs on this list for the same reason the other
three do — it was built to solve a correctness problem specific to ch.24's
extraction, and it happens to also be exactly what "process-level
interruption" in this chapter's taxonomy calls for.

## The one new mechanism: tenacity retry-with-timeout on `enrich`

Every mechanism above predates this chapter. The one new piece
Chapter 24 introduces is also the smallest, and it exists because ch.24's saga made
a kind of call this project had not made before: `enrich_client.py` is the
first outbound HTTP call any service in this book makes to another service —
every other cross-service call so far has been gRPC (ch.19) or Kafka (every
choreographed/orchestrated saga). A plain HTTP call needed its own resilience
treatment, not an inherited one.

```python
# app/enrich_client.py -- the retry policy
_RETRYABLE_EXCEPTIONS = (httpx.TransportError, httpx.TimeoutException)
_MAX_ATTEMPTS = 3

@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    reraise=True,
)
async def _get_order(client, base_url, order_id, timeout_s):
    response = await client.get(f"{base_url}/api/orders/{order_id}", timeout=timeout_s)
    response.raise_for_status()
    return response.json()
```

Four choices in this decorator are worth reading individually, because each
one is a direct answer to this chapter's taxonomy, not an arbitrary
`tenacity` default.

**Why `retry_if_exception_type` scoped to exactly two exception classes?**
Because retrying is only correct for the taxonomy's "transient blip"
category. `httpx.TransportError` (connection refused, DNS failure, a reset
connection) and `httpx.TimeoutException` (this call's own per-attempt
timeout fired) are both transient-shaped: the callee might simply be
reachable on the next attempt. A non-2xx HTTP response is
**not** in this set — `_get_order` calls `response.raise_for_status()`,
which raises `httpx.HTTPStatusError`, a type `tenacity`'s `retry_if_exception_type`
does not match, so it propagates on the first attempt, unretried. A 404 or a
500 from the monolith means something is wrong with the *contract or the
data*, not a blip the network will fix on attempt two; retrying it three
times would just add latency to an inevitable failure. This is the single
most important discipline a retry policy has to get right, and getting it
wrong is one of the most common ways retries make a system worse instead of
better — retrying a non-idempotent write on a false-transient classification
can duplicate the write, and retrying a permanent failure just
delays the correct error by the full retry budget.

**Why `stop_after_attempt(3)` and not more?** Because this call sits inside a
saga step that the orchestrator itself will retry at a higher level if it
fails — `enrich`'s failure routes the whole saga to `COMPENSATING`, and a
redelivered `payment.captured` (or a manual retry) would call `enrich` again
from scratch. Three attempts here is enough to absorb a single transient
network blip without turning one saga step into an unbounded wait; it
does not try to be the *only* line of defense, because the saga
engine above it already provides a coarser one.

**Why `wait_exponential` instead of a fixed delay?** A fixed, short retry
delay against a callee that is struggling under load adds a synchronized
burst of retries right back at it — every failing caller retrying at the
same cadence is close to a self-inflicted thundering herd. Exponential
backoff (`0.2s`, then roughly `0.4s`, capped at `2s`) spaces the attempts out
and caps the worst case, so a transient blip gets a fast second chance
without three callers' retries colliding into a sustained spike against an
already-struggling dependency.

**Why `reraise=True`?** Without it, `tenacity` wraps the final failure in its
own `RetryError`, which would hide the real `httpx` exception from the code
that has to decide what happened. `reraise=True` means the caller sees the
*original* exception type after the final attempt, which `fetch_shipping_address`
then translates into this service's own `EnrichmentError` — a single,
service-specific failure type that `app/orchestrator.py::_advance_one_step`
catches identically to any other step failure, never needing to know
whether the underlying cause was a timeout, a connection refused, or a bad
response.

```python
# app/enrich_client.py -- fetch_shipping_address, the translation boundary
async def fetch_shipping_address(*, base_url, order_id, timeout_s):
    async with httpx.AsyncClient() as client:
        try:
            body = await _get_order(client, base_url, order_id, timeout_s)
        except httpx.HTTPStatusError as exc:
            raise EnrichmentError(f"order {order_id} enrichment failed: "
                                   f"{exc.response.status_code} response") from exc
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise EnrichmentError(f"order {order_id} enrichment failed after "
                                   f"{_MAX_ATTEMPTS} attempts: {exc}") from exc
    address = body.get("shippingAddress")
    if not address:
        raise EnrichmentError(f"order {order_id}'s read surface did not provide a shippingAddress")
    return address
```

That last check — a 2xx response with a missing or empty `shippingAddress`
field — is its own, third failure category, distinct from both the retried
and non-retried exception paths above: the response *succeeded* by HTTP's
own accounting, but the data this step actually needed is not in it. Treating
this as an immediate `EnrichmentError` rather than silently proceeding with
`None` is the same accurate-error discipline this book has applied since
ch.14 — a step that got an incomplete answer should fail loudly, not guess.

## Deferred, and why: pybreaker and `asyncio.Semaphore`

A circuit breaker (this project's open-source option would be `pybreaker`)
and a bulkhead (in an `asyncio`-based service, a `Semaphore` bounding
concurrent calls to a specific dependency) are both well-known, legitimate
resilience patterns, and a reasonable reader might expect a chapter titled
"Failure Modes & the Resilience Chassis" to build both. This chapter
does not, and the reason matters as much as the mechanisms themselves:
**neither pattern has a problem in this system to solve yet.**

A circuit breaker is worth its added complexity when a dependency fails *sustained*
and *repeatedly* — enough that fast-failing without even attempting the call
becomes better than attempting it, because attempts are statistically
certain to fail and are themselves consuming resources (connections,
threads, retry budget) that could serve a healthier request instead. This
system has exactly one outbound HTTP call (`enrich`), made once per saga
step, with a bounded retry and a bounded per-attempt timeout already in
place. Nothing in this project's evidence base — not the newman runs, not
the live cutover — has produced a sustained-failure condition against the
monolith's `/api/orders/{id}` endpoint; every demonstrated failure in this
chapter's evidence is either a single transient blip (handled by the retry
already in place) or the monolith being entirely down (which the proxy's
502 bridge and this project's negative checks already treat as a hard
failure, correctly). Adding a breaker now would be defending against a
failure mode this system has never actually exhibited, at the cost of a new
dependency, a new state machine, and a new set of tuning parameters (failure
threshold, half-open probe interval) with no real traffic pattern to tune
them against.

A bulkhead is worth its added complexity when one dependency's slowness can starve
resources another, unrelated call path needs — a shared thread pool, a
shared connection pool, a shared semaphore with too generous a limit. This
service's `enrich` call opens a short-lived `httpx.AsyncClient` per saga
step (not a shared pool across requests, as `enrich_client.py`'s own
docstring notes — "this is one call per saga step, not a hot path needing a
shared connection pool"), and each saga step already runs inside its own
database transaction serialized by the row lock ch.24 covered. There is no
shared, boundedly-sized resource today that a slow `enrich` call could
exhaust out from under some other, unrelated request — the thing a bulkhead
exists to protect does not yet exist in this service's architecture.

Naming both as deferred, with the specific reason, is itself part of this
book's resilience discipline, not a hedge against criticism. A pattern
adopted because a chapter title implies it should exist — rather than
because a real failure mode demands it — adds exactly the kind of
speculative infrastructure this book's own conventions have argued against
since ch.03: complexity with no corresponding problem is a cost with no
offsetting benefit, and the accurate thing to write is the condition under
which it *would* become justified (sustained dependency failure for a
breaker; a second, shared, contendable resource for a bulkhead), rather than
an implementation nobody has a reason to exercise.

## When the verifier breaks: a check that can pass vacuously is not a check

The most instructive failure this chapter has to report did not happen in
any of the code above. It happened in the test harness verifying it, and
leaving that finding visible rather than quietly patching around it is
itself the resilience lesson this closing section is about: **a check that
can pass vacuously is not a check.**

`tooling/newman/mea.postman_collection.json`'s bounded-wait poll scripts —
the same `setNextRequest`-retry idiom ch.17 introduced and ch.22/ch.23 reused
for their own eventual-consistency assertions — retried only while an
order's status was the literal string `'PENDING'`:

```javascript
// before -- 1c / 3c / 4c / N1b, identical shape
if (json.status === 'PENDING' && attempt < maxAttempts - 1) {
    pm.collectionVariables.set('happyPathPollAttempt', String(attempt + 1));
    postman.setNextRequest(pm.info.requestName);
    return;
}
```

ch.24's `AWAITING_SHIPMENT` is a real, if short-lived, intermediate status
these scripts had no knowledge of — introduced after the scripts were
written, by a different chapter's extraction. A poll landing in that
(sub-second) window observed a status that was neither `'PENDING'` (so the
retry loop gave up) nor the expected terminal value (so the assertion
failed) — a reproducible **false RED** on a saga that was, in fact, healthy
and about to resolve correctly a fraction of a second later. This was first
caught on `4c` during the cutover run, `AWAITING_SHIPMENT` observed
against an expected `SHIPPING_FAILED` on attempt 3/20, with the order
confirmed by direct query to have reached `SHIPPING_FAILED` just
**273ms** after the poll had already given up — and independently reproduced
by `demos/demo-shipping-cutover.sh` on the happy-path poll (`1c`) as well.

The fix generalizes the retry condition from one allowed value to a named
set, so the next intermediate status this project's saga shapes introduce is
tolerated by construction rather than requiring another one-off patch:

```javascript
// after
var NON_TERMINAL_STATUSES = ['PENDING', 'AWAITING_SHIPMENT'];
if (NON_TERMINAL_STATUSES.indexOf(json.status) !== -1 && attempt < maxAttempts - 1) {
    pm.collectionVariables.set('happyPathPollAttempt', String(attempt + 1));
    postman.setNextRequest(pm.info.requestName);
    return;
}
```

Two details about how this fix was applied matter more than the diff itself.
First, **the strict terminal assertion did not change** at any of the four
sites — only the loop-continuation condition widened. A version of this fix
that instead relaxed the final assertion (accepting any non-`PENDING` value
as a pass) would have reintroduced exactly the vacuous-check failure mode
ch.23 already rejected once for the same reason: it would also pass against
a saga stuck in `AWAITING_SHIPMENT` forever, which is precisely
the condition the suite's own negative check needs to be able to catch.
Second, the fix was applied to **all four** sites sharing this retry shape —
`1c`, `3c`, `4c`, and `N1b`, the Notification Context Contract's own
order-confirmation poll — found by grepping the exact `=== 'PENDING'`
pattern across the whole collection file rather than trusting that the bug
report's named list (`1c`/`3c`/`4c`) was exhaustive. `N1b` shares the
identical self-loop shape and would have carried the identical false-RED
exposure the moment the Notification contract is ever run against the
orchestrated topology — this is the same "search for the pattern, not the
instance" discipline this book's own conventions require of every fix, applied
here to a test script instead of application code.

The fix is proven not by a single subsequent green run, but by **stability**:
the fully-orchestrated suite run through the proxy **6 consecutive times**,
0 failed every run, newman exit 0 every time, with the saga's own log
confirming 18 real `AWAITING_SHIPMENT` transitions absorbed across that
window — not a vacuous pass, because the intermediate status was actually
observed in-flight on every single run, and every one of those 18
observations correctly triggered a retry instead of a false failure. A
single green run after a fix proves the fix didn't break anything it touched
directly; six consecutive green runs against a timing-dependent race proves
the fix actually closes the race window, not just the one instance that
happened to be caught.

> **ADLC in Action** — The poll-script gap was discovered live, during the
> cutover run, not anticipated at the planning gate — the plan correctly
> scoped `AWAITING_SHIPMENT` as a new order status but did not anticipate
> that an existing test script elsewhere in the project had hardcoded an
> assumption about which statuses count as "still in flight." The repair
> was scoped as its own lane (`tooling/newman/` only, no application code
> touched) specifically so a test-infrastructure fix stays visibly separate
> from a saga-logic fix in this project's own history — a reader auditing
> what changed to make the cutover pass should be able to tell, from the ledger
> alone, that the system under test never had the bug; the harness did.

## What you learned

- A distributed saga's failure taxonomy is wider than "it raised or it
  didn't" — total unavailability, slow-but-alive, transient blips, sustained
  degradation, resource starvation, and process-level interruption each call
  for a different mitigation, and applying the wrong one (retrying a
  permanent failure, timing out a call that needed a breaker instead) can
  make the system worse, not better.
- Four resilience mechanisms were already doing real work in this system before
  this chapter existed to name them: a bounded gRPC deadline (ch.19), an
  at-least-once outbox with a per-write idempotency idiom chosen to fit the
  write (ch.17/ch.20/ch.23), a proxy that fails loud instead of swallowing
  an error (ch.14), and a crash-resumable saga (ch.24) — each built to solve
  a correctness problem for its own chapter, which is how resilience
  usually accumulates in a real system.
- `tenacity`'s retry policy on `enrich_client.py` retries only the two
  exception types that are actually transient (`TransportError`,
  `TimeoutException`), reraises the original exception rather than hiding it
  behind `tenacity`'s own wrapper, and explicitly does not retry a non-2xx
  response or a contract violation — retrying the wrong failure category is
  one of the most common ways a retry policy makes a system worse.
- A circuit breaker and a bulkhead were not built — not because
  they are bad patterns, but because nothing in this system's evidence base
  has produced the sustained-failure or shared-resource-contention condition
  either one exists to solve; naming the deferral and its reason is part of
  this book's resilience discipline, not a gap.
- A check that can pass vacuously is not a check: the `AWAITING_SHIPMENT`
  poll-script bug was a false RED, not a false green, but the fix for it —
  widening a retry condition without touching the strict terminal assertion,
  applied to all four sites sharing the pattern, and proven by 6 consecutive
  stable runs rather than one — is the same verification discipline this book
  applies to the system under test, applied to the thing testing it.

Part 7 — Coordinating Across Services — closes here, with payment and
shipping extracted under opposite saga shapes and both chased to a failure
taxonomy with real, cited mitigations. ch.26 moves to Part 8 and the sixth
and final extraction: the order context itself, and the communication
patterns that tie every extracted service back together as one coherent
system.

---

*Verification status: <span class="status status--verified">verified</span>.
Every mechanism this chapter inventories is cited against a live run
already recorded in a prior chapter or `tooling/newman/GOLDEN-BASELINE.md`:
the gRPC deadline/503 translation, the two-layer outbox idempotency, the
proxy's 502 bridge, and the saga crash-resume proof. The new `tenacity`
retry in `enrich_client.py` is unit- and integration-tested, but its
retry-on-transient-failure branch was not independently fault-injected
against a live, killed-and-restarted monolith — that run remains the
highest-value thing a future iteration should confirm.*
