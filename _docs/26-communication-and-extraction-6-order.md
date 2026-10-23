---
title: "Communication Styles & Extraction 6: Order + GraphQL Gateway"
order: 26
part: "Communication & Contracts"
description: "REST, gRPC, async sagas, and GraphQL (Strawberry) aggregation side by side; the god order context extracted last into a CQRS write/read split; the strangler completes, the proxy goes flagless, and the monolith is decommissioned."
duration: 45 minutes
---

Every extraction before this one carved a single slice off the monolith's
`order/services.py` and left the rest of it standing. ch.15 removed review.
ch.17 removed notification. ch.19 removed inventory behind a gRPC seam.
ch.23 removed payment into a choreographed saga. ch.24 removed shipping into
an orchestrated one. Each extraction left `place_order()` with one fewer
collaborator to reach into, by design, because order was always going to
move last: the only way to extract a function that calls four other
contexts directly is to remove the four other contexts first. What's left
standing at the start of this chapter is `place_order()` itself, its four
saga reactions, and the `Order`/`OrderItem`/`Customer` aggregate they
mutate: this project's own god service, and the last of
`examples/00-monolith/SMELLS.md`'s two oldest, longest-lived entries still
open. This chapter extracts that core onto `examples/07-order-service`, a
CQRS write/read split built from day one (ch.21 already walked through its
read side in full); adds `examples/08-graphql-gateway`, a data-less
Strawberry aggregation layer stitching five services into one query; and
then does what no prior chapter could: it turns off the monolith for good.
Every artifact cited below is running code already committed to this
repository, exercised end to end in `tooling/newman/GOLDEN-BASELINE.md`.

## Why order had to go last, and what closes when it does

