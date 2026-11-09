---
title: "Communication Styles & Extraction 6: Order + GraphQL Gateway"
order: 26
part: "Communication & Contracts"
description: "REST, gRPC, async sagas and GraphQL aggregation side by side; the order context extracted last into a CQRS write/read split; the strangler completes, the proxy goes flagless and the monolith is frozen."
duration: 45 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain why order had to be extracted last, and name what `SMELLS.md` marks STRUCK once it leaves.
- Trace what disappeared from `place_order()` (direct calls to payment, shipping and notification) and what remains (a gRPC reservation, persist, an outbox write).
- State what the same-schema `order_view` projection does and does not buy for read-after-write consistency.
- Compare the four communication styles in one system (REST, gRPC, asynchronous sagas, GraphQL aggregation) and the problem each solves.
- Build a data-less Strawberry gateway with lazy, nullable resolvers, and bound its query depth and token count.
- Prove reversibility before the one irreversible step, then convert an equivalence suite into a contract suite with zero assertions changed.

## Why this matters

Every earlier extraction carved one slice off the monolith's `order/services.py` and left the rest standing: review, notification, inventory behind a gRPC seam, payment into a choreographed saga, shipping into an orchestrated one. Each left `place_order()` with one fewer collaborator to reach into. Order moves last because a function that calls four other contexts directly can only be extracted after those four are gone.

What remains is `place_order()`, its four saga reactions and the `Order`/`OrderItem`/`Customer` aggregate they mutate: the god service, and the last of `examples/00-monolith/SMELLS.md`'s two oldest entries still open. The extraction lands on `examples/07-order-service`, a CQRS write/read split. `examples/08-graphql-gateway` adds a data-less aggregation layer over five services. Then the monolith is turned off. The runs cited below are recorded in `tooling/newman/GOLDEN-BASELINE.md`.

## What closes when order leaves

`SMELLS.md` has two entries on the same function.

- **Smell #1, the god checkout service.** `place_order()` reached directly into inventory, payment, shipping and notification's services and models. It is struck because `07-order-service/app/service.py::place_order` reaches inventory only through a versioned gRPC contract (`AsyncInventoryClient`) and never touches payment, shipping or notification code or tables. Those contexts react to events order-service produces and consumes.
- **Smell #2, one in-process ACID transaction across six contexts.** A single `transaction.atomic()` wrapped the order row, the reservation, the charge, the dispatch and the outbox write, so any failure rolled everything back without any code. It is struck because the one remaining local transaction spans only order-service's own `order_svc` schema (the order row, the `order_view` projection and the outbox row). Every cross-context guarantee left is a saga with an explicit, tested compensation, not an implicit rollback a shared database used to provide.

## Pattern: CQRS

The command side sits beside the `order_view` read model, which is projected inside the same transaction as every aggregate write. The `place_order` body is what remains of the monolith's version:

```python
# app/service.py -- place_order: reserve outside any local tx,
# then persist the aggregate + order_view + outbox in ONE transaction
async def place_order(session_factory, *, inventory_grpc_target,
                       grpc_timeout_s, customer_id, items,
                       payment_method, shipping_address):
    customer = await repository.get_customer_by_id(session, customer_id)
    line_snapshots, reserved = await _reserve_lines_remote(
        inventory_grpc_target, grpc_timeout_s, items
    )
    try:
        order = await repository.create_order_with_outbox_and_view(
            session, customer=customer, items=line_snapshots,
            shipping_address=shipping_address, payment_method=payment_method,
            created_at=datetime.now(UTC),
        )
        return order
    except Exception:
        await _release_reserved(inventory_grpc_target, grpc_timeout_s, reserved)
        raise
```

The customer is validated against the service's own `customers` table, a forward-filled copy seeded at migration, never a live lookup into the monolith's schema. Every line is reserved over gRPC before any local transaction opens, because a remote `Reserve` cannot be rolled back by this process's Postgres. The method stops at `PENDING` with an `order.placed` outbox row, and `POST /api/orders` returns `202 Accepted`, never `201`: confirmation happens later, off four saga reactions on the same four topics the monolith's `order_saga_listener.py` consumed.

