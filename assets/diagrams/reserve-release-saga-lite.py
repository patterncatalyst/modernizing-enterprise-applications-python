#!/usr/bin/env python3
"""ch.19 figure: reserve-release-saga-lite -- where the free rollback went.

BEFORE (INVENTORY_MODE=local, r01-r03): reserve/order/payment/shipping/
outbox all run inside ONE `transaction.atomic()`. A PaymentDeclined or
ShippingFailed anywhere in that chain unwinds EVERYTHING, including the
inventory decrement automatically -- Postgres's own rollback, SMELL[ch.22]'s
"free rollback."

AFTER (INVENTORY_MODE=grpc, ch.19): the gRPC Reserve commits in
inventory-service's OWN database, BEFORE and OUTSIDE any local
transaction.atomic() -- there is no longer one write-ahead log spanning
both writes for Postgres to unwind. order.services._place_order_remote
rebuilds that guarantee explicitly: a PaymentDeclined/ShippingFailed from
the (still-local) atomic block triggers an explicit compensating gRPC
Release for every sku reserved this checkout. This is a deliberate first
taste of a choreographed saga (forward-ref ch.23), proven by the net-zero
direct-query numbers in GOLDEN-BASELINE.md.

Sourced from examples/00-monolith/order/services.py
(_place_order_local/_place_order_remote/_release_reserved),
examples/04-inventory-service/app/repository.py (reserve/release).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1400, 800

band_before = {"x": 20, "y": 60, "w": 1360, "h": 220,
               "label": "BEFORE -- INVENTORY_MODE=local: one transaction, free rollback", "fill": "#fafafa"}
band_after = {"x": 20, "y": 320, "w": 1360, "h": 420,
              "label": "AFTER -- INVENTORY_MODE=grpc: Reserve crosses the boundary FIRST, outside any local transaction.atomic()", "fill": "#f1f5f9"}

b1_reserve = node(50, 150, 240, 110, ["Reserve stock", "in-process, SAME tx", "pessimistic-lock query"], style="box")
b1_order = node(330, 150, 200, 110, ["Create Order row"], style="box")
b1_payment = node(570, 150, 220, 110, ["Charge payment", "decline rolls back", "reserve + order"], style="box")
b1_ship = node(830, 150, 240, 110, ["Dispatch shipping", "SHIP-FAIL rolls back", "everything above"], style="box")
b1_outbox = node(1110, 150, 220, 110, ["OutboxEvent row"], style="box")
before_nodes = [b1_reserve, b1_order, b1_payment, b1_ship, b1_outbox]
before_edges = [connect(before_nodes[i], before_nodes[i + 1]) for i in range(len(before_nodes) - 1)]

b2_reserve = node(50, 440, 280, 110, ["gRPC Reserve()", "OUTSIDE transaction.atomic()", "commits in inventory-service's OWN db"], style="accent")
b2_order = node(410, 440, 200, 110, ["Create Order row", "local tx starts here"], style="box")
b2_payment = node(640, 440, 220, 110, ["Charge payment", "decline raises"], style="box")
b2_ship = node(890, 440, 220, 110, ["Dispatch shipping", "SHIP-FAIL raises"], style="box")
b2_outbox = node(1140, 440, 190, 110, ["OutboxEvent row"], style="box")
after_nodes = [b2_reserve, b2_order, b2_payment, b2_ship, b2_outbox]
after_edges = [connect(after_nodes[i], after_nodes[i + 1]) for i in range(len(after_nodes) - 1)]
after_edges[0]["label"] = "local transaction.atomic() begins"

b2_release = node(410, 600, 300, 110, ["gRPC Release()", "compensating RPC --", "NOT automatic, must be called"], style="accent")
release_edges = [
    connect(b2_payment, b2_release, dashed=True, amber=True, label="on PaymentDeclined (402)"),
    connect(b2_ship, b2_release, dashed=True, amber=True, label="on ShippingFailed (422)"),
]

notes = [
    {"x": W / 2, "y": 32, "text": "reserve/release across the boundary: where the free rollback went",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 40, "y": H - 60, "text": "Postgres's WAL can only unwind writes inside ITS OWN transaction -- a commit in inventory-service's own database is",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 42, "text": "permanent the instant it lands. The compensating Release call is the thing doing the work now, not an artifact of one",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 24, "text": "shared transaction -- proven live: quantityOnHand held at 96 across both the payment-declined AND ship-fail checkouts.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "reserve-release-saga-lite", W, H,
    bands=[band_before, band_after],
    nodes=before_nodes + after_nodes + [b2_release],
    edges=before_edges + after_edges + release_edges,
    notes=notes,
)
