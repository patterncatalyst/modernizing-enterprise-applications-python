---
title: "Strategic & Tactical DDD + Hexagonal"
order: 11
part: "Finding the Seams"
description: "Subdomains, bounded contexts, context mapping, aggregates, and domain events: keeping the ORM out of the domain core so extraction is mechanical."
---

Chapter 9 catalogued the smells still standing in `examples/00-monolith/` and
named, for each one, the chapter that will cut it. Chapter 10 built the
behavior-equivalence suite that will prove each cut preserved behavior. Both
chapters used the word "seam" freely, a line where a conceptual boundary
already exists but the implementation currently welds it shut, without ever
explaining where that vocabulary comes from, or how to find a seam in a
system that didn't ship with a `SMELLS.md` file pointing at one. This chapter
supplies that vocabulary. Domain-Driven Design is not a styling choice for
how you name your Django apps; it is a discipline for deciding where a
system should be cut, and hexagonal architecture is the structural
discipline for making a cut, once decided, cheap to execute. Together they
are this book's seam-finding toolkit, and every smell Chapter 9 named turns
out to be a DDD concept with its name filed off.

The code is in `examples/00-monolith/` and, for contrast, in
`examples/02-review-service/`; nothing new has been scaffolded for this
chapter. Every excerpt below is quoted verbatim from files already in those
two modules, the same discipline Chapter 9 held itself to.

## Strategic DDD: naming the lines that already exist

Strategic DDD starts from a blunt question: not "how should we write this
code," but "what are the different things this business does, and which of
them deserve their own model." Evans calls the answer a **subdomain**, and
classifies each one by how much competitive value it carries and how fast it
changes. A **core** subdomain is where the business actually differentiates
itself: complex, strategically important, worth your best engineering
attention. A **supporting** subdomain is necessary but not a differentiator:
build it simply, because nobody chooses this business over a competitor
because of how well it does this one thing. A **generic** subdomain is a
solved problem elsewhere (notifications, ratings, authentication) that
most systems need in roughly the same shape, which is exactly why it's
usually fine to adopt an off-the-shelf answer rather than invent one.

Run that classification against the six Django apps the monolith already
has, and the answer falls out almost without effort. **Order** is core: it's
the checkout aggregate, the one piece of the system whose correctness and
responsiveness customers notice directly, and the one every other context
exists to serve. **Inventory**, **payment**, and **shipping** are
supporting: every e-commerce system needs stock levels, a way to capture a
charge, and a way to get a package moving, but doing those three things is
table stakes, not a competitive edge; build them correctly and move on.
**Notification** and **review** are generic: sending a confirmation and
collecting a star rating are both solved problems with well-known shapes,
which is precisely why Chapter 4's strategy discussion would file them under
"adopt a known pattern" rather than "invest heavily here."

Notice what that classification predicts, before this book ever reaches the
extraction roadmap: the two generic subdomains, review and notification,
are also the first two services extracted (Chapters 15 and 17), and the core
subdomain, order, is extracted last (Chapter 26). That is not a
coincidence this chapter is pointing out after the fact; it's strategic
DDD's own logic. A generic subdomain changes rarely, has few internal
invariants worth agonizing over, and has the least organizational risk if
its extraction goes imperfectly. A core subdomain is exactly the opposite on
every axis, which is why you save it for last, once the strangler mechanism
and the equivalence gate have both been proven on lower-stakes ground.

Each subdomain, in turn, becomes one or more **bounded contexts**: the
scope within which one model and one **ubiquitous language** stay internally
consistent, and outside of which the same word is allowed to mean something
else entirely. This is the half of strategic DDD the monolith's design
actively works against, and it's worth being precise about how. A bounded
context's defining property is that it owns its model privately and exposes
only a deliberate, public contract, which means two different contexts are
*allowed*, even expected, to have two different ideas of what a "customer"
is. In the monolith today, `order`, `inventory`, `payment`, `shipping`,
`notification`, and `review` all import from one `common` app for their
shared entities and, more to the point, write to one Postgres schema in
which every table is a first-class citizen any context's Django ORM can
join against. That is not six bounded contexts; it is one context wearing
six app labels. A single shared vocabulary stretched across six conceptually
distinct areas of responsibility is itself a notable symptom, not a
convenience to take for granted, and it is the root condition most of
Chapter 9's smells grow out of.

## Context mapping: naming the relationship nobody decided

Once you have candidate bounded contexts, the next strategic-DDD question is
how they should relate to each other, and DDD's **context mapping** gives
that question a fixed vocabulary instead of leaving it to whatever the
cheapest line of code happened to do. Four of those patterns matter most for
this book's purposes, and the order↔inventory seam `place_order()` reaches
across is a worked example of nearly all of them at once.

