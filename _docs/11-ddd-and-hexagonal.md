---
title: "Strategic & Tactical DDD + Hexagonal"
order: 11
part: "Finding the Seams"
description: "Subdomains, bounded contexts, context mapping, aggregates and domain events find where to cut; ports and adapters make the cut cheap."
---

## Learning objectives

By the end of this chapter you can:

- Classify the monolith's six Django apps as core, supporting or generic, and predict the extraction order from that alone.
- Explain why the shared `common` app and single Postgres schema violate a bounded context's defining property: a private model and a public contract.
- Diagnose the order-to-inventory call as an undecided conformist coupling using shared kernel, customer/supplier, conformist and anti-corruption layer.
- Tell a value-object snapshot from a live entity reference at an aggregate boundary.
- Explain what ports and adapters buy: a boundary already decided becomes cheap to cut, and an undecided one stays expensive.
- Read the review service's Phase A to Phase B diff and say why zero outbound edges to sibling business logic, not a declared port, made it cheap to extract.
- Reconstruct the extraction order (review, notification, inventory, payment and shipping, order) from classification, context mapping and outbound-edge counting.

## Why this matters

The monolith's smells all sit on a seam: a line where a conceptual boundary exists but the implementation welds it shut. Finding seams in a system that didn't ship with a `SMELLS.md` takes vocabulary. Domain-Driven Design decides where a system should be cut, and hexagonal architecture makes a cut cheap to execute. Every smell in the monolith turns out to be a DDD concept with its name filed off.

The excerpts below come from `examples/00-monolith/` and, for contrast, `examples/02-review-service/`.

## Strategic DDD: naming the lines that already exist

Strategic DDD asks what different things the business does and which deserve their own model. Each answer is a **subdomain**, classified by competitive value and rate of change:

| Class | Meaning | Treatment |
|---|---|---|
| Core | Where the business differentiates; complex and strategic | Best engineering attention |
| Supporting | Necessary, not a differentiator | Build simply |
| Generic | Solved elsewhere in a common shape | Adopt an off-the-shelf answer |

Against the monolith's six apps: **order** is core, the checkout aggregate whose correctness and responsiveness customers notice and which every other context serves. **Inventory**, **payment** and **shipping** are supporting: stock levels, a captured charge and a moving package are table stakes. **Notification** and **review** are generic: a confirmation and a star rating are solved problems.

That classification predicts the extraction order. The two generic subdomains go first and the core goes last. A generic subdomain changes rarely, has few internal invariants and carries the least organizational risk if its extraction goes imperfectly. The core is the opposite on every axis, so it waits until the strangler mechanism and the equivalence gate are proven on lower-stakes ground.

Each subdomain becomes one or more **bounded contexts**: the scope in which one model and one **ubiquitous language** stay consistent, and outside which the same word may mean something else. A context owns its model privately and exposes a deliberate public contract, so two contexts may hold two different ideas of "customer." In the monolith, `order`, `inventory`, `payment`, `shipping`, `notification` and `review` all import shared entities from one `common` app and write to one Postgres schema where any context's ORM can join any table. That is one context wearing six app labels, and the root condition most of the smells grow from.

## Context mapping: naming the relationship nobody decided

Context mapping gives the relationship between two contexts a fixed vocabulary instead of whatever the cheapest line of code happened to do.

| Relationship | What it is | In the monolith |
|---|---|---|
| Shared kernel | A narrow slice of model two contexts share explicitly, changed only by agreement | The whole database, shared with no governed edges, because a `ForeignKey` is the cheapest way to relate rows in one schema |
| Customer/supplier | Downstream negotiates a stable, versioned contract (a DTO or event schema) with upstream | What order and inventory should have |
| Conformist | Downstream accepts the upstream's internal model wholesale | What order and inventory have |
| Anti-corruption layer | A translation that protects the downstream model from the upstream's | Missing |

`order.services.place_order` accepts inventory's internal representation as is:

```python
# inventory/services.py
def reserve(sku: str, quantity: int) -> InventoryItem:
    """Reserves (decrements) stock for one checkout line.

    SMELL[ch.26]: called directly from order.services.place_order() against
    this app's own model/queryset, with no translation layer (anti-corruption
    layer) and no network boundary in between -- a cross-context in-process
    call, not a call to an independently deployable service over a stable
    contract.
    """
```

```python
# order/services.py::_place_order_local
for line in items:
    inventory_item = inventory_services.get_by_sku(line["sku"])
    inventory_services.reserve(line["sku"], line["quantity"])
    OrderItem.objects.create(
        order=order,
        sku=inventory_item.sku,
        item_name=inventory_item.name,
        quantity=line["quantity"],
        unit_price_cents=inventory_item.price_cents,
    )
```

Conformist is legitimate when the upstream is clean, stable and outside your influence, like a small team integrating a large vendor's API. Here `order` and `inventory` are sibling apps heading toward independent deployment, and they could negotiate. Conformism chosen with the cost understood is a strategy. Conformism because the live `InventoryItem` was sitting right there is a missing **anti-corruption layer (ACL)**. The inventory extraction builds it as `order.inventory_client.RemoteInventoryClient` over a proto-defined gRPC contract.

