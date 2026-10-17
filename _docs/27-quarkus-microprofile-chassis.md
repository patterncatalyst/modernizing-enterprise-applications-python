---
title: "The FastAPI Chassis"
order: 27
part: "Communication & Contracts"
description: "A used/partial/deferred scorecard for the cross-cutting platform the 8 FastAPI/Starlette services already share: config, logging, health, errors, and resilience as convention, not a framework feature, plus what is named but not yet built."
duration: 30 minutes
---

Chapter 26 turned off the monolith for good: six independently deployable
services plus a data-less GraphQL gateway, reached through one flagless
edge router with nothing left to fall back to. What hasn't been asked yet,
across twelve chapters of extractions, is a question that only makes sense
once every service exists side by side: strip away what each one does
differently — review's reviews, payment's captures, order's saga — and
what's left that every single one does the *same* way? That shared-but-
unlabeled layer is a chassis: the configuration, logging, health, error-
handling, and resilience plumbing a service needs before it can do its
actual job, present in every service whether or not anyone ever points at
it and names it. This chapter does exactly that pointing. It introduces no
new extraction and no new runnable example — it audits eight already-
running codebases (`examples/01-strangler-proxy` through
`examples/08-graphql-gateway`) capability by capability, against this
front matter's own menu, and reports which parts of that chassis a service
actually wired in versus which parts stayed a name in a build-plan
paragraph. The discipline to hold onto from here to the scorecard at the
end: a pattern copied into one service's `app/main.py` is a capability
*used*. A capability mentioned in `_plans/build-plan.md` and never written
is a capability *deferred*, and naming the gap in plain terms beats
carrying it forward unexamined.

{% include excalidraw.html file="fastapi-chassis-anatomy" alt="A band labeled 'Inside one FastAPI service, startup to request' containing: config.py's frozen dataclass Settings.from_env() and stdlib RotatingFileHandler logging feeding from the uvicorn ASGI entry point; the lifespan() context manager wiring db engine, Kafka consumer, and outbox relay; errors.py's uniform error body and the GET /health route as request-time concerns present on 6 of 8 services; a box for the Containerfile present on all 8; tenacity retry as the one resilience wrapper, used only in shipping-service's enrich_client.py; and a dashed ghost box naming OpenTelemetry/Prometheus, pybreaker/bulkhead, and a shared chassis library named as not yet built." caption="Figure 27.1 — The chassis inside one FastAPI service: what every service does identically, what's opt-in, and what's named but not built" %}

## What "chassis" means when there is no framework BOM

The Java sibling of this book can answer "what's in the chassis" by
grepping eight `pom.xml` files for a shared `quarkus-bom` and a short list
of MicroProfile extensions — Config, Health, Fault Tolerance, Metrics,
OpenAPI, REST Client, Security each arrive as a dependency line, and
turning one on is a one-line diff. FastAPI has no equivalent catalog.
Starlette gives a service an ASGI application, a routing table, and a
`lifespan` context manager; FastAPI layers typed request/response
validation via Pydantic v2 on top of that; `uv` resolves and pins
dependencies per service into its own `pyproject.toml`/`uv.lock` pair. None
of that ships a health endpoint, a uniform error body, a retry policy, or a
metrics exporter — every one of those is either a third-party package a
service's `pyproject.toml` chooses to add, or plain application code
someone writes once and copies into the next service. That's the real
difference this chapter has to keep surfacing: in the Quarkus book, "is
Health used" is a dependency-presence question; in this one, it's a
code-presence question, because there is no framework switch to flip. A
chassis capability here becomes real the moment someone writes the file
that provides it — not when a BOM happens to include it.

That also means this project has no single shared chassis package that all
eight services import from. `app/config.py`, `app/errors.py`, and the
`_configure_logging()` function inside `app/main.py` are each written once
per service and then copied, by hand, into the next one — the same
convention, repeated eight times, not eight imports of one library. Whether
that absence is a gap or a deliberate choice is this chapter's last section;
first, the scorecard itself, row by row, cited against the real code.

## Configuration: a frozen dataclass, not pydantic-settings

