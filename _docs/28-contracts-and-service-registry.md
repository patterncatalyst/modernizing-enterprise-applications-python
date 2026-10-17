---
title: "Contracts & the Service Registry"
order: 28
part: "Communication & Contracts"
description: "Schema/API/shared-data-type registry use cases and enterprise requirements; Apicurio with Avro, demonstrated additively alongside the live JSON event flows."
duration: 35 minutes
---

Chapter 17 introduced `order.placed` as a JSON Kafka event and, in the same
breath, introduced a cost this book has been carrying ever since: there is
no shared package between any two of this project's eight independently
deployable services, so a wire contract three of them need to agree on gets
authored three separate times, by hand, in three separate `app/schemas.py`
files. `examples/07-order-service/EVENTS.md`'s own "Produces: `order.placed`"
section names the frozen shape: `orderId`, `customerId`, `customerEmail`,
`totalCents`, `confirmationMessage`, `placedAt`, `paymentMethod` — seven
fields. `examples/05-payment-service/app/schemas.py::OrderPlacedEvent` has
all seven, `payment_method` included, because the choreographed decline rule
needs it to decide CAPTURE versus DECLINE. `examples/03-notification-service/
app/schemas.py::OrderPlacedEvent` — read it and count — has six. There is no
`payment_method` field at all:

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

Nothing in the build catches this, and in this particular case nothing is
actually broken — notification-service never reads `paymentMethod`, so its
model simply doesn't declare it, and Pydantic happily ignores the extra key
on the wire. That is precisely what makes the drift worth naming rather than
dismissing: it is invisible by design. If a future consumer *did* need
`paymentMethod` and an author copied notification's six-field model instead
of payment's seven-field one — an easy mistake, since both are called
`OrderPlacedEvent` and live in a file called `app/schemas.py` in services
that look alike from the outside — nothing would fail at startup, at
deserialization, or in CI. The field would simply never arrive, silently,
in a service whose own docstring claims to be "this service's own copy of
the frozen `order.placed` JSON payload." Both services' own schema modules
say the same thing about why this duplication exists at all: there is no
shared module between the monolith and either service — each is an
independently deployable project — so the duplication above is the real
cost of a hand-maintained JSON wire contract, carried with no schema
registry until this chapter (DRQ-036).

That reasoning has been sitting in two services' docstrings since r03 and
r05, each with a forward reference to a chapter that didn't exist yet. This
chapter is where that reference resolves — not by making the hand-authored
duplication disappear (it doesn't; both schemas above are exactly the code
they were before this chapter), but by building, against live
infrastructure, the mechanism that would have made the gap between those two
schemas a build-time rejection instead of a silent absence.

{% include excalidraw.html file="hand-duplicated-vs-registry-schema" alt="Two side-by-side panels. Left, today: payment-service's seven-field OrderPlacedEvent with paymentMethod and notification-service's six-field copy without it, two independent hand-authored understandings of the same frozen contract. Right, ch.28's demonstrator: one order-placed-v1.avsc registered once with Apicurio, resolved by global id from both a producer and a consumer, with a BACKWARD compatibility rule standing between any future version and the registry." caption="Figure 28.1 — Two hand-duplicated Pydantic copies of the same contract, one drifted silently, versus one registry-governed schema demonstrated in parallel" %}

It is worth being precise, up front, about what this chapter does and does
not do about that drift, because the real answer is narrower than "adopt a
schema registry." The live flows stay JSON. `examples/00-monolith`
through `examples/07-order-service`, and every real consumer of
`order.placed` — payment, notification — are untouched by anything below.
What changes is additive: a new, isolated module,
`examples/09-schema-registry-demo`, publishes a field-for-field Avro mirror
of `order.placed` to its own topic, fronted by a real Apicurio registry, so
the two things a registry actually buys — a central contract of record, and
compatibility enforcement strong enough to reject a breaking change before
it ships — can be demonstrated against live infrastructure without touching
a system that currently works. Why this stays a demonstrator rather than a
cutover is explained in full once you've seen what the registry does; for
now, hold both facts side by side: the drift above is real, and the fix this
chapter ships is a parallel, provable mechanism, not a migration.

## What a schema registry is for

Strip away the specific product and a schema registry answers one question
a JSON-over-Kafka system like this one's live flows has no good answer for:
when a producer and a consumer in two different deployables both need to
agree on the shape of a message, where does that agreement live, and who
enforces it?

