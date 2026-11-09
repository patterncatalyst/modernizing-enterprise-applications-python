---
title: "Coupling, the Modular Monolith & When Not to Split"
order: 13
part: "Finding the Seams"
description: "Constantine's coupling ladder, afferent and efferent coupling as an extraction ranking, Khononov's balancing model, and the modular monolith as a legitimate destination."
---

## Learning objectives

By the end of this chapter you can:

- State Constantine's pairing of cohesion and coupling and say why coupling is the dimension that produces an extraction order.
- Place the monolith's smells on the coupling ladder (content, common, control, stamp, data) with a concrete Python example for each rung.
- Compute afferent (Ca) and efferent (Ce) coupling for a Django app from its imports and foreign keys, and rank the six contexts from the scores.
- Explain Khononov's strength, distance and volatility model and why splitting strong, volatile coupling across a network yields a distributed monolith.
- Apply the three disciplines of a Python modular monolith: `import-linter` boundaries, plain id fields instead of cross-module `ForeignKey`s, and module-owned tables.
- State the precondition for cutting a seam: an ACL, an outbox, a CDC pipeline or a saga is already in place.

## Why this matters

Bounded contexts and event storming say where a system could be cut. They don't say which seam to cut first, or whether to cut at all. Coupling answers both, because it can be counted. Every smell in `examples/00-monolith/` (a shared schema, a god function, a synchronous call, a leaked entity) is a coupling problem, and scoring them on one scale turns an extraction order into a computed sequence instead of an argument won by whoever spoke last in planning.

The monolith is unchanged here. What follows is the measurement behind the order: review first, order last.

## Coupling and cohesion

Larry Constantine's structured-design rule: a structure is stable if cohesion is high and coupling is low. Cohesion is how tightly the elements inside a module belong together. Coupling is how much one module's internals depend on another's.

`order.services.place_order` is low on cohesion. It checks stock, persists the order, charges payment and dispatches a shipment: four verbs and three "and"s, the plain-English tell for a god function. A function with no single purpose has no natural boundary keeping it out of everyone else's business, so its coupling is high too.

Coupling is the better basis for a strategy because it is measurable. You can count edges in a dependency graph with a static tool or a disciplined `grep`. Cohesion stays a per-module judgment. Conway's observation is the organizational mirror: systems copy the communication structure of the organizations that build them. A `ForeignKey` between `order` and `customers` is also a standing requirement that whoever owns the shared migrations coordinate with whoever owns order's queries.

## The Constantine ladder, applied to the monolith

Constantine and Yourdon ranked module coupling from worst to best. Every rung has a live example in the monolith.

| Rung | What it means | Where it lives |
|---|---|---|
| Content | One module relies on another's internals | `_place_order_local` receives a live, queryset-managed `InventoryItem` from `inventory_services.get_by_sku()` and `reserve()` and reads `.sku`, `.name`, `.price_cents` directly. Python has no access modifiers, and there is no ACL at the seam |
| Common | Modules share a global data store | One Postgres schema for `order`, `inventory`, `payment`, `shipping`, `notification` and `review`. `customers` has no owner and is joined by `order`, `review` and `notification` |
| Control | A parameter's value selects the callee's branch | `OrderCreateSerializer.paymentMethod` is threaded into `payment.services.charge`, where `DECLINE_SENTINEL` picks approve or decline and checkout then depends on the result |
| Stamp | A whole structure is passed when a part is needed | The same `get_by_sku()` handoff returns the full five-column `InventoryItem` for the three fields copied into `OrderItem` |
| Data | Only simple, purpose-built values cross | `InventoryItemSerializer` and `OrderSerializer` return serialized DTOs, never raw models |

One call site earns two rungs at once (content and stamp) because nobody separated "data this call needs a copy of" from "a reference to someone else's aggregate". The codebase also shows both ends of the ladder in sibling files: the serializers were written for an HTTP client, `get_by_sku()` for a Python caller's convenience, and only the first got the discipline.

Two further rungs, message coupling (only messages, no shared state) and API contract coupling, have no monolith example. They are the target: the extracted services already reach them for the edges they cut, with a FastAPI route and a JSON body, a gRPC proto and a stub, or an aiokafka consumer and an event schema.

