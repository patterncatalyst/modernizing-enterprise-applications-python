#!/usr/bin/env python3
"""ch.10 figure: test-pyramid: the monolith's real pytest-django shape, not
a textbook fully-mocked-collaborator pyramid. Counted directly from `examples/00-monolith/
tests/` (`python3 -m pytest --collect-only -q` -> "50 tests collected",
8 files, every file carrying `pytestmark = pytest.mark.django_db`):

  - 1 pure-unit test with no database at all: `test_order_snapshot.py::
    test_orderitem_has_no_inventory_item_fk` inspects `OrderItem._meta.
    get_fields()` directly.
  - 21 API/acceptance tests that go through `APIClient` end to end
    (`test_checkout.py`, `test_smoke.py`, `test_review_auth.py`, most of
    `test_outbox.py` and `test_order_snapshot.py`): real Postgres, real DRF
    view/serializer stack, real HTTP status codes.
  - 28 service/consumer integration tests that call `order.services.
    place_order()` or a saga/consumer handler function directly, no HTTP,
    but still against a real Postgres test database (`test_choreographed_
    checkout.py`, `test_grpc_checkout.py`, `test_orchestrated_shipping.py`,
    `test_outbox.py::test_record_order_placed_is_idempotent`).

Unlike a fully-mocked-collaborator unit-test pyramid, pytest-django gives no
free fully-isolated unit tier for anything beyond pure field/metadata
introspection: the moment
a test touches `order.services.place_order()` or a model manager, it needs
the `db` fixture and a real, disposable Postgres test database
(`pytest-django` creates/drops `test_<NAME>` per run). The widest tier here
is therefore service-level integration, not mocked units.

Sourced from `examples/00-monolith/tests/` and `AGENTS.md`'s own "Testing"
section ("Tests need a reachable Postgres"). No codenames; generic/public
names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1200, 780

CX = 600

# narrow at the top (pure unit, almost none), wide at the base (service/
# consumer integration, the real center of mass of this suite)
tier_unit = node(CX - 260, 120, 520, 150, [
    "Pure unit: no database",
    "1 test: test_order_snapshot.py::test_orderitem_has_no_inventory_item_fk",
    "inspects OrderItem._meta.get_fields() directly, no db fixture, no Postgres",
    "proves: the FK is really gone, the snapshot columns really exist",
], style="box")

tier_api = node(CX - 380, 310, 760, 150, [
    "API / acceptance: APIClient, real Postgres",
    "21 tests: test_checkout, test_smoke, test_review_auth, most of test_outbox/test_order_snapshot",
    "full DRF view -> serializer -> service -> model -> db stack, real HTTP status codes",
    "proves: does the checkout/review/smoke surface behave correctly end to end",
], style="box")

tier_service = node(CX - 490, 500, 980, 150, [
    "Service & consumer integration: direct calls, real Postgres",
    "28 tests: test_choreographed_checkout, test_grpc_checkout, test_orchestrated_shipping, outbox idempotency",
    "calls order.services.place_order() or a saga/consumer handler directly, no HTTP, db fixture required",
    "proves: does the saga/consumer logic transition status and compensate correctly",
], style="box")

nodes = [tier_unit, tier_api, tier_service]
edges = [
    connect(tier_unit, tier_api),
    connect(tier_api, tier_service, label="one `uv run pytest` run exercises all three tiers", amber=True),
]

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.10: the monolith's test shape: pytest-django, not a textbook fully-mocked pyramid",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": W / 2, "y": 56,
     "text": "8 files, 50 tests collected, every file django_db-marked: widest tier is service integration, not isolated units",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": CX - 490, "y": H - 32,
     "text": "Counted via `python3 -m pytest --collect-only -q` against examples/00-monolith/tests/ (50 tests collected).",
     "anchor": "start", "size": 10, "color": "#777777"},
    {"x": CX - 490, "y": H - 16,
     "text": "pytest-django creates/drops its own test_<NAME> Postgres database per run: see AGENTS.md's \"Testing\" section.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "test-pyramid", W, H,
    bands=[],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
