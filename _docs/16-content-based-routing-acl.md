---
title: "Content-Based Routing & the Anti-Corruption Layer"
order: 16
part: "The Strangler Fig in Practice"
description: "The strangler proxy's routing decision generalized past a URL path, and the anti-corruption layer as a contract rather than a request; the pattern ch.17's notification extraction puts to work and every later extraction in Part 5 reuses."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- Distinguish what content-based routing decides (which backend answers a request) from what an anti-corruption layer decides (what is safe to carry across once routing gets it there), even though both sit at the same seam.
- Generalize `_select_backend()`'s path-prefix `if` into a header-based or payload-based predicate, while keeping its one invariant fixed: a forwarding target must always come from operator configuration, never from caller-supplied data.
- Explain why review-service's shared-table reads need no ACL (a synchronously-consistent REST leaf) while notification-service's Kafka consumer does, using the two-independent-writers/split-brain argument.
- Read `OrderPlacedEvent` in `app/schemas.py` as a contract rather than a request: a service-owned Pydantic model that validates and raises on a mismatch instead of silently deserializing into a half-populated value.
- Apply the decorating-collaborator pattern: the monolith's own `order_placed_consumer.py` becomes a peer subscriber to `order.placed` rather than keeping a privileged synchronous path, which is what makes the ACL necessary instead of ceremony.
- Explain why the routing change is additive and symmetric (one more `Settings` field pair, one more `if`) while the ACL side has no "before" to diff against, since `OrderPlacedEvent` is net-new for the first extraction that actually needs one.
- Verify the generalized routing claim by running `pytest -k routing` against all three flag combinations and driving the live proxy with both flags toggled independently.

## Why this matters

ch.15 cut one seam and proved the extraction loop end to end: capture the
contract, stand up the service, flip a flag, watch the equivalence suite go
green. That chapter's routing decision was a single `if`: one path prefix,
one flag, one backend. This chapter generalizes that decision into a named
pattern (content-based routing) and introduces its quieter, more consequential
sibling: the anti-corruption layer, the thing that decides what's allowed to
cross a seam once routing alone has gotten a request to the right side of it.
ch.17 puts both to work on the notification extraction; ch.19's inventory
seam reuses the same two ideas against a harder case (a real-time stock
read, not a fire-and-forget event).

This chapter's code spans two examples already in this repo rather than
introducing a new one: `examples/01-strangler-proxy/app/main.py` (the routing
side, now carrying a second flag) and `examples/03-notification-service/app/schemas.py`
(the ACL side, `OrderPlacedEvent`). Both are built and verified; ch.17 walks
`examples/03-notification-service` in full.

{% include excalidraw.html file="notification-content-based-routing" alt="One routing topology: client through the strangler proxy to one of three backends (monolith default, review-service on a path-prefix match, notification-service on a path-prefix match), with a side panel naming header- and payload-based routing as generalizations of today's path-prefix predicate" caption="Figure 16.1: One routing decision, generalized past a single URL-path predicate" %}

## Content-based routing, generalized past a URL path

"Content-based routing" is the Enterprise Integration Patterns name for a
component that inspects something about a message and uses that to choose
where the message goes next, rather than every message always going to the
same place. ch.14's proxy already does this, but it's easy to read that
implementation as "a path-prefix `if`" rather than an instance of the general
pattern, so this section names the generalization explicitly before ch.17
adds a second flag to the same function.

`examples/01-strangler-proxy/app/config.py` now carries two independent
pairs of settings, not one:

```python
@dataclass(frozen=True, slots=True)
class Settings:
    """Strangler proxy configuration, read once from the environment."""

    port: int = 8888
    review_enabled: bool = False
    monolith_base_url: str = "http://localhost:8000"
    review_base_url: str = "http://localhost:8001"
    notification_enabled: bool = False
    notification_base_url: str = "http://localhost:8002"
```

And `_select_backend()`, the one function that decides where any given
request goes, grew one more `if`, not a rewrite:

```python
def _select_backend(settings: Settings, path: str) -> str:
    """Operator-configured, request-independent target selection.

    Never builds a target from request data (header, query string, path
    segment) -- only ever from the two fixed base URLs in ``settings`` --
    which keeps this proxy's dynamic-URI seam closed to SSRF: no caller can
    redirect it to an arbitrary host.
    """
    if settings.review_enabled and path.startswith("/api/reviews"):
        return settings.review_base_url
    if settings.notification_enabled and path.startswith("/api/notifications"):
        return settings.notification_base_url
    return settings.monolith_base_url
```