A **shared kernel** is a deliberate, narrow slice of model two bounded
contexts agree to share explicitly: both sides know the kernel exists, both
have to coordinate before changing it, and both accept the coupling as a
conscious trade-off for a small, stable piece of shared vocabulary. That is
not what the monolith has. One Postgres schema, readable and joinable by
every app's Django ORM, is a shared kernel with no edges, not a narrow,
governed slice of shared model, but the entire database treated as if it
belonged equally to all six contexts at once. Nobody decided this was a
shared kernel; it is simply what you get by default when nobody decides
anything, because a `ForeignKey` field is the cheapest way to relate two
rows that happen to live in the same schema.

The relationship the order↔inventory seam *should* have is
**customer/supplier**: order is the downstream consumer of inventory's stock
data, inventory is the upstream supplier, and a well-formed
customer/supplier relationship means the two sides negotiate a stable,
versioned contract, a DTO or event schema the supplier commits to and the
consumer builds against, with the downstream side carrying enough weight in
that negotiation to actually shape what the contract contains, because it's
the downstream side's business need driving the integration in the first
place.

Instead, what actually exists is **conformist**: `order.services.place_order`
accepts `inventory`'s internal representation wholesale, with no negotiation
at all.

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

Conformist is a legitimate choice *sometimes*: it's the right call when the
upstream is clean, stable, and outside your influence, the way a small team
integrating with a large vendor's API has no real leverage to negotiate a
bespoke contract and is better off just accepting the vendor's shape. That is
not this situation. `order` and `inventory` are sibling Django apps in the
same codebase, owned by (eventually) the same organization, heading toward
being two independently deployable services that absolutely could negotiate
a contract. Conformism chosen as a trade-off, with the cost understood, is a strategy.
Conformism that happens because nobody built the alternative and the live
`InventoryItem` instance was sitting right there, returned by
`get_by_sku()`, is what Chapter 9 calls a smell, and what this chapter can
now name precisely: a missing **anti-corruption layer (ACL)**, the
translation Evans prescribes specifically for a downstream context that
needs to protect its own model from an upstream context's internal
representation. That translation layer, built in Chapter 19 as
`order.inventory_client.RemoteInventoryClient` talking to a proto-defined
gRPC contract instead of a shared queryset, is this chapter's conceptual
gap turned into working code, several chapters from here.

It's worth being exact about what was actually missing, because it is a
specific, nameable thing and not a vague complaint about code quality:
nobody ever decided what the order↔inventory relationship *should be*. No
deliberate decision was made, no contract was drafted, no map was drawn;
the relationship that exists today is simply whatever the cheapest
implementation produced, which is a direct function call into another app's
`services` module, because that is always the cheapest thing a shared
process and a shared schema can produce. Context mapping's real value isn't
the four vocabulary words above; it's the discipline of forcing that
decision to be made explicitly, for every seam, so the relationship between
two contexts is something somebody chose rather than something nobody
noticed.

{% include excalidraw.html file="context-map" alt="A context map of the monolith's six bounded contexts: order's edge into inventory is conformist, with no anti-corruption layer at the seam; order's edges into payment and shipping are direct synchronous calls inside one transaction.atomic(), with no port; order's edge into notification is already cured, reached only via an outbox and an asynchronous consumer; review has zero outbound edges to any sibling context; and all six sit on one Postgres schema, a shared kernel with no governed edges." caption="Figure 11.1: Context map: six bounded contexts, one relationship nobody decided" %}

Notice one edge on that map that is *not* still conformist: `order`'s edge
into `notification` is already drawn as a cured relationship, reached only
through `common.models.OutboxEvent` and a Kafka topic
(`settings.ORDER_PLACED_TOPIC`), not a direct call into
`notification.services`. That isn't a forward-looking aspiration this
chapter is asking you to take on faith; it's the monolith's own code,
today, in `order/services.py::_write_order_placed_outbox_event`. Chapter 9
already named it as cured; this chapter's job is just to say *why* it counts
as cured in context-mapping terms: the outbox row is a negotiated,
versioned, append-only contract, written once by order and read
independently by notification's own consumer, which is exactly what a
customer/supplier relationship looks like once nobody has to trust the
other side's live model.

## Tactical DDD: modeling what lives inside a seam

Strategic DDD decides where the lines go. **Tactical DDD** decides what the
model looks like on each side of a line, and three of its building
blocks (aggregates, value objects versus entities, and domain events) are
each, again, a name for something Chapter 9 already found broken, or in one
case, already found fixed.