What was missing is a decision. Nobody chose what the relationship should be; a direct call into another app's `services` module is simply the cheapest thing a shared process and schema produce. Context mapping's value is forcing that decision for every seam.

{% include excalidraw.html file="context-map" alt="A context map of the monolith's six bounded contexts: order's edge into inventory is conformist, with no anti-corruption layer at the seam; order's edges into payment and shipping are direct synchronous calls inside one transaction.atomic(), with no port; order's edge into notification is already cured, reached only via an outbox and an asynchronous consumer; review has zero outbound edges to any sibling context; and all six sit on one Postgres schema, a shared kernel with no governed edges." caption="Figure 11.1: Context map of the six bounded contexts and the relationship nobody decided" %}

One edge on the map is already cured: `order` reaches `notification` only through `common.models.OutboxEvent` and a Kafka topic (`settings.ORDER_PLACED_TOPIC`), written in `order/services.py::_write_order_placed_outbox_event`. In context-mapping terms the outbox row is a negotiated, versioned, append-only contract, written once by order and read independently by notification's own consumer. That is customer/supplier without trusting the other side's live model.

## Tactical DDD: what lives inside a seam

Strategic DDD decides where the lines go. Tactical DDD decides what the model looks like on each side.

An **aggregate** is a cluster of objects treated as one consistency unit: the boundary inside which invariants hold together and a single transaction commits. `Order` and its `OrderItem`s are the clearest aggregate in the monolith, and `OrderItem` is shaped well. It holds no live reference to another aggregate's root; it carries `sku`, `item_name` and `unit_price_cents` as plain columns copied at checkout:

```python
# order/models.py
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.CharField(max_length=64)
    item_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()
```

That is a **value object** snapshot: an immutable fact about this line at this moment, with no identity or lifecycle, so a later price change in `inventory` never rewrites a historical order. `InventoryItem` is a legitimate **entity**: it has identity and a lifecycle (`reserve` decrements `quantity_on_hand`).

The leak is one call earlier, in what gets passed. `get_by_sku()` and `reserve()` hand the checkout loop the live, queryset-managed `InventoryItem`, and the loop reads three fields off it before copying them. Storage is clean; the call boundary hands a whole aggregate across a context line. The rule from the calling side: reference another context's aggregate by a small copied value, never by holding a live reference to its root, even long enough to read three fields.

**Domain events** let aggregates in different contexts react to each other's state changes without holding references. `config/settings.py` names four as live constants (`ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`, `PAYMENT_DECLINED_TOPIC`, `SHIPMENT_DISPATCHED_TOPIC`), and one is already wired to a working transactional outbox. For its other two collaborators `place_order` still calls `payment_services.charge(...)` and `shipping_services.dispatch(...)` as synchronous functions inside one transaction. That is the ACID-transaction smell and the god-service smell restated: a published event, consumed independently, belongs in place of each direct call.

Data access carries one more rule: only a context's own code calls its persistence layer. `order/services.py` does `import inventory.services as inventory_services`, so an app's service module is imported across a context boundary. That is the missing ACL seen from the data-access side. The three findings are one absent seam viewed from three tactical angles.

## Hexagonal architecture: ports that make a seam cheap to cut

Hexagonal architecture (ports and adapters) determines how expensive it is to act on a boundary once decided. A domain core holds entities, aggregates and business logic and depends on nothing: no web framework, no ORM, no broker. It declares **ports**: inbound ports for what it can be asked to do, outbound ports for what it needs from the world. **Driving adapters** (a REST route, a gRPC service, a message consumer) translate a protocol into a call on an inbound port. **Driven adapters** (a repository module, an event publisher) implement the outbound ports. Every dependency points inward, and a protocol can be swapped without the core noticing.

The monolith doesn't have this structure. A DRF view's validated data flows through a `services` function into a model's `.save()` with nothing between "an HTTP request arrived" and "a row changed." `place_order` imports `inventory.services`, `payment.services` and `shipping.services` at the top of the file: other contexts' concrete modules, not ports. Wrapping it in a `Protocol` today would only declare the same three-context fan-out it already has. Hexagonal architecture makes a clean boundary cheap to cut; it has no opinion on a boundary that was never drawn. So the inventory, payment and shipping extractions each remove one of `place_order`'s direct edges before order can be extracted at all.

{% include excalidraw.html file="hexagonal-ports-adapters" alt="A hexagonal-architecture diagram: a domain core at center, holding entities, aggregates, and business logic, with no dependency on any web framework, ORM, or message broker; driving adapters (a REST route, a gRPC service, a message consumer) each depending inward on an inbound port; driven adapters (a database repository module, an event publisher) each depending inward on an outbound port the core declared." caption="Figure 11.2: Hexagonal architecture, with every dependency pointing inward" %}

## Pattern: Ports and Adapters