In this project's live flows today, the answer is "nowhere, and no one."
The agreement exists only as three separate authors' understanding of what
the order service's `order.placed` event looks like, captured once in each
model's own docstring, with no mechanism checking that the understandings
stay in sync over time. A registry turns that implicit, distributed
agreement into an explicit, centralized one: a schema is registered once,
under an artifact id every interested service can reference, and from that
point on the registry — not a docstring, not a convention, not a reviewer's
memory — is the thing that knows what the contract is.

That central record of truth buys two things in practice, and they are
different things even though they're often sold together. The first is
**governance**: a human or a CI job can go to one place and ask "what does
the `order.placed` contract actually look like today, and what did it look
like two versions ago?" rather than diffing three `app/schemas.py` files
across three repositories by hand, the way confirming this chapter's own
opening claim required. The second, sharper benefit is **compatibility
enforcement**: a registry can be configured with a rule — BACKWARD,
FORWARD, FULL, and transitive variants of each — and then it *refuses* a
new schema version that would violate that rule, at registration time,
before a single message is published under the broken shape. That second
property is the one a hand-maintained Pydantic model can never give you, no
matter how careful the team: nothing stops a developer from retyping a
field in `app/schemas.py`, and nothing tells them they just broke every
consumer still running the old model until a `ValidationError` shows up in
a service's logs, in production, after the fact.

The practical payoff downstream of both properties is **decoupled
producer/consumer deploys**. A producer that wants to add an optional field
doesn't need to coordinate a simultaneous consumer release if the
registry's rule and the schema's defaults make that addition provably
safe; a consumer can upgrade on its own schedule and trust that whatever it
reads will either match what it expects or has already been rejected before
it could ever be written. Without a registry, "is it safe to deploy the
producer first" is a question a team answers by reading code across
repositories and hoping. With one, it's a question the registry already
answered, mechanically, at registration time, the same way every time —
which is exactly the question notification-service's own missing field
should have triggered and didn't.

Apicurio, the registry this project adopts, is format-agnostic by design:
it governs Avro, Protobuf, and JSON Schema as data formats, and OpenAPI and
AsyncAPI as API-description formats, all under the same artifact/version/
rule model. This chapter scopes itself to one corner of that menu — Avro,
for one Kafka topic — because that is the corner `order.placed`'s own drift
lives in, and because proving the mechanism once, concretely, against real
infrastructure, teaches more than surveying every format shallowly. The
registry itself doesn't care which format it's governing; the same artifact/
version/rule model would apply to a Protobuf gRPC contract or an OpenAPI
spec with no change to the underlying engine.

## The pure-Python choice: fastavro + aiokafka, not confluent-kafka

Every other service in this project reaches Kafka through `aiokafka` —
pure-Python, no native extension, matching the asyncio event loop every
FastAPI service already runs on. The obvious tool for "Avro plus a schema
registry" in most Kafka tutorials is `confluent-kafka[avro]`, which wraps
`librdkafka` (a C library) and ships a ready-made Avro serializer that
talks to Confluent Schema Registry's wire format out of the box. DRQ-033
rejected that path for this project, explicitly, and the reason is the same
consistency argument this book has made before about picking one idiom and
holding it: pulling in a second Kafka client, with its own native
dependency and its own serialization conventions, for exactly one
demonstrator module would mean this project no longer has one Kafka story —
it would have `aiokafka` everywhere except the one place a registry got
involved. `examples/09-schema-registry-demo`'s own `AGENTS.md` records the
decision as directly as the code enforces it: "**No confluent-kafka, no
Java/Quarkus Avro serde** — DRQ-033's decision."

Staying pure-Python has a real cost, and this chapter doesn't minimize it:
there is no Confluent or Apicurio Python serde to lean on, no drop-in
`AvroSerializer`/`AvroDeserializer` pair that already knows how to stamp a
schema id onto the wire. `examples/09-schema-registry-demo` builds the
whole stack itself from three pieces that each do one job — `fastavro` for
Avro encode/decode, `aiokafka` for the same broker client every sibling
service uses, and a plain `httpx`-based REST client (`app/registry_client.py`)
against Apicurio's own v3 API, with no SDK in between:

{% include codetabs.html langs="pyproject.toml — the three runtime dependencies this module depends on|app/registry_client.py — register_or_resolve" %}

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