An **aggregate** is a cluster of objects treated as one consistency unit:
the boundary inside which invariants must hold together, and the unit a
single transaction commits as a whole. `Order` and its `OrderItem`s are the
monolith's clearest aggregate, and the way `OrderItem` is shaped today
already shows good tactical instincts, which this chapter names before
turning to what's still missing. `OrderItem` does not hold a live reference to
another aggregate's root object; it holds `sku`, `item_name`, and
`unit_price_cents` as its own plain columns, copied once at checkout time:

```python
# order/models.py
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.CharField(max_length=64)
    item_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price_cents = models.BigIntegerField()
```

That's a **value object** snapshot done correctly: a plain, immutable fact
about this specific line at this specific moment, with no identity and no
lifecycle of its own, captured so a later price change in `inventory` never
retroactively rewrites a historical order line. `InventoryItem` itself, by
contrast, is a legitimate **entity**: it has identity, it has a lifecycle
(`reserve` decrements `quantity_on_hand`), and inventory's own code is right
to model it as one.

The leak tactical DDD still catches isn't in what gets stored; it's in what
gets *passed*, one call earlier. `inventory_services.get_by_sku()` and
`reserve()` both hand `_place_order_local`'s checkout loop back the live,
queryset-managed `InventoryItem` instance, not a purpose-built contract type,
and the loop then reads three of that instance's five fields
(`inventory_item.sku`, `.name`, `.price_cents`) directly off it before
copying them into `OrderItem`. The storage side of this is clean; the
call-boundary side still hands the whole aggregate across a context line it
shouldn't cross, which is tactical DDD's rule about aggregate references
stated from the *calling* side rather than the *persisted* side: reference
another context's aggregate by a small, copied value, never by holding (even
briefly, even just long enough to read three fields off it) a live reference
to its root.

**Domain events** are tactical DDD's mechanism for aggregates in different
contexts to react to each other's state changes without holding references
to each other at all, and `config/settings.py` already names four as live
constants (`ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`,
`PAYMENT_DECLINED_TOPIC`, `SHIPMENT_DISPATCHED_TOPIC`), not merely reserved
for later, the way a greenfield rewrite's event catalog so often is, but
already wired to a working transactional outbox for the one edge Chapter 9
marked cured. `order.services.place_order` still fakes the effect a domain
event should have for its other three collaborators, calling
`payment_services.charge(...)` and `shipping_services.dispatch(...)`
directly, as ordinary synchronous function calls, inside the same
transaction, which is Chapter 9's ACID-transaction smell and god-service
smell, both restated: a domain event is precisely what should exist in
place of each of those direct calls, published once `Order` has reserved
its stock, consumed independently by whichever context reacts to it.
Chapters 19, 23, and 24 build that replacement for inventory, payment, and
shipping respectively; notification already has it.

