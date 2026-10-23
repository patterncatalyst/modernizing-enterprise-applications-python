---
title: "Testing the Monolith (the Equivalence Suite)"
order: 10
part: "The Reference Monolith"
description: "Unit and pytest/Testcontainers integration tests plus the Newman contract collection that becomes the behavior-equivalence suite for every later extraction."
duration: 30 minutes
---

Ch.9 named seven smells and pointed each one at the chapter that cures it.
None of those cures are safe to make without a way to prove, afterward,
that nothing observable changed. That proof has two layers in this project:
a pytest/pytest-django test suite that knows the monolith's internals, and
a Newman (Postman) contract collection that knows only its HTTP surface.
The first is a whitebox pyramid. The second becomes, starting in Part 5, a
blackbox equivalence gate: the suite every extraction has to pass,
unmodified, against both the monolith and whatever replaces it.

## pytest/pytest-django: the whitebox tiers

`examples/00-monolith/tests/` is one flat directory, not nested per app,
because most of what it tests, checkout, already crosses every app's
boundary. `tests/conftest.py` carries the shared fixtures: an `APIClient`,
a `customer`/`other_customer` pair, a `widget`/`low_stock_item` pair of
`InventoryItem`s (one with low stock on hand), a `reviewer_auth_header` for
the Basic-auth gate, and a `confirmed_order` fixture that drives a full
checkout once so the read-side smoke tests have something to find.

The suite runs against `pytest.mark.django_db` on every module: a real
Postgres-backed test database per run, not mocks standing in for the ORM.
That single choice is deliberate: this monolith's defining behavior is
transactional (one `transaction.atomic()` spanning five contexts), and a
mocked ORM cannot prove a rollback rolled back. Seven files cover
it:

| File | What it proves |
|---|---|
| `test_smoke.py` | One assertion per `/api/*` surface: all six contexts still serve 200/201, none have silently gone missing. |
| `test_checkout.py` | The happy path, the over-order → 409, the `CARD-DECLINE` → 402 rollback, and the `SHIP-FAIL` → 422 full-checkout rollback: smells 1 and 2's deterministic failure injections (ch.9). |
| `test_outbox.py` | Checkout writes exactly one `order.placed` outbox row; a declined/failed checkout writes zero; `record_order_placed()` is idempotent on redelivery: smells 5 and 6's cure (ch.9, ch.17). |
| `test_review_auth.py` | The 401/201 Basic-auth gate on `POST /api/reviews`, and that reads stay open even with a garbage `Authorization` header: smell 7 (ch.9, ch.15). |
| `test_order_snapshot.py` | `OrderItem`'s denormalized sku/price snapshot survives a later inventory price change (ch.19's FK-to-snapshot cure). |
| `test_grpc_checkout.py` | The gRPC-mode checkout path and its compensating `Release` calls, once inventory moves behind a network boundary (ch.19). |
| `test_choreographed_checkout.py`, `test_orchestrated_shipping.py` | The saga-listener reactions once payment and shipping become asynchronous collaborators (ch.22–25). |

The first four files are the ones this chapter is really about: they
exercise the monolith exactly as ch.8 and ch.9 describe it, with no saga
machinery in play yet. The remaining three exist because this is a living
codebase, not a frozen teaching snapshot: as later chapters flip the
`INVENTORY_MODE`/`PAYMENT_MODE`/`SHIPPING_MODE` flags ch.8 pointed at,
`place_order()` grows new code paths, and each one earns its own test file
rather than crowding the original four. That pattern (new behavior gets a
new, additive test file; the original tests for the original behavior stay
unmodified) is itself a small preview of how this book prefers to change
code: add beside, verify, then default over, never rewrite a passing test
to make room for a new one.