`register_or_resolve` is the Python-native analogue of the Java sibling's
`apicurio.registry.auto-register=true` — a producer can call it on every
`start()` without worrying about double-registering, because
`ifExists=FIND_OR_CREATE_VERSION` returns the existing version, with
`200`, if the content already matches byte-for-byte. `RegistryClient`'s own
module docstring is explicit about where every one of these shapes came
from: "Every request/response shape below was verified BY HAND against a
live `quay.io/apicurio/apicurio-registry:3.3.3` container... not guessed
from documentation." That caution is not boilerplate — Apicurio's v3 REST
API is young enough, and has changed its error-response shape across minor
versions recently enough (see the 400-versus-409 history two sections
below), that assuming a shape from memory would have been a real risk in a
module whose entire teaching point is "trust the registry, not your
assumption about the registry."

## The contract as an `.avsc`

The schema this demonstrator registers is `schemas/order-placed-v1.avsc`, a
field-for-field Avro mirror of the real JSON event — same field names, same
meanings, same source of truth (`examples/07-order-service/EVENTS.md`'s
"Produces: `order.placed`" section), authored once and kept in sync by hand
rather than generated from either side:

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

Two choices in that schema need naming, because they're easy to misread as
oversights rather than the teaching decisions the schema's own `doc` fields
record. First, `placedAt` is a `long` with Avro's
`timestamp-millis` **logical type**, not a bare integer and not a string.
Avro's logical types attach a documented interpretation to a primitive
representation — here, "this long is milliseconds since the Unix epoch" —
so `fastavro` can encode a Python `datetime` directly and decode it back to
one, without either side hand-rolling an ISO-8601 string parser the way a
plain-JSON contract has to. The trade-off `tests/test_roundtrip.py`
documents directly: the wire format truncates to millisecond precision, so
a round-trip comparison has to truncate both sides to the same resolution
before asserting equality, or a sub-millisecond difference introduced
before serialization produces a false failure.

Second, `paymentMethod` is modeled as a **union with `null`, defaulting to
`null`** — `["null", "string"]` — even though the real JSON event always
sets it. That's a chosen deviation from the real event's always-present
field, made so this schema demonstrates Avro's optional-field-with-default
idiom starting from v1, rather than waiting until the v2 evolution fixture
to show it for the first time. It is the same idiom
`examples/05-payment-service`'s own hand-maintained `OrderPlacedEvent`
already uses for the identical field
(`payment_method: str | None = Field(default=None, ...)`) — the Avro schema
and the Pydantic model independently arrived at the same shape for the
same reason, because an optional field with a safe default is the only way
a consumer schema can evolve without breaking.

## The wire envelope: why a global id travels with every message

A schema registered with Apicurio is identified by a numeric **global id**.
A consumer reading an Avro-encoded Kafka record needs to know which schema
wrote it before it can decode a single byte — Avro's binary format carries
no field names or type tags inline, unlike JSON, so decoding with the wrong
schema doesn't throw a clear error, it silently produces garbage. The
standard solution, the one Confluent's own serializers and Apicurio's own
Java/Quarkus serde both implement, is to stamp that identifier onto the
front of every record's bytes — a tiny header the consumer reads first,
before touching the Avro payload at all.

Because this project's pure-Python lane has no Confluent or Apicurio serde
to supply that header format, `examples/09-schema-registry-demo` defines
its own, in exactly one place so the producer and consumer can never drift
on the framing:

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

The shape — a magic byte, then a schema identifier, then the payload — is
in the same spirit as Confluent's own wire format (which uses
a magic byte followed by a **4-byte** big-endian schema id). This module's
own docstring is careful not to overclaim: it "is NOT the Confluent/Apicurio
serde wire format — it is this demo's own, documented format," not a
byte-compatible drop-in. The practical difference that matters is the id
width: Confluent's format reserves four bytes because Confluent Schema
Registry's own schema ids are 32-bit; Apicurio's v3 global ids are 64-bit
(a Java `long`) in principle, so this envelope reserves eight bytes rather
than silently truncating an id that happens to fit today but might not
always. A reader pointed at the wrong topic — one that isn't carrying this
envelope at all — gets a clean, immediate `ValueError` from the magic-byte
check rather than a confusing `fastavro` decode failure three calls deeper.

