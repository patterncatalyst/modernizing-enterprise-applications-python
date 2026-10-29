#!/usr/bin/env python3
"""ch.19 figure: cdc-backfill-then-retire -- transaction-log tailing end to
end. Top row: Debezium's Postgres connector reads the write-ahead log (via
a logical replication slot, pgoutput) for a ONE-TIME snapshot backfill
(op=r per existing row) and then streams ongoing op=c/u/d changes, so
inventory-service's OWN schema tracks the monolith's still-live table
during the cutover window. Bottom row (ghosted): the retire runbook --
once the monolith's checkout calls gRPC Reserve/Release exclusively and its
table is decommissioned, there is nothing left to tail, so the connector,
replication slot, and publication are explicitly torn down.

Sourced from infra/debezium/inventory-connector.json, scripts/
register-debezium.sh, app/cdc_consumer.py (InventoryCdcConsumer), and
CUTOVER.md's retire runbook + scripts/retire-debezium.sh.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1480, 660

band_top = {"x": 20, "y": 60, "w": 1440, "h": 220,
            "label": "BACKFILL + SYNC (transition window) -- Debezium tails the WAL, flag-gated INVENTORY_CDC_ENABLED=true", "fill": "#fafafa"}
band_bottom = {"x": 20, "y": 340, "w": 1440, "h": 220,
               "label": "RETIRE (CUTOVER.md runbook, after both cutover dimensions have flipped) -- nothing left to tail", "fill": "#f1f5f9"}

wal = node(30, 150, 220, 110, ["Postgres WAL", "public.inventory_items", "REPLICA IDENTITY FULL"], style="box")
slot = node(270, 150, 220, 110, ["Replication slot + publication", "meap_inventory_slot /", "meap_inventory_publication"], style="box")
connector = node(510, 150, 220, 110, ["Debezium Postgres connector", "snapshot.mode=initial", "register-debezium.sh"], style="box")
topic = node(750, 150, 220, 110, ["Kafka topic", "meap.public.inventory_items", "op=r once, then c/u/d"], style="box")
consumer = node(990, 150, 220, 110, ["app/cdc_consumer.py", "InventoryCdcConsumer", "ON CONFLICT upsert, keyed delete"], style="accent")
owned = node(1230, 150, 220, 110, ["inventory.inventory_items", "OWNED copy -- backfilled,", "then kept current"], style="accent")

top_nodes = [wal, slot, connector, topic, consumer, owned]
top_edges = [connect(top_nodes[i], top_nodes[i + 1]) for i in range(len(top_nodes) - 1)]
top_edges[-1]["amber"] = True

r1 = node(270, 430, 260, 110, ["1. kcat drains the topic", "-o end -e: nothing new", "(monolith write-silent)"], style="ghost")
r2 = node(600, 430, 260, 110, ["2. retire-debezium.sh", "DELETE connector,", "drop slot + publication"], style="ghost")
r3 = node(930, 430, 260, 110, ["3. INVENTORY_CDC_ENABLED=false", "(already the default)", "own Alembic seed is now the SoR"], style="ghost")

bottom_nodes = [r1, r2, r3]
bottom_edges = [
    connect(consumer, r1, dashed=True, label="gRPC Reserve/Release own all writes"),
    connect(r1, r2, dashed=True),
    connect(r2, r3, dashed=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "CDC tails the WAL for a ONE-TIME backfill + transition sync, then is retired",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 40, "y": H - 40, "text": "Debezium is transition-only infrastructure here: it is never part of the CI equivalence gate, and the running system",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "does not depend on it after cutover -- inventory-service reaches its end state via its own schema and seed, not a live consumer.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "cdc-backfill-then-retire", W, H,
    bands=[band_top, band_bottom],
    nodes=top_nodes + bottom_nodes,
    edges=top_edges + bottom_edges,
    notes=notes,
)
