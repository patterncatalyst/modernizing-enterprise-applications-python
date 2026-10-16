# AGENTS.md -- 08-graphql-gateway

Context for an AI agent (or a human) picking this module up.

## What this is

The **GRAPHQL-GATEWAY lane** of r07 (the finale): a new, additive, **data-less**
Strawberry GraphQL aggregation gateway on `:8090`, its OWN front door --
never routed through `01-strangler-proxy`. The single `order(id)` query
federates reads across every already-extracted service: order
(`07-order-service`, REST `:8088`), payment (`05-payment-service`, REST
`:8085`), shipping (`06-shipping-service`, REST `:8087`), review
(`02-review-service`, REST `:8001`), and per-item stock from inventory
(`04-inventory-service`, gRPC `GetStock` on `:9004`).

This is the Python sibling of the role played by
`~/Dev/modernizing-enterprise-applications/examples/08-graphql-gateway`
(Java/Quarkus, SmallRye GraphQL) -- same chapter intent, same five-service
federation shape -- but its own independent implementation on Strawberry,
adapted from the house aggregation style in
`~/Dev/datamesh-reference-arch-python/examples/lgtm-datamesh/services/graphql-gateway`.

There is no monolith original for this module at all: GraphQL aggregation
across five independently-extracted services is a net-new capability that
only exists once every extraction (`02`/`04`/`05`/`06`/`07`) is already
standing on its own.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **FastAPI 0.143.2**, **uvicorn[standard] 0.54.0**, **strawberry-graphql
  0.335.0**, **httpx 0.28.1**, **grpcio 1.84.0**, **protobuf 7.36.2**,
  **pydantic 2.14.1**. Dev-only: **pytest 9.1.1** + **pytest-asyncio
  1.4.0**, **ruff 0.17.1**, **testcontainers 4.15.0** (present for parity
  with every other service's dev toolchain; unused by this lane's unit
  tests -- there's no database or broker here to containerize), **grpcio-
  tools 1.84.0** (only used to regenerate `app/grpc_gen/`).
- **No SQLAlchemy, no asyncpg, no Alembic, no aiokafka** -- this gateway
  owns no database and no Kafka topic. Don't add any of them; a write path
  or a persisted cache would contradict "data-less aggregation gateway."

## Commands

```sh
uv sync --group dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8090
uv run ruff check .
uv run pytest
```

See `README.md`'s "Configuration" table for every `*_SERVICE_URL`/
`INVENTORY_GRPC_TARGET`/`MAX_QUERY_*` env var and its default.

## Structure

- `app/main.py` -- FastAPI app factory. Builds `Settings` once, builds the
  schema via `app/schema.py::build_schema(settings)`, mounts
  `strawberry.fastapi.GraphQLRouter` at `/graphql` with a
  `context_getter` that carries `settings` into every resolver's
  `info.context["settings"]`, `/health` (liveness only -- never probes a
  downstream, see its docstring), `/sdl` (the schema as SDL). No lifespan,
  no engine, no background task -- there is nothing to start or stop.
- `app/schema.py` -- the ONLY resolver module. `Query.order` calls
  `fetch_order`; `OrderView.payments`/`OrderView.shipments` and
  `OrderItemView.stock`/`OrderItemView.reviews` are `@strawberry.field`
  resolvers calling the matching `app/clients.py` function. The four
  `_*_from_rest`/`_stock_from_grpc` helpers are the ONLY place REST/gRPC
  JSON shapes get mapped onto Strawberry types -- never construct a
  Strawberry type from a raw dict anywhere else. `build_schema(settings)`
  takes `Settings` as a parameter (not a module-level singleton) so tests
  can construct a schema with a deliberately tiny depth/token budget.
- `app/clients.py` -- `fetch_order`/`fetch_payments`/`fetch_shipments`/
  `fetch_reviews` (httpx, REST) and `fetch_stock` (grpc.aio). Every
  function either returns the downstream's parsed payload or raises
  `DownstreamUnavailable` -- EXCEPT `fetch_order`, which returns `None` on a
  404 (not an error). Resolvers deliberately do NOT catch
  `DownstreamUnavailable` -- see the module docstring for why that's the
  partial-failure contract, not an oversight.
- `app/config.py` -- `Settings.from_env()`, read at call time (same
  convention as every other service's `app/config.py`). Carries the four
  REST base URLs, the inventory gRPC target, both timeouts, and the two
  query-limit knobs (`max_query_depth`, `max_query_tokens`) -- ALL fixed
  operator config, never derived from the incoming request (secure-by-
  design: an aggregation gateway that let a client redirect a downstream
  call, or pick its own depth/complexity budget, would be a trivial SSRF/
  amplification vector).
- `app/grpc_gen/`, `proto/` -- generated gRPC stubs + the `.proto` contract,
  vendored byte-identical from `04-inventory-service/proto/.../inventory.proto`
  (verified with `diff` when this lane was built). Don't hand-edit the
  `.proto` here; if the canonical contract changes, copy the canonical file
  over this one and regenerate (see README.md's "Regenerating the gRPC
  stubs").
- `tests/test_gateway.py` -- all five downstream clients MOCKED
  (`monkeypatch.setattr("app.schema.fetch_*", ...)` -- patch the name
  `app/schema.py` imported, not `app.clients`'s own name, since Python
  binds the import at module-load time). Drives the schema directly via
  `strawberry.Schema.execute(..., context_value={"settings": settings})` --
  no FastAPI `TestClient`, no running server, no live downstream.

## Contract notes (don't "fix" these -- they match the design intent on purpose)

- `order(id:)` for an unknown id returns `data.order: null` with **no**
  `errors[]` -- a missing order is a legitimate answer. Don't change this to
  raise/error; see `app/clients.py::fetch_order`'s docstring.
- Every federated field (`payments`, `shipments`, `stock`, `reviews`) is
  declared `X | None` in `app/schema.py`, never a non-null type -- that
  nullability is what lets a downstream failure null just that one field
  instead of the whole query. If you add a new federated field, declare it
  nullable too, or a downstream outage will null the ENTIRE order instead
  of just the new field (GraphQL non-null propagation bubbles up to the
  nearest nullable ancestor).
- `app/schema.py`'s field resolvers call `app/clients.py` functions and let
  `DownstreamUnavailable` propagate uncaught -- do not wrap these calls in a
  `try/except` that swallows the exception and returns `None` manually;
  that would still null the field correctly but would SILENTLY drop the
  `errors[]` entry, breaking the "never a silent null with no error"
  contract this gateway is built around.
- `build_schema` constructs `QueryDepthLimiter`/`MaxTokensLimiter` via
  factory lambdas (`lambda: QueryDepthLimiter(max_depth=...)`), not bare
  instances -- passing instances directly is deprecated in strawberry-
  graphql 0.335 (an instance would be shared/reused across requests instead
  of freshly constructed per request).
- This gateway is a gRPC CLIENT ONLY (no `@GrpcService`/gRPC server of its
  own) -- unlike `04-inventory-service`, there is no second port to bind.

## Testing

```sh
uv sync --group dev
uv run pytest         # 6 tests, no Docker, no Postgres, no Kafka, no live downstream
uv run ruff check .
```

No Testcontainers-backed integration layer exists in this lane (there's no
database or broker to containerize) -- a LIVE cross-service proof (a real
order-/payment-/shipping-/review-/inventory-service stack standing behind
this gateway) is the later cutover lane's job, not this one; scope here was
strictly `examples/08-graphql-gateway/`.