**Status: USED, 7 of 8.** The original build-plan line for this chapter —
still sitting in `_plans/build-plan.md`'s Part 5 table as "FastAPI +
pydantic-settings" — was aspirational, written before any service existed.
What actually shipped, starting with `03-notification-service` and
repeated unchanged through `08-graphql-gateway`, is a plain, frozen
`@dataclass` with a `from_env()` classmethod that reads `os.environ` at
call time, not `pydantic-settings`' `BaseSettings` with its `.env`-file
loading and field-level validators. `examples/07-order-service/app/
config.py` is the clearest instance — twelve fields, one `from_env()`
method, each field defaulted and read with a plain `os.environ.get`:

```python
# examples/07-order-service/app/config.py
@dataclass(frozen=True)
class Settings:
    http_port: int
    database_url: str
    kafka_bootstrap_servers: str
    inventory_grpc_target: str
    # ... eight more fields, same shape

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            # ... one os.environ.get per field, each with its own module-level default
        )
```

`frozen=True` is doing real work, not decoration: once a `Settings`
instance exists, nothing in the service can mutate a config value
mid-request, which rules out an entire class of bugs where one request path
accidentally changes a timeout or a topic name that every other in-flight
request is also reading. Calling `from_env()` fresh inside `lifespan()`
rather than once at import time is the second deliberate choice the
docstring calls out directly: a test can set an environment variable
immediately before constructing the app and `Settings.from_env()` picks it
up, instead of inheriting whatever was in `os.environ` the first time the
module happened to be imported.

`01-strangler-proxy` carries the same `@dataclass(frozen=True, slots=True)`
shape — `slots=True` on top, since the proxy's `Settings` has no ORM or
Pydantic layer touching it and the memory saving is free — but with one
real inconsistency worth naming rather than smoothing over: its module
constructs `settings = Settings.from_env()` once at import time and the
rest of `app/main.py` falls back to that singleton (`default_settings`)
whenever a caller doesn't supply its own, rather than re-resolving the
environment inside the request/response path the way the other six
services resolve it inside their own `lifespan()`. It's a smaller
difference in practice than it sounds — the proxy has no per-request state
that depends on config — but it's a second config idiom living in the same
codebase, not the uniform one.

The real exception is `02-review-service`, and it's an absence, not a
variant: there is no `app/config.py` in that service at all.
`examples/02-review-service/app/db.py` reads `DATABASE_URL` directly with a
bare `os.environ.get` call, no dataclass, no `from_env()`, no central place
listing every tunable the service has:

{% include codetabs.html langs="02-review-service — app/db.py, no config.py at all|07-order-service — app/config.py, the settled convention" %}

```python
# examples/02-review-service/app/db.py
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"

def resolve_database_url(raw: str | None = None) -> str:
    value = raw if raw is not None else os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://") :]
    return value
```

```python
# examples/07-order-service/app/config.py
@dataclass(frozen=True)
class Settings:
    database_url: str
    # ... every tunable the service has, in one place

    @classmethod
    def from_env(cls) -> Settings:
        return cls(database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL), ...)
```

This isn't a defect to fix retroactively; it's the fossil record of
when the convention solidified. `review-service` is this book's first
extraction (Chapter 15), written before `notification-service` established
the dataclass-and-`from_env()` shape every later service copied. Review's
Phase B was frozen once it passed its equivalence suite, and nothing in the
six extractions since has forced a reason to go back and retrofit a
`config.py` onto a service nobody has touched. Seven of eight services
share one config idiom; the eighth is older than the idiom.

One more thing worth naming precisely here, because the stub this chapter
replaces conflated it with settings: Pydantic v2 **is** used everywhere in
this project, just not for configuration. Every service's `app/
schemas.py` defines its wire-contract request/response models as
`pydantic.BaseModel` subclasses — `examples/07-order-service/app/
schemas.py`'s `OrderCreate`/`OrderRead`/the four consumed event shapes, and
the same pattern in every sibling. That's real, used, and worth crediting;
it's simply a different capability than `pydantic-settings`, and the two
shouldn't be read as one checkbox.

## Logging and the Containerfile: the two universal rows

**Status: USED, 8 of 8, both rows.** Every one of the eight services —
including the Starlette-only `01-strangler-proxy` — configures stdlib
`logging` identically: a `RotatingFileHandler` writing to
`logs/<service>.log` (10 MB per file, five backups) alongside a
`StreamHandler` on the console, both attached to the root logger before
anything else in the process can log a line. `examples/07-order-service/
app/main.py`'s `_configure_logging()` is representative of all eight:

```python
# examples/07-order-service/app/main.py
def _configure_logging() -> None:
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "order-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
    )
    console_handler = logging.StreamHandler()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