{% include excalidraw.html file="coupling-ladder" alt="The Constantine coupling ladder as stacked rungs, worst to best, each paired with its monolith example. Content: _place_order_local reading a live InventoryItem from get_by_sku() and reserve(). Common: one shared Postgres schema across all contexts. Control: paymentMethod threaded into payment.services.charge, where DECLINE_SENTINEL selects the path. Stamp: the full InventoryItem returned for three fields. Data: serializers returning DTOs, already done right. Message and API contract coupling have no monolith example; the extracted services reach them." caption="Figure 13.1: The Constantine coupling ladder, worst to best, each rung pinned to its monolith example" %}

## The two worst offenders

**Shared-schema coupling** is common coupling edging toward content coupling. `order`, `payment`, `shipping` and `notification` each hold a foreign key back into `orders`, and several apps join `customers`. A foreign key is not a negotiated contract. It is the database enforcing a promise that neither context's code declared and neither can relax alone. It is also invisible at the point of use: nothing in `order.services` says it depends on inventory's schema, until a migration three deploys later drops a column and breaks a query `order` never knew it relied on.

In Khononov's balancing-coupling model this is the maximal case: intrusive strength, on data that changes constantly, with all three dimensions high. It stays survivable only because distance is zero. The moment one context gets its own database, distance jumps to its maximum while strength stays put, and the distributed monolith arrives unless strength changes first.

**God-function orchestration** is control coupling stacked across three relationships. `place_order` calls `inventory_services`, `payment_services` and `shipping_services` in one synchronous in-process sequence, and a caller that must know each callee's exception behavior (`InsufficientStock`, `PaymentDeclined`, `ShippingFailed`) is control-coupled three times over. In Robert Martin's terms it has Ce of three and Ca near zero, so instability `I = Ce/(Ca+Ce)` is close to 1: it depends on everything and nothing depends on it. Where the schema is dangerous because it is invisible, the god function is dangerous because it is a single point of maximum fan-out. Each other extraction removes one of its outbound edges, which is why order goes last.

## Afferent and efferent coupling

The ladder says what kind of coupling a smell is. It doesn't rank contexts. Two numbers do:

- **Afferent coupling (Ca):** how many other components depend on this one.
- **Efferent coupling (Ce):** how many other components this one depends on.

Both are countable from an import graph or a model's foreign keys. **Extract low-Ca, low-Ce contexts first and save high-Ca, high-Ce contexts for last.** Ca is the number of dependents that must migrate with you, Ce the number of dependencies you must sever or bridge before leaving. Together they are the blast radius.

| Context | Ca | Ce | Consequence |
|---|---|---|---|
| Review | about 0 | about 0 | Nothing calls it and it calls nothing. The floor, so it goes first |
| Notification | low: one asynchronous consume off the outbox | about 0 | Its only inbound edge is already async, so extraction promotes an existing consumer to its own deployable |
| Inventory | moderate: the call from `place_order`, plus the historical FK join | about 0 | Needs a gRPC contract and a client-side ACL before the boundary can be trusted |
| Payment, Shipping | moderate: one inbound call from `place_order` each | about 0 today | Both run inside the same spanning transaction, so the cut needs a saga to replace the free rollback. Payment gains an inbound edge once shipping is out: a `shipment.failed` event drives a refund |
| Order | highest: `Payment`, `Shipment` and `Notification` all carry an `order` foreign key | highest: three synchronous edges plus the async edge into notification | Worst on both axes, so last |

Putting order first would mean solving every other context's severance problem at once, with no smaller extraction's lessons to carry forward: the biggest-cut-first failure a blast-radius ranking exists to prevent.

{% include excalidraw.html file="context-dependency-graph-cace" alt="A directed dependency graph of the six contexts. Order sits at the center with three synchronous outbound edges (inventory, payment, shipping) and one async edge into notification, its efferent coupling, and three inbound foreign-key edges from payment, shipment and notification, its afferent coupling. Inventory also has a data-level edge from order through the historical FK. Review has no edges. A dashed edge from shipping to payment marks a dependency payment only gains once shipping is extracted. Below, the contexts sorted into extraction order: review, notification, inventory, payment, shipping, order." caption="Figure 13.2: The six contexts' dependency graph, scored by Ca and Ce, resolving into the extraction order" %}

The method is to rank by Ca and Ce, cut the lowest first, and let each completed extraction lower the score of what remains until the hardest context is also the smallest remaining problem. The git tags `stage/01-review` through `stage/06-order` follow this order.

## The modular monolith

