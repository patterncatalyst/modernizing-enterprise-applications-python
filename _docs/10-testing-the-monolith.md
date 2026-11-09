---
title: "Testing the Monolith (the Equivalence Suite)"
order: 10
part: "The Reference Monolith"
description: "A pytest whitebox suite guards the monolith's internals, and an unedited Newman contract collection proves every extraction behaves like what it replaced."
duration: 30 minutes
---

## Learning objectives

By the end of this chapter you can:

- State the one question each test layer answers that the other can't: a pytest-django whitebox suite for internals, a Newman blackbox collection for the HTTP surface.
- Explain why the whitebox tests run against a real Postgres database and why mocking `payment_services.charge()` would delete the rollback they exist to prove.
- Capture the Newman collection against the unmodified monolith as the behavior-equivalence baseline.
- Re-point the same collection at a monolith, a proxy or an extracted service with {% raw %}`{{baseUrl}}`{% endraw %} and an environment file.
- Write scenarios that capture their own "before" stock level, so the collection re-runs safely against a long-lived process.
- Apply the extraction rule: the collection is re-pointed, never rewritten, and a green run of the unedited file is what makes an extraction done.

## Why this matters

Each smell in the monolith has a cure, and no cure is safe without a way to prove afterward that nothing observable changed. That proof has two layers. A pytest/pytest-django suite knows the monolith's internals. A Newman (Postman) contract collection knows only its HTTP surface, and it becomes the equivalence gate that every extraction passes unmodified, against both the monolith and whatever replaces it.

## The whitebox tiers: pytest and pytest-django

`examples/00-monolith/tests/` is one flat directory, not nested per app, because checkout already crosses every app's boundary. `conftest.py` carries the shared fixtures: an `APIClient`, a `customer` and `other_customer` pair, a `widget` and a `low_stock_item`, a `reviewer_auth_header` for the Basic-auth gate, and a `confirmed_order` that drives one full checkout so the read-side tests have something to find.

Every module runs under `pytest.mark.django_db` against a real Postgres test database. The monolith's defining behavior is transactional: one `transaction.atomic()` spans five contexts, and a mocked ORM can't prove a rollback rolled back. There is no tier in between, such as checkout with inventory mocked out. Mocking `payment_services.charge()` would delete the thing under test, whether the shared transaction rolls every context back together.

| File | Behavior covered |
|---|---|
| `test_smoke.py` | Each `/api/*` surface answers 200 or 201; no context has gone missing. Closest to a unit tier: one endpoint, one field. |
| `test_checkout.py` | Happy path, over-order returns 409, `CARD-DECLINE` returns 402 and rolls back, `SHIP-FAIL` returns 422 and rolls back the whole checkout. |
| `test_outbox.py` | A checkout writes exactly one `order.placed` outbox row, a failed one writes none, and `record_order_placed()` is idempotent on redelivery. |
| `test_review_auth.py` | `POST /api/reviews` returns 401 without Basic auth and 201 with it; reads stay open even with a garbage `Authorization` header. |
| `test_order_snapshot.py` | An `OrderItem`'s sku and price snapshot survives a later inventory price change. |
| `test_grpc_checkout.py` | The gRPC-mode checkout path and its compensating `Release` calls. |
| `test_choreographed_checkout.py`, `test_orchestrated_shipping.py` | Saga-listener reactions once payment and shipping are asynchronous. |

The first four files cover the monolith as it stands, with no saga machinery. The rest exist because `place_order()` grows new code paths as `INVENTORY_MODE`, `PAYMENT_MODE` and `SHIPPING_MODE` flip. New behavior gets a new, additive test file, and the tests for the original behavior stay unmodified: add beside, verify, then default over.

No Kafka broker is needed. The outbox tests hand the stored payload straight to `notification.services.record_order_placed()` in-process.

{% include excalidraw.html file="test-pyramid" alt="Test pyramid for the monolith: a broad base of Django ORM/service-layer tests, a middle layer of DRF view tests via APIClient, and a thin top layer of full-stack checkout scenarios against real Postgres" caption="Figure 10.1: The monolith's whitebox pyramid" %}

Every one of these tests knows internals: it imports `order.services.place_order`, counts `OutboxEvent.objects`, refreshes an `InventoryItem` to read `quantity_on_hand`. That's what a whitebox test is for, proving a transaction boundary, an idempotency guard or a status-transition check. It can't answer the harder question: does a FastAPI service that has never heard of Django's ORM behave identically from outside?

## The blackbox layer: the Newman contract collection

`tooling/newman/mea.postman_collection.json` answers that question. It knows only HTTP: request in, status code and JSON body out. Every request uses {% raw %}`{{baseUrl}}`{% endraw %}. Point it at the monolith and it asserts the monolith's contract; point it at an extracted service and the same unedited requests assert that service's contract. Folders:

- **Smoke**: one reachability check.
- **Scenario 1 to 4**: the four checkout outcomes. Happy path (confirmed, stock decremented by exactly the ordered quantity), out-of-stock (409, stock untouched), payment declined (402, stock net-zero), shipping failure (422, stock net-zero).
- **One contract folder per context** (Review, Inventory, Payment, Shipping, Order, Notification): list, get and 404 shapes, camelCase field names, and for Review the 401/201 auth gate.
- **GraphQL Gateway Contract**: staged and inert until a gateway exists.

