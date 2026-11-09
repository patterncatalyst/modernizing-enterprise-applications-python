---
title: "Failure Modes & the Resilience Chassis"
order: 25
part: "Coordinating Across Services"
description: "Partial-failure taxonomy; timeouts, retry with backoff, circuit breaker, bulkhead; the FastAPI resilience chassis and what is not built."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Name the partial-failure taxonomy for a distributed saga (total unavailability, slow but alive, transient blips, sustained degradation, resource exhaustion, process-level interruption, a broken verifier) and match each kind to its mitigation.
- Explain what `RemoteInventoryClient`'s five-second gRPC timeout buys and why a timed-out RPC maps to a `503`, never to the `422` an insufficient-stock outcome gets.
- State the rule "a retry is only as safe as the idempotency behind it" and the three idempotent-consumer idioms that pair with the outbox relay's at-least-once publish.
- Explain what a circuit breaker (`pybreaker`) and a bulkhead (an `asyncio.Semaphore`) add beyond a deadline, and why they are deferred until a failure condition justifies them.
- Explain the strangler proxy's `502` fail-safe, never a swallowed `200` on `httpx.HTTPError`, as what gives every negative check meaning.
- Read the four choices in `tenacity`'s retry policy on `enrich_client.py` as answers to the taxonomy.
- Explain why a check that can pass vacuously is not a check, using the poll-script false RED.

## Why this matters

A monolith in one process has two failure modes: the request raises, or it doesn't. Once an operation spans a Kafka topic, a gRPC call, an HTTP call to a sibling service and a saga that can be interrupted mid-sequence, the right mitigation for one kind of failure is useless or harmful against another. Retrying a permanent failure repeats it three times instead of once. Timing out a call that needed a breaker keeps hammering a dependency that will not recover.

The system already carries four resilience mechanisms that were built for correctness, not as a resilience initiative. One new piece joins them: a retry policy on the only outbound HTTP call the saga makes. A circuit breaker and a bulkhead are named and not built.

{% include excalidraw.html file="shipping-resilience-chassis" alt="The resilience chassis: four mechanisms already running, one new mechanism, and two patterns named as deferred, with the reason" caption="Figure 25.1: What already runs, what is new, and what is not built yet" %}

## A failure-mode taxonomy for a distributed saga

| Failure | What it looks like | Mitigation |
|---|---|---|
| Total unavailability | Connection refused, DNS failure, crashed process | Fail fast; retry only if the call is idempotent and the outage may be transient |
| Slow but alive | Answers far past any useful budget: a GC pause, a saturated pool, a struggling dependency | **Timeout**. Without one, a slow callee is an unbounded wait that nothing observes as a failure |
| Transient blip | One dropped packet, one reset connection | **Retry**, and only for this kind. A structural failure (bad request, broken contract) just repeats |
| Sustained degradation | Up but consistently failing or slow for a window | **Circuit breaker**: stop calling a dependency that has shown it will not succeed |
| Resource exhaustion | One slow downstream call consumes a shared pool another path needs | **Bulkhead**: a hard cap per dependency, independent of every other cap |
| Process-level interruption | The caller dies mid-operation: a crash, `kill -9`, a redeploy | Durability: persist enough to resume. This is a failure of state, not of calls |
| A broken verifier | The check reports green when the answer is unknown, or red for a reason unrelated to the code | A check that can fail for the right reason, shown by a negative run |

## What already runs

**A gRPC deadline.** `RemoteInventoryClient` has carried a bounded timeout since checkout started calling inventory-service:

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

A hung inventory-service delays checkout by five seconds at most. Any `grpc.RpcError` (timeout, `UNAVAILABLE`, anything else the channel reports) becomes `InventoryServiceUnavailable`, distinct from insufficient stock because the caller's next action differs: insufficient stock is a terminal `422` the customer needs to see, and a timeout is a `503` the customer should retry. It also triggers the compensating `Release` when an earlier line in the same checkout already reserved stock.