Khononov's model says distance is a cost multiplier: splitting strong, volatile coupling across a network adds distance without removing strength. The result is a distributed monolith, the same tangle now paying for network calls, partial failure and coordinated deploys. Most of coupling's damage, invisible cross-context writes, unbounded fan-out and leaked model instances, comes from module boundaries, not process boundaries, and module boundaries can be enforced inside one deployable.

The monolith already contains one example. The notification edge was cured with a transactional outbox, closing the dual-write hazard, before notification became a deployable. That took one model (`common.models.OutboxEvent`), one management command (`outbox_relay`) and one consumer (`notification.management.commands.order_placed_consumer`), all in the same Django project and release train. The behavioral seam was cut at module-boundary cost, and the deployable boundary came later, when there was a reason to pay for it.

A Python modular monolith needs three disciplines that a distributed system enforces by default:

- **Import-boundary isolation.** `import-linter`, or a CI-enforced convention, refuses an import from another app's internal module. The content-coupling rung (`order` importing `inventory.models.InventoryItem` instead of a contract type `inventory` publishes) becomes a build failure instead of an incident.
- **No cross-module model references.** A module persists only its own models and refers to another module's data by a plain identifier, an `order_id` integer instead of a `ForeignKey`, plus a published in-process function to resolve it. This is the discipline a gRPC contract imposes on a distributed seam, applied before the seam crosses a network.
- **Module-owned tables.** Each app names its tables so ownership is explicit (`inventory_items` is migrated only by `inventory` and never written by a cross-app query). A foreign key can't cross the boundary by accident, and the second database, connection pool and credential set are deferred until a decomposition need justifies them. This decomposed-database monolith is the midpoint between one undifferentiated schema and one database per service: "own your data" at its lightest weight. The move from a shared schema to owned data, including CDC, is a separate topic.

Doing all three first separates two questions a premature microservices migration conflates. Are the module boundaries right, and do they track real bounded contexts? Moving a function between apps answers that cheaply. Is coupling now low enough, and the context's operational profile different enough, to justify a second deployable, a second database and a network between them? Ask the second only when the first has a confident answer; microservices are not the goal in themselves.

The reference monolith here skips most of this stage. It goes from one shared schema to owned services, with notification's outbox as the single exception, because it demonstrates the full strangler journey with a measured before and after. For your own system the modular monolith is frequently the right destination. If the problem is lead time and change-failure rate inside one team's release train, and not independent scaling or independent team ownership, import boundaries, banned cross-module references and table ownership retire most of the damage without a second deployable, a broker or a mesh. Distribute only for a named, measured need: independent scaling, deployment cadence or team ownership.

## The distributed-monolith trap

The common failure runs backwards from this analysis: a team sees coupling, concludes microservices fix coupling, and distributes a system whose coupling it never reduced. It pays latency, partial failure, deploys that still have to be coordinated, and tracing in place of a stack trace, and keeps none of the monolith's simplicity, because the former in-process calls are now network calls making the same synchronous demands.

In Khononov's terms distance went up, strength did not go down, and volatility on the core domain was already high. A version of this monolith split into six services without first addressing the shared schema and the god function would be six deployables reaching across the network into tables and services they don't own. Each extraction here cuts a context only once the specific coupling in its way has an answer: an ACL, an outbox, a CDC pipeline or a saga. The behavior-equivalence gate then proves the answer held, instead of production discovering that it didn't.

> **Decision**
>
> Rank contexts by Ca and Ce and cut the lowest first. Before cutting any seam, reduce its coupling strength inside the monolith; split only when a named scaling, deployment or team-ownership need outweighs the network tax.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith/`, compute Ca and Ce for the review, notification, inventory, payment, shipping and order apps from their imports and foreign keys, then list which edges `place_order` in `order/services.py` would have to lose before order can be extracted. Add an `import-linter` contract that forbids other apps from importing `inventory.models`, and say which rung of the coupling ladder each violation sits on."
>
> Check: order scores highest on both Ca and Ce, and `lint-imports` flags `from inventory.models import InventoryItem` in `review/services.py`.

## For deeper coverage

Larry Constantine and Edward Yourdon, *Structured Design*, defines the coupling ladder. Vlad Khononov, *Balancing Coupling in Software Design*, supplies the strength, distance and volatility model. Melvin Conway's 1968 "How Do Committees Invent?" is the source of Conway's law. Robert Martin's package metrics define afferent and efferent coupling and instability. The bibliography page lists the books.
