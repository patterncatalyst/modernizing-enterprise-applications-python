# graphql-gateway -- Migration Notes (data-less aggregation rationale)

This lane has no monolith original and no two-phase (A -> B) migration in the
sense every prior extraction's `MIGRATION.md` documents. There is nothing to
"lift": `02-review-service`, `04-inventory-service`, `05-payment-service`,
`06-shipping-service`, and `07-order-service` already each own their slice of
the domain as an independently deployable service, each with its own REST (or
gRPC) read surface. This module is **net-new, additive infrastructure** that
sits on top of all five -- a single GraphQL endpoint that lets a client ask
one question ("give me order 42, its payments, its shipments, and the live
stock + reviews for every line item") instead of five separate HTTP/gRPC
calls fanned out client-side.

## Why data-less

The gateway owns no database, runs no migration, and holds no write path on
purpose:

- **Single source of truth stays put.** Every field this gateway serves is
  already owned by exactly one extracted service. Caching or re-persisting
  any of it here would create a second copy that can drift from the owner's
  own data -- the same "owned schema, no shared tables" discipline every
  prior extraction enforced, just applied to a read-aggregation layer
  instead of a write-owning one.
- **No migration to run, no schema to version.** A stateless FastAPI process
  with a Strawberry schema has nothing for Alembic to manage -- `uv sync &&
  uvicorn app.main:app` is the entire startup sequence (see
  `Containerfile`'s `CMD`, which runs no migration step, unlike every other
  service in this project).
- **Failure isolation is structural, not incidental.** Because every
  federated field is resolved independently (REST or gRPC, per-field,
  lazily), a slow or down downstream can only ever cost that ONE field --
  never corrupt or block a cached aggregate this gateway might otherwise be
  tempted to maintain.

## Why Strawberry, not a port of the Java sibling's SmallRye GraphQL

The Java sibling
(`~/Dev/modernizing-enterprise-applications/examples/08-graphql-gateway`)
plays the identical architectural role -- a `GatewayApi` MicroProfile GraphQL
class with `@Source` field resolvers over four REST clients and one gRPC
client -- but this lane is its own independent implementation on Strawberry,
the code-first GraphQL library this project's Python side already uses as
its house style (see
`~/Dev/datamesh-reference-arch-python/examples/lgtm-datamesh/services/graphql-gateway`).
The resolver SHAPE is the same across both languages (a thin stitching layer,
one query, lazy per-field federation); the depth/complexity-limiting MECHANISM
differs by necessity -- `smallrye.graphql.instrumentation.queryDepth`/
`queryComplexity` config properties on the Java side, versus Strawberry's
`QueryDepthLimiter`/`MaxTokensLimiter` schema extensions here
(`app/schema.py::build_schema`) -- but both enforce the same secure-by-design
intent: an aggregation gateway's depth/complexity budget is FIXED operator
config, never influenced by request content.

## Protocol parity with the services being federated

Every federated field is resolved over the SAME protocol that service's other
consumers already use -- never a new, gateway-only protocol:

| Field                      | Owning service       | Protocol | Same seam as                                   |
|----------------------------|-----------------------|----------|--------------------------------------------------|
| `OrderView` (base fields)  | `07-order-service`    | REST     | `GET /api/orders/{id}`                           |
| `OrderView.payments`       | `05-payment-service`  | REST     | `GET /api/payments?orderId=`                     |
| `OrderView.shipments`      | `06-shipping-service` | REST     | `GET /api/shipments?orderId=`                    |
| `OrderItemView.reviews`    | `02-review-service`   | REST     | `GET /api/reviews?sku=`                          |
| `OrderItemView.stock`      | `04-inventory-service`| gRPC     | `GetStock`, the same read-only RPC `07-order-service`'s `AsyncInventoryClient.get_stock` dials |

The inventory `.proto` contract (`proto/dev/patterncatalyst/inventory/v1/inventory.proto`)
is vendored byte-identical from `04-inventory-service`'s canonical copy, the
same vendoring convention `07-order-service` already established for itself
as a gRPC *client* of inventory-service.

## Verification

- `uv sync --group dev`: resolves cleanly on Python 3.14 -- 48 packages,
  `strawberry-graphql==0.335.0` (current stable at build time) included with
  no dependency conflicts.
- `uv run python -m grpc_tools.protoc ...` + the `inventory_pb2_grpc.py`
  import-path fixup: generates `app/grpc_gen/inventory_pb2.py` and
  `inventory_pb2_grpc.py` cleanly; `inventory_pb2_grpc.InventoryGrpcServiceStub`
  and `GetStock` import and construct without error.
- `uv run pytest`: **6 passed** --
  `test_order_stitches_all_five_sources` (the full aggregation shape across
  all five services), `test_downstream_failure_nulls_only_that_field` +
  `test_downstream_grpc_failure_nulls_only_stock_field` (one failing REST or
  gRPC downstream nulls only its own field, `errors[]` populated, siblings
  still resolve, never a 500), `test_unknown_order_id_returns_null` (a 404
  from order-service is a plain `null`, no `errors[]`), and
  `test_depth_bomb_rejected_by_depth_limiter` +
  `test_token_bomb_rejected_by_max_tokens_limiter` (both query-amplification
  budgets are actually wired and reject a query before any resolver runs).
- `uv run ruff check .`: **All checks passed.**
- `schema.as_str()` / `GET /sdl`: confirmed to emit a correctly camelCased
  SDL (`totalCents`, `customerId`, `unitPriceCents`, ...) matching every REST
  service's own wire contract.
- `GET /health` and `POST /graphql` confirmed live via `fastapi.testclient.TestClient`
  against the real `app.main.app` (not just `schema.execute` in isolation):
  both return `200`; a `/graphql` query against a nonexistent order-service
  (nothing listening on `:8088` in this sandbox) came back as
  `{"data": {"order": null}, "errors": [{"message": "order-service
  unavailable: ...", "path": ["order"]}]}` -- the partial-failure contract
  holds end-to-end through the real ASGI app, not only in the mocked unit
  tests.
- Containerfile: `docker build -f Containerfile -t mea-graphql-gateway:r07 .`
  -- builds successfully (UBI 10 multi-stage, non-root, same pattern as
  `05-payment-service`/`06-shipping-service`/`07-order-service`'s
  Containerfiles, with the migration step removed since this gateway owns
  no database). The built image was then run LIVE: `docker run -p
  18090:8090 mea-graphql-gateway:r07` -> `GET /health` -> `200
  {"status":"ok","service":"graphql-gateway"}`; `GET /sdl` -> `200` with the
  expected camelCased SDL.
- Live cross-service proof (a real order-/payment-/shipping-/review-/
  inventory-service stack standing behind this gateway, confirming the
  aggregation against REAL data end-to-end) is explicitly out of scope for
  this lane -- it belongs to the later cutover lane that stands up the full
  r07 stack together.