`examples/02-review-service` shows the payoff in a real diff. Phase A lifted review onto FastAPI nearly unchanged, reusing the monolith's Django ORM as a path dependency. Phase B, the live code under `app/`, moved to idiomatic FastAPI: Pydantic v2 schemas, async SQLAlchemy 2.x against the same shared schema, and HTTP Basic auth reverified against Django's password hash format via `passlib`.

```python
# app/routes.py: the driving adapter translates an HTTP request into
# calls on repository functions, nothing more.
@router.post("/api/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    payload: ReviewCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _authenticated_username: str = Depends(require_basic_auth),
) -> ReviewOut:
    customer = await repository.get_customer_by_id(session, payload.customer_id)
    item = await repository.get_inventory_item_by_sku(session, payload.sku)
    review = await repository.create_review(
        session, customer_id=payload.customer_id, inventory_item_id=item.id,
        rating=payload.rating, comment=payload.comment or "",
    )
    response.headers["Location"] = f"/api/reviews/{review.id}"
    return ReviewOut(id=review.id, customerId=review.customer_id, sku=item.sku, ...)
```

```python
# app/repository.py: the driven adapter holds the async SQLAlchemy queries
# that no route handler needs to know the shape of.
async def create_review(session: AsyncSession, *, customer_id, inventory_item_id,
                         rating: int, comment: str) -> Review:
    review = Review(customer_id=customer_id, inventory_item_id=inventory_item_id,
                     rating=rating, comment=comment, created_at=datetime.now(UTC))
    session.add(review)
    await session.flush()
    await session.commit()
    return review
```

The route imports nothing that depends on the persistence technology behind `repository`. Phase A's version of this route reached Django's ORM through the path dependency; Phase B swapped in async SQLAlchemy and the handler barely moved, the only change being `await`ing calls that used to be synchronous. When only a context's own adapter depends on its persistence internals, changing the adapter is cheap.

Two caveats. First, `app/repository.py` is a module of plain async functions, not a declared `Protocol`, so this isn't textbook hexagonal. What made review cheap to extract was more modest: its business logic has **zero outbound edges to any other context's services**. It reads `Customer` and `InventoryItem` rows for validation but never calls `order.services`, `payment.services`, `shipping.services` or `notification.services`.

Second, review still borrows from its siblings. The write endpoint uses Django's shared `auth_user` table, gated per view with HTTP Basic auth, and the service still reads the shared schema for `Customer` and `InventoryItem`. Its `README.md` calls this "Option B," a scoped deferral rather than an oversight, with credentials checked through `passlib`'s `django_pbkdf2_sha256` scheme instead of a hand-rolled comparison. Zero outbound edges to sibling business logic is a narrower claim than zero coupling. A context with the lowest business coupling can still share an authentication table or a schema, and a careful seam-finder names what remains instead of letting a clean afferent and efferent coupling count (Ca/Ce) paper over it.

## The extraction order is a prediction

Subdomain classification, the context-mapping audit and edge counting together turn the extraction order from preference into forecast:

- **Review first.** Generic, zero outbound business edges, nothing to renegotiate or make asynchronous. The shared `auth_user` table is a named deferral, not a blocker.
- **Notification second.** The asynchronous edge it needs is already live through the outbox before it becomes deployable, so the cure doesn't wait for the cut.
- **Inventory third.** Its relationship with order is conformist with no ACL, so the translation layer must be built before a clean boundary exists.
- **Payment and shipping next.** Each is a synchronous call inside `place_order`'s single transaction. Extracting either forces the ACID-to-ACD shift and saga machinery, with domain events coordinating for the first time.
- **Order last.** The core, with the most outbound edges and invariants, can't be cut cleanly until its neighbors have standalone, negotiated boundaries to be cut against.

The method generalizes to any system. Classify each area by value and rate of change. Draw a context map and ask, for every integration point, which relationship exists and whether anyone chose it. Check what each call site hands across a boundary, a value snapshot or a live reference. Count a module's outbound edges before judging how hard it is to free, and name coupling the count doesn't capture.

> **Decision**
>
> Classify the subdomain, then count outbound edges. Cut a context with zero outbound business edges first, build the missing anti-corruption layer before cutting a conformist seam, and extract the core last. Ports and adapters speed up a decided boundary; they never decide one.

> **🤖 Explore with your agent**
>
> "Audit `examples/00-monolith` for outbound edges: for each of the six apps, list which other apps' `services` and `models` modules it imports, and for `order/services.py` list every place a live model instance crosses a context boundary instead of a copied value. Classify each context as core, supporting or generic, and rank them by extraction cost using the rule that zero outbound business edges goes first and the core goes last."
>
> Check: `grep -n "import .*services" examples/00-monolith/*/services.py` shows only `order/services.py` importing other contexts' services (inventory, payment, shipping); the reply should match that, note that `review/services.py` reads `inventory.models.InventoryItem` without calling inventory's services, put order last, and flag `get_by_sku()` and `reserve()` as returning a live `InventoryItem`.