| Event | Transition |
|---|---|
| `payment.captured` | `PENDING` to `AWAITING_SHIPMENT` |
| `payment.declined` | Release every reserved line; `PAYMENT_DECLINED` |
| `shipment.dispatched` | `AWAITING_SHIPMENT` to `CONFIRMED` |
| `shipment.failed` | Release; `SHIPPING_FAILED` |

Each reaction is idempotent through the atomic conditional `UPDATE` that `order_view`'s consistency rests on: a redelivered event for an order that already left its expected status is a no-op. One gap is stated in the docstrings rather than papered over. A payment that captures and then hits `shipment.failed` is not refunded by `handle_shipment_failed`, which only releases inventory and transitions the order. `05-payment-service`'s own `shipment.failed` consumer (`app/refund_consumer.py`) refunds it, reacting to the same event. No shared transaction and no central orchestrator decides both outcomes; each service owns the compensation for the event it receives.

## Four communication styles, one system

{% include excalidraw.html file="rest-grpc-graphql-protocol-fit" alt="REST, gRPC and GraphQL side by side, each labeled with the seam it was chosen for: REST request/reply for each service's own surface, gRPC for the inventory reservation hot path, GraphQL bounded aggregation for the gateway's one query" caption="Figure 26.1: Three protocols, three different problems, used side by side in one system" %}

| Style | Use it when | Where it sits here |
|---|---|---|
| REST | A caller waits for an answer, usually a user | Every service's own front door, including the two new ones |
| gRPC | The caller cannot proceed without the answer and a typed, versioned wire contract matters more than a readable payload | Inventory's `Reserve`/`Release`/`GetStock`, called by `AsyncInventoryClient` over the same proto the monolith used, re-authored async |
| Asynchronous events | Independent reactions with no caller waiting | Every saga: payment's choreography has no coordinator, shipping's orchestration names its own steps, and order-service's four reactions are choreography again |
| GraphQL aggregation | One client needs one order plus its payments, shipments, live stock and reviews in a single round trip | The gateway's `order(id)` query |

## The data-less aggregation gateway

`examples/08-graphql-gateway` owns no data and sits on its own front door, `:8090`, not behind the strangler proxy. `order(id)` federates five sources: order-service over REST for the order, payment-service and shipping-service over REST for payments and shipments, review-service over REST for each item's reviews by sku, and inventory-service over gRPC for each item's live stock. `app/schema.py` is the only resolver module. Every field below the order's own read-model fields is a separate federated fetch, resolved lazily only when the client's selection set asks for it.

```python
# app/schema.py -- lazy, per-item federated resolvers
@strawberry.type
class OrderItemView:
    sku: str
    quantity: int
    unit_price_cents: int

    @strawberry.field
    async def stock(self, info: strawberry.Info) -> StockView | None:
        settings = info.context["settings"]
        data = await fetch_stock(settings, self.sku)      # inventory, gRPC
        return _stock_from_grpc(data)

    @strawberry.field
    async def reviews(self, info: strawberry.Info) -> list[ReviewView] | None:
        settings = info.context["settings"]
        rows = await fetch_reviews(settings, self.sku)     # review-service, REST
        return [_review_from_rest(row) for row in rows]
```

Every federated field is optional (`X | None`), and that nullability is the partial-failure contract. `app/clients.py`'s `fetch_*` functions raise `DownstreamUnavailable` on a failed REST call or a broken gRPC channel, and the resolver does not catch it. Strawberry's null propagation nulls just that field and appends an entry to the top-level `errors[]`; siblings still resolve and the query never becomes a 500. Catching the exception and returning `None` would null the field but silently drop the `errors[]` entry.

An unknown order id goes the opposite way: a 404 from order-service becomes `data.order: null` with no `errors[]` entry, because a missing order is a legitimate answer and a client must tell it apart from a downstream failure.

