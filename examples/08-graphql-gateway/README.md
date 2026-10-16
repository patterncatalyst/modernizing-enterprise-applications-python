# graphql-gateway

**The GRAPHQL-GATEWAY lane of r07 (the finale) -- a new, additive, data-less
Strawberry GraphQL aggregation gateway.** Adapted from the house Strawberry
aggregation style in
`~/Dev/datamesh-reference-arch-python/examples/lgtm-datamesh/services/graphql-gateway`
and the role played by the Java/Quarkus sibling,
`~/Dev/modernizing-enterprise-applications/examples/08-graphql-gateway`
(SmallRye GraphQL) -- re-authored on Strawberry, not ported line-for-line.

**This module owns no data.** It answers one GraphQL query by federating
reads from `07-order-service` (REST), `05-payment-service` (REST),
`06-shipping-service` (REST), `02-review-service` (REST), and
`04-inventory-service` (gRPC `GetStock`) -- each field is resolved by calling
the service that owns it, the same protocol that service's other consumers
use. It sits ALONGSIDE every other service's own REST surface and the
strangler proxy (`01-strangler-proxy`), never replacing or routing through
either -- its own front door, port **`8090`**.

- `type Query { order(id: ID!): OrderView }` -- `OrderView` carries the
  order read-model fields (`id`, `customerId`, `status`, `totalCents`,
  `createdAt`, `shippingAddress`) plus `items: [OrderItemView!]!`,
  `payments: [PaymentView!]`, `shipments: [ShipmentView!]`. Each
  `OrderItemView` carries its own `stock: StockView` (inventory-service,
  gRPC `GetStock`) and `reviews: [ReviewView!]` (review-service, REST, by
  sku).
- `app/schema.py` is the only resolver module: `Query.order` calls
  `app/clients.py::fetch_order`; `payments`/`shipments` are field resolvers
  on `OrderView`; `stock`/`reviews` are field resolvers on `OrderItemView`.
  Every federated fetch is lazy -- it only runs if a client's selection set
  actually asks for that field.
- **Unknown-id handling:** `order(id:)` for an id order-service 404s on
  returns a plain `null` -- `data.order: null` with **no** `errors[]` entry.
  A missing order is a legitimate answer, not a downstream failure.
- **Partial-failure handling:** every federated field below the order's own
  read-model fields (`payments`, `shipments`, `stock`, `reviews`) is
  declared **nullable**. A downstream REST/gRPC failure raises
  `app/clients.py::DownstreamUnavailable`, left uncaught by the resolver on
  purpose -- Strawberry/graphql-core's own null-propagation then nulls
  *just* that field and appends an entry to the response's top-level
  `errors[]`. Siblings still resolve. The whole query never crashes into a
  500.
- **Secure-by-design:** query depth and total token count are bounded
  (`strawberry.extensions.QueryDepthLimiter` + `MaxTokensLimiter`, wired in
  `app/schema.py::build_schema` from `app/config.py::Settings`) so the
  aggregation can't be turned into a request-controlled amplification
  vector, and every downstream target (the four REST base URLs, the
  inventory gRPC target) is FIXED operator config -- never derived from the
  incoming GraphQL request.
- `proto/` carries a byte-identical copy of inventory-service's
  `.proto` (the same `GetStock` RPC `07-order-service`'s
  `AsyncInventoryClient` dials), vendored and regenerated the same way
  `07-order-service` vendors its own copy (see "Regenerating the gRPC
  stubs" below).

## Endpoints

| Method | Path       | Notes                                            |
|--------|------------|---------------------------------------------------|
| POST   | `/graphql` | The aggregation query; GraphiQL UI when opened in a browser. |
| GET    | `/sdl`     | The generated schema as SDL -- the discovery contract. |
| GET    | `/health`  | Liveness only -- never probes a downstream (see `app/main.py`). |

## Configuration

Every downstream target is overridable via env (`app/config.py::Settings.from_env`):

| Env var                 | Default                  |
|--------------------------|---------------------------|
| `HTTP_PORT`              | `8090`                    |
| `ORDER_SERVICE_URL`      | `http://localhost:8088`   |
| `PAYMENT_SERVICE_URL`    | `http://localhost:8085`   |
| `SHIPPING_SERVICE_URL`   | `http://localhost:8087`   |
| `REVIEW_SERVICE_URL`     | `http://localhost:8001`   |
| `INVENTORY_GRPC_TARGET`  | `localhost:9004`          |
| `REST_TIMEOUT_S`         | `5.0`                     |
| `GRPC_TIMEOUT_S`         | `3.0`                     |
| `MAX_QUERY_DEPTH`        | `10`                      |
| `MAX_QUERY_TOKENS`       | `1000`                    |

## Commands

```sh
uv sync --group dev

uv run uvicorn app.main:app --host 0.0.0.0 --port 8090
uv run ruff check .
uv run pytest
```

No `DATABASE_URL`, no Alembic, no migrations -- this gateway owns no
database.

## Regenerating the gRPC stubs

```sh
cd examples/08-graphql-gateway
uv run python -m grpc_tools.protoc \
  -I proto/dev/patterncatalyst/inventory/v1 \
  --python_out=app/grpc_gen --grpc_python_out=app/grpc_gen \
  proto/dev/patterncatalyst/inventory/v1/inventory.proto
# then re-apply the import-path fixup scripts/gen-proto.sh documents:
sed -i \
  -e 's/^import inventory_pb2 as inventory__pb2$/from . import inventory_pb2 as inventory__pb2/' \
  app/grpc_gen/inventory_pb2_grpc.py
```

`proto/dev/patterncatalyst/inventory/v1/inventory.proto` is byte-identical
to `04-inventory-service/proto/.../inventory.proto` (verified with `diff` at
build time) -- don't hand-edit it; if the canonical contract changes, copy
it over this one and regenerate.

## Testing

`tests/test_gateway.py` mocks all five downstream clients
(`app/clients.py::fetch_order`/`fetch_payments`/`fetch_shipments`/
`fetch_reviews`/`fetch_stock`, monkeypatched at `app.schema`'s import
site) and drives `app/schema.py`'s schema directly via
`strawberry.Schema.execute` -- no running server, no live downstream:

- `test_order_stitches_all_five_sources` -- the full aggregation shape,
  field-for-field, across all five services.
- `test_downstream_failure_nulls_only_that_field` /
  `test_downstream_grpc_failure_nulls_only_stock_field` -- one failing
  downstream (REST, then gRPC) nulls only its own field; siblings still
  resolve, `errors[]` is populated, never a 500.
- `test_unknown_order_id_returns_null` -- a 404 from order-service is a
  plain `null`, no `errors[]`.
- `test_depth_bomb_rejected_by_depth_limiter` /
  `test_token_bomb_rejected_by_max_tokens_limiter` -- proves the depth and
  token budgets are actually wired and active, under a deliberately tiny
  test-only budget.

Live cross-service proof (a real order-service/payment-service/.../
inventory-service stack behind this gateway) is the later cutover lane's
job, not this one.