```

This is `structlog`-free by choice, not oversight: nothing in this project
emits structured JSON log lines, and no service correlates a log line back
to a request or a saga step via a trace or correlation ID in the log
format itself — the `%(message)s` body is whatever string the call site
built by hand. What the convention does buy, stated directly in
`02-review-service`'s own docstring, is simpler and still real: "console
output alone scrolls away and can't be grep'd after a crash or a failed
test run." A file under `logs/` that survives the process exiting is the
actual requirement this project has had so far; a structured, queryable
log pipeline is a different, larger capability nothing here has asked for
yet.

The Containerfile row needs no hedge at all: all eight example directories
— `01-strangler-proxy` through `08-graphql-gateway` — ship one. Every
service this project extracted is independently buildable into a
container image, full stop, the one row in this scorecard with zero
asterisk.

## Health: six of eight, liveness only, no consumer

**Status: PARTIAL, 6 of 8.** `GET /health` exists in
`03-notification-service`, `04-inventory-service`, `05-payment-service`,
`06-shipping-service`, `07-order-service`, and `08-graphql-gateway`. It is
absent from `01-strangler-proxy` and `02-review-service` — the same two
outliers the config scorecard already named, for related reasons: the
proxy is a thin router with no owned dependency to report on, and
review-service is old enough to predate the convention. `08-graphql-
gateway`'s own docstring states the design choice behind every one of the
six implementations as directly as any source in this project does:

```python
# examples/08-graphql-gateway/app/main.py (module docstring)
# GET  /health   -- liveness (process is up; no downstream probed -- see
#                    docstring below for why readiness never couples to
#                    downstreams)
```

Every one of the six is liveness-only — "this process is up and able to
answer HTTP" — never readiness in the MicroProfile sense of "and every
downstream I depend on is also reachable." That's a real, stated design
decision this project has made twice now (once in prose here, once
implicitly in the Java sibling's own Health section): coupling a service's
own health signal to a downstream's availability means one slow
dependency can cascade into marking an otherwise-healthy process as down,
which is the opposite of what a liveness probe is for. `07-order-
service`'s own `/health` goes one step further than "process is up" without
crossing into readiness — it reports the saga consumer's Kafka partition
assignment, specifically so this project's own CI readiness wait can poll
it before firing requests, without that poll ever gating traffic on
payment's or shipping's availability.

What none of the six endpoints has yet is a consumer that acts on the
answer. Nothing in this repository's compose definitions or CI points a
platform's liveness or readiness probe at any of these routes to gate
restarts or traffic — that wiring is a Kubernetes-appendix concern, not
something a standalone FastAPI service can do to itself. The six endpoints
exist, respond correctly, and currently answer nobody.

## Errors: `errors.py`'s uniform mapping, six of eight

**Status: PARTIAL, 6 of 8.** `app/errors.py` exists in `02-review-service`
through `07-order-service` — six consecutive services — each defining the
same shape: an `ApiError` base exception carrying a `status_code` and an
`error_code`, a small set of subclasses for that service's own domain
failures, and an `install_exception_handlers()` function registered on the
FastAPI app that maps every one of them, plus FastAPI's own
`RequestValidationError` and Starlette's `HTTPException`, onto one uniform
JSON body: `{"error": <CODE>, "message": ..., "timestamp": ...}`.
`examples/07-order-service/app/errors.py` is representative:

```python
# examples/07-order-service/app/errors.py
class ApiError(Exception):
    status_code: int = 500
    error_code: str = "ERROR"
    def __init__(self, message: Any):
        super().__init__(str(message))
        self.message = message

class ResourceNotFound(ApiError):
    status_code = 404
    error_code = "NOT_FOUND"

class InsufficientStock(ApiError):
    status_code = 409
    error_code = "OUT_OF_STOCK"

class InventoryServiceUnavailable(ApiError):
    status_code = 503
    error_code = "INVENTORY_SERVICE_UNAVAILABLE"
