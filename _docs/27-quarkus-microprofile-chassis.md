---
title: "The FastAPI Chassis"
order: 27
part: "Communication & Contracts"
description: "A used, partial and deferred scorecard for the cross-cutting platform the eight FastAPI and Starlette services share: config, logging, health, errors and resilience as convention, plus what is named but not built."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- Audit which chassis capabilities (configuration, logging, health, errors, resilience) a FastAPI service wires into its code versus which a `pyproject.toml` dependency merely makes available.
- Explain the frozen-dataclass `Settings.from_env()` pattern and why it was chosen over `pydantic-settings`' `BaseSettings`.
- Say why `tenacity` retries exactly one call site (`shipping-service`'s `enrich_client.py`) instead of a `pybreaker` circuit breaker, and what adding one would take.
- Explain the `GET /health` convention on 6 of 8 services and why `strangler-proxy` and `graphql-gateway` omit it.
- Weigh a shared chassis package against a convention copied by hand into each `app/config.py`, `app/errors.py` and `_configure_logging()`.
- Tell a capability present in a Containerfile or `pyproject.toml` from one proven by a wired-in code path and a passing test.

## Why this matters

With six services, a gateway and a proxy running side by side, one question only makes sense: what does every service do the same way, apart from what it does differently (review's reviews, payment's captures, order's saga)? That shared layer is the chassis: the configuration, logging, health, error-handling and resilience plumbing a service needs before it can do its job. It exists whether or not anyone names it.

The audit covers eight running codebases, `examples/01-strangler-proxy` through `examples/08-graphql-gateway`, capability by capability. A pattern copied into a service's code is **used**. A capability named in a plan and never written is **deferred**, and naming the gap beats carrying it forward unexamined.

{% include excalidraw.html file="fastapi-chassis-anatomy" alt="One FastAPI service from startup to request: config.py's frozen dataclass Settings.from_env() and stdlib RotatingFileHandler logging, the lifespan() context manager wiring the db engine, Kafka consumer and outbox relay, errors.py's uniform error body and the GET /health route on 6 of 8 services, a Containerfile on all 8, tenacity retry in shipping-service only, and a dashed box for OpenTelemetry, Prometheus, pybreaker, bulkhead and a shared chassis library as not yet built" caption="Figure 27.1: The chassis inside one FastAPI service: what every service does identically, what is opt-in and what is named but not built" %}

## What "chassis" means without a framework BOM

A framework built around a shared BOM answers "what's in the chassis" by grepping build files: Config, Health, Fault Tolerance, Metrics, OpenAPI, REST Client and Security each arrive as a dependency line, and turning one on is a one-line diff. FastAPI has no such catalog. Starlette gives a service an ASGI app, routing and a `lifespan` context manager. FastAPI adds typed validation through Pydantic v2. `uv` pins dependencies per service in its own `pyproject.toml` and `uv.lock`. None of that ships a health endpoint, a uniform error body, a retry policy or a metrics exporter. Each is a third-party package a service chooses, or application code written once and copied.

So "is Health used" is a code-presence question, not a dependency-presence one. And no shared chassis package exists: `app/config.py`, `app/errors.py` and `_configure_logging()` in `app/main.py` are written per service and copied by hand.

| Capability | Status | Count |
|---|---|---|
| Configuration, frozen dataclass | Used | 7 of 8 |
| Logging, stdlib `RotatingFileHandler` | Used | 8 of 8 |
| Containerfile | Used | 8 of 8 |
| `GET /health` | Partial | 6 of 8 |
| `errors.py` uniform mapping | Partial | 6 of 8 |
| `tenacity` retry | Partial | 1 of 8 |
| Metrics, OpenTelemetry | Deferred | 0 |
| `pybreaker`, bulkhead | Deferred | 0 |
| Shared chassis library | Deferred by choice | 0 |

## Configuration: a frozen dataclass, not pydantic-settings

The original plan said "FastAPI + pydantic-settings". What shipped, starting with `03-notification-service` and repeated through `08-graphql-gateway`, is a plain frozen `@dataclass` with a `from_env()` classmethod that reads `os.environ` at call time. `examples/07-order-service/app/config.py` has twelve fields, each defaulted and read with `os.environ.get`:

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

`frozen=True` rules out a class of bugs where one request path changes a timeout or topic name that every other in-flight request reads. Calling `from_env()` inside `lifespan()` instead of at import time lets a test set an environment variable just before building the app and have it picked up, instead of inheriting whatever `os.environ` held at first import.

`01-strangler-proxy` uses `@dataclass(frozen=True, slots=True)`, since nothing ORM or Pydantic touches its `Settings`. It has one inconsistency: its module builds `settings = Settings.from_env()` once at import and `app/main.py` falls back to that singleton (`default_settings`) when a caller supplies none, instead of resolving the environment in `lifespan()` like the other six. The proxy has no per-request state that depends on config, so this is harmless, but it is a second idiom in the codebase.

The real exception is `02-review-service`, which has no `app/config.py` at all. `app/db.py` reads `DATABASE_URL` with a bare `os.environ.get`, with no dataclass, no `from_env()` and no single list of tunables:

{% include codetabs.html langs="02-review-service: app/db.py, no config.py at all|07-order-service: app/config.py, the settled convention" %}

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

Review is the first extraction, written before `notification-service` set the dataclass shape every later service copied. Review's Phase B was frozen once it passed its equivalence suite, and nothing since has forced a retrofit. Seven of eight share one idiom; the eighth predates it.

Pydantic v2 is used everywhere, just not for configuration. Every service's `app/schemas.py` defines request and response models as `pydantic.BaseModel` subclasses (`OrderCreate`, `OrderRead` and the four consumed event shapes in order-service). That is a different capability from `pydantic-settings`.

## Logging and the Containerfile

Every service, including the Starlette-only proxy, configures stdlib `logging` identically: a `RotatingFileHandler` writing `logs/<service>.log` (10 MB per file, five backups) plus a console `StreamHandler`, both attached to the root logger before anything else can log.

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

There is no `structlog`: no service emits structured JSON lines or carries a trace or correlation ID in the log format, and `%(message)s` is whatever string the call site built. What the file buys is stated in `02-review-service`'s docstring: console output alone scrolls away and cannot be grepped after a crash or a failed test run. A queryable log pipeline is a larger capability nothing has asked for. All eight example directories also ship a Containerfile, the one row with no asterisk.

## Health: six of eight, liveness only

`GET /health` exists in `03-notification-service`, `04-inventory-service`, `05-payment-service`, `06-shipping-service`, `07-order-service` and `08-graphql-gateway`. It is absent from `01-strangler-proxy`, a thin router with no owned dependency to report, and `02-review-service`, which predates the convention. The gateway's module docstring states the design:

```python
# examples/08-graphql-gateway/app/main.py (module docstring)
# GET  /health   -- liveness (process is up; no downstream probed -- see
#                    docstring below for why readiness never couples to
#                    downstreams)
```

All six are liveness only: the process is up and answers HTTP. Coupling a service's health to a downstream's availability lets one slow dependency mark a healthy process as down, the opposite of what a liveness probe is for. order-service's `/health` goes one step further without becoming readiness: it reports the saga consumer's Kafka partition assignment, so CI can wait on it before firing requests, without gating traffic on payment's or shipping's availability.

No consumer acts on the answer. Nothing in the compose definitions or CI points a liveness or readiness probe at these routes; that wiring belongs to a Kubernetes deployment, not to a standalone service.

## Errors: a uniform mapping, six of eight

`app/errors.py` exists in `02-review-service` through `07-order-service`. Each defines an `ApiError` base carrying `status_code` and `error_code`, a few subclasses for the service's domain failures, and an `install_exception_handlers()` that maps them, plus FastAPI's `RequestValidationError` and Starlette's `HTTPException`, onto one body: `{"error": <CODE>, "message": ..., "timestamp": ...}`.

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

`InsufficientStock` (409) and `InventoryServiceUnavailable` (503) are separate codes because the caller reacts differently: one means try a smaller quantity, the other means retry later.

The two absences are structural. `01-strangler-proxy` has no domain errors; its error story is to bridge the upstream's status code unchanged and turn an unreachable upstream into a `502`, with no uniform JSON body:

{% include codetabs.html langs="01-strangler-proxy: no errors.py, raw bridge semantics|07-order-service: errors.py, uniform JSON body" %}

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

`08-graphql-gateway` is the second absence. A failed resolver surfaces in the response's `errors` array beside whatever `data` the other resolvers produced, and a REST-style uniform body does not fit a response that can be a partial success and a partial failure at once.

## Resilience: `tenacity`, one call site

A grep of `examples/` for `tenacity` finds one hit outside documentation: `examples/06-shipping-service/app/enrich_client.py`, one `@retry` decorator on the only outbound synchronous HTTP call the services make mid-saga. Every other saga reaction reacts to a Kafka event.

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

Only `httpx.TransportError` and `httpx.TimeoutException` (refused, DNS failure, a blown per-call timeout) trigger a retry. A non-2xx response, or a 2xx missing the field the saga needs, raises `EnrichmentError` immediately: that is a contract violation, and retrying a wrong answer returns the same wrong answer slower. `tenacity` sits in `06-shipping-service`'s `pyproject.toml` and nowhere else's.

## Deferred: metrics, OpenTelemetry, breakers and a shared library

No `opentelemetry-*` or `prometheus-client` package in any lock file is imported by any `app/*.py`, there is no `/metrics` endpoint, and nothing emits a span. A later addition builds this onto three of the eight services; building it now, with no dashboard or alert to consume it, would add infrastructure because a catalog says a service should have it.

`pybreaker` and an `asyncio.Semaphore` bulkhead are one step further from built: zero lines in `examples/`. A breaker buys what bounded retry cannot, a state machine that stops hammering a known-down dependency instead of retrying it three times per call forever. No measured sustained failure rate has justified it. When one does, it is a decorator on one call site, not a redesign.

A shared chassis package, one installable library shipping a `Settings` base, one `install_exception_handlers()` and one `_configure_logging()`, would collapse eight near-identical files into one. The cost is a second dependency every service must bump, test and roll out on its own schedule, when the services have so far evolved and redeployed independently without a coordinated release. Eight copies of a fifteen-line `_configure_logging()` are cheap to keep in sync by hand. The trigger is the same as for a breaker: drift across the copies causing real bugs.

> **ADLC in Action**
>
> The brief for this audit arrived with a plausible claim already attached: configuration runs on `pydantic-settings`, carried from the build plan, which was written before any service existed. Confirming it meant grepping `examples/*/app/config.py` for the import, finding a plain `dataclasses.dataclass` in every one, and finding no `pydantic_settings` import anywhere. The same pass caught a second drift: `02-review-service` has no `config.py`, which no earlier prose had stated outright. An agent drafting from the plan's wording alone would have shipped a scorecard wrong in the two ways a reader is most likely to re-check with one `grep`.

{% include excalidraw.html file="chassis-scorecard" alt="Three stacked bands. USED, every service: config via a frozen dataclass and from_env() (7 of 8, review-service is the exception), stdlib RotatingFileHandler logging to logs/ (8 of 8), a Containerfile (8 of 8). PARTIAL, with a named reason for each gap: GET /health (6 of 8, absent in the proxy and review-service), errors.py (6 of 8, absent in the proxy and the GraphQL gateway), tenacity retry (1 of 8, shipping-service's one outbound HTTP call). DEFERRED, zero footprint today: metrics and OpenTelemetry, pybreaker and bulkhead, and a shared chassis library" caption="Figure 27.2: The chassis scorecard: used, partial and deferred across all 8 services" %}

> **Decision**
>
> Count a capability as used only when a code path wires it in and a test exercises it. Defer a platform capability, such as metrics, a breaker or a shared library, until a consumer, a measured failure or real drift asks for it.

> **🤖 Explore with your agent**
>
> "Audit examples/01-strangler-proxy through examples/08-graphql-gateway for the chassis scorecard: for config, logging, /health, errors.py and tenacity, report which services wire each one into app code and which only list it in pyproject.toml, and flag any service that disagrees with the 7 of 8, 8 of 8, 6 of 8, 6 of 8 and 1 of 8 counts."
>
> Check: `grep -rl "^from tenacity" examples/*/app` returns only `examples/06-shipping-service/app/enrich_client.py`, and `ls examples/*/app/config.py` lists seven files.
