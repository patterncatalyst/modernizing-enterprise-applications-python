# 09-schema-registry-demo

ch.28 (DRQ-038 follow-up, DRQ-076) -- an Avro + Apicurio **Schema Registry
DEMONSTRATOR**, ADDITIVE to every live JSON event flow in this project. The
Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/09-schema-registry-demo`
(Java/Quarkus) -- same teaching intent, but **pure-Python** (DRQ-033):
`fastavro` + `aiokafka` + a plain `httpx` client against Apicurio's v3 REST
API, not `confluent-kafka`.

## What this is (and isn't)

This module publishes a field-for-field Avro mirror of the real
`order.placed` JSON event (`../07-order-service`'s actual wire contract --
see its `EVENTS.md`) to its OWN topic, `order.events.avro.demo`, fronted by
an Apicurio registry. It exists to teach:

1. **Schema registration** -- an Avro schema registered against Apicurio,
   resolved by a stable global id carried on the wire.
2. **BACKWARD compatibility evolution** -- a new version that only adds an
   optional field (with a default) is accepted; a new version that retypes
   an existing field is rejected.

It does **not** touch, replace, or share a topic with any existing
extracted service. `examples/00-monolith` through `examples/07-order-service`
keep publishing/consuming plain JSON forever (DRQ-038) -- this module is a
separate teaching surface, not a migration of the live event flows.

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **fastavro 1.13.1** (Avro encode/decode), **aiokafka 0.14.0** (the same
  Kafka client every other service in this project uses), **httpx 0.28.1**
  (the Apicurio v3 REST client -- see `app/registry_client.py`). Dev-only:
  **pytest 9.1.1** + **pytest-asyncio 1.4.0**, **ruff 0.17.1**,
  **testcontainers 4.15.0**.
- **No confluent-kafka, no Java/Quarkus Avro serde** -- DRQ-033's decision.
  The wire envelope carrying Apicurio's global schema id
  (`app/envelope.py`) is this demo's own, hand-rolled format.

## Commands

```sh
uv sync --group dev

uv run ruff check .
uv run pytest     # Testcontainers-managed Kafka + Apicurio; needs Docker
```

There is no separate unit-test layer to split against with a `-m` marker --
every test in this module IS an integration test against a real registry
and broker (same posture the Java sibling's `OrderAvroRoundTripTest`/
`SchemaCompatibilityTest` take against Quarkus Dev Services).

## Running the demo against the live compose stack

```sh
./demos/demo-schema-registry.sh   # from the repo root; throwaway Kafka + Apicurio, self-torn-down
```

Or manually, against the shared `compose.yaml` services (after
`docker compose --env-file .env up -d`):

```sh
cd examples/09-schema-registry-demo
REGISTRY_URL=http://localhost:8095/apis/registry/v3 \
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
uv run python -m app.demo_cli
```

## Structure

- `schemas/order-placed-v1.avsc` -- the Avro schema, field-for-field
  mirroring the real `order.placed` JSON event.
- `app/envelope.py` -- the hand-rolled `[magic byte][8-byte global id][Avro bytes]`
  wire envelope shared by the producer and consumer.
- `app/registry_client.py` -- `RegistryClient`, an `httpx`-based async
  client for Apicurio's v3 REST API (create/resolve an artifact version,
  attach a compatibility rule, register a new version, fetch by global id).
  Its module docstring records the EXACT status codes observed live against
  the pinned `3.3.3` image.
- `app/producer.py` -- `OrderAvroProducer` + `DemoOrderPlaced`: encodes,
  registers/resolves the schema, and publishes.
- `app/consumer.py` -- `OrderAvroConsumer`: unwraps the envelope, fetches
  the writer schema by global id, decodes.
- `app/demo_cli.py` -- the standalone progression
  `demos/demo-schema-registry.sh` runs: register -> round trip -> v2 accept
  -> v3 reject.
- `tests/conftest.py` -- Testcontainers fixtures (Kafka + a generic
  `DockerContainer`-based Apicurio wrapper; there is no upstream
  `testcontainers.apicurio` module).
- `tests/test_roundtrip.py` -- the field-for-field round-trip proof.
- `tests/test_compatibility.py` -- the BACKWARD compatibility proof
  (v2 accepted, v3 rejected with the live-observed status).
- `tests/resources/order-placed-v2-backward-compatible.avsc`,
  `tests/resources/order-placed-v3-incompatible.avsc` -- the evolution
  fixtures.

## Contract notes (don't "fix" these -- they match the design intent on purpose)

- `paymentMethod` is modeled OPTIONAL in the Avro schema (union with
  `null`, default `null`) even though the real JSON event always sets it --
  a deliberate choice to demonstrate Avro's optional-field-with-default
  idiom from v1 onward (see `schemas/order-placed-v1.avsc`'s doc).
- The wire envelope (`app/envelope.py`) is NOT the Confluent/Apicurio
  serde wire format -- it is this demo's own, documented format, because
  DRQ-033 ruled out depending on `confluent-kafka` or a Java-only serde.
