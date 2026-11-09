---
title: "Content-Based Routing & the Anti-Corruption Layer"
order: 16
part: "The Strangler Fig in Practice"
description: "Routing decides which backend answers; the anti-corruption layer decides what crosses the seam. The proxy's path-prefix if generalizes to headers and payloads, and a Pydantic event model turns a Kafka message into a contract."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- Tell what content-based routing decides (which backend answers a request) from what an anti-corruption layer decides (what is safe to carry across once the request is there).
- Generalize `_select_backend()` from a path-prefix `if` to a header-based or payload-based predicate while keeping its one invariant: a forwarding target comes from operator configuration, never from caller-supplied data.
- Say why review-service's shared-table reads need no ACL and notification-service's Kafka consumer does.
- Read `OrderPlacedEvent` as a contract: a service-owned Pydantic model that validates and raises on a mismatch.
- Make the monolith a peer subscriber to its own `order.placed` event instead of keeping a privileged synchronous path.

## Why this matters

The first extraction needed one routing decision: one path prefix, one flag, one backend. The second extraction needs two things the first did not. The router has to grow without being rewritten, and the new service has to decide for itself what it accepts from the monolith's event stream.

The two ideas sit at the same seam and answer different questions. Routing gets a request to the right side. The ACL decides what is allowed to cross once it is there. The code is in `examples/01-strangler-proxy/app/main.py` (routing) and `examples/03-notification-service/app/schemas.py` (the ACL).

{% include excalidraw.html file="notification-content-based-routing" alt="One routing topology: client through the strangler proxy to one of three backends (monolith default, review-service on a path-prefix match, notification-service on a path-prefix match), with a side panel naming header- and payload-based routing as generalizations of the path-prefix predicate" caption="Figure 16.1: One routing decision, generalized past a single URL-path predicate" %}

## Pattern: Content-Based Router

A content-based router inspects a message and uses what it finds to choose the next destination. The proxy's settings now carry two independent flag and base-URL pairs:

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

`_select_backend()` is the one function that decides where a request goes, and the second seam added one `if`:

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

Each new seam is a field pair named `STRANGLER_<CONTEXT>_ENABLED` and `STRANGLER_<CONTEXT>_BASE_URL` plus one `if`. Nothing else in the proxy changes.

What makes this a content-based router is the shape of the predicate, not its current input. Today it reads the full request path. The same shape takes other inputs:

| Predicate | Routes on | Example |
| --- | --- | --- |
| Path (built) | `request.url.path` | `/api/notifications*` goes to notification-service |
| Header | `request.headers["X-Tenant-Id"]` | One tenant's traffic goes to a dedicated backend |
| Payload | A field in the body | Orders above a total, or a customer segment, go to a dedicated backend |

Only the path predicate is built, because two REST extractions need nothing more. What never changes is the contract: settings in, a base URL out. The values that choose a destination must come from configuration set by whoever operates the proxy. A router that built its target from a caller-supplied header or body field would give an attacker a request-driven redirect to an arbitrary host (SSRF), and changing the predicate's shape doesn't reopen that hole as long as the target stays in `Settings`.

## Where routing stops helping

Routing answers which backend should see a request. It says nothing about what that backend may assume about the data it receives.

Review needed no answer to the second question. `examples/02-review-service` reads and writes the same Postgres tables the monolith uses (`reviews`, `customers`, `inventory_items`, `auth_user`). Both sides agree on the data's shape because they read the identical table, and the seam is a synchronously consistent REST leaf. That shared-table choice is a named deferral.

Notification can't do the same. It is reached asynchronously over Kafka by a consumer with no request/response tie to whatever wrote the event. If it shared the monolith's `notifications` table, two independent writers (the monolith's synchronous path and the service's consumer) would race on the same rows with no transaction between them. That is a split-brain, not a simplification. So the dividing line is: routing decides who answers, the ACL decides what crosses.

## Pattern: Anti-Corruption Layer

Eric Evans's anti-corruption layer is usually introduced as a wall that keeps a legacy model out of a new one. That framing makes it sound like the job is filtering bad data. A more useful framing: an ACL turns a request into a contract. A request asks the other side to do something and trusts what comes back. A contract states, in this side's own terms, exactly what crosses and nothing else.

{% include excalidraw.html file="acl-contract-seam" alt="Two panels: Panel A shows review-service reaching directly into the monolith's shared Postgres tables with no anti-corruption layer; Panel B shows notification-service's OrderPlacedEvent as a translation boundary between the monolith's Kafka contract and the service's own owned schema" caption="Figure 16.2: The ACL is a translation boundary, not just another request" %}

`OrderPlacedEvent` is that contract:

```python
class OrderPlacedEvent(BaseModel):
    """This service's own copy of the frozen `order.placed` JSON payload:
    topic `order.placed`, key = `orderId` (string).
    Field names and types match the producer side byte-for-byte so Pydantic
    round-trips the JSON value without any custom deserializer. There is no
    shared module between the monolith and this service (each is an
    independently deployable project) -- this duplication is the honest cost
    of a hand-maintained JSON wire contract until a schema registry replaces it."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
```

Three properties make it the ACL rather than decoration around one:

1. **It's this service's own copy, not an import.** A shared `events.py` that both services depend on would let one change ripple into both at once, which is the coupling an extraction exists to remove. Each side owns the shape it expects, and the two copies agree by discipline until a schema registry enforces it.
2. **It validates instead of deserializing.** `OrderPlacedEvent.model_validate(record.value)` yields a value the service can trust or raises. A plain `json.loads()` returns a `dict` with whatever keys happen to be present, and a mismatch surfaces as a `KeyError` three calls deeper.
3. **Nothing past it knows Kafka's JSON exists.** `record_order_placed` takes an `OrderPlacedEvent`, not a `dict` or a `ConsumerRecord`. The rest of the service speaks its own vocabulary (`order_id`, `customer_id`, `int`, `str`, `datetime`).

Review's posture at the same seam is the contrast. `app/models.py` maps SQLAlchemy classes onto the monolith's own table names (`__tablename__ = "reviews"`), and `app/repository.py` joins across them by hand. There is no translation step because there is no contract: at the data layer, review-service and the monolith are one system with two HTTP front ends. That is a legitimate choice for a REST leaf with no eventual-consistency problem, but it is not an ACL.

## The monolith consumes its own event

Once `place_order()` stops calling notification code directly and writes an outbox row instead, something must still turn that row into a `Notification` record. The monolith's `GET /api/notifications` read path hasn't moved yet and won't until `STRANGLER_NOTIFICATION_ENABLED` flips for good.

So the monolith becomes a consumer of its own event. `notification/management/commands/order_placed_consumer.py` subscribes to `order.placed` under its own consumer group (`monolith-notification`) and repopulates the `Notification` table the old synchronous code wrote directly.

That is the decorating collaborator: rather than keeping a privileged in-process path while the new service gets a second-class asynchronous one, both become peers of one topic. It is also what makes the ACL necessary. With two independent subscribers, the only thing preventing them from diverging on what a field means is each subscriber's own translation of the contract.

## Before and after at the seam

{% include codetabs.html langs="app/config.py: one flag|app/config.py: two flags, same shape" %}

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

The routing diff is additive and symmetric, so a third extraction repeats it: one field pair, one `if`. The ACL side has no "before" to diff against. `OrderPlacedEvent` is net-new, written the first time an extraction needs one, and the Review extraction never needed it.

Later seams change the transport (an inventory check over gRPC instead of a path or a topic) but not the two questions. Something still picks the backend, and something still owns the translation between the monolith's view of an `InventoryItem` and the new service's shape.

> **Decision**
>
> Route on any property of the request, but take the destination only from operator configuration. Add an ACL when the seam is asynchronous or the two sides would otherwise write the same data: the receiving service owns its copy of the contract and validates against it.

> **🤖 Explore with your agent**
>
> "In `examples/01-strangler-proxy/app/main.py`, add a header-based predicate on `X-Tenant-Id` to `_select_backend()` that chooses between two base URLs held in `Settings`. Add routing tests proving a caller-supplied header value can never become the forwarding target."
>
> Check: `cd examples/01-strangler-proxy && uv run pytest -k routing`, and confirm a hostile header value still resolves to a URL from `Settings`.

## Build, run, observe

The two-flag proxy is at the `stage/02-notification` tag (`git checkout stage/02-notification`); on `main` the proxy is a flagless edge router.

```bash
cd examples/01-strangler-proxy
uv run pytest -k routing
uv run ruff check .
```

The routing tests cover all three flag combinations. To drive the live proxy, start `examples/02-review-service` on `:8001` and `examples/00-monolith` on `:8000`, then run:

```bash
STRANGLER_REVIEW_ENABLED=true STRANGLER_NOTIFICATION_ENABLED=false \
  uv run uvicorn app.main:app --port 8888
```

`/api/reviews*` reaches the review service while `/api/notifications*` still reaches the monolith. The two flags are independent: `/api/reviews*` is unaffected by `STRANGLER_NOTIFICATION_ENABLED`, and the reverse.

- Set `STRANGLER_NOTIFICATION_ENABLED=true` with no notification-service on `:8002`: `/api/notifications*` returns the proxy's 502 while `/api/reviews*` keeps working.