That's the whole story of adding a second extracted service to this proxy:
one more `Settings` field pair, one more `if`, in the same function, with
the same shape as the one before it. Nothing about the function's structure
had to change to accommodate a second seam, which is itself evidence that
`_select_backend()` was designed as a real content-based router from the
start, not a one-off special case that happened to work for Review.

What makes this a *content-based* router rather than just "an `if`
statement" is the shape of the predicate, not its current implementation:
the function inspects something about the inbound message and routes on
what it finds. Today that something is `request.url.path`, the full path,
per ch.14's full-path-prefix lesson, never a value relative to a mount
point. But the predicate's *shape* generalizes cleanly to other things a
router could inspect:

- **Header-based.** Route on `request.headers["X-Tenant-Id"]` to send one
  tenant's traffic to a dedicated backend, without touching the path at all.
- **Payload-based.** Route on something in the body, an order's total, a
  customer's segment, the pattern Enterprise Integration Patterns calls
  content-based routing in its narrowest sense, where the "content" really
  is the message content, not just its address.

None of that is built here: this proxy only ever matches a path prefix,
because that's all two REST extractions actually need. The reason the
generalization matters anyway is what *doesn't* change if a future
chapter needed it: `_select_backend()`'s contract (settings in, a base URL
out, read only from operator configuration) stays exactly the same no
matter which property of the request the predicate inspects. The one rule
that never generalizes away, regardless of which dimension a future router
adds: the values that choose a destination have to come from configuration
set by whoever operates the proxy, never from anything a caller controls.
A router that built a forwarding target from a caller-supplied header or
body field would be handing an attacker a request-driven redirect to an
arbitrary host, the same SSRF class ch.14's design note already closed for
the path-based case, and it doesn't reopen just because the predicate
changed shape.

## Where content-based routing stops helping

Routing answers one question: *which backend should see this request?*
It has nothing to say about a second, different question: *what is this
backend allowed to assume about the data it receives?* ch.15's review
extraction answered that second question by *not answering it*: a
deliberate, named deferral, not an oversight. `examples/02-review-service`
reads and writes the exact same Postgres tables
(`reviews`, `customers`, `inventory_items`, `auth_user`) the monolith
itself uses. Routing got the request to the right process; nothing
translates or filters what that process does once it gets there, because
there's nothing to translate yet: both sides agree on the shape of the
data by construction, since they're reading the identical table.

That arrangement works for Review specifically because Review only ever
*reads* a synchronously-consistent REST contract against a shared schema.
It stops working the moment a seam needs to decouple two services' *data
models*, not just their processes, which is exactly notification's
situation. `examples/03-notification-service` cannot share the monolith's
`notifications` table the way review-service shares `reviews`, because it
isn't reached synchronously over HTTP; it's reached asynchronously over
Kafka, by a consumer that has no request/response relationship with
whatever wrote the event. Two independent writers, the monolith's
decommissioned-in-progress synchronous path and this service's own
consumer, racing on the same rows with no transaction tying them together
is a split-brain waiting to happen, not a simplification. That's the
dividing line this chapter draws: **routing decides who answers; the ACL
decides what crosses.** Once a seam needs the second answer, something has
to own it, and "nothing, we'll just share the table" isn't an available
option anymore.

## The ACL as a contract, not a request

{% include excalidraw.html file="acl-contract-seam" alt="Two panels: Panel A shows review-service reaching directly into the monolith's shared Postgres tables with no anti-corruption layer; Panel B shows notification-service's OrderPlacedEvent as a translation boundary between the monolith's Kafka contract and the service's own owned schema" caption="Figure 16.2: The ACL is a translation boundary, not just another request" %}

Eric Evans's anti-corruption layer is usually introduced as a defensive
wall: a seam that stops a legacy system's bad model from leaking into a new
one. That framing is accurate but easy to over-apply: it makes it sound
like the ACL's job is filtering out *bad* data, which invites the question
"but the monolith's data isn't bad, so do we even need one?" The more
useful framing for this book: **an ACL is what turns a request into a
contract.** A request asks the other side to do something and trusts
whatever comes back. A contract specifies, in writing, on *this* side's own
terms, exactly what crosses, and nothing else does, no matter what the
other side might also be willing to send.

`examples/03-notification-service/app/schemas.py::OrderPlacedEvent` is
that contract, made concrete:

