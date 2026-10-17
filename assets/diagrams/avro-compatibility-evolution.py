#!/usr/bin/env python3
"""ch.28 figure: avro-compatibility-evolution -- the BACKWARD compatibility
proof tests/test_compatibility.py runs against a live Apicurio: v1 registers
cleanly, v2 (adds giftMessage WITH a default) is ACCEPTED (200), v3 (retypes
totalCents long -> string) is REJECTED (400, RuleViolationException) -- the
ACTUAL status observed against the pinned apicurio-registry:3.3.3 image (an
older, pre-3.3 registry answers 409 for the identical request -- see
app/registry_client.py's module docstring).

Sourced from examples/09-schema-registry-demo/schemas/order-placed-v1.avsc,
tests/resources/order-placed-v2-backward-compatible.avsc,
tests/resources/order-placed-v3-incompatible.avsc, and
tests/test_compatibility.py::test_v1_registers_and_v2_is_backward_
compatible_but_v3_is_rejected (the four asserted steps below).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 560

v1 = node(60, 150, 320, 160,
          ["v1 -- order-placed-v1.avsc", "orderId, customerId, customerEmail,", "totalCents: long, confirmationMessage,",
           "placedAt, paymentMethod (optional)", "", "register_or_resolve() -> version \"1\""],
          style="box")
v2 = node(500, 150, 320, 160,
          ["v2 -- adds giftMessage", "[\"null\",\"string\"], default null", "",
           "register_version(version=\"2\")", "", "200 OK, version \"2\""],
          style="accent")
v3 = node(940, 150, 320, 160,
          ["v3 -- retypes totalCents", "long -> string (no valid Avro", "promotion path)",
           "", "register_version(version=\"3\")", "", "400, name=\"RuleViolationException\""],
          style="ghost")

rule = node(360, 380, 600, 80,
            ["Apicurio BACKWARD compatibility rule, attached to artifact", "order-placed-compat-test-* via set_compatibility_rule(\"BACKWARD\")"],
            style="sub")

edges = [
    connect(v1, v2, label="evolve: add optional field with default"),
    connect(v2, v3, label="evolve: retype an existing field"),
    connect(v1, rule, dashed=True),
    connect(v2, rule, label="ACCEPTED", amber=True),
    connect(v3, rule, label="REJECTED", dashed=True),
]

notes = [
    {"x": W / 2, "y": 32, "text": "ch.28 -- schema evolution against a live BACKWARD rule: an additive change passes, a retype is rejected before a single message ships",
     "anchor": "middle", "bold": True, "size": 18},
    {"x": 50, "y": 70, "text": "tests/test_compatibility.py, live-verified against quay.io/apicurio/apicurio-registry:3.3.3 -- not guessed from documentation.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 50, "y": H - 22, "text": "A hand-maintained JSON record can never give you this: nothing stops a retyped field until a consumer's deserializer breaks in production.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "avro-compatibility-evolution", W, H,
    bands=[],
    nodes=[v1, v2, v3, rule],
    edges=edges,
    notes=notes,
)
