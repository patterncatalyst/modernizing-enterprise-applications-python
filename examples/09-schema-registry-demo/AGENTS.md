# AGENTS.md -- 09-schema-registry-demo

Context for an AI agent (or a human) picking this module up.

## What this is

ch.28 (DRQ-038 follow-up, DRQ-076) Avro + Apicurio Schema Registry
DEMONSTRATOR, pure-Python per DRQ-033 (`fastavro` + `aiokafka` + a plain
`httpx` client against Apicurio's v3 REST API -- deliberately NOT
`confluent-kafka`). ADDITIVE ONLY: see `README.md` for the full picture.
This is the Python sibling of
`~/Dev/modernizing-enterprise-applications/examples/09-schema-registry-demo`
(Java/Quarkus) -- same chapter intent, independent implementation (there is
no Quarkus Dev Services / `apicurio-registry-serdes` equivalent here; this
module hand-rolls both the registry client and the wire envelope).

**Do not** route any existing service's event traffic through this module,
and do not touch `examples/00-monolith` through `examples/08-graphql-gateway`
or `tooling/newman/` from here -- this module owns its own topic
(`order.events.avro.demo`) and its own Apicurio artifact
(`order-placed-value`).

## Toolchain

- **uv** manages the interpreter, the virtualenv, and the lockfile.
- **Python 3.14**.
- **fastavro 1.13.1**, **aiokafka 0.14.0**, **httpx 0.28.1**. Dev-only:
  **pytest 9.1.1** + **pytest-asyncio 1.4.0**, **ruff 0.17.1**,
  **testcontainers 4.15.0**.

## Commands

```sh
uv sync --group dev
uv run ruff check .
uv run pytest                      # Testcontainers Kafka + Apicurio, needs Docker -- the ONLY test layer here
uv run python -m app.demo_cli      # against REGISTRY_URL/KAFKA_BOOTSTRAP_SERVERS (defaults: localhost:8095 / localhost:9092)
```

## Structure

- `schemas/order-placed-v1.avsc` -- the ONE schema this module owns, not
  generated from anywhere; field names/types are hand-matched against
  `../07-order-service/EVENTS.md`'s "Produces: order.placed" JSON example.
  Keep these two in sync if that event's shape ever changes -- this schema
  is a teaching mirror, not derived automatically.
- `app/envelope.py` -- `encode_envelope`/`decode_envelope`, the ONE place
  the wire framing (`[magic byte][8-byte global id][Avro bytes]`) is
  defined. Both `app/producer.py` and `app/consumer.py` import this module
  rather than each hand-rolling their own pack/unpack -- if you ever need to
  change the envelope shape, change it here once.
- `app/registry_client.py` -- `RegistryClient`. `register_or_resolve` is the
  ONLY method that raises on an unexpected (not deliberately tested)
  Apicurio error; `register_version` deliberately returns the raw
  `httpx.Response` so `tests/test_compatibility.py`/`app/demo_cli.py` can
  assert on an ACTUAL rejection status instead of catching an exception.
  Its module docstring is the one place documenting the live-verified
  200/204/400 status codes -- update it (and re-verify against the pinned
  image) before changing `APICURIO_IMAGE_TAG` in the repo root's
  `.env.example`.
- `app/producer.py` -- `OrderAvroProducer`/`DemoOrderPlaced`/
  `ARTIFACT_ID`/`TOPIC`. `ARTIFACT_ID = "order-placed-value"` is imported by
  `app/demo_cli.py` and referenced by `tests/test_roundtrip.py` indirectly
  (via the default topic) -- don't duplicate the literal string elsewhere.
- `app/consumer.py` -- `OrderAvroConsumer`. `poll_one()` is a
  request/response call (`AIOKafkaConsumer.getone()` under
  `asyncio.wait_for`), not a background consume loop -- there is no
  `app/main.py`/FastAPI app in this module to run one from.
- `app/demo_cli.py` -- `main()` returns an int exit code (not `sys.exit`
  directly) so it's importable/testable if ever needed; `if __name__ ==
  "__main__"` is the only place that calls `sys.exit(asyncio.run(main()))`.
- `tests/conftest.py` -- `_ApicurioContainer(DockerContainer)`: there is no
  upstream `testcontainers.apicurio` wrapper, so this is a small generic
  subclass. `wait_until_ready()` polls `/apis/registry/v3/system/info`
  (NOT the management-port `/health/ready` `compose.yaml`'s healthcheck
  uses -- port 9000 isn't exposed in this fixture).
- `Containerfile` -- optional for a demo module (no long-running server),
  included for consistency with every other example in this project; `CMD`
  runs `app.demo_cli` against env-var-configured `REGISTRY_URL`/
  `KAFKA_BOOTSTRAP_SERVERS`.

## Testing

```sh
uv run pytest   # 2 tests, Testcontainers-managed Kafka + Apicurio, needs Docker
```

No `-m "not integration"` split -- unlike every other service in this
project, this module has no Kafka-free/Apicurio-free unit layer to run
without Docker; both tests need a real registry and a real broker.