{% include excalidraw.html file="avro-wire-envelope-registry-flow" alt="Top band: the wire envelope byte layout, a 1-byte magic value, an 8-byte big-endian Apicurio global schema id, and the raw schemaless Avro bytes, contrasted with Confluent's 4-byte-id format. Bottom band: the full produce/consume flow against a live Apicurio registry -- register_or_resolve, encode and publish, consume, fetch the writer schema by global id, decode with that exact schema." caption="Figure 28.2 — The hand-rolled wire envelope and the register/resolve round trip against Apicurio's v3 REST API" %}

`app/producer.py::OrderAvroProducer.start()` calls `register_or_resolve`
exactly once per producer lifetime, caches the returned global id, and
stamps that same id onto every subsequent `send()` — registration happens
once, not per message:

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

`app/consumer.py::OrderAvroConsumer` does the inverse, and the discipline
here is exactly what a registry is supposed to buy over a hand-maintained
schema, stated directly in the module's own docstring: it "never assumes
its own locally-parsed copy of
`order-placed-v1.avsc` is what actually produced the bytes." Every consumed
record unwraps the envelope, pulls out the global id, and fetches *that
exact* writer schema from the registry — caching it by id so a steady
stream of records from the same producer only pays the registry round trip
once:

```python
# examples/09-schema-registry-demo/app/consumer.py
async def poll_one(self, timeout: float = 30.0) -> dict[str, Any]:
    record = await asyncio.wait_for(self._consumer.getone(), timeout=timeout)
    global_id, avro_bytes = decode_envelope(record.value)
    schema = await self._schema_for(global_id)   # GET /ids/globalIds/{global_id}, cached
    return fastavro.schemaless_reader(io.BytesIO(avro_bytes), schema)
```

`tests/test_roundtrip.py` — the pure-Python analogue of the Java sibling's
`OrderAvroRoundTripTest` — proves this whole path end to end against a
Testcontainers-managed Kafka and Apicurio: encode a `DemoOrderPlaced` event,
register/resolve its schema, publish it, consume it back, and assert every
field matches, field for field, including the millisecond-truncated
timestamp comparison the logical type requires:

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

Round-tripping one fixed schema proves serialization works. It does not
prove the thing a registry is actually *for* — catching a breaking change
before it ships. That proof needs at least two schema versions and a rule
that can tell them apart, and `tests/test_compatibility.py` — the pure-
Python sibling of the Java `SchemaCompatibilityTest` — builds exactly that
scenario against a live registry.

Apicurio supports the standard compatibility rule vocabulary: **BACKWARD**
(a new schema can read data written by the previous one — the rule this
demonstrator uses), **FORWARD** (the previous schema can read data written
by the new one), and **FULL** (both directions hold at once), each with a
transitive variant checking against every prior version rather than just
the immediately preceding one. BACKWARD is the rule most teams reach for
first because it matches the most common real deployment order — upgrade
consumers before producers, so a consumer already running the new schema
needs to be able to read messages a still-old producer is still writing.

The test registers `order-placed-v1.avsc` as a fresh artifact, attaches a
BACKWARD `COMPATIBILITY` rule via `set_compatibility_rule`, and then
exercises two differently-shaped evolutions against that same artifact. The
first, `order-placed-v2-backward-compatible.avsc`, adds exactly one new
field, with a default:

```json
{ "name": "giftMessage", "type": ["null", "string"], "default": null }
```

Because `giftMessage` carries a default — the same `["null", "string"]`
union idiom `paymentMethod` already used in v1 — a reader using the v2
schema can still make sense of a message a v1 writer produced: the missing
field is simply filled in with its default. That is precisely what BACKWARD
compatibility requires, and Apicurio accepts it. The second evolution,
`order-placed-v3-incompatible.avsc`, does something structurally different:
it keeps the field name `totalCents` but retypes it from `long` to
`string`. Avro's schema-resolution rules define a specific, narrow set of
type promotions a reader schema is allowed to apply when resolving a writer
schema that doesn't match exactly — `int` promotes to `long`, `float`, or
`double`; `long` promotes to `float` or `double` — and `long` to `string`
is not among them. A v3 reader has no defined way to interpret bytes a v1
writer laid down as a 64-bit integer as a string.

{% include codetabs.html langs="tests/test_compatibility.py — the full live assertion|order-placed-v3-incompatible.avsc — the rejected evolution" %}

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

