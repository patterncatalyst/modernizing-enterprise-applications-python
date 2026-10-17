#!/usr/bin/env python3
"""ch.28 figure: avro-wire-envelope-registry-flow -- the hand-rolled wire
envelope ([1-byte magic][8-byte global id][Avro bytes]) plus the
register/resolve round trip against Apicurio, pure-Python (fastavro +
aiokafka + a plain httpx REST client -- DRQ-033 rejected confluent-kafka,
so there is no Confluent/Apicurio Avro serde available to supply a wire
format). Top band is the byte layout itself; bottom band is the live
produce/consume flow against Apicurio's v3 REST API.

Sourced from examples/09-schema-registry-demo/app/envelope.py
(encode_envelope/decode_envelope, struct.Struct(">BQ")),
app/producer.py::OrderAvroProducer (register_or_resolve on start(), then
encode_envelope on every send), app/consumer.py::OrderAvroConsumer
(decode_envelope, then get_schema_by_global_id -- never assumes its local
schema copy matches what produced the bytes), and
app/registry_client.py's module docstring (the exact Apicurio v3 REST
shapes, verified by hand against quay.io/apicurio/apicurio-registry:3.3.3).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 700
BAND1_H = 160
BAND2_H = 420

band_envelope = {"x": 30, "y": 60, "w": 1260, "h": BAND1_H,
                  "label": "The wire envelope -- app/envelope.py (NOT Confluent's wire format; this demo's own, documented framing)",
                  "fill": "#fafafa"}
band_flow = {"x": 30, "y": 60 + BAND1_H + 30, "w": 1260, "h": BAND2_H,
             "label": "Produce / consume against a live Apicurio registry",
             "fill": "#f1f5f9"}

# Envelope byte layout, drawn as three adjacent sub-boxes
magic = node(70, 60 + 55, 160, 70, ["1 byte", "magic = 0x00"], style="sub")
gid = node(250, 60 + 55, 300, 70, ["8 bytes, big-endian", "Apicurio global schema id", "struct \">BQ\""], style="sub")
payload = node(570, 60 + 55, 420, 70, ["raw schemaless Avro bytes", "fastavro.schemaless_writer()", "no embedded schema, no header"], style="box")
contrast = node(1030, 60 + 55, 260, 70,
                ["Confluent wire format:", "magic byte + 4-byte int id", "(this demo's own, not byte-compat)"],
                style="ghost")

# Flow band
y0 = 60 + BAND1_H + 30
producer = node(70, y0 + 70, 220, 90, ["OrderAvroProducer", "fastavro-encodes", "DemoOrderPlaced"], style="accent")
registry = node(380, y0 + 20, 300, 90, ["Apicurio v3 REST", "/groups/default/artifacts", "ifExists=FIND_OR_CREATE_VERSION", "-> 200, globalId"], style="box")
topic = node(780, y0 + 70, 220, 90, ["order.events.avro.demo", "key = orderId", "value = envelope bytes"], style="sub")
consumer = node(1080, y0 + 70, 200, 90, ["OrderAvroConsumer", "decode_envelope()", "-> (globalId, bytes)"], style="accent")
lookup = node(780, y0 + 220, 300, 90, ["GET /ids/globalIds/{id}", "-> raw writer schema JSON", "cached by global id"], style="box")
decode = node(1080, y0 + 220, 200, 90, ["fastavro.schemaless_reader()", "decode using the", "WRITER schema, not", "the consumer's own copy"], style="accent")

edges = [
    connect(producer, registry, label="1. register_or_resolve"),
    connect(registry, producer, label="globalId", dashed=True),
    connect(producer, topic, label="2. encode_envelope + send", amber=True),
    connect(topic, consumer, label="3. getone()"),
    connect(consumer, lookup, label="4. get_schema_by_global_id"),
    connect(lookup, decode, label="5. parse_schema", amber=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.28 -- the hand-rolled envelope and the register/resolve round trip, pure-Python (fastavro + aiokafka + httpx, DRQ-033)",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 50, "y": H - 22, "text": "The consumer always fetches the writer schema by global id -- it never trusts its own locally parsed .avsc matches what produced the bytes.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "avro-wire-envelope-registry-flow", W, H,
    bands=[band_envelope, band_flow],
    nodes=[magic, gid, payload, contrast, producer, registry, topic, consumer, lookup, decode],
    edges=edges,
    notes=notes,
)
