---
title: "Contracts & the Service Registry"
order: 28
part: "Communication & Contracts"
description: "A schema registry replaces hand-copied Pydantic contracts with one governed schema and a compatibility rule that rejects breaking changes at registration. Apicurio with Avro, demonstrated alongside the live JSON flows."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Explain what a schema registry enforces that a hand-maintained Pydantic contract cannot, and why `paymentMethod` is missing from notification-service's copy of `OrderPlacedEvent`.
- Write an Avro `.avsc` that mirrors a Pydantic model field for field, including the `timestamp-millis` logical type.
- Register, serialize and deserialize with `fastavro`, `aiokafka` and Apicurio's v3 REST API, with no vendor serde.
- Frame each message with a magic byte and a global schema id, and resolve the writer schema from that id on the consumer side.
- Configure a BACKWARD rule and predict whether a schema evolution is accepted or rejected.
- Say why the registry runs beside the live `order.placed` topic instead of replacing it, and what a real cutover would need.

## Why this matters

`order.placed` is a JSON event, and the eight services share no package. A contract that three of them must agree on is written three times, by hand, in three `app/schemas.py` files. The frozen shape in `examples/07-order-service/EVENTS.md` has seven fields: `orderId`, `customerId`, `customerEmail`, `totalCents`, `confirmationMessage`, `placedAt`, `paymentMethod`. payment-service's `OrderPlacedEvent` has all seven, because the decline rule needs `paymentMethod` to choose CAPTURE or DECLINE. notification-service's copy has six:

```python
# examples/03-notification-service/app/schemas.py
class OrderPlacedEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order_id: int = Field(alias="orderId")
    customer_id: int = Field(alias="customerId")
    customer_email: str = Field(alias="customerEmail")
    total_cents: int = Field(alias="totalCents")
    confirmation_message: str = Field(alias="confirmationMessage")
    placed_at: datetime = Field(alias="placedAt")
    # no payment_method field at all
```

Nothing is broken today. notification-service never reads `paymentMethod`, and Pydantic ignores the extra key on the wire. That is the problem: the drift is invisible by design. A future consumer that copies the six-field model would start, deserialize and pass CI, and the field would never arrive.

{% include excalidraw.html file="hand-duplicated-vs-registry-schema" alt="Two side-by-side panels. Left: payment-service's seven-field OrderPlacedEvent with paymentMethod and notification-service's six-field copy without it, two hand-authored understandings of the same frozen contract. Right: one order-placed-v1.avsc registered once with Apicurio, resolved by global id from a producer and a consumer, with a BACKWARD compatibility rule between any future version and the registry." caption="Figure 28.1: Two hand-duplicated Pydantic copies of one contract, one drifted silently, versus one registry-governed schema" %}

The live flows stay JSON. A new module, `examples/09-schema-registry-demo`, publishes an Avro mirror of `order.placed` to its own topic behind a real Apicurio registry. The drift is real, and the fix is a parallel mechanism, not a migration.

## What a schema registry is for

When a producer and a consumer in two deployables must agree on a message shape, the agreement has to live somewhere and something has to enforce it. In the JSON flows it lives in each author's reading of the event and nothing enforces it. A registry makes it explicit: a schema is registered once under an artifact id, and the registry is the record of the contract. It buys three things:

- **Governance.** One place answers "what does `order.placed` look like today, and two versions ago", instead of diffing three `app/schemas.py` files in three repositories.
- **Compatibility enforcement.** A rule (BACKWARD, FORWARD, FULL, each with a transitive variant) makes the registry refuse a new version that violates it, at registration, before any message ships under the broken shape. A Pydantic model can't do this: nothing stops a developer retyping a field, and the first signal is a `ValidationError` in a consumer's logs.
- **Decoupled deploys.** Adding an optional field needs no simultaneous consumer release when the rule and the defaults make it provably safe. "Is it safe to deploy the producer first" becomes a registration result instead of a read through several repositories.