**At-least-once delivery with idempotent consumers.** Every outbox relay (the monolith's, payment-service's, shipping-service's) publishes, then stamps the row as published, as two operations. A crash between them republishes the identical payload on the next poll instead of losing it. That is the right trade when the alternative is distributed exactly-once delivery, which Kafka does not give you. The rule that follows: a retry is only as safe as the idempotency behind it. Each receiving side uses the idiom that fits its write:

| Write | Idiom | Where |
|---|---|---|
| A new row | Check-then-insert plus a unique index | Notification dedupe, saga-by-order-id dedupe |
| An existing row's lifecycle | A status-transition guard | `_is_pending`, `_is_awaiting_shipment` |
| A compensating action that must never double-apply | `INSERT ... ON CONFLICT DO NOTHING` against a stable key | The inventory `Release` ledger |

**The strangler proxy's 502.** The proxy treats an unreachable upstream as a failure, never a swallowed success:

```python
# examples/01-strangler-proxy/app/main.py
except httpx.HTTPError as exc:
    # Bridge semantics: an unreachable/broken upstream is a real 502,
    # never a swallowed 200.
    return Response(status_code=502, ...)
```

This small clause is what gives every negative check in the equivalence suite meaning. A proxy that returned a cached or default `200` would make every "service X down" scenario pass vacuously, which is the worst outcome a resilience mechanism can produce: looking resilient while hiding the failure from the one system positioned to notice it.

**Saga crash-resume.** `resume_running_sagas()` scans at startup and turns a process that crashed mid-saga from a silent loss into a resumable condition. It answers the process-level interruption row.

## Pattern: Retry with Backoff

`enrich_client.py` is the first outbound HTTP call any service here makes to another service; every other cross-service call is gRPC or Kafka. A plain HTTP call needs its own treatment:

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

Each of the four choices answers the taxonomy.

- **Retry exactly two exception types.** `httpx.TransportError` (refused, DNS failure, reset) and `httpx.TimeoutException` (this attempt's own timeout) are transient-shaped. A non-2xx response raises `httpx.HTTPStatusError`, which `retry_if_exception_type` does not match, so it propagates on the first attempt. A 404 or 500 from the monolith means the contract or the data is wrong, and retrying only delays the right error by the whole retry budget. Retrying a non-idempotent write on a false-transient classification can also duplicate the write.
- **Three attempts.** The call sits inside a saga step the orchestrator already handles: a failure routes the saga to `COMPENSATING`, and a redelivered `payment.captured` calls `enrich` again from scratch. Three attempts absorb one blip without making one step an unbounded wait, and the saga above provides the coarser line of defense.
- **Exponential backoff.** A fixed short delay against a struggling callee adds a synchronized burst of retries right back at it. Backoff (`0.2s`, then about `0.4s`, capped at `2s`) gives a fast second chance without colliding callers into a sustained spike.
- **`reraise=True`.** Without it `tenacity` wraps the last failure in its own `RetryError` and hides the real `httpx` exception. With it, `fetch_shipping_address` sees the original type and translates it into one service-specific `EnrichmentError`, which `app/orchestrator.py::_advance_one_step` handles like any other step failure.

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

A `2xx` with a missing `shippingAddress` is a third category: the response succeeded by HTTP's accounting, but the data the step needs is absent. It fails immediately with `EnrichmentError` rather than proceeding with `None`.

## Deferred: pybreaker and `asyncio.Semaphore`

A circuit breaker pays for itself when a dependency fails repeatedly enough that not attempting the call beats attempting it, because attempts are near-certain to fail and consume connections, threads and retry budget. This system has one outbound HTTP call (`enrich`), made once per saga step, with a bounded retry and per-attempt timeout. Neither the newman runs nor the live cutover produced a sustained failure against `/api/orders/{id}`. Every demonstrated failure was a single blip, handled by the retry, or the monolith being entirely down, which the proxy's 502 and the negative checks already treat as a hard failure. A breaker now would add a dependency, a state machine and tuning parameters (failure threshold, half-open probe interval) with no traffic to tune them against.

A bulkhead pays for itself when one dependency's slowness can starve a resource an unrelated path needs. `enrich` opens a short-lived `httpx.AsyncClient` per saga step, not a shared pool ("one call per saga step, not a hot path needing a shared connection pool", in `enrich_client.py`'s docstring), and each step runs in its own database transaction under a row lock. No shared, bounded resource exists for a slow `enrich` to exhaust.

| Pattern | Becomes justified when |
|---|---|
| Circuit breaker | A dependency shows sustained failure or slowness in real traffic |
| Bulkhead | A second path shares a contendable pool, thread set or semaphore with the slow call |

## When the verifier breaks

The most instructive failure here happened in the harness. The bounded-wait poll scripts in `tooling/newman/mea.postman_collection.json` retried only while an order's status was the literal `'PENDING'`:

```javascript
// before -- 1c / 3c / 4c / N1b, identical shape
if (json.status === 'PENDING' && attempt < maxAttempts - 1) {
    pm.collectionVariables.set('happyPathPollAttempt', String(attempt + 1));
    postman.setNextRequest(pm.info.requestName);
    return;
}
```

`AWAITING_SHIPMENT` is a real, short-lived intermediate status the scripts did not know. A poll landing in that sub-second window saw a status that was neither `'PENDING'` (so the loop gave up) nor the expected terminal value (so the assertion failed): a reproducible **false RED** on a healthy saga. It was first caught on `4c` during the cutover run, `AWAITING_SHIPMENT` observed against an expected `SHIPPING_FAILED` on attempt 3/20, with direct query showing the order reached `SHIPPING_FAILED` **273ms** after the poll gave up. `demos/demo-shipping-cutover.sh` reproduced it independently on the happy-path poll (`1c`).

The fix widens the retry condition from one value to a named set, so the next intermediate status is tolerated by construction:

```javascript
// after
var NON_TERMINAL_STATUSES = ['PENDING', 'AWAITING_SHIPMENT'];
if (NON_TERMINAL_STATUSES.indexOf(json.status) !== -1 && attempt < maxAttempts - 1) {
    pm.collectionVariables.set('happyPathPollAttempt', String(attempt + 1));
    postman.setNextRequest(pm.info.requestName);
    return;
}
```

Two details matter more than the diff. The strict terminal assertion did not change at any site; only the loop-continuation condition widened. Relaxing the final assertion to accept any non-`PENDING` value would pass against a saga stuck in `AWAITING_SHIPMENT` forever, the very condition the negative check must catch. And the fix went to all four sites, `1c`, `3c`, `4c` and `N1b` (the Notification contract's order-confirmation poll), found by grepping the exact `=== 'PENDING'` pattern across the collection instead of trusting the bug report's list of three. `N1b` had the identical false-RED exposure for any run against the orchestrated topology.

The evidence is stability, not one green run. The fully orchestrated suite ran through the proxy 6 consecutive times: 0 failed every run, newman exit 0 every time, and the saga log showed 18 real `AWAITING_SHIPMENT` transitions absorbed across the window. Each one triggered a retry instead of a false failure, so the passes were not vacuous. A single green run proves the fix broke nothing it touched; six against a timing-dependent race show the window is closed.

> **ADLC in Action**
>
> The gap surfaced live during the cutover run, not at the planning gate. The plan scoped `AWAITING_SHIPMENT` as a new order status but did not anticipate that an existing test script hardcoded which statuses count as still in flight. The repair was its own lane, touching `tooling/newman/` only and no application code, so a test-infrastructure fix stays visibly separate from a saga-logic fix in history. A reader auditing the ledger can tell the system under test never had the bug; the harness did.

> **Decision**
>
> Add a resilience mechanism when the system has shown the failure it exists for. Retry transient errors only, behind an idempotent receiver. Add a breaker for sustained failure and a bulkhead for a shared, contendable resource, and not before.

> **🤖 Explore with your agent**
>
> "In examples/06-shipping-service, review app/enrich_client.py against the rule 'retry transient errors only, and add a breaker or bulkhead only once the system has shown the failure.' Then grep tooling/newman/mea.postman_collection.json for every poll script that tests a literal status and list any that would false-RED on an intermediate status."
>
> Check: the review should name `httpx.HTTPStatusError` as the unretried path, and the grep for `=== 'PENDING'` should return no remaining sites.