And **module boundaries on data access** carry one rule tactical DDD is
explicit about that the monolith also breaks in the same place a repository
would: only one context's own code should call into its persistence layer
directly. `inventory.services` is imported not just inside `inventory`'s own
views but, via `order/services.py`'s `import inventory.services as
inventory_services`, by `order` as well. An app's service module imported
across a context boundary is the same violation as the missing ACL, viewed
from the data-access side rather than the domain-model side. These are not
three separate problems with three separate causes; they are one absent
seam, visible from three different tactical-DDD angles at once.

## Hexagonal architecture: ports that make a seam cheap to cut

Strategic and tactical DDD tell you *where* a boundary should be and *what*
should live on each side of it. **Hexagonal architecture** (ports and
adapters) is the structural discipline that determines how expensive it is
to actually act on that decision once you've made it. A domain core sits in
the middle, holding entities, aggregates, and business logic, and depends on
nothing: no web framework, no ORM, no message broker. It declares
**ports**: inbound ports describing what it can be asked to do, outbound
ports describing what it needs from the world. **Driving adapters** (a REST
route, a gRPC service, a message consumer) translate an incoming protocol
into a call on an inbound port. **Driven adapters** (a database repository
module, an event publisher) implement the outbound ports the core declared.
Every dependency arrow points inward, toward the core; the core never
imports a protocol, and a protocol can be swapped without the core noticing.

Chapter 8 already told you the monolith does not have this structure:
Django's own request/response cycle, its ORM's `QuerySet` API, and its
`services.py` functions are not separated by any declared port; a DRF
view's validated data flows straight through a `services` function into a
model's `.save()` call, with nothing standing between "an HTTP request
arrived" and "a row changed" that a different protocol could be slotted
behind without editing the function in between. That absence is deliberate,
so that this chapter's introduction of ports-and-adapters discipline has a
real gap to fill rather than a strawman nobody would actually build.
`order.services.place_order` is the sharpest example: its module imports
`inventory.services`, `payment.services`, and `shipping.services` directly
at the top of the file: four other contexts' concrete modules, not four
ports. Wrapping `place_order` in a `Protocol` today wouldn't buy you an
extraction boundary; the protocol would just have to declare the same
three-context fan-out the function already has, because hexagonal
architecture makes a *clean* boundary cheap to cut; it has no opinion on a
boundary that was never drawn in the first place. That is exactly why
Chapters 19, 23, and 24 each have to remove one of `place_order`'s direct
edges before Chapter 26 can extract order at all: ports-and-adapters
discipline is a force multiplier on a boundary decision already made, not a
substitute for making one.

{% include excalidraw.html file="hexagonal-ports-adapters" alt="A hexagonal-architecture diagram: a domain core at center, holding entities, aggregates, and business logic, with no dependency on any web framework, ORM, or message broker; driving adapters (a REST route, a gRPC service, a message consumer) each depending inward on an inbound port; driven adapters (a database repository module, an event publisher) each depending inward on an outbound port the core declared." caption="Figure 11.2: Hexagonal architecture: ports and adapters, dependencies pointing inward" %}

## Why review could leave first: ports, measured in a real diff

This chapter doesn't have to argue hexagonal's payoff only in the abstract;
the contrast already exists in the examples. `examples/02-review-service` is
the review context after its two-phase migration (Chapter 7, Chapter 15):
Phase A lifted it onto FastAPI nearly unchanged by reusing the monolith's own
Django ORM as a path dependency; Phase B, the live code under `app/`,
refactored it to idiomatic FastAPI: Pydantic v2 schemas, async SQLAlchemy
2.x against the same shared schema, HTTP Basic auth reverified directly
against Django's password hash format via `passlib`. Look at what changed
and what didn't.

```python
# app/routes.py — the driving adapter: translates an HTTP request into
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
# app/repository.py — the driven adapter: async SQLAlchemy queries, nothing
# that any route handler has to know the shape of.
async def create_review(session: AsyncSession, *, customer_id, inventory_item_id,
                         rating: int, comment: str) -> Review:
    review = Review(customer_id=customer_id, inventory_item_id=inventory_item_id,
                     rating=rating, comment=comment, created_at=datetime.now(UTC))
    session.add(review)
    await session.flush()
    await session.commit()
    return review