The actual numbers this project observed, live, against the pinned
`quay.io/apicurio/apicurio-registry:3.3.3` image: v2 registers at **HTTP
200**, version `"2"` recorded; v3 is rejected at **HTTP 400**, with an RFC
7807 problem body whose `"name"` field is `"RuleViolationException"`.
That specific status code is not incidental trivia — `app/registry_client.py`'s
own module docstring records that an **older, pre-3.3 registry answers
`409`** for the identical rejected request, the same 409-to-400 shift the
Java sibling's own test docstring independently observed across its own
registry-version bump. `tests/test_compatibility.py` and `app/demo_cli.py`
both assert the actual, live-observed `400` rather than a remembered or
assumed status — exactly the discipline `RegistryClient.register_version`
is built around: unlike every other method on that client, it returns the
raw `httpx.Response` instead of raising on a non-2xx status, so a caller
testing an expected rejection can assert on what the registry really said
rather than catching an exception that would swallow the status code and
body.

{% include excalidraw.html file="avro-compatibility-evolution" alt="Three schema versions in sequence: v1 registers cleanly, v2 adds an optional giftMessage field with a default and is ACCEPTED (200), v3 retypes totalCents from long to string and is REJECTED (400, RuleViolationException) -- the actual status observed against the pinned Apicurio 3.3.3 image, against a BACKWARD compatibility rule attached to the artifact." caption="Figure 28.3 — Schema evolution against a live BACKWARD rule: an additive change passes, a retype is rejected before a single message ships" %}

`demos/demo-schema-registry.sh` runs this identical progression —
register/resolve v1, round-trip produce/consume, attach the BACKWARD rule,
register v2, register v3 — against a throwaway Kafka and Apicurio pair
rather than Testcontainers, via `app/demo_cli.py`, and fails loudly (exit
non-zero, under `set -euo pipefail`) if any step doesn't come out the way
this chapter says it must:

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

This is the rejection that never ships a bad message: the schema is
refused at the moment someone tries to register it, not discovered as a
`ValidationError` in a consumer's logs three services downstream, days or
weeks later — exactly the failure mode notification-service's silently
missing `paymentMethod` field illustrates in miniature, except a registry
with a rule attached would have caught *that* drift too, the first time
someone tried to register a schema missing a field the rule's reference
version required.

## Why this stays a demonstrator

It would be easy to read the sections above and conclude the natural next
step is cutting `order.placed` over to Avro wholesale. This chapter does
not do that, and the reason is the same scope discipline the original JSON
decision already modeled once, back in Chapter 17: this project does not
retrofit infrastructure into a system that currently works just because the
infrastructure is now proven to work in isolation.

The live flows stay JSON, permanently, as Chapter 17 already decided — this
chapter does not revisit that call. `examples/00-monolith` through
`examples/07-order-service`'s outbox, and every real consumer of
`order.placed` — payment, notification — are exactly the code they were
before this chapter, unedited; neither `app/schemas.py` shown at the top of
this chapter has a single line changed. `examples/09-schema-registry-demo`
publishes to its own topic, `order.events.avro.demo`, which no other
service in this project reads or writes, and registers against its own
Apicurio artifact, `order-placed-value`, which no other artifact in the
registry depends on. There is no flag to flip here and no cutover to
reverse, unlike Chapter 17's two-flag notification cutover — because
nothing is being cut over. `compose.yaml`'s own `apicurio` service entry
states the blast radius as directly as the code does: "used ONLY by
`examples/09-schema-registry-demo` — a DEMONSTRATOR, additive to the live
topology. No other service in this stack ... depends on it, reads from it,
or has its JSON event flows touched by it in any way."

What the parallel path buys that a hypothetical future cutover chapter
could not have bought more cheaply is twofold. First, it proves the
mechanism — auto-registration, the hand-rolled envelope, field-for-field
fidelity across the wire, the writer-schema-by-global-id discipline — against
real infrastructure rather than asserting it from Apicurio's documentation.
Second, and this is the sharper point, it lets this chapter show the
*rejected* case. This project's real `order.placed` topic cannot safely be
used to demonstrate "here is what happens when someone tries to publish a
breaking schema change" — that would mean setting out to break a live
contract three real services depend on, just to capture an error
message for a book. The parallel topic's whole value is that
`tests/test_compatibility.py`'s v3 case *can* run that experiment,
repeatedly, on demand, with zero risk to anything that matters, because
`order.events.avro.demo` is a topic this project invented specifically so
it could be broken safely.