```

```python
# examples/07-order-service/app/errors.py (install_exception_handlers)
def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                             content=_error_body(exc.error_code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request, exc) -> JSONResponse:
        # FastAPI's own default is 422; the monolith's DRF contract uses 400 --
        # this handler remaps BOTH the status code and the body shape.
        return JSONResponse(status_code=400, content=_error_body("VALIDATION_FAILED", exc.errors()))
```

`InsufficientStock` (409) and `InventoryServiceUnavailable` (503) are a
small but telling design decision: a logical "not enough
stock" and a transport-level "couldn't reach inventory-service" are
two distinct error codes, never folded into one generic 5xx,
because a caller needs to react to them differently — one means try a
smaller quantity, the other means retry later.

The two absences are structural, not accidental. `01-strangler-proxy`
has no `errors.py` because it has no domain errors of its own to map — its
entire error-handling story is "bridge the upstream's real status code
through unchanged, and turn an unreachable upstream into a real 502,"
which is exactly what `app/main.py`'s own `except httpx.HTTPError` clause
does, with no uniform JSON body involved at all:

{% include codetabs.html langs="01-strangler-proxy — no errors.py, raw bridge semantics|07-order-service — errors.py, uniform JSON body" %}

```python
# examples/01-strangler-proxy/app/main.py
try:
    upstream_response = await client.send(upstream_request, stream=True)
except httpx.HTTPError as exc:
    # Bridge semantics: an unreachable/broken upstream is a real 502,
    # never a swallowed 200.
    return Response(
        content=f"strangler-proxy: upstream unavailable ({exc.__class__.__name__})",
        status_code=502, media_type="text/plain",
    )
return StreamingResponse(_iter_upstream_body(upstream_response),
                          status_code=upstream_response.status_code, ...)
```

```python
# examples/07-order-service/app/errors.py
@app.exception_handler(ApiError)
async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                         content=_error_body(exc.error_code, exc.message))
```

`08-graphql-gateway` is the second absence, and for a different reason:
GraphQL has its own error convention — a failed resolver surfaces inside
the response envelope's `errors` array, next to whatever `data` the other
resolvers still produced, rather than as an HTTP-status-coded body. A REST
`errors.py` style uniform JSON error wouldn't fit a protocol where a
single response can be a partial success and a partial failure at once.

## Resilience: `tenacity`, one service, one call site

**Status: PARTIAL, narrowly.** Grep this project's `examples/` tree for
`tenacity` and the only hit outside documentation is
`examples/06-shipping-service/app/enrich_client.py` — one `@retry`
decorator, wrapping the one outbound synchronous HTTP call this entire
system's choreographed services make (every other saga reaction reacts to
a Kafka event; nothing else here calls out over HTTP mid-saga):

```python
# examples/06-shipping-service/app/enrich_client.py
_RETRYABLE_EXCEPTIONS = (httpx.TransportError, httpx.TimeoutException)
_MAX_ATTEMPTS = 3

@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5, max=4),
)
async def fetch_shipping_address(order_id: int) -> str:
    ...
