"""The hand-rolled Avro-over-Kafka envelope this demo uses on the wire:

    [1-byte magic][8-byte big-endian Apicurio global schema id][raw schemaless Avro bytes]

DRQ-033 chose pure-Python (fastavro + aiokafka + a plain Apicurio v3 REST
client) over confluent-kafka, which means there is no Confluent/Apicurio
Avro *serde* available to supply a wire format for us the way the Java
sibling's `AvroKafkaSerializer`/`AvroKafkaDeserializer` do. This module is
this demo's OWN envelope -- similar in spirit to the Confluent wire format
(a magic byte followed by a schema identifier) but not claiming byte
compatibility with it or with Apicurio's own serializers. It exists so
`app/producer.py` and `app/consumer.py` can't drift on the framing: both
import this one module rather than each hand-rolling their own pack/unpack.
"""

from __future__ import annotations

import struct

MAGIC_BYTE = 0x00

# '>BQ': big-endian, 1-byte unsigned magic + 8-byte unsigned global id.
# Apicurio v3 global ids are signed 64-bit (Java long) in principle, but
# always non-negative in practice for a freshly-provisioned registry; 'Q'
# keeps the envelope fixed-width and simple for a teaching demo.
_HEADER = struct.Struct(">BQ")


def encode_envelope(global_id: int, avro_bytes: bytes) -> bytes:
    """Prefixes `avro_bytes` (already fastavro-encoded, schemaless) with the
    magic byte + the Apicurio global schema id that produced it."""
    return _HEADER.pack(MAGIC_BYTE, global_id) + avro_bytes


def decode_envelope(data: bytes) -> tuple[int, bytes]:
    """Splits a Kafka record value back into `(global_id, avro_bytes)`.
    Raises `ValueError` if the magic byte doesn't match -- a cheap guard
    against accidentally pointing this consumer at a non-Avro-demo topic."""
    magic, global_id = _HEADER.unpack_from(data)
    if magic != MAGIC_BYTE:
        raise ValueError(f"unexpected envelope magic byte: {magic!r} (expected {MAGIC_BYTE!r})")
    return global_id, data[_HEADER.size :]