That framing also sets a fair expectation for what a full cutover would
actually require, if this project's own operational needs ever did justify
one. It is not "swap the serializer." Every consumer of the current JSON
topic — payment-service's choreographed decline path, notification-service's
idempotent write — would need a coordinated upgrade window, or the
BACKWARD-compatibility discipline this chapter demonstrates would need to
govern the transition itself, because old JSON readers and new Avro writers
cannot coexist on one topic without a bridging strategy. The harder piece,
named here only so a reader doesn't assume the rest of the migration is a
smaller lift than it is: nothing elsewhere in this project's stack is wired
to Apicurio today — a real cutover would also mean deciding, for the very
first time, which of this project's other hand-maintained JSON contracts
(the four saga-outcome topics `order-service` consumes, the gRPC inventory
proto, the REST contracts the GraphQL gateway fans out across) are worth
the same treatment, and that decision is exactly the kind of speculative
infrastructure this book has declined to build ahead of a stated need
before.

> **ADLC in Action** — This chapter's opening claim — that notification-
> service's `OrderPlacedEvent` is missing `paymentMethod` — could have been
> taken on faith from the pattern established by payment-service's copy,
> which does carry it. Confirming it required reading
> `examples/03-notification-service/app/schemas.py` directly, field by
> field, rather than assuming symmetry across three services that otherwise
> look alike. The same discipline applied to the registry side: rather than
> writing `app/registry_client.py` against Apicurio's v3 API documentation
> alone, the request/response shapes it encodes — `200` on
> `ifExists=FIND_OR_CREATE_VERSION`, `204` on attaching a rule, and
> critically, **`400`** with `RuleViolationException` on a BACKWARD
> violation against the pinned `3.3.3` image, not the `409` an older
> registry version answers for the identical request — were each verified
> by hand against a live container before being encoded into the client or
> asserted in a test. An agent drafting this chapter's compatibility claim
> from a remembered or documented status code, rather than the actual
> response a live `3.3.3` instance returns, would have shipped exactly the
> kind of silent, unverified drift this chapter's own subject matter exists
> to prevent.

## What you learned

- **A schema registry is a central contract of record with teeth** — it
  doesn't just document a shape, the way a docstring on a hand-authored
  Pydantic model does; it *refuses* a new version that would break a stated
  compatibility rule, at registration time, before a single message ships
  under the broken shape.
- **The drift this chapter opens on is real, not hypothetical** —
  `payment-service`'s `OrderPlacedEvent` carries `paymentMethod`;
  `notification-service`'s does not; nothing in the build, in CI, or at
  runtime currently checks that the two independently-authored copies of
  the same frozen contract still agree.
- **Pure-Python means hand-rolling what a serde would otherwise supply** —
  DRQ-033 rejected `confluent-kafka` to keep one Kafka client idiom across
  this project; the cost is that the wire envelope (`[magic][global
  id][Avro bytes]`) and the registry REST client are this project's own,
  verified by hand against a live `3.3.3` Apicurio image rather than
  inherited from an existing serde.
- **BACKWARD compatibility has a precise, checkable boundary** — adding an
  optional field with a default (`giftMessage`) is a valid evolution a v2
  reader can apply to v1 data; retyping an existing field (`totalCents`
  long → string) has no defined Avro promotion path and is rejected, live,
  with the actual `400 RuleViolationException` this project observed
  against its pinned registry version, not a remembered `409`.
- **The fix stays additive, by the same scope discipline that deferred it
  in the first place** — the live JSON flows, including the two schemas
  this chapter opened on, are unedited; `examples/09-schema-registry-demo`
  proves the registry mechanism, including the case a live production topic
  could never safely demonstrate, on a topic invented specifically so it
  could be broken without risk.

Chapter 29 turns from the contract a message carries to the shape a
deployment takes — packaging, promoting, and rolling out eight independently
versioned services (plus, now, one Apicurio-governed Avro artifact) across
environments, without the registry this chapter just built becoming one more
thing a deploy has to coordinate by hand.

---

*Verification status: <span class="status status--verified">verified</span>.
The drift claim is read directly from the payment- and
notification-service event schemas against `examples/07-order-service/
EVENTS.md`'s reference shape. Every registry claim is proven in
`examples/09-schema-registry-demo` under Testcontainers-managed Kafka and
Apicurio: a field-for-field round trip and a compatibility suite confirming
v2 accepted (`200`) and v3 rejected (`400`, `RuleViolationException`);
`demos/demo-schema-registry.sh` reproduces the identical progression
standalone.*