Apicurio governs Avro, Protobuf and JSON Schema as data formats, and OpenAPI and AsyncAPI as API descriptions, under one artifact, version and rule model. The demonstrator uses Avro for one Kafka topic, because that is where the `order.placed` drift lives.

## The pure-Python choice: fastavro and aiokafka

Every other service reaches Kafka through `aiokafka`, which is pure Python and matches the asyncio loop FastAPI already runs. The usual Avro-plus-registry tool is `confluent-kafka[avro]`, which wraps `librdkafka` and ships a ready serializer. This project rejected it so there stays one Kafka client idiom; `examples/09-schema-registry-demo/AGENTS.md` records the decision as "No confluent-kafka, no Java/Quarkus Avro serde".

The cost is real: no drop-in `AvroSerializer` that stamps a schema id onto the wire. The module builds it from three pieces, each doing one job: `fastavro` for Avro encode and decode, `aiokafka` as the broker client, and an `httpx` client (`app/registry_client.py`) against Apicurio's v3 REST API. The producer registers idempotently on every `start()`:

{% include codetabs.html langs="pyproject.toml: the three runtime dependencies this module depends on|app/registry_client.py: register_or_resolve" %}

```toml
# examples/09-schema-registry-demo/pyproject.toml (runtime deps, abbreviated)
dependencies = [
    "fastavro==1.13.1",
    "aiokafka==0.14.0",
    "httpx==0.28.1",
]
```

```python
# examples/09-schema-registry-demo/app/registry_client.py
async def register_or_resolve(self, artifact_id: str, schema_json: str) -> RegisteredVersion:
    """Idempotently registers `schema_json` as `artifact_id`'s FIRST
    version, or resolves the existing registration if one with
    byte-identical content already exists -- Apicurio's
    `ifExists=FIND_OR_CREATE_VERSION` semantics."""
    resp = await self._http.post(
        f"/groups/{self._group_id}/artifacts",
        params={"ifExists": "FIND_OR_CREATE_VERSION"},
        json={
            "artifactId": artifact_id,
            "artifactType": "AVRO",
            "firstVersion": {
                "content": {"content": schema_json, "contentType": "application/json"},
            },
        },
    )
    if resp.status_code != 200:
        raise ApicurioRegistryError(f"register_or_resolve({artifact_id!r}) failed: ...")
    version = resp.json()["version"]
    return RegisteredVersion(
        artifact_id=version["artifactId"], version=version["version"],
        global_id=version["globalId"], content_id=version["contentId"],
    )
```

With `ifExists=FIND_OR_CREATE_VERSION` the registry returns the existing version with `200` when the content matches byte for byte, so double registration is harmless. Every request and response shape in the client was verified by hand against a live `quay.io/apicurio/apicurio-registry:3.3.3` container, not taken from documentation. The v3 API is young and has already changed its rejection status across minor versions (see below).

## The contract as an `.avsc`

`schemas/order-placed-v1.avsc` mirrors the JSON event field for field, authored once from `EVENTS.md` and kept in sync by hand:

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "dev.patterncatalyst.contracts.avro",
  "fields": [
    { "name": "orderId", "type": "long" },
    { "name": "customerId", "type": "long" },
    { "name": "customerEmail", "type": "string" },
    { "name": "totalCents", "type": "long" },
    { "name": "confirmationMessage", "type": "string" },
    { "name": "placedAt", "type": { "type": "long", "logicalType": "timestamp-millis" } },
    { "name": "paymentMethod", "type": ["null", "string"], "default": null }
  ]
}
```

Two choices are deliberate. `placedAt` is a `long` with the `timestamp-millis` **logical type**, which documents the meaning (milliseconds since the epoch), so `fastavro` encodes a `datetime` and decodes it back without an ISO-8601 parser on either side. The trade-off is precision: the wire format truncates to milliseconds, so a round-trip comparison must truncate both sides.

`paymentMethod` is a **union with `null` and a `null` default**, although the real event always sets it. That shows the optional-with-default idiom from v1. payment-service's Pydantic model uses the same shape for the same field (`payment_method: str | None = Field(default=None, ...)`), because an optional field with a safe default is the only way a consumer schema can evolve without breaking.

## The wire envelope

A consumer needs to know which schema wrote a record before it can decode it. Avro's binary format carries no field names or type tags, so decoding with the wrong schema yields garbage instead of an error. Confluent's serializers and Apicurio's Java serde both solve this by prefixing every record with a small header. With no serde available, the module defines its own in one place, so producer and consumer can't drift on the framing:

```python
# examples/09-schema-registry-demo/app/envelope.py
MAGIC_BYTE = 0x00
_HEADER = struct.Struct(">BQ")  # big-endian: 1-byte magic + 8-byte global id