{% include excalidraw.html file="graphql-gateway-five-source-fanout" alt="One order(id) query fanning out to five sources: order-service REST for the order, payment-service and shipping-service REST for payments and shipments, inventory-service gRPC for per-item stock, review-service REST for per-item reviews, each field lazy and nullable" caption="Figure 26.2: One query, five sources, no data owned locally: partial failure is a null field, never a crashed request" %}

A layer that fans one request out to five backends can turn one hostile request into five times the load, or a deeply nested query into a combinatorial explosion. `app/schema.py::build_schema` wires `QueryDepthLimiter` and `MaxTokensLimiter` from operator-configured budgets (`Settings.max_query_depth` and `max_query_tokens` in `app/config.py`), and every downstream target (four REST base URLs, the inventory gRPC target) is fixed configuration that no request can influence.

The contract query in `tooling/newman/mea.postman_collection.json` was written and left inert before the gateway existed, and it guessed a wrong schema. It asked for `stock { quantityOnHand }`; the real field on `StockView` is `onHandQty`. It asked for a top-level `order.reviews`; the schema federates reviews per item, because a review is posted against a sku. Run against the live gateway, it produced `data.order: null` with two `errors[]` entries naming both unknown fields, not a silent wrong answer. The fix corrects the query to `items { sku stock { onHandQty } reviews { rating } } }`, rewrites the assertions to the per-item shape and adds an explicit "no GraphQL errors" assertion so schema drift fails loudly instead of as a `TypeError` deeper in the script. A staged query that was never executed was syntactically valid and wrong for a whole lane.

## Pattern: Strangler Fig, completed

Every earlier cutover left at least one `STRANGLER_*_ENABLED` flag live and a path back to the monolith. This one removes the monolith as an option, in two steps, because the second cannot be undone.

**Step A** adds `STRANGLER_ORDER_ENABLED` and re-points `06-shipping-service`'s enrich call from the monolith to order-service's `order_view`, then proves reversibility before anything irreversible.

| Configuration | Requests | Assertions | Failed | Notes |
|---|---|---|---|---|
| Flag on, full extracted topology, no monolith process | 44 | 117 | 0 | `O1` returns `202 Accepted`; a poll sees a real order reach `CONFIRMED` through the Kafka saga on attempt 4/20 |
| No `STRANGLER_*` flags, extracted services stopped, bare monolith | 33 | 105 | 0 | `O1` returns `201 Created` |

Both runs used the same unedited suite and exited 0. This is the last reversible proof in the strangler's history: turning the flag off was still a config change and a restart.

**Step B** has no flag to flip back. `examples/01-strangler-proxy/app/config.py` and `app/main.py` were rewritten: every `*_enabled` boolean and the `monolith_base_url` fallback are gone from `Settings`, and `_select_backend()` is an unconditional six-way lookup that returns `None` for any path matching none, which `proxy_handler` turns into a real `404`.

```python
# app/main.py -- flagless: no monolith fallback left
def _select_backend(settings: Settings, path: str) -> str | None:
    if path.startswith("/api/reviews"):
        return settings.review_base_url
    if path.startswith("/api/notifications"):
        return settings.notification_base_url
    if path.startswith("/api/inventory"):
        return settings.inventory_base_url
    if path.startswith("/api/payments"):
        return settings.payment_base_url
    if path.startswith("/api/shipments"):
        return settings.shipping_base_url
    if path.startswith("/api/orders"):
        return settings.order_base_url
    return None
```

`tests/test_routing.py` was rewritten for this shape: all twelve path variants route to their one owning backend, near-miss prefixes such as `/api/order` do not match `/api/orders` and get a `404`, and each of six backends being down yields a `502` scoped to that backend. Result: 29/29 green, `ruff check` clean. The monolith is frozen, not deleted. `examples/00-monolith/README.md` and `AGENTS.md` carry a "FROZEN STATUS" section recording that it stays in the repo as the golden-baseline referent and a break-glass fallback, while `compose.yaml`, `scripts/` and `demos/` no longer start it or its background processes.

{% include excalidraw.html file="final-monolith-free-topology" alt="The end-state topology: six independently deployable services plus the GraphQL gateway behind one flagless edge router with no monolith fallback, and the monolith frozen and unwired" caption="Figure 26.3: The final topology: six services and a GraphQL gateway behind one flagless router, the monolith frozen and unwired" %}