```

The scope of what gets retried is as deliberate as the choice to retry
anything at all: only `httpx.TransportError`/`httpx.TimeoutException` —
connection refused, DNS failure, a request that blew its own per-call
timeout — ever triggers a retry. A non-2xx response, or a 2xx response
simply missing the field the saga needs, is raised immediately as an
`EnrichmentError` and never retried, because that's a contract violation,
not a transient blip, and retrying a wrong answer three times just gets
the same wrong answer three times slower. No other service in this project
wraps an outbound call this way, because no other service makes the kind
of synchronous, mid-saga outbound call that needs it — `tenacity` sits in
`06-shipping-service`'s `pyproject.toml` and nowhere else's.

## Metrics, OpenTelemetry, and fault tolerance: named, not built

**Status: DEFERRED, both.** There is nothing to hedge here because there
is nothing in the tree: no `opentelemetry-*` or `prometheus-client`
package in any service's dependency lock file is actually imported by any
`app/*.py` file, no `/metrics` endpoint anywhere, no span or trace emitted
by anything this project runs today. The `_plans/backmatter-track-plan.md`
line that scoped this very chapter states the gap directly rather than
letting a reader infer it from absence: "no OTel/metrics anywhere." Chapter
30 is where this gets built — additively, onto three of the eight services
— and building it now, with no dashboard or alert waiting to consume it,
would be the same speculative-infrastructure trap this project has
declined before: a capability added because a catalog says a service
should have it, not because an operational need has asked for it.

`pybreaker` (a circuit breaker) and an `asyncio.Semaphore`-based bulkhead
are the same story, one level further from built: named in `_plans/
build-plan.md` and `_plans/decisions.md`'s prose, zero lines of code
anywhere in `examples/`. What a circuit breaker buys that `tenacity`'s
bounded retry doesn't — a state machine that stops hammering a
known-down dependency entirely, rather than retrying it three times per
call forever — is real, and it's exactly what this project's own
resilience chapter already scoped and declined to build for the same
reason this chapter inherits rather than re-argues: no measured, sustained
failure rate in this project's own traffic has yet justified the added
complexity. The day it does, it's a decorator added to one call site, not
a redesign.

## What a true shared chassis library would cost, and why this project hasn't built one

**Status: DEFERRED, by choice.** Every row above is a convention copied
eight times, not a dependency imported once. A `pattern-catalyst-chassis`
package — one `pip`-installable library every service depends on, shipping
one `Settings` base class, one `install_exception_handlers()`, one
`_configure_logging()` — would collapse eight near-identical files into
one, and it is exactly the kind of refactor this chapter's own brief
explicitly rules out: synthesizing the real state of eight services, not
retrofitting a ninth artifact underneath them. The reason that refactor
stays unbuilt is more than "out of scope for one chapter," though — it's a
real trade-off worth naming. A shared library versioned independently of
the eight services means every service now has a second dependency to
bump, test, and roll out on its own schedule, and the one thing this
project's services have proven so far is that they can each evolve, break,
and redeploy independently of one another without coordinating a release.
Eight copies of a fifteen-line `_configure_logging()` function are cheap to
keep in sync by hand; eight services sharing one versioned internal package
is a coordination cost that should wait for the same trigger a circuit
breaker waits for — when drift across the eight copies starts causing real
bugs, not before.

> **ADLC in Action** — This chapter's own research phase is a small case
> study in the discipline the scorecard above tries to model. The chapter
> prompt that commissioned it arrived with a plausible-sounding claim
> already attached — that configuration in this project runs on
> `pydantic-settings` — carried forward from `_plans/build-plan.md`'s
> own Part 5 table, written before a single service existed. Confirming it
> meant grepping `examples/*/app/config.py` for the actual import, finding
> a plain `dataclasses.dataclass` in every one of them, and finding no
> `pydantic_settings` import anywhere in the tree at all. The same
> verification pass caught a second, smaller drift: `02-review-service`
> has no `config.py`, which no prior chapter's prose had stated outright
> (it reads naturally as "the first extraction, so naturally it's simpler,"
> until the actual file listing makes the absence concrete). An agent
> drafting this chapter from the build-plan's wording alone, without
> re-reading the eight `app/config.py` files directly, would have shipped
> a scorecard that was wrong in exactly the way a chassis chapter cannot
> afford to be wrong — the two mismatches a reader is most likely to
> re-check with a single `grep` of their own.

{% include excalidraw.html file="chassis-scorecard" alt="Three stacked bands. USED, every service: config via a frozen dataclass and from_env() (7 of 8, review-service is the exception), stdlib RotatingFileHandler logging to logs/ (8 of 8), and a Containerfile (8 of 8). PARTIAL, a real count with a named reason for each gap: GET /health (6 of 8, absent in the proxy and review-service), errors.py's uniform error mapping (6 of 8, absent in the proxy and the GraphQL gateway, each for a structural reason), and tenacity retry (1 of 8, shipping-service's one outbound HTTP call site). DEFERRED, zero footprint today: metrics/OpenTelemetry (ch.30 adds it to three services), pybreaker/bulkhead (named in planning prose, no code), and a true shared chassis library (each file is copied and adapted per service, never imported from one shared package)." caption="Figure 27.2 — The chassis scorecard: used, partial, and deferred, across all 8 services" %}

## What you learned

- **A FastAPI chassis is a code-presence question, not a dependency-
  presence one** — there is no BOM or extension catalog to grep; a
  capability here becomes real the moment the file that implements it is
  written, and this project writes that file eight times rather than
  importing it once.
- **Config and logging are the floor every service shares identically** —
  a frozen dataclass with `from_env()` (7 of 8; `review-service` predates
  the convention) and stdlib `RotatingFileHandler` logging to `logs/<service>.log`
  (8 of 8), plus a Containerfile on all eight — the three rows in this
  scorecard that needed no hedge.
- **"Partial" means a real, re-checkable count, not a euphemism** —
  `/health` on 6 of 8, `errors.py` on 6 of 8, `tenacity` on 1 of 8 — and
  every absence traces to a stated, structural reason (the proxy routes
  rather than owns a domain, the gateway's GraphQL envelope has its own
  error convention, review-service predates a convention that solidified
  after it shipped) rather than an unexplained gap.
- **Deferred is a decision, re-checkable by grep, not a silent gap** —
  metrics/OpenTelemetry, `pybreaker`/bulkhead, and a shared chassis
  library all have zero footprint in this tree today, each for a stated
  reason: no consumer waiting on a dashboard, no measured failure rate
  that justifies a circuit breaker, and a coordination cost that a
  codebase of eight independently-deployable services hasn't yet earned
  paying.
- **Pydantic v2 is real and used — for wire contracts, not settings** —
  every service's `app/schemas.py` is a `BaseModel` hierarchy; correcting
  the build-plan's "pydantic-settings" framing doesn't erase Pydantic from
  this project, it just puts it in its actual place.

Chapter 28 turns from the chassis a service runs on to the question of
what a service promises the services calling it — contracts, versioning,
and the service registry a system this size eventually needs once
"whichever base URL is in `application.properties`'s Python sibling,
`config.py`, today" stops being a sufficient answer for who's allowed to
call whom, and with what guarantee the shape won't change underneath them.

---

*Verification status: not applicable — conceptual chapter, no new runnable
example. Cited: `examples/01-strangler-proxy/app/config.py` (`@dataclass(frozen=True, slots=True)`,
module-level `settings = Settings.from_env()` singleton) and `app/main.py`
(the `httpx.HTTPError` → 502 bridge, no `errors.py`, no `/health` route,
confirmed by its own test file's `/health` 404 parametrization in
`tests/test_routing.py`); `examples/02-review-service/app/db.py` (bare
`os.environ.get("DATABASE_URL", ...)`, no `config.py` in the directory) and
`app/main.py` (rotating-file logging present, no `/health` route);
`examples/03-notification-service/`, `04-inventory-service/`,
`05-payment-service/`, `06-shipping-service/`, `07-order-service/`, and
`08-graphql-gateway/`'s `app/main.py` files (each with `GET /health` and
identical `_configure_logging()` shapes) and `app/config.py` files (each a
`@dataclass(frozen=True)` with a `from_env()` classmethod); `examples/02-
review-service/` through `07-order-service/`'s `app/errors.py` (the
`ApiError` hierarchy and `install_exception_handlers()`), and the confirmed
absence of `app/errors.py` in `01-strangler-proxy/` and `08-graphql-
gateway/`; `examples/06-shipping-service/app/enrich_client.py` (the
`tenacity` `@retry` decorator, `_RETRYABLE_EXCEPTIONS`) and its
`pyproject.toml` (the only `tenacity` dependency declaration in this
project); `examples/07-order-service/app/schemas.py` and five sibling
services' `app/schemas.py` (`pydantic.BaseModel` wire contracts); all eight
`examples/*/Containerfile`; and `_plans/build-plan.md` (the "FastAPI +
pydantic-settings" line this chapter corrects) and `_plans/backmatter-
track-plan.md` (the real-state note this chapter is built from). Re-confirm
before relying on this scorecard again: a fresh `grep -rl tenacity
examples/*/pyproject.toml`, `grep -rli "opentelemetry\|prometheus"
examples/*/app/`, and `grep -rl "pydantic_settings" examples/` should each
still return exactly the same (narrow or empty) results, since an added
dependency in any service's `pyproject.toml` would move a row in this
scorecard from DEFERRED to PARTIAL or USED.*