def encode_envelope(global_id: int, avro_bytes: bytes) -> bytes:
    return _HEADER.pack(MAGIC_BYTE, global_id) + avro_bytes

def decode_envelope(data: bytes) -> tuple[int, bytes]:
    magic, global_id = _HEADER.unpack_from(data)
    if magic != MAGIC_BYTE:
        raise ValueError(f"unexpected envelope magic byte: {magic!r}")
    return global_id, data[_HEADER.size:]
```

The shape follows Confluent's (magic byte, schema id, payload) but is not byte-compatible with it: the module's docstring says it is "NOT the Confluent/Apicurio serde wire format". The id is 8 bytes, where Confluent uses 4, because Apicurio v3 global ids are 64-bit. A reader pointed at a topic without the envelope gets an immediate `ValueError` from the magic-byte check instead of a `fastavro` failure three calls deeper.

{% include excalidraw.html file="avro-wire-envelope-registry-flow" alt="Top band: the wire envelope byte layout, a 1-byte magic value, an 8-byte big-endian Apicurio global schema id, and the schemaless Avro bytes, contrasted with Confluent's 4-byte-id format. Bottom band: the produce and consume flow against Apicurio: register_or_resolve, encode and publish, consume, fetch the writer schema by global id, decode with that schema." caption="Figure 28.2: The hand-rolled wire envelope and the register and resolve round trip against Apicurio's v3 REST API" %}

`OrderAvroProducer.start()` registers once per producer lifetime, caches the global id and stamps it on every `send()`:

```python
# examples/09-schema-registry-demo/app/producer.py
async def start(self) -> None:
    await self._producer.start()
    registered = await self._registry.register_or_resolve(self._artifact_id, load_schema_json())
    self._global_id = registered.global_id

async def send(self, event: DemoOrderPlaced) -> int:
    avro_bytes = encode_order_placed(event, self._schema)
    envelope = encode_envelope(self._global_id, avro_bytes)
    await self._producer.send_and_wait(self._topic, key=str(event.order_id).encode(), value=envelope)
    return self._global_id
```

`OrderAvroConsumer` never assumes its own parsed copy of `order-placed-v1.avsc` is what produced the bytes. It unwraps the envelope, fetches that exact writer schema by global id, and caches it per id so a steady stream pays one registry round trip:

```python
# examples/09-schema-registry-demo/app/consumer.py
async def poll_one(self, timeout: float = 30.0) -> dict[str, Any]:
    record = await asyncio.wait_for(self._consumer.getone(), timeout=timeout)
    global_id, avro_bytes = decode_envelope(record.value)
    schema = await self._schema_for(global_id)   # GET /ids/globalIds/{global_id}, cached
    return fastavro.schemaless_reader(io.BytesIO(avro_bytes), schema)
```

A round trip against Testcontainers-managed Kafka and Apicurio compares every field, truncating the sent timestamp to milliseconds as the logical type requires:

```python
# examples/09-schema-registry-demo/tests/test_roundtrip.py (abbreviated)
sent = DemoOrderPlaced(order_id=555123, customer_id=1, customer_email="ada@example.com",
                        total_cents=3998, confirmation_message="Order #555123 placed, total $39.98",
                        placed_at=datetime.now(UTC), payment_method="VISA-1234")