```python
class OrderPlacedEvent(BaseModel):
    """This service's own copy of the frozen `order.placed` JSON payload
    (STEP 0 contract): topic `order.placed`, key = `orderId` (string).
    Field names and types match the producer side byte-for-byte so Pydantic
    round-trips the JSON value without any custom deserializer. There is no
    shared module between the monolith and this service (each is an
    independently deployable project) -- this duplication is the honest cost
    of a hand-maintained JSON wire contract with no schema registry until
    ch.28/Apicurio."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
```

Three things about this class are the ACL, not decoration around it:

1. **It is this service's own copy, not an import.** There is no shared
   `events.py` module `00-monolith` and `03-notification-service` both
   depend on. If there were, a change to that shared module could ripple
   into both services simultaneously, exactly the coupling an extraction
   exists to remove. Instead, each side owns its own copy of the shape it
   expects, and the two copies agreeing is a fact maintained by discipline
   (and, eventually, by ch.28's schema registry), not enforced by the
   language's import system.
2. **It validates, it doesn't just deserialize.** `OrderPlacedEvent.model_validate(record.value)`
   (in `app/consumer.py`, walked in full in ch.17) either produces a value
   this service's own code can trust completely, or raises. There is no
   third option where a malformed or unexpected payload silently becomes a
   half-populated Python object. A plain `json.loads()` call would hand the
   consumer a `dict` with whatever keys happened to be present; the
   `BaseModel` subclass is what makes "this event doesn't match the
   contract" a loud, catchable failure instead of a `KeyError` three calls
   deeper in `app/service.py`.
3. **Nothing past this class knows Kafka's JSON exists.** `app/service.py::record_order_placed`
   takes an `OrderPlacedEvent`, not a `dict` and not a Kafka `ConsumerRecord`.
   The translation already happened by the time persistence logic sees
   anything. That's what "contract, not a request" means concretely: the
   rest of the service is written against this service's own vocabulary
   (`order_id`, `customer_id`, Python `int`/`str`/`datetime`), never
   against the wire format a different team, in a different codebase,
   happened to choose.

Compare that to review-service's posture at the same seam, named directly
rather than glossed over: `examples/02-review-service/app/models.py` maps
SQLAlchemy classes directly onto the monolith's own table names
(`__tablename__ = "reviews"`), and `app/repository.py` joins across them by
hand. There's no translation step, because there's no contract: review-service
and the monolith are, at the data layer, still the same system wearing two
different HTTP front ends. That's a legitimate, explicitly-scoped choice
for a REST leaf with no eventual-consistency problem (ch.18's
shared-data-to-owned-data gives it a real cure later), but it is not an ACL,
and this chapter's point is naming that difference rather than treating
every extraction as automatically ACL-shaped just because it has its own
service.

## The decorating collaborator: the monolith becomes a consumer of its own event

One more piece of vocabulary belongs here before ch.17 builds it in full,
because it's the move that makes the ACL's existence necessary in the first
place rather than optional. Once `order.services.place_order()` stops
calling notification code directly and starts writing an outbox row
instead (ch.17's transactional outbox), *something* still has to turn that
row into a `Notification` record the monolith's own, still-live
`GET /api/notifications` endpoint can serve, because that endpoint's
read path hasn't moved yet, and won't, until `STRANGLER_NOTIFICATION_ENABLED`
flips for good. The answer this project takes: the monolith becomes a
consumer of its own event. `notification/management/commands/order_placed_consumer.py`
subscribes to `order.placed` under its own consumer group
(`monolith-notification`) and repopulates the exact same `Notification`
table the old synchronous code used to write directly.

That's the *decorating collaborator* pattern: rather than the monolith
keeping a privileged, synchronous, in-process path to its own data while
the new service gets a second-class, asynchronous one, both sides become
peers of the same event, one more subscriber decorates the topic, not a
special case bolted onto checkout. Naming it here matters because it's the
detail that makes this chapter's ACL actually necessary rather than
optional ceremony: once the monolith is *also* just a consumer of
`order.placed`, the only thing standing between "two independent
subscribers to one topic" and "two subscribers quietly diverging on what a
field means" is each subscriber's own translation of the contract. Ch.17
walks both consumers side by side, the monolith's Django management
command and the FastAPI service's `aiokafka` consumer, doing the identical
job against the identical event, through two independent translations of
the same contract.

## Before and after at the seam

{% include codetabs.html langs="app/config.py: before ch.17 (one flag)|app/config.py: after ch.17 (two flags, same shape)" %}

```python
@dataclass(frozen=True, slots=True)
class Settings:
    """Strangler proxy configuration, read once from the environment."""

    port: int = 8888
    review_enabled: bool = False
    monolith_base_url: str = "http://localhost:8000"
    review_base_url: str = "http://localhost:8001"
```

```python
@dataclass(frozen=True, slots=True)
class Settings:
    """Strangler proxy configuration, read once from the environment."""

    port: int = 8888
    review_enabled: bool = False
    monolith_base_url: str = "http://localhost:8000"
    review_base_url: str = "http://localhost:8001"
    notification_enabled: bool = False
    notification_base_url: str = "http://localhost:8002"
```

The diff is additive and symmetric: a second flag/base-URL pair, following
the exact naming convention the first one set (`STRANGLER_<CONTEXT>_ENABLED`,
`STRANGLER_<CONTEXT>_BASE_URL`), which is what makes `_select_backend()`'s
one-more-`if` change (shown above, in "Content-based routing, generalized")
a safe, mechanical addition rather than a redesign. A third extraction
(ch.19's inventory, or ch.24's shipping) adds the same shape again: one
field pair in `Settings`, one `if` in `_select_backend()`, nothing else in
this proxy changes.

The ACL side of "before and after" isn't a diff on an existing file,
because there was no "before" to diff against: `OrderPlacedEvent` is
net-new, authored for this extraction rather than adapted from something
the monolith already had. That asymmetry (routing extends an existing
pattern; the ACL is built from scratch for the first time an extraction
actually needs one) is itself notable: ch.15's review extraction
never needed this section at all.

## What this sets up for ch.19's inventory seam

Every piece of vocabulary this chapter names gets reused, not re-derived,
the next time Part 5 cuts a harder seam. ch.19 extracts `inventory` behind
a gRPC call instead of a REST path or a Kafka topic, which changes the
*transport* the routing decision and the ACL operate over, but not the
two questions this chapter separated. Something will still decide which
backend answers a stock-level check (routing, generalized here past a URL
path to "whatever property of the request/call carries the signal"), and
something will still own the translation between the monolith's view of an
`InventoryItem` and whatever shape the new service exposes over gRPC (the
ACL, generalized here past "a Pydantic model for one Kafka event" to
"whatever owns the contract for this particular seam"). Readers who
internalize this chapter's two-question split will recognize both halves
immediately in ch.19, even though neither HTTP paths nor Kafka topics are
involved there.

## Cross-check

Confirm the generalized routing claim directly rather than taking the
prose's word for it. `examples/01-strangler-proxy/tests/test_routing.py`
exercises `_select_backend()` under all three flag combinations the real
function now supports:

```bash
cd examples/01-strangler-proxy
uv run pytest -k routing
uv run ruff check .
```

Then drive the live proxy with both flags independently toggled, confirming
each is fully independent of the other (a request to `/api/reviews*`
is unaffected by `STRANGLER_NOTIFICATION_ENABLED`, and vice versa):

```bash
STRANGLER_REVIEW_ENABLED=true STRANGLER_NOTIFICATION_ENABLED=false \
  uv run uvicorn app.main:app --port 8888
```

With `examples/02-review-service` on `:8001` and `examples/00-monolith` on
`:8000`, `/api/reviews*` should reach the review service while
`/api/notifications*` still reaches the monolith: the two flags composing
without interference is the generalization claim made concrete.

## What you learned

- Content-based routing is "inspect something about the message, choose
  the destination from it." This proxy generalizes from one path-prefix
  predicate to two without changing `_select_backend()`'s shape, and the
  same shape extends to header- or payload-based predicates a future
  extraction might need.
- Routing and the anti-corruption layer answer different questions: routing
  decides *which backend sees a request*; the ACL decides *what that
  backend is allowed to assume about the data it receives*. A seam can need
  one without the other: review-service needed only routing; notification
  needs both.
- An ACL is a contract, not a request: notification-service's own
  `OrderPlacedEvent` copy validates and translates the wire format into this
  service's own vocabulary before any business logic sees it, and nothing
  past that boundary knows Kafka's JSON shape exists.
- The decorating-collaborator pattern, the monolith becoming a consumer of
  its own event, as a peer subscriber rather than a privileged synchronous
  path, is what makes the ACL necessary rather than ceremonial: two
  independent subscribers to one topic need their own correct translation
  of what they're reading.
- The invariant that survives every generalization of routing: the values
  that choose a destination must come from operator configuration, never
  from anything a caller controls.

Next: ch.17 builds the extraction this chapter set up: notification's
transactional outbox, its idempotent `aiokafka` consumer, and the two-flag
cutover proven live against a real Kafka broker.