Within those four core files, the tests split cleanly by what they need
from the database. `test_smoke.py`'s six assertions are closest to a unit
tier: each one hits a single endpoint and checks for a non-404 response
and one field, nothing about cross-context interaction. `test_checkout.py`
and `test_outbox.py` are integration tests in every sense that matters:
they drive a real HTTP request through DRF's routing, through
`order.services.place_order()`, through four other contexts' `services.py`
modules, and all the way down to real committed (or rolled-back) rows in a
real Postgres database. There's no tier in between: no "unit test the
checkout service with inventory mocked out," because mocking out `payment_
services.charge()` would quietly delete the exact thing under test: whether
the shared transaction rolls every context back together. A
repository-layer mock would make the smell invisible to the test suite that
exists to prove it's real.

Run the whole suite with:

```sh
uv run pytest
```

against a throwaway Postgres container; no Kafka broker is required for
any of it: `test_outbox.py` proves the outbox write and the consumer's
idempotency directly, in-process, by handing the stored payload straight to
`notification.services.record_order_placed()` rather than requiring a live
broker in the loop.

{% include excalidraw.html file="test-pyramid" alt="Test pyramid for the monolith: a broad base of Django ORM/service-layer tests, a middle layer of DRF view tests via APIClient, and a thin top layer of full-stack checkout scenarios against real Postgres" caption="Figure 10.1: The monolith's whitebox pyramid" %}

Every one of these tests knows the monolith's internals: it imports
`order.services.place_order` directly, inspects `OutboxEvent.objects.count()`,
refreshes an `InventoryItem` from the database to check `quantity_on_hand`.
That's exactly what a whitebox test is for: proving a specific internal
mechanism (a transaction boundary, an idempotency guard, a status-transition
check) behaves correctly. None of it can answer a different, harder
question this book needs answered over and over, starting in Part 5: does
an *entirely different system* (a FastAPI service that has never heard of
Django's ORM) behave identically from the outside?

## The Newman contract collection: the blackbox layer

`tooling/newman/mea.postman_collection.json` answers that question. It is
a Postman collection, driven by the `newman` CLI, that knows nothing about
Django, pytest, or the ORM, only HTTP: request in, status code and JSON
body out. Every request is parameterized by `{{baseUrl}}`, and that one
variable is the whole mechanism this collection is built around: point it
at the monolith, and it asserts the monolith's contract; point it at an
extracted FastAPI service instead, and the exact same, unedited requests
assert that service's contract. The collection is organized into folders:

- **Smoke**: one reachability check.
- **Scenario 1–4**: the four checkout outcomes end to end: happy path
  (confirmed, stock decremented by exactly the ordered quantity),
  out-of-stock (409, stock untouched), payment-declined (402, stock
  net-zero), and shipping-failure (422, stock net-zero). Each scenario
  captures its own "before" stock level as a collection variable rather
  than asserting an absolute number, so the suite is safe to re-run against
  a long-lived process.
- **Review / Inventory / Payment / Shipping / Order / Notification Context
  Contract**: one folder per bounded context, asserting that context's own
  REST surface directly: list/get/404 shapes, camelCase field names, and
  (for Review) the exact 401/201 auth-gate contract ch.9 named as smell 7.
- **GraphQL Gateway Contract**: staged, inert at this point in the book;
  it exercises a gateway that doesn't exist yet until later chapters stand
  one up.

`tooling/newman/GOLDEN-BASELINE.md` freezes the first run of this
collection against the monolith directly: 14 requests, 28 test scripts, 42
assertions, all green, confirmed on two consecutive runs, averaging 55ms a
response. That frozen record is the contract itself: "the externally
observable HTTP behavior every later extraction will be held to,
request-for-request, assertion-for-assertion," in the file's own words,
captured before any context has been pulled out of this monolith at all.
Stock levels for the run came straight from `manage.py seed` (100 widgets,
50 gadgets, 5 gizmos, the last one seeded low so the
out-of-stock scenario needs no extra setup); no manual data manipulation
happens before or between runs, because every scenario captures its own
"before" stock level as a collection variable rather than asserting an
absolute number. That's what makes the collection safe to re-run
indefinitely against the same long-lived process, which matters once it's
being re-run against a live strangler proxy during an actual cutover window
(ch.14 onward) rather than a fresh database every time.

Two environment files point `{{baseUrl}}` at different targets without
touching a single request in the collection: `local.postman_environment.json`
(`http://localhost:8000`, the monolith directly, what this chapter runs)
and `proxy.postman_environment.json` (`http://localhost:8888`, the
strangler proxy ch.14 builds). Re-pointing the collection is changing which
environment file `newman run` loads, nothing else:

```sh
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/local.postman_environment.json
```

{% include excalidraw.html file="whitebox-pyramid-vs-blackbox-equivalence" alt="Two parallel structures: the whitebox pytest pyramid testing the monolith's internals, versus the one flat Newman contract collection asserting only externally observable HTTP behavior, re-pointable at either the monolith or an extracted service" caption="Figure 10.2: Whitebox pyramid vs. blackbox equivalence: two different questions, two different shapes" %}

## Build, run, observe

Both layers run against the same stack ch.8 stood up, with nothing extra to
install beyond the `dev` dependency group:

```sh
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000 &

uv run pytest                                        # whitebox: 20+ cases, real Postgres
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/local.postman_environment.json   # blackbox: 14 requests, 42 assertions
```

Pytest talks to Postgres directly and never goes over HTTP; Newman only
ever goes over HTTP and never imports a line of this project's Python.
Running both back to back after any change to `order/services.py` is the
cheapest way to catch the two different kinds of regression each layer is
built to catch: pytest catches a broken internal invariant (the transaction
didn't roll back, the idempotency guard let a duplicate through); Newman
catches a broken external contract (a field got renamed, a status code
changed, the `Location` header went missing), the kind of regression that
can slip past a whitebox suite entirely if the test asserts on the ORM
object instead of the response body.

## Cross-check

A quick gut check that this chapter's description matches the running
code, run once by hand before trusting it on faith:

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

The first two numbers match the table above exactly; the third confirms the
collection has grown since the frozen baseline: later forward-ref
context-contract folders and the staged GraphQL folder already live in the
same file this chapter describes, even though this chapter's own scope is
the Smoke/Scenario/contract shape the baseline run captured. That habit
(checking a chapter's claims against the artifact it describes, not just
against memory of having read it once) is the same discipline this whole
book asks of every extraction starting in Part 5.

## From pyramid to gate: the rule that makes extraction safe

The whitebox pyramid and the blackbox collection are not redundant with
each other; they answer different questions, at different layers, for
different audiences. The pyramid tells the person changing
`order/services.py` whether their change broke an internal invariant: did
the transaction still roll back, is the outbox write still exactly-once
per checkout, does the status-transition guard still block a redelivered
event. The collection tells everyone else (a reviewer, an operator, a
later chapter cutting a seam) whether the system *as observed from
outside* still does what it did before, regardless of which internal
mechanism produced that behavior.

That second property is what Part 5 turns into an operating rule, starting
in ch.14: **this collection is never rewritten per extraction, only
re-pointed.** Once a chapter pulls a context out of the monolith and stands
it up as its own service, the exact same, unedited collection gets run
again against the new service's own address. A context is only "done"
being extracted once that unedited run passes: not a modified version of
it, not a subset, the same JSON file, byte for byte. The monolith's pytest
suite stays useful as a regression net on the monolith's own internals for
as long as the monolith keeps running; the Newman collection is what
proves equivalence, because it is the one artifact in this
project that was built to not care which system answers it.

That is also why this chapter's test suite matters even after the
monolith itself is retired. By the time Part 5 finishes extracting every
context, `examples/00-monolith` is frozen and no live traffic reaches it,
but `tooling/newman/mea.postman_collection.json` is still running, against
the strangler proxy and then against the monolith-free mesh behind it,
because the collection was never about the monolith specifically. It was
always about the contract the monolith happened to be the first system to
satisfy.

That's also the plain answer to a question that deserves asking directly:
why does a chapter about tests matter this much in a book about
decomposing a monolith? Because every claim the chapters after this one
make about an extraction being safe rests on exactly one piece of evidence: an
unmodified collection staying green before and after the cutover. Without
that collection existing first, "this extraction didn't break anything"
would be an opinion. With it, it's a number: 42 assertions, run twice,
zero failures, same as the first time anyone ran it against code that had
never been touched by a strangler proxy at all.

Next: Part 4 steps back from this running code to the design vocabulary
behind it: subdomains, bounded contexts, aggregates, and why review's lack
of coupling (smell 7, ch.9) is also the reason it leaves the monolith
first.