Each scenario captures its own "before" stock level as a collection variable instead of asserting an absolute number. That makes the collection safe to re-run against a long-lived process, which matters once it runs against a live strangler proxy during a cutover rather than a fresh database. Seed data comes from `manage.py seed` (100 widgets, 50 gadgets, 5 gizmos); the gizmo is seeded low so the out-of-stock scenario needs no setup.

`tooling/newman/GOLDEN-BASELINE.md` freezes the first run against the monolith directly: 14 requests, 28 test scripts, 42 assertions, all green on two consecutive runs, averaging 55 ms a response. In the file's words, that is "the externally observable HTTP behavior every later extraction will be held to, request-for-request, assertion-for-assertion," captured before any context left the monolith. The collection has since grown to include later contract folders and the staged GraphQL folder; the baseline records the Smoke, Scenario and contract shape it captured.

Environment files change the target without touching a request: `local.postman_environment.json` points {% raw %}`{{baseUrl}}`{% endraw %} at `http://localhost:8000` (the monolith) and `proxy.postman_environment.json` at `http://localhost:8888` (the strangler proxy). Re-pointing is choosing a different file for `newman run`:

```sh
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/local.postman_environment.json
```

{% include excalidraw.html file="whitebox-pyramid-vs-blackbox-equivalence" alt="Two parallel structures: the whitebox pytest pyramid testing the monolith's internals, versus the one flat Newman contract collection asserting only externally observable HTTP behavior, re-pointable at either the monolith or an extracted service" caption="Figure 10.2: Whitebox pyramid vs. blackbox equivalence: two different questions, two different shapes" %}

## From pyramid to gate

The two layers answer different questions for different people. The pyramid tells whoever changes `order/services.py` whether an internal invariant broke: the transaction still rolls back, the outbox write is still once per checkout, the status-transition guard still blocks a redelivered event. The collection tells everyone else whether the system as observed from outside still does what it did, whichever mechanism produced it.

That second property becomes the operating rule for every extraction: **the collection is never rewritten per extraction, only re-pointed.** When a context becomes its own service, the same collection runs against the new address. The extraction is done when that unedited run passes, not a modified version, not a subset, the same JSON file. The monolith's pytest suite stays a regression net for the monolith's internals while it runs. The collection keeps working after the monolith is frozen, against the strangler proxy and then the monolith-free services behind it, because it was never about the monolith. It is the contract the monolith happened to satisfy first.

Every claim that an extraction is safe rests on one piece of evidence: the unmodified collection staying green before and after cutover. Without it, "nothing broke" is an opinion. With it, it's a number: 42 assertions, run twice, zero failures.

> **Decision**
>
> Test internals with pytest against real Postgres; prove equivalence with the Newman collection through HTTP only. Never edit the collection to fit a new service: change the environment file, and fix the service until the same file passes.

> **🤖 Explore with your agent**
>
> "In `examples/00-monolith`, add a test next to `test_checkout.py` for a checkout whose second line item is out of stock, asserting the 409 leaves `InventoryItem.quantity_on_hand` and the `OutboxEvent` count unchanged. Use a real database, mock nothing, and don't edit any existing test or `tooling/newman/mea.postman_collection.json`."
>
> Check: `uv run pytest` passes, and `git status --short` lists one new file under `examples/00-monolith/tests/` and nothing under `tooling/`.

## Build, run, observe

Both layers run against the same stack, with nothing to install beyond the `dev` group:

```sh
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &

uv run pytest                                        # whitebox: 20+ cases, real Postgres
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/local.postman_environment.json   # blackbox: 14 requests, 42 assertions
```

pytest talks to Postgres and never goes over HTTP; Newman only goes over HTTP and never imports project code. Run both after any change to `order/services.py`. pytest catches a broken internal invariant (a transaction that didn't roll back, an idempotency guard that let a duplicate through). Newman catches a broken external contract (a renamed field, a changed status code, a missing `Location` header), which can slip past a whitebox test that asserts on the ORM object instead of the response body.

Check the description against the code, from the repository root:

```sh
ls examples/00-monolith/tests/*.py | wc -l        # 10 files (incl. conftest.py, __init__.py)
grep -c 'def test_' examples/00-monolith/tests/test_smoke.py     # 6
grep -c 'def test_' examples/00-monolith/tests/test_checkout.py  # 4
python3 -c "
import json
d = json.load(open('tooling/newman/mea.postman_collection.json'))
print('folders:', len(d['item']))
print('requests:', sum(len(f['item']) for f in d['item']))"
```

The first three match the file table. The collection prints 12 folders and 39 requests, more than the 14-request baseline, because the later contract folders and the staged GraphQL folder live in the same file.

Experiments:

- Run the Newman command with `proxy.postman_environment.json` once the strangler proxy is up: the same file runs against `http://localhost:8888`.
- Run Newman twice in a row without reseeding: scenarios capture their own "before" stock, so the second run passes.