`SMELLS.md` names two entries on the same function, and both required every
other context to leave first before either could be struck. **Smell #1**,
the god checkout service: `place_order()` reached directly into inventory,
payment, shipping, and notification's services and models instead of
treating them as independently deployable collaborators reached over a
stable contract. **Smell #2**, one in-process ACID transaction spanning six
contexts: a single `transaction.atomic()` wrapped the order row, the
inventory reservation, the payment charge, the shipping dispatch, and the
outbox write, so a failure anywhere rolled back everything, everywhere, for
free, a guarantee ch.22 already named the cost of once payment and
shipping had their own databases to commit to. Both rows in `SMELLS.md` are
now marked **STRUCK**, and the evidence for each is specific rather
than declarative: smell #1 is struck because `07-order-service/app/
service.py::place_order` reaches inventory only through a versioned gRPC
contract (`AsyncInventoryClient`, unchanged since ch.19) and never touches
payment, shipping, or notification's code or tables at all: those three
contexts react to events order-service produces and consumes, not to direct
calls from one orchestrating function. Smell #2 is struck because the one
remaining local transaction `07-order-service` runs spans only its own
`order_svc` schema (the order row, the `order_view` projection, and the
outbox row), and every cross-context consistency guarantee left in the
system is a saga with an explicit, tested compensation, never an implicit
rollback a shared database used to provide as a side effect.

## The CQRS write model, recapped from the read side ch.21 already proved

ch.21 built the case for `order_view` as this book's clearest CQRS example:
a read model projected inside the same transaction as every aggregate
write, proven to do real work by a negative test that disables the projection
and watches the read go stale while the write moves on. This chapter's job
is the command side that read model sits beside, and the four reactions
that drive the aggregate through its lifecycle, all of it lifted from the
monolith's own choreographed-payment, orchestrated-shipping flavor, in
shape unchanged:

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

`place_order` validates the customer against this service's own, owned
`customers` table (a forward-filled copy seeded at migration time, never a
live lookup against the monolith's shared schema), reserves every line over
gRPC before any local transaction opens (the same reserve-outside-the-tx
discipline ch.19 established, because a remote `Reserve` cannot be rolled
back by this process's Postgres), and stops at `PENDING` with an
`order.placed` outbox row. There is no synchronous confirm path in this
service at all: `POST /api/orders` returns `202 Accepted`, never `201`,
because there is nothing left to confirm in the same request: confirmation
happens later, off four saga reactions consuming the same four topics
`00-monolith/order/management/commands/order_saga_listener.py` always did:
`payment.captured` advances `PENDING → AWAITING_SHIPMENT`; `payment.
declined` releases every reserved line and transitions to `PAYMENT_
DECLINED`; `shipment.dispatched` advances `AWAITING_SHIPMENT → CONFIRMED`;
`shipment.failed` releases and transitions to `SHIPPING_FAILED`. Each
reaction is idempotent via the same atomic conditional `UPDATE` ch.21 built
`order_view`'s consistency on top of: a redelivered event for an order
that already left its expected status is a safe no-op, proven directly by
this service's own test suite rather than assumed from the shape of the
code. The one gap this chapter's docstrings refuse to paper over: a payment
that captures and then hits `shipment.failed` is **not** refunded by
`handle_shipment_failed` itself; that function only releases inventory and
transitions the order; it is refunded independently by `05-payment-
service`'s own `shipment.failed` consumer (`app/refund_consumer.py`),
reacting to the exact same event this service reacts to. No
shared transaction, no central orchestrator deciding both outcomes: each
service owns its own compensation for the event it both receives.

## Four communication styles, one system

Part 8 steps back from any single extraction to ask how services should
talk to each other at all, and this chapter is where every style this book
has used ends up standing side by side in one running topology, each
solving a problem the other three don't.

{% include excalidraw.html file="rest-grpc-graphql-protocol-fit" alt="REST, gRPC, and GraphQL side by side, each labeled with the real seam this project chose it for: REST's request/reply for every service's own surface, gRPC's strongly-typed hot path for order-service's inventory reservation, GraphQL's bounded aggregation for the gateway's one query" caption="Figure 26.1: Three protocols, three different problems, used side by side in one system" %}

**REST** is the contract between a client and any one service's own
read/write surface, every `GET`/`POST` this book has built from the start, a
request/reply exchange where the caller waits for an answer before moving
on. It fits anything a user is directly waiting on, and it is what every
service in this project, including the two new ones this chapter adds,
exposes as its own front door. **gRPC** is the choice this book made for
exactly one seam: inventory's reservation calls, where checkout cannot
proceed without knowing stock was actually decremented, and a strongly
typed, versioned wire contract matters more than a human-readable payload.
`07-order-service/app/inventory_client.py::AsyncInventoryClient` calls the
identical `Reserve`/`Release`/`GetStock` RPCs the monolith always did, over
the same proto, re-authored async for FastAPI's event loop; the seam
doesn't change just because the caller moved services. **Asynchronous
events** are the backbone of every saga in this book: ch.23's choreography
has no coordinator, just independent reactions wired by topic name; ch.24's
orchestration has one explicit coordinator that names its own steps; this
chapter's four lifted reactions are choreography again, now running inside
order-service rather than the monolith. None of the first three styles fit
a fourth problem this chapter introduces: a client that wants one order's
data plus its payments, its shipments, its line items' live stock, and
their reviews, in one round trip, without calling five endpoints and
stitching the responses by hand. That is what GraphQL aggregation is for,
and it is the one style this book has not used until now.

## The data-less aggregation gateway

`examples/08-graphql-gateway` owns no data of its own and sits alongside
every other service's REST surface on its own front door, `:8090`, never
routed through the strangler proxy. It answers one query, `order(id)`, by
federating five sources: order-service over REST for the order itself,
payment-service and shipping-service over REST for payments and shipments,
review-service over REST for each line item's reviews by sku, and
inventory-service over gRPC for each line item's live stock. `app/
schema.py` is the only resolver module, and its own header comment states
the contract directly: every field below the order's own read-model fields
is a **separate federated fetch, resolved lazily** only when a client's
selection set actually asks for it.

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

Every one of those federated fields is typed as optional (`X | None`), and
that nullability is the whole partial-failure contract: `app/clients.py`'s
`fetch_*` functions raise `DownstreamUnavailable` on a failed REST call or a
broken gRPC channel, and the resolver above, by design, does **not** catch
it. Strawberry's own null-propagation then nulls *just* that field and
appends an entry to the response's top-level `errors[]` array; siblings
still resolve, and the whole query never crashes into a 500. Swallowing the
exception and returning `None` by hand would still null the field
correctly but would silently drop the `errors[]` entry, which is why the
module's own docstring calls out leaving it uncaught as deliberate, not an
oversight. An unknown order id is handled the opposite way, by design: a
404 from order-service maps to a plain `data.order: null` with **no**
`errors[]` entry, because a missing order is a legitimate answer, not a
downstream failure: a client needs to tell the two cases apart, and the
gateway's job is to keep that distinction intact rather than flattening
both into the same shape.

{% include excalidraw.html file="graphql-gateway-five-source-fanout" alt="One order(id) query fanning out to five sources: order-service REST for the order itself, payment-service and shipping-service REST for payments and shipments, inventory-service gRPC for per-item stock, and review-service REST for per-item reviews, each field resolved lazily and nullable" caption="Figure 26.2: One query, five sources, no data owned locally: partial failure is a null field, never a crashed request" %}

An aggregation layer that fans one request out across five backends is
also a layer that could turn a single hostile request into five times the
load, or a query nested deep enough to explode combinatorially across
joins a client never has to see, so `app/schema.py::build_schema` wires
`QueryDepthLimiter` and `MaxTokensLimiter` from fixed, operator-configured
budgets (`app/config.py::Settings.max_query_depth`/`max_query_tokens`), and
every downstream target, the four REST base URLs, the inventory gRPC
target, is equally fixed configuration, never a value the incoming
request can influence. `tests/test_gateway.py`'s depth-bomb and token-bomb
tests prove the bound is actually wired, under a tiny, test-only
test-only budget, rather than resting on the configuration file alone.

## An integration bug, found only once the query ran against a live gateway

The GraphQL contract item in `tooling/newman/mea.postman_collection.json`
was authored in an earlier lane, staged and inert, before
`08-graphql-gateway` existed at all, and it guessed a schema shape that
turned out wrong the moment a live gateway stood behind it. The staged
query asked for `stock { quantityOnHand }`; the real field, defined on
`StockView` in `app/schema.py`, is `onHandQty`. The staged query also asked
for a top-level `order.reviews`; the real schema federates reviews
**per item** (`OrderItemView.reviews`), because a review is posted against
a sku, not an order as a whole. Running the untouched staged query against
the live gateway produced exactly the failure a schema mismatch should
produce: `data.order: null` with two `errors[]` entries naming both
unknown fields, not a silent wrong answer. The fix was narrow: correct the
query to `items { sku stock { onHandQty } reviews { rating } } }`, rewrite
the assertions to match the real, per-item-nested shape, and add an
explicit "no GraphQL errors" assertion so a future schema drift fails loudly
instead of producing a confusing `TypeError` deeper in the test script. This
is the kind of bug an equivalence suite exists to catch precisely because
it was written against an assumption rather than a running system, and it
is also the clearest argument in this chapter for why "STAGED, inert" items
belong in a collection at all: the query existed, syntactically valid and
confidently wrong, for an entire lane before anything forced it to meet
reality.

## The strangler completes: a flagless edge router

Every extraction before this one left at least one `STRANGLER_*_ENABLED`
flag live in the proxy, and at least one code path still able to fall back
to the monolith. This chapter's cutover is the one that removes the
monolith as an option at all, but it does so in two separated steps, by
design, because the second one cannot be undone.

**Step A** adds `STRANGLER_ORDER_ENABLED` and re-points `06-shipping-
service`'s enrich call from the monolith to order-service's `order_view`,
then proves reversibility *before* doing anything irreversible. With the
flag on and the full extracted topology running (no monolith process at
all), the suite ran **44 requests, 117 assertions, 0 failed, exit 0**; `O1`
returned a real `202 Accepted`, and an independent bounded-wait poll
confirmed a real order reaching `CONFIRMED` through the full Kafka saga on
attempt 4/20. With no `STRANGLER_*` flags set at all and every extracted
service stopped (only the bare monolith running at its original
synchronous defaults), the same unedited suite ran **33 requests, 105
assertions, 0 failed, exit 0**, and `O1` returned a plain `201 Created`.
That is the last reversible proof in this project's entire strangler-fig
history: turning the flag off was still just a config change and a
restart, and the monolith still answered checkout correctly, right up to
this exact point.

**Step B** is the move with no flag to flip back. `examples/01-strangler-
proxy/app/config.py` and `app/main.py` were rewritten, not incrementally
patched: every `*_enabled` boolean and the `monolith_base_url` fallback are
gone from `Settings` entirely, and `_select_backend()` is now an
unconditional six-way lookup: review, notification, inventory, payment,
shipping, order, each with exactly one owning backend, returning `None`
for anything that matches none of them, which `proxy_handler` turns into a
real `404`, never a silent pass-through:

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

`tests/test_routing.py` was rewritten from scratch for this shape: one
fully-wired `Settings` instance, a parametrized test asserting all twelve
path variants route to their one owning backend, an all-six-coexist test, a
parametrized unmatched-path test (including near-miss prefixes like
`/api/order` that must **not** match `/api/orders`) asserting a real `404`,
and six independent backend-down tests, each producing a real `502` scoped
to the one dead backend. **29/29 tests green, `ruff check` clean.** The
monolith itself is not deleted: `examples/00-monolith/README.md` and
`AGENTS.md` gained a "FROZEN STATUS" section recording that the
module stays in-repo as the golden-baseline referent and a break-glass
fallback, but `compose.yaml`/`scripts/`/`demos/` no longer start it or any
of its background processes as part of the live topology.

{% include excalidraw.html file="final-monolith-free-topology" alt="The end-state topology: six independently deployable services plus the GraphQL gateway, reached through one flagless edge router with no monolith fallback left, and the monolith itself frozen and unwired" caption="Figure 26.3: The final topology: six services and a GraphQL gateway behind one flagless router, the monolith frozen and unwired" %}

## From equivalence to contract, with the suite unchanged

Every run before this chapter asserted the same claim: the extracted
service behaves like the monolith did. That claim needs a monolith to
compare against, and once Step B's decommission lands, there is nothing
left in the running topology to compare against. `tooling/newman/proxy.
postman_environment.json` re-points at the flagless edge (`:8888`) and now
bakes every context's contract flag on permanently: there is no more
flag-off/flag-on equivalence comparison left to make, only "does the live
system satisfy its own contract." Against the full monolith-free mesh
(Postgres, Kafka, all six extracted services, the gateway, the flagless
proxy, no monolith process anywhere), the suite ran green, repeatedly:
**50 requests / 133 assertions, 0 failed, exit 0**, twice before the
negative checks below and **45 requests / 128 assertions, 0 failed, exit
0**, twice after them: four clean runs, the second pair the stronger
stability proof because each followed a real service restart.

A green suite that would pass identically whether or not the system
underneath it actually worked proves nothing, which is why the same three
negative checks ch.21 already drew one of from this same evidence file were
run against the finished, monolith-free mesh. **Consumer-down**: killing
`order-service`, both its `/api/orders*` HTTP surface and its Kafka
consumer group reacting to all four saga-outcome topics, turned a clean
run into **59/111 assertions failed, exit 1**; restarting it returned the
suite to **0 failed, exit 0**. **Compensation-disabled**: commenting out the
`await _release_order_lines(...)` call inside `handle_payment_declined`
left stock short by exactly one unit after a declined checkout:
`expected 81 to deeply equal 82`, **1/30 failed**; restoring the line and
re-running returned **0 failed**. **Projection-disabled**: ch.21 already
walked through this one in full: commenting out `order_view`'s upsert
inside a status transition left `GET /api/orders/{id}` stuck at `PENDING`
for the full bounded-wait budget while the aggregate had actually reached
`CONFIRMED`, **1/53 failed**, restored to **0 failed**. All three
interventions were temporary, single-line comment-outs, confirmed restored
by a clean `ruff check` and the stable green runs recorded above. None of
this chapter's own re-designation from "equivalence suite" to "contract
suite" touched a single assertion or negative check: the claim changed
from "matches the monolith" to "satisfies its own contract" because there
is no longer a monolith left to match, not because the bar moved.

`demos/demo-final-topology.sh` is this chapter's own closing artifact: a
self-contained script that brings up the complete monolith-free topology
from scratch in throwaway Postgres and Kafka containers, migrates every
schema, starts all seven services plus the flagless proxy, runs the full
contract suite, and tears everything down, verified standalone at
**50 requests / 133 assertions, 0 failed, exit 0**, with a clean teardown.
The one Django command it runs at all is a one-shot `manage.py migrate &&
manage.py seed`; `examples/00-monolith` is never started as a live process.

> **ADLC in Action.** This is the sixth and final extraction, and the
> planning phase settled the order it had to run in before any code
> existed: Step A (the reversible flag cutover) had to prove the extracted
> order-service and the re-pointed shipping enrichment both worked *before*
> Step B's irreversible decommission ran, because once the monolith's order
> context and its collaborators are deleted, there is nothing left to
> revert to if the extraction turned out to be subtly wrong. The 44/117
> (flag on) and 33/105 (flag off) numbers above are that reversibility
> proof, captured before Step B on that order by design, not after. Step C's own
> ordering was just as deliberate: the three negative checks ran *after*
> the stability runs that prove the suite is reliably green, specifically
> so the later green runs (45/128, twice) would demonstrate recovery from a
> real intervention rather than a suite that had simply never been
> disturbed. The one real bug this lane found (the GraphQL contract query
> guessing a schema shape that didn't match the as-built gateway) surfaced
> precisely because the verification phase insisted on running a
> previously-staged, never-executed query against a live gateway rather than trusting
> that "it parses" meant "it's correct."

## What you learned

- **REST, gRPC, asynchronous sagas, and GraphQL aggregation solve four
  different problems**, not four versions of the same problem: a
  synchronous request a caller waits on, a strongly typed call on a hot
  path that can't proceed without an answer, a sequence of independent
  reactions with no central coordinator, and one client query that needs
  several services' data in a single round trip.
- **A data-less aggregation gateway's partial-failure contract is nullable
  fields plus a populated `errors[]`**, never a swallowed exception and
  never a crashed request; and an unknown root entity (`order(id)` for a
  missing order) is a different, legitimate case (`null`, no `errors[]`)
  that a gateway has to keep distinct from a downstream failure.
- **An aggregation layer that owns no data is still an attack surface**:
  bounding query depth and token count, and fixing every downstream target
  in operator configuration rather than deriving it from the request, are
  what keep a fan-out gateway from becoming an amplification vector.
- **Order went last because it was the only context every other extraction
  had to leave a seam for.** Both of `SMELLS.md`'s oldest entries, the
  god service and the shared ACID transaction, could only be struck once
  the function they both lived on had nothing left to reach into directly.
- **Reversibility has to be proven before the one step that can't be
  undone, not after.** This project's last flag-on/flag-off comparison
  (44/117 versus 33/105 assertions) ran before the irreversible
  decommission, by design, not as an afterthought once it was already
  too late to matter.
- **Freezing a decommissioned system, rather than deleting it, is what
  lets an equivalence suite convert into a contract suite without going
  vacuous.** The frozen monolith is the referent the contract suite was
  built from, and the three negative checks (consumer-down, compensation-
  disabled, projection-disabled) are what keep that contract from becoming
  a suite that would pass no matter what the system underneath it did.

This is the last extraction this book makes. Six bounded contexts are now
independently deployable services, the strangler proxy is a permanent,
flagless edge router, and a GraphQL gateway stands alongside it aggregating
five of those six into one query surface. Chapter 27 turns from what moved
to what it moved onto: the FastAPI chassis conventions (configuration,
health, the uniform error envelope, the REST-and-gRPC-client shape) every
one of these seven services has been using since the moment each was
scaffolded, named and explained in their own right for the first time.