```

Two things are worth being precise about, in both directions. First, the
payoff: `app/routes.py` is a driving adapter in every sense that matters:
it imports nothing that depends on what persistence technology sits behind
`repository`, and it does nothing but translate a FastAPI request into
function calls. Phase A's implementation of that same route reused Django's
ORM directly through a path dependency on the monolith's own package; Phase
B swapped it for async SQLAlchemy, and the route handler's shape barely
moved; the only real change was `await`ing calls that used to be
synchronous. That is the entire argument for ports and adapters, proved on a
real diff instead of asserted in the abstract: when the only thing depending
on a context's persistence internals is that context's own adapter module,
changing the adapter is cheap, and changing the protocol or the persistence
technology never touches the request-handling logic at all.

Second, two caveats, because this chapter owes you the whole picture, not
just the flattering half. `app/repository.py` is a module of plain async
functions, not a declared `Protocol` the routes program against. This is
not textbook hexagonal with an explicit port interface the domain owns and
an adapter implementing it elsewhere. What made review cheap to extract
wasn't a perfectly drawn hexagon; it was something more modest and, for this
book's purposes, more important: review's business logic had **zero
outbound edges to any other bounded context's services**. It reads
`Customer` and `InventoryItem` rows for validation, but it never calls
`order.services`, `payment.services`, `shipping.services`, or
`notification.services`; review has no synchronous dependency on anything
else in the monolith, a property Chapter 9 named explicitly.

The second caveat is the one worth sitting with, because it's a nuance the
Java-sibling version of this chapter didn't have to carry: review's write
endpoint *does* still borrow something from its siblings: Django's shared
`auth_user` table, gated per-view with HTTP Basic auth, even though nothing
about reviewing a product requires authenticating against the same user
store `order` would use if it ever needed login. `examples/02-review-service`
keeps that exact coupling as a named trade-off: its own `README.md` calls
this "Option B," a scoped deferral, not an oversight: the service
still reaches the shared Postgres schema for `Customer` and `InventoryItem`
reads, and still verifies Basic-auth credentials against the same
`auth_user` rows the monolith seeds, via `passlib`'s
`django_pbkdf2_sha256` scheme rather than a hand-rolled comparison. The
lesson this chapter draws from it: zero outbound edges to sibling
*business logic* is what made review's extraction cheap, and it is a
narrower claim than "review has no coupling of any kind." A context can
have the lowest possible business coupling score in this book and still
share an authentication table, a schema, or a deployment pipeline with its
former siblings, and a careful seam-finder names that remaining coupling
instead of letting a clean Ca/Ce score paper over it.

## The extraction order is a prediction, not a preference

Put strategic DDD's subdomain classification, context mapping's relationship
audit, and hexagonal architecture's edge-counting together, and the
extraction order stops looking like a pedagogical convenience and starts
looking like something closer to a forecast. Review goes first because it is
a generic subdomain with zero outbound business edges: nothing to
renegotiate, nothing to make asynchronous, nothing to backfill; the one
thing it does carry over, the shared `auth_user` table, is a named
deferral rather than a blocker. Notification goes second because it already
has the asynchronous edge it needs: this chapter showed you the outbox is
live *before* notification is ever pulled into its own deployable, proof
that the cure doesn't have to wait for the cut. Inventory is harder, because
its context-mapping relationship with order isn't just synchronous: it's a
conformist relationship with no ACL, so its extraction (Chapter 19) has to
build the translation layer this chapter only named before a clean boundary
can even exist. Payment and shipping (Chapters 23 and 24) are each reached
as a synchronous call inside `place_order`'s single transaction, and
extracting either one forces the ACID-to-ACD shift Chapter 22 names and the
saga machinery those chapters build: domain events, for the first time for
these two contexts, doing the coordinating work tactical DDD always said
they should. And order, the core subdomain, the context with the most
outbound edges and the most invariants worth protecting, goes last
(Chapter 26), not as a narrative flourish but because strategic DDD's own
logic makes it true: the context with the most relationships to everyone
else cannot be cleanly cut until its neighbors already have standalone,
negotiated boundaries of their own to be cut *against*.

That is the method this chapter hands you, and it generalizes past this one
monolith. Classify each area of the system by value and rate of change. Draw
a context map and ask, for every integration point, which of the possible
relationships actually exists today and whether anyone chose it or it just
accumulated.
Check what each call site hands across a boundary: a value snapshot of
what it needs, or a live reference to something it doesn't own. Count a
module's outbound edges before you judge how hard it will be to cut free,
and name any remaining coupling a clean edge-count doesn't capture. None of
those steps require inside knowledge of this book's specific domain; they
are a repeatable audit you can run against any system, including one that
never shipped a `SMELLS.md` file telling you where to look.

## What you learned

- Strategic DDD's subdomain classification (core/supporting/generic)
  predicts this book's own extraction order before the roadmap ever states
  it: order is core and extracted last; inventory, payment, and shipping are
  supporting; notification and review are generic and extracted first.
- A bounded context's defining property (a private model, a public
  contract) is exactly what the monolith's shared `common` app and single
  Postgres schema erase; context mapping gives the resulting, undecided
  relationship a name (shared kernel with no edges, conformism instead of a
  negotiated customer/supplier contract) instead of leaving it undiagnosed.
- The missing anti-corruption layer at the order↔inventory seam is
  precisely a context-mapping decision nobody made: order should be
  inventory's customer, negotiating a stable contract; instead it conforms
  wholesale to a live `InventoryItem` instance, because that was the
  cheapest thing available, not because anyone chose it.
- Tactical DDD's aggregate and value-object rules show the monolith getting
  storage right (`OrderItem`'s snapshot columns) while still leaking at the
  call boundary (the live `InventoryItem` instance `reserve()` and
  `get_by_sku()` hand back); the notification edge shows what a fully cured
  seam looks like, outbox and all, before any service boundary is cut.
- Hexagonal architecture doesn't create a clean boundary; it makes one that
  already exists cheap to cut. Review's extraction proves the payoff on a
  real diff: its routes never imported a persistence detail, and its
  repository module was swapped from a Django ORM path dependency to async
  SQLAlchemy with almost no change to request handling, precisely because
  review had zero outbound edges to sibling business logic, the one
  property that mattered more than any port's literal shape. Its still-live
  dependency on the shared `auth_user` table is the reminder that a
  low coupling score on one axis doesn't mean zero coupling on every axis.

Chapter 12, "Event Storming the Monolith," takes a complementary approach to
everything this chapter just did by classification: instead of reading code
and sorting it into subdomains, it discovers seams from *behavior*: walking
the checkout process as a sequence of facts and decisions, and produces the
decomposition backlog the rest of Part 4 and Part 5 draw from.
