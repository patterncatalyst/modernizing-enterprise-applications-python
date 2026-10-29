#!/usr/bin/env python3
"""ch.12 figure: event-storm-checkout: two readings of one call chain.

TOP band: today's `order/services.py::_place_order_local` as it actually
executes: one synchronous call chain, one `transaction.atomic()` (SMELL #2,
SMELL #1). BOTTOM band: the same business process re-read with the
event-storming grammar: actor, command, aggregate, domain events,
policies/reactions, an external system, and a read model. Five of the
domain-event names below are REAL Kafka topic constants already defined in
`config/settings.py` (`ORDER_PLACED_TOPIC`, `PAYMENT_CAPTURED_TOPIC`,
`PAYMENT_DECLINED_TOPIC`, `SHIPMENT_DISPATCHED_TOPIC`,
`SHIPMENT_FAILED_TOPIC`: wired for the `choreographed`/`orchestrated` modes
r05/r06 added); `StockReserved`, `OrderConfirmed`, and `NotificationSent`
have no topic constant today: they are this chapter's own re-reading of a
fact that, on the default synchronous path, never leaves process memory as
an event at all.

Node-style reuse note: this project's generate_diagram.py palette has six
light-box styles (box/sub/accent/user/kernel/ghost), not the six sticky-note
colors of a physical event-storm wall. The legend note at the bottom of the
figure maps this project's styles onto the standard grammar; no literal
orange/blue/yellow is implied by the SVG's actual fill colors.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1600, 1000

# ---- TOP band: today's synchronous call chain ------------------------------
customerT = node(40, 130, 120, 90, ["Customer"], style="sub")
commandT = node(190, 130, 150, 90, ["POST /api/orders", "HTTP request"], style="user")
invT = node(370, 130, 190, 90, ["inventory.services.reserve()", "direct in-process call"], style="box")
orderT = node(590, 130, 160, 90, ["Order", "persisted"], style="box")
payT = node(780, 130, 190, 90, ["payment.services.charge()", "direct in-process call"], style="box")
shipT = node(1000, 130, 190, 90, ["shipping.services.dispatch()", "direct in-process call"], style="box")
outboxT = node(1220, 130, 230, 90, ["OutboxEvent row", "written in the SAME transaction"], style="box")

top_nodes = [customerT, commandT, invT, orderT, payT, shipT, outboxT]
top_edges = [
    connect(customerT, commandT),
    connect(commandT, invT),
    connect(invT, orderT, amber=True, label="SMELL #1 no ACL"),
    connect(orderT, payT, amber=True, label="SMELL #2"),
    connect(payT, shipT, amber=True),
    connect(shipT, outboxT, amber=True, label="SMELL #5/#6 cured here"),
]

# ---- BOTTOM band: the event-storm reading ----------------------------------
customerB = node(40, 390, 120, 80, ["Customer"], style="sub")
commandB = node(190, 390, 160, 80, ["Place Order", "command"], style="user")
orderAgg = node(380, 390, 160, 80, ["Order", "aggregate"], style="box")

evOrderPlaced = node(380, 510, 170, 90, ["OrderPlaced", "domain event"], style="accent")
polReserve = node(590, 510, 170, 90, ["reserve stock", "policy / reaction"], style="ghost")
evStockReserved = node(800, 510, 180, 90, ["StockReserved", "domain event (conceptual)"], style="accent")
polCapture = node(1020, 510, 180, 90, ["capture payment", "policy / reaction"], style="ghost")
evPaymentCaptured = node(1240, 510, 190, 90, ["PaymentCaptured", "domain event"], style="accent")

extGateway = node(1020, 370, 230, 90, ["Payment Gateway", "external system"], style="sub")
evPaymentDeclined = node(1020, 650, 190, 90, ["PaymentDeclined", "domain event (failure)"], style="accent")

polDispatch = node(1240, 650, 190, 90, ["dispatch shipment", "policy / reaction"], style="ghost")
evShipmentDispatched = node(1020, 790, 210, 90, ["ShipmentDispatched", "domain event"], style="accent")
polNotify = node(790, 790, 190, 90, ["write outbox row", "policy / reaction"], style="ghost")
evOrderConfirmed = node(560, 790, 190, 90, ["OrderConfirmed", "domain event (conceptual)"], style="accent")
evNotificationSent = node(330, 790, 200, 90, ["NotificationSent", "domain event (conceptual)"], style="accent")

readModel = node(420, 910, 380, 70, ["Order Status", "read model"], style="kernel")

bottom_nodes = [
    customerB, commandB, orderAgg,
    evOrderPlaced, polReserve, evStockReserved, polCapture, evPaymentCaptured,
    extGateway, evPaymentDeclined,
    polDispatch, evShipmentDispatched, polNotify, evOrderConfirmed, evNotificationSent,
    readModel,
]
bottom_edges = [
    connect(customerB, commandB),
    connect(commandB, orderAgg),
    connect(orderAgg, evOrderPlaced, label="emits"),
    connect(evOrderPlaced, polReserve),
    connect(polReserve, evStockReserved),
    connect(evStockReserved, polCapture),
    connect(extGateway, polCapture, label="authorize/capture"),
    connect(polCapture, evPaymentCaptured, label="approved"),
    connect(polCapture, evPaymentDeclined, label="declined", dashed=True),
    connect(evPaymentCaptured, polDispatch),
    connect(polDispatch, evShipmentDispatched),
    connect(evShipmentDispatched, polNotify),
    connect(polNotify, evOrderConfirmed),
    connect(polNotify, evNotificationSent),
    connect(evOrderPlaced, readModel, dashed=True, label="projects"),
    connect(evPaymentCaptured, readModel, dashed=True),
    connect(evShipmentDispatched, readModel, dashed=True),
    connect(evOrderConfirmed, readModel, dashed=True),
]

notes = [
    {"x": W / 2, "y": 30, "text": "Event-storming the checkout flow: two readings of one call chain",
     "anchor": "middle", "bold": True, "size": 18},

    {"x": 40, "y": 65, "text": "TOP: today: _place_order_local, one transaction.atomic(), four contexts + an outbox write, synchronous calls",
     "anchor": "start", "bold": True, "size": 14},
    {"x": 40, "y": 345, "text": "BOTTOM: the same process, event-stormed: actor -> command -> aggregate -> domain events, "
                                "policies/reactions, an external system, a read model",
     "anchor": "start", "bold": True, "size": 14},

    {"x": 1020, "y": 360, "text": "timeout/retry sit here once this is a network call", "anchor": "start", "size": 10, "color": "#555555"},
    {"x": 1020, "y": 745, "text": "saga compensation releases the stock reservation here instead of an ACID rollback",
     "anchor": "start", "size": 10, "color": "#555555"},

    {"x": 380, "y": 505, "text": "settings.ORDER_PLACED_TOPIC", "anchor": "start", "size": 9, "color": "#3d7a4e"},
    {"x": 1240, "y": 505, "text": "settings.PAYMENT_CAPTURED_TOPIC", "anchor": "start", "size": 9, "color": "#3d7a4e"},
    {"x": 1020, "y": 785, "text": "settings.SHIPMENT_DISPATCHED_TOPIC", "anchor": "start", "size": 9, "color": "#3d7a4e"},

    {"x": 40, "y": 985,
     "text": "Legend (this project's diagram palette, not literal sticky-note colors): ACCENT = domain event * "
             "USER = command * SUB = actor / external system * BOX = aggregate (bottom) / today's direct call (top) * "
             "GHOST (dashed) = policy/reaction * KERNEL = read model",
     "anchor": "start", "size": 10, "color": "#555555"},
]

g.emit(
    "event-storm-checkout", W, H,
    bands=[
        {"x": 20, "y": 50, "w": 1560, "h": 280, "label": "", "fill": "#f4f4f4"},
        {"x": 20, "y": 330, "w": 1560, "h": 660, "label": "", "fill": "#fafafa"},
    ],
    nodes=top_nodes + bottom_nodes,
    edges=top_edges + bottom_edges,
    notes=notes,
)