await producer.send(sent)
received = await consumer.poll_one(timeout=30.0)

assert received["orderId"] == sent.order_id
assert received["customerEmail"] == sent.customer_email
assert received["paymentMethod"] == sent.payment_method
expected_millis = sent.placed_at.replace(microsecond=(sent.placed_at.microsecond // 1000) * 1000)
assert received["placedAt"] == expected_millis
```

## Schema evolution and compatibility rules

Round-tripping one schema shows serialization works, not that the registry blocks a breaking change. That takes two versions and a rule. Apicurio supports the standard vocabulary:

| Rule | A schema is accepted when |
| --- | --- |
| BACKWARD | the new schema can read data written by the previous one |
| FORWARD | the previous schema can read data written by the new one |
| FULL | both hold |

Each has a transitive variant that checks every prior version, not only the last. BACKWARD is the usual first choice because it matches the common deployment order: upgrade consumers before producers, so a consumer on the new schema must read what a still-old producer writes.

The demonstrator attaches a BACKWARD rule to an artifact holding v1, then registers two evolutions. v2 adds one field with a default:

```json
{ "name": "giftMessage", "type": ["null", "string"], "default": null }
```

A v2 reader fills the missing field from the default when it reads v1 data, which is what BACKWARD requires. v3 keeps the name `totalCents` but retypes it from `long` to `string`. The registry calls, and the rejected field:

{% include codetabs.html langs="tests/test_compatibility.py: the full live assertion|order-placed-v3-incompatible.avsc: the rejected evolution" %}

```python
# examples/09-schema-registry-demo/tests/test_compatibility.py
v1 = await registry.register_or_resolve(artifact_id, _V1_SCHEMA)
assert v1.version == "1"

await registry.set_compatibility_rule(artifact_id, config="BACKWARD")

v2_response = await registry.register_version(artifact_id, _V2_SCHEMA, version="2")
assert v2_response.status_code == 200
assert v2_response.json()["version"] == "2"

v3_response = await registry.register_version(artifact_id, _V3_SCHEMA, version="3")
assert v3_response.status_code == 400
assert v3_response.json()["name"] == "RuleViolationException"
```

```json
{
  "name": "totalCents", "type": "string",
  "doc": "INCOMPATIBLE CHANGE: retyped from 'long' (v1/v2) to 'string' -- no valid Avro promotion path, breaks BACKWARD compatibility."
}
```

Avro schema resolution allows a narrow set of promotions (`int` to `long`, `float` or `double`; `long` to `float` or `double`). `long` to `string` is not one, so a v3 reader has no defined way to read a 64-bit integer as a string.

Against the pinned `3.3.3` image, v2 registers with HTTP **200** and version `"2"`. v3 is rejected with HTTP **400** and an RFC 7807 problem body whose `name` is `"RuleViolationException"`. An older, pre-3.3 registry answers **409** for the same request. `register_version` is the one client method that returns the raw `httpx.Response` instead of raising on a non-2xx status, so a caller expecting a rejection can assert on the status and body the registry actually sent.

{% include excalidraw.html file="avro-compatibility-evolution" alt="Three schema versions in sequence: v1 registers cleanly, v2 adds an optional giftMessage field with a default and is accepted (200), v3 retypes totalCents from long to string and is rejected (400, RuleViolationException), observed against the pinned Apicurio 3.3.3 image with a BACKWARD rule on the artifact." caption="Figure 28.3: Schema evolution against a live BACKWARD rule: an additive change passes, a retype is rejected before a message ships" %}

The rejection happens when someone tries to register the schema, not as a `ValidationError` in a consumer's logs days later. A rule on the contract would also have caught the missing `paymentMethod` the first time someone registered a schema without a field the reference version required.

## Why this stays a demonstrator

The natural next step looks like cutting `order.placed` over to Avro. The live flows stay JSON, for the same reason the original JSON decision held: infrastructure that works in isolation is not retrofitted into a system that already works. The monolith, `examples/07-order-service`'s outbox and both real consumers are unchanged, and neither `app/schemas.py` above has a line edited. The module publishes to its own topic, `order.events.avro.demo`, and registers its own artifact, `order-placed-value`. Nothing is cut over, so there is no flag to flip and nothing to reverse. `compose.yaml`'s `apicurio` entry states the blast radius: used only by the demonstrator, with no other service depending on it or reading from it.

The parallel path buys two things. It proves the mechanism (registration, envelope, field-for-field fidelity, writer schema by global id) against real infrastructure. And it can show the rejected case, which the live topic can't: demonstrating a breaking publish on a contract three real services depend on would mean breaking it. `order.events.avro.demo` exists to be broken, repeatedly, at no risk.

A real cutover is more than swapping the serializer:

- Old JSON readers and new Avro writers can't share one topic without a bridge, so payment-service's decline path and notification-service's idempotent write need a coordinated upgrade window, or BACKWARD discipline has to govern the transition.
- Nothing else in the stack talks to Apicurio today. A cutover also forces the first decision about which other hand-maintained contracts deserve a registry: the four saga-outcome topics order-service consumes, the gRPC inventory proto and the REST contracts behind the GraphQL gateway.

> **ADLC in Action**
>
> The claim that notification-service's `OrderPlacedEvent` lacks `paymentMethod` could have been assumed from payment-service's copy, which has it. It was confirmed by reading `examples/03-notification-service/app/schemas.py` field by field, because three similar-looking services give no reason to assume symmetry. The same rule applied to the registry client: the shapes it encodes (`200` on `FIND_OR_CREATE_VERSION`, `204` on attaching a rule, `400` with `RuleViolationException` on a BACKWARD violation) were checked by hand against a live `3.3.3` container. A status code taken from documentation or memory, such as the `409` an older registry returns, would have shipped exactly the silent drift a registry exists to prevent.

> **Decision**
>
> When two or more deployables share a wire contract, put the schema in a registry and attach a compatibility rule, BACKWARD by default. Add the registry beside a working flow, prove it on its own topic, and cut over only when a stated need justifies coordinating every consumer.

> **🤖 Explore with your agent**
>
> "In examples/09-schema-registry-demo, add an optional `giftNote` field with a default to a new order-placed-v4 .avsc that keeps the BACKWARD rule satisfied, then write a second candidate that retypes `customerId` from `long` to `string` and show Apicurio rejects it under the BACKWARD rule. Do not touch examples/03-notification-service or examples/05-payment-service."
>
> Check: registering the additive version returns 200 and the retyped one returns 400 with `RuleViolationException`; `./demos/demo-schema-registry.sh` still ends with `ALL CHECKS PASSED.`

## Build, run, observe

`demos/demo-schema-registry.sh` starts a throwaway Kafka and Apicurio pair, runs `app/demo_cli.py` and tears both down on exit. It needs Docker or Podman and exits non-zero if any step fails:

```sh
./demos/demo-schema-registry.sh
```

```
step 1-2: registered/resolved schema globalId=1
step 2: round trip OK -- consumed orderId=555123 field-for-field equal to what was sent
step 3: attached BACKWARD compatibility rule to 'order-placed-value'
step 4: v2 (optional giftMessage, WITH a default) ACCEPTED as expected (200)
step 5: v3 (totalCents long -> string) REJECTED as expected (400 RuleViolationException)
ALL CHECKS PASSED.
```

The module's own `uv run pytest` runs the same progression against Testcontainers-managed Kafka and Apicurio.

- **Retype a field in a new candidate schema:** registration returns `400` with `RuleViolationException`, the v3 outcome.
- **Add an optional field with a default:** registration returns `200` and the new version number, the v2 outcome.
- **Read the topic without the envelope:** the magic-byte check raises `ValueError` before any Avro decoding runs.