## From equivalence to contract

Until now the equivalence runs asserted that the extracted service behaves like the monolith, which needs a monolith to compare against. After Step B there is none. `tooling/newman/proxy.postman_environment.json` points at the flagless edge (`:8888`) with every context's contract flag permanently on, and the question becomes whether the live system satisfies its own contract. Against the full mesh (Postgres, Kafka, six extracted services, the gateway, the flagless proxy, no monolith process) the runs were green repeatedly: 50 requests / 133 assertions, 0 failed, twice before the negative checks, and 45 requests / 128 assertions, 0 failed, twice after them. The second pair is the stronger evidence, because each followed a real service restart.

Three negative checks keep a green suite from being one that would pass regardless.

| Intervention | Result | After restoring |
|---|---|---|
| Consumer-down: kill `order-service`, both its `/api/orders*` surface and its Kafka consumer group for the four saga-outcome topics | 59 of 111 assertions failed, exit 1 | 0 failed, exit 0 |
| Compensation-disabled: comment out `await _release_order_lines(...)` in `handle_payment_declined` | 1 of 30 failed; stock short by one unit after a declined checkout, `expected 81 to deeply equal 82` | 0 failed |
| Projection-disabled: comment out `order_view`'s upsert inside a status transition | 1 of 53 failed; `GET /api/orders/{id}` stuck at `PENDING` for the full bounded-wait budget while the aggregate reached `CONFIRMED` | 0 failed |

Each was a temporary single-line comment-out, confirmed restored by a clean `ruff check` and the stable runs above. No assertion or negative check changed in the conversion: the claim moved from "matches the monolith" to "satisfies its own contract" because there is nothing left to match, not because the bar moved.

> **ADLC in Action**
>
> The order of the work was settled in planning, before any code. Step A had to prove the extracted order-service and the re-pointed shipping enrichment worked before Step B's decommission, because once the monolith's order context is deleted nothing is left to revert to. The 44/117 and 33/105 numbers are that proof, captured before Step B by design. The negative checks ran after the stability runs so the later green runs (45/128, twice) show recovery from a real intervention, not a suite that was never disturbed. The one real bug in this lane, the GraphQL query that guessed a schema, surfaced because verification ran a previously staged, never-executed query against a live gateway instead of trusting that "it parses" meant "it's correct."

> **Decision**
>
> Extract the god service last, after every context it calls. Choose the protocol by the problem: REST for a waiting caller, gRPC for a hot path that needs a typed answer, events for independent reactions, GraphQL for one client query across services. Prove reversibility before the irreversible step, and freeze the old system instead of deleting it.

> **🤖 Explore with your agent**
>
> "In examples/08-graphql-gateway, add a field to OrderItemView that fetches one more value from review-service or inventory-service as a lazy, nullable resolver that lets DownstreamUnavailable propagate, then show the query returns a null field plus an errors[] entry when that service is stopped, and that a query deeper than Settings.max_query_depth is rejected."
>
> Check: run the gateway tests, then query `order(id)` on :8090 with review-service stopped and confirm `data.order` is present, the new field is null and `errors[]` has an entry for each nulled field.

## Build, run, observe

`demos/demo-final-topology.sh` brings up the whole monolith-free topology from scratch in throwaway Postgres and Kafka containers, migrates every schema, starts all seven services and the flagless proxy, runs the full contract suite and tears everything down. It was verified standalone at 50 requests / 133 assertions, 0 failed, exit 0, with a clean teardown. The only Django command it runs is a one-shot `manage.py migrate && manage.py seed`; `examples/00-monolith` is never started as a live process.

- **Stop `order-service` mid-run:** the run fails 59 of 111 assertions; restart it and the run returns to 0 failed.
- **Comment out the release call in `handle_payment_declined`:** stock ends one unit short after a declined checkout.
- **Comment out the `order_view` upsert in a status transition:** the order read stays `PENDING` while the aggregate reaches `CONFIRMED`.
