#!/usr/bin/env python3
"""ch.20 figure: outbox-relay-at-least-once -- the outbox pattern generalized
past Notification's single case (ch.17's outbox-write-in-transaction), as the
reusable shape every extraction in this book reuses: one DB transaction
commits the state change AND the outbox row together; a separate relay polls
and publishes at-least-once; the required counterpart on the far side is an
IDEMPOTENT consumer, because "at-least-once" is a promise about the pipe, not
about the final effect -- idempotency is what turns "delivered one or more
times" into "applied exactly once," and this book has landed three different
idioms for it by r05.

Sourced from examples/00-monolith/common/management/commands/outbox_relay.py,
examples/05-payment-service/app/relay.py (the same shape, second service),
examples/03-notification-service (check-then-insert + unique index),
examples/04-inventory-service/app/cdc_consumer.py (INSERT...ON CONFLICT
upsert), examples/00-monolith/order/services.py::_is_pending (status-guard).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1360, 760

band_top = {"x": 20, "y": 56, "w": 1320, "h": 230,
            "label": "The bridge: one transaction, state change + outbox row, same commit", "fill": "#fafafa"}
band_mid = {"x": 20, "y": 56 + 230 + 30, "w": 1320, "h": 150,
            "label": "The relay: polls unpublished rows, publishes, THEN stamps published_at -- at-least-once", "fill": "#f1f5f9"}
band_bot = {"x": 20, "y": 56 + 230 + 30 + 150 + 30, "w": 1320, "h": 230,
            "label": "The necessary counterpart: an idempotent consumer, in whichever idiom fits the write", "fill": "#fafafa"}

n_request = node(50, 130, 210, 110, ["Handle the request", "(checkout, order.placed, ...)"], style="box")
n_txn = node(300, 110, 290, 150, ["ONE DB transaction", "state row (Order/Payment) +", "outbox row -- same COMMIT"], style="accent")
n_db = node(640, 130, 180, 110, ["Postgres", "outbox table", "published_at IS NULL"], style="box")
top_nodes = [n_request, n_txn, n_db]
top_edges = [connect(n_request, n_txn), connect(n_txn, n_db)]

n_poll = node(850, 130, 210, 110, ["Relay polls", "oldest unpublished rows", "every poll_ms"], style="box")
top_edges.append({"x1": 820, "y1": 180, "x2": 850, "y2": 180, "label": "reads"})
top_nodes.append(n_poll)

n_relay = node(70, 56 + 230 + 30 + 35, 260, 80, ["AIOKafkaProducer", "send_and_wait(topic, key, value)"], style="box")
n_kafka = node(400, 56 + 230 + 30 + 35, 260, 80, ["Kafka topic", "order.placed / payment.captured /", "payment.declined -- key=aggregateId"], style="accent")
n_stamp = node(730, 56 + 230 + 30 + 35, 280, 80, ["mark published_at", "(crash here -> row stays", "unpublished -> republished)"], style="ghost")
mid_nodes = [n_relay, n_kafka, n_stamp]
mid_edges = [connect(n_relay, n_kafka), connect(n_kafka, n_stamp, dashed=True, label="after ack")]
top_edges.append(connect(n_poll, n_relay))

bot_y = 56 + 230 + 30 + 150 + 30 + 40
n_check = node(50, bot_y, 300, 130,
               ["check-then-insert + unique index", "(notification-service: dedupe by", "order_id; a redelivery is a no-op)"], style="box")
n_upsert = node(400, bot_y, 300, 130,
                ["INSERT ... ON CONFLICT upsert", "(inventory CDC consumer: same", "end state applied once or twice)"], style="box")
n_guard = node(750, bot_y, 300, 130,
               ["status-transition guard", "(order_saga_listener: an order", "that already left PENDING no-ops)"], style="box")
n_effect = node(1100, bot_y + 20, 200, 90, ["Exactly-once EFFECT", "from an at-least-once", "delivery"], style="accent")
bot_nodes = [n_check, n_upsert, n_guard, n_effect]
bot_edges = [
    connect(n_check, n_effect),
    connect(n_upsert, n_effect),
    connect(n_guard, n_effect),
]
mid_edges.append({"x1": 860, "y1": 56 + 230 + 30 + 75, "x2": 860, "y2": bot_y - 10, "dashed": True,
                   "label": "a consumer somewhere on this topic"})

notes = [
    {"x": W / 2, "y": 30, "text": "ch.20 -- the outbox done right: one bridge, three idempotent-consumer idioms this book has already shipped",
     "anchor": "middle", "bold": True, "size": 17},
    {"x": 40, "y": H - 46, "text": "At-least-once is a promise about the PIPE, not the effect -- the relay can republish, the broker can redeliver.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 28, "text": "Idempotency at the consumer is what makes redelivery safe; which idiom fits depends on what kind of write it is.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "outbox-relay-at-least-once", W, H,
    bands=[band_top, band_mid, band_bot],
    nodes=top_nodes + mid_nodes + bot_nodes,
    edges=top_edges + mid_edges + bot_edges,
    notes=notes,
)
