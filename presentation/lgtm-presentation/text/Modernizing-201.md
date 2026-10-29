# Modernizing-201

Source: Modernizing-201.pptx · 83 slides

## [001] MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201 · The patterns, end to end (sldId 256)

The full technical pattern set behind the Django-to-FastAPI migration: seams, data ownership, coordination, contracts, and operating the result.

[chip] r1.1

> This is the 201, the patterns deck, for engineers and architects implementing a strangler-fig migration. It walks the full pattern set this project shipped at just-enough-code depth; the deep async/FastAPI mechanics (SQLAlchemy 2.0 sessions, the outbox relay as an asyncio task, grpc.aio, Pydantic v2 at the edges) live in the 201-FastAPI companion. The main body is 50 slides across ten sections; Appendix A (OpenShift/CRC parity), B (the extended figure set), and C (reference) are deeper material to keep open in another window, not slides to project live.

## [002] 201 · THE PATTERNS · The implementation, one section per part, plus an appendix (sldId 257)

p. 2

- Why modernize, the restraint case, and the ADLC + equivalence gate
- The reference monolith, its smells, and finding the seams with DDD
- The strangler fig in practice: proxy, ACL, event-driven notification
- Data across the seam: owned data, the outbox, CDC, CQRS, ACID→ACD
- Coordinating across services: both saga shapes, idempotent compensation
- Communication, contracts, and the chassis: REST, gRPC, GraphQL, the registry
- Operating and delivering: deploy topology, the mesh, the trace, the supply-chain gate
- The pattern language, revisited: what earned its place, and where to stop
- Appendix A: OpenShift/CRC parity
- Appendix B / C: extended figures + reference

> Ten sections, same order the system is built in: why/how, the ADLC, the monolith, DDD seam-finding, the strangler fig, data, coordination, contracts, operating, and the pattern-language retrospective. Appendix A carries OpenShift/CRC parity; B carries every figure that didn't fit the 50-slide main body; C is the examples index, stack pins, and a glossary. Cross-references in this deck are by concept, never by slide number, so the deck stays correct if a section is trimmed for time.

## [003] Why Modernize (sldId 258)

01

The case for change, and the discipline to leave most of it alone.

> Opens with the why-modernize case, then immediately the restraint case: this project extracted six services because five concrete smells demanded it, not because a target architecture was decided up front. That discipline is the throughline for the whole deck.

## [004] WHY MODERNIZE · THE CASE · Modernize because change got expensive (sldId 259)

p. 4

- A Django monolith holding six bounded contexts in one shared Postgres schema makes every change touch everything else: one deployable, one release train, one blast radius.
- The target is independent deployability, not a service count: a change to shipping should never require testing or redeploying payment.
- The full pattern set gets there: the strangler fig, owned data, both saga shapes, contracts, and the operating model that keeps the result running as one system.

> Frame this as the business case before any pattern name appears: coupling is a cost, measured in how many things have to move together for one change. The monolith is the believable common ancestor every real legacy system starts from, not bad engineering. The case for moving is narrower and stronger than 'microservices are better': it's that specific changes get safer and cheaper once the coupling that forced them together is gone.

## [005] WHY MODERNIZE · RESTRAINT · And when not to modernize at all (sldId 260)

p. 5

- Stable, low-value contexts are the cheapest ones to leave alone: encapsulate a seam before extracting it, and extract only when a concrete change gets safer or cheaper.
- Every extraction in this project traces to a named coupling smell already in the monolith, not to a target architecture decided in advance.
- The test at every seam: does this specific change get safer or cheaper, never whether the result looks more modern.

> This is the restraint case, and it matters because this deck could otherwise read as 'decompose everything.' Six services came out of five documented smells, not a service-count plan. The pattern-language retrospective returns to this with the receipts: six extractions against five smells, applied consistently, not invoked once and abandoned.

## [006] The ADLC + the Equivalence Gate (sldId 261)

02

The lifecycle, and the automated check, that make agent-driven change safe.

> Introduces the Agentic Development Lifecycle this whole modernization was built with, and the automated equivalence gate every cutover has to pass before a flag is allowed to flip. This project itself, ten build iterations and three ledger files, is the worked example.

## [007] THE ADLC · FROM SDLC · The human moves up a level (sldId 262)

p. 7

- The agent authors the change; the human frames the seam, sets the acceptance bar, and gates the merge, the same division of labor across all ten build iterations behind this modernization.
- The method rests on an automated equivalence gate, not on trust in a model's output: every cutover re-runs the same Newman contract suite the monolith already had to pass.
- The Map and Generate phases here use manual reconnaissance plus a scaffolding skill's conventions, since this stack has no framework-aware MCP server.

> This Python/FastAPI stack has no framework-aware MCP server that knows FastAPI/aiokafka. That gap is named directly rather than worked around quietly.

## [008] THE ADLC · THE LOOP · Frame, Map, Plan, Generate, Verify, Operate, Reconcile (sldId 263)

p. 8

- Seven phases, one seam at a time: Frame states the outcome, Map does reconnaissance, Plan produces a gated step plan, Generate writes the code, Verify runs the gated equivalence check, Operate rolls out behind a flag, Reconcile records what shipped against what was planned.
- Two human gates carry the whole method: approve the plan before any code exists, and sign off on equivalence before the flag flips.
- Reconcile is where the record lives: three real corrections surfaced across ten iterations (a configuration mechanism, a ConfigMap's real shape, a harder-than-expected CVE scan) because the validation pass read the actual files, not the plan's description of them.

> Walk the seven phases against a concrete example if there's time: the chassis extraction's own plan assumed pydantic-settings as the configuration mechanism. The Verify/Reconcile phase caught that no service ever adopted it (every service uses a frozen @dataclass with from_env()) by grepping all eight config.py files directly, not by re-trusting the plan. That correction is itself evidence the loop works.

## [009] THE ADLC · THE EQUIVALENCE GATE · The behaviour-equivalence suite pins observable behaviour (sldId 264)

p. 9

[chip] python · pytest

```python
# examples/00-monolith/tests/test_checkout.py
def test_decline_sentinel_returns_402_and_rolls_back_stock(api_client, customer, widget):
    before = widget.quantity_on_hand
    response = _checkout(api_client, customer, widget.sku, 1, "CARD-DECLINE", address)
    assert response.status_code == 402
    assert response.json()["error"] == "PAYMENT_DECLINED"
    widget.refresh_from_db()
    # net-zero: the atomic() rolled back the inventory reservation too.
    assert widget.quantity_on_hand == before

def test_ship_fail_sentinel_rolls_back_entire_checkout(api_client, customer, widget):
    response = _checkout(api_client, customer, widget.sku, 1, "CARD-VISA", "SHIP-FAIL Lane")
    assert response.status_code == 422
    widget.refresh_from_db()
    assert widget.quantity_on_hand == before  # net-zero stock, SMELL

# examples/00-monolith/tests/test_smoke.py -- one assertion per /api/* surface
def test_inventory_serves(api_client, widget):
    response = api_client.get("/api/inventory")
    assert response.status_code == 200
```

examples/00-monolith/tests/test_checkout.py + test_smoke.py: the suite every cutover re-runs, old position and new, before a flag is allowed to flip

> This is the same unedited Newman/pytest suite re-run at every single cutover across all six extractions. The point isn't that it's a big suite, it's that it never gets edited to make a cutover pass. test_ship_fail_sentinel is the one worth lingering on: it proves the whole checkout's transaction.atomic() rolls back, including the inventory reservation, leaving stock net-zero. That is the exact behavior the ACID→ACD shift has to replace with an explicit compensation.

## [010] The Reference Monolith (sldId 265)

03

Six bounded contexts, one shared schema, and planted coupling smells.

> Introduces the Django reference monolith this whole migration starts from: a fresh Django 5.2 LTS + DRF build, not a decomposed system with the extractions undone. Six smells, each tagged in the code, each cured by a named pattern.

## [011] THE MONOLITH · ARCHITECTURE · One Django project, six apps, one shared schema (sldId 266)

p. 11

[chip] python · django

```python
# examples/00-monolith/config/settings.py
INSTALLED_APPS = [
    "common.apps.CommonConfig",
    "order.apps.OrderConfig",
    "inventory.apps.InventoryConfig",
    "payment.apps.PaymentConfig",
    "shipping.apps.ShippingConfig",
    "notification.apps.NotificationConfig",
    "review.apps.ReviewConfig",
]

# SMELL: every app above migrates into ONE shared Postgres schema,
# the coupling this system unwinds, context by context.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (_parsed_db_url.path or "/monolith").lstrip("/"),
        "USER": _parsed_db_url.username or "monolith",
    }
}
```

examples/00-monolith/config/settings.py: six Django apps, one shared Postgres schema, the coupling this system unwinds one seam at a time

> Every app in INSTALLED_APPS is a full bounded context, not a module convenience: order/inventory/payment/shipping/notification/review map 1:1 onto the six services the system eventually extracts, in rising order of difficulty. The DATABASES block is the smell the data-ownership material spends the most slides curing.

## [012] THE MONOLITH · SMELLS · Each smell maps to the pattern that removes it (sldId 267)

p. 12

- Six smells, each tagged # SMELL in the code: a shared schema, a god checkout service, one ACID transaction spanning every context, a synchronous notification call inside that transaction, no anti-corruption layer, and auth tangled into an otherwise independent context.
- Each smell maps to the pattern that cures it: the shared schema to owned data, the single transaction to a saga, the synchronous call to an outbox.
- By the end of the extraction roadmap every smell but the two kept for the frozen baseline is struck through in the project's own SMELLS.md, crossed out as each cure landed rather than just described as fixed.

> The map the deck keeps returning to: the anti-corruption layer cures smell #5 (no ACL) and #6 (review tangled in auth); owned data and the outbox cure #1 and #4 (shared schema, synchronous send); the saga cures #2 and #3 (god service, one ACID transaction). If time is short, this is the one slide worth not skipping: everything downstream is a cure for something named here.

## [013] Finding the Seams (sldId 268)

04

Event storming, bounded contexts, and the coupling ladder.

> Introduces domain-driven seam-finding as the technique that precedes every extraction here. The six bounded contexts aren't an architecture diagram handed down from above; they're what falls out of event storming the checkout flow.

## [014] FINDING THE SEAMS · EVENT STORMING · Lay out the events, then cluster by aggregate (sldId 269)

p. 14

- Lay out what happens in a checkout (order placed, stock reserved, payment captured, shipment dispatched, customer notified) before any code moves.
- The clusters that fall out are the bounded contexts the system extracts in rising order of difficulty: review, notification, inventory, payment, shipping, order.
- A seam drawn around a cluster of events is a seam a reader can explain in one sentence; a seam drawn around a file structure usually can't.

> This is light on ceremony: event storming here isn't a multi-day workshop artifact, it's the discipline of naming what happened before naming what owns it. The six-context list follows the same vocabulary (OrderDto/OrderStatus/StockDto/Topics) carried through from the monolith's own Django apps into every extracted service, not an arbitrary split.

## [015] FINDING THE SEAMS · BOUNDED CONTEXTS · A real seam has a clean boundary (sldId 270)

p. 15

- A real seam has a boundary the domain already respects: the data crossing it is data the domain already exchanged, so the anti-corruption layer at that boundary has almost nothing left to translate.
- Service count follows the domain, not the other way around: this project stopped at six contexts plus a data-less gateway because that's where the real seams ran out, not because a target number was hit.
- The modular-monolith-with-decomposed-databases trap is the warning sign for the opposite failure: splitting a schema before splitting the coupling that made it one schema in the first place.

> The pattern-language retrospective returns to this trap by name: a database split with no corresponding code split is strictly worse than the monolith it replaced, because it gives up atomic consistency and gets independent deployability back for nothing.

## [016] The Strangler Fig in Practice (sldId 271)

05

A proxy in front, an ACL at the seam, events to notify.

> Walks the strangler-fig mechanics this migration used: a thin ASGI reverse-proxy façade, an anti-corruption layer at each boundary, and the first event-driven extraction with no synchronous dependency on the monolith at all.

## [017] THE STRANGLER FIG · THE FOUR MOVES · Observe, seam, divert, retire (sldId 272)

p. 17

Figure 14.1: The strangler fig's four moves, in the order that matters: intercept, route, incrementally replace, retire, with a reversibility window spanning the first three and a warning against retiring too early.

> The warning on retiring too early is the whole point of this figure: this project kept the monolith frozen-in-repo (a reference branch plus tags) all the way through the sixth extraction, and only removed the fallback path once every context had its own equivalence gate green. Retire is a one-way door; the other three moves aren't.

## [018] THE STRANGLER FIG · PROXY ROUTING · The edge router chooses old or new by flag (sldId 273)

p. 18

Figure 14.2: Content-based routing: the STRANGLER_REVIEW_ENABLED flag off vs. on, both topologies routing through the same proxy against the same shared schema.

> The proxy is a Starlette + httpx.AsyncClient streaming ASGI reverse-proxy, not a Camel route; there's no Python equivalent of a dedicated integration-routing framework, so this is a project-first implementation. The chunked-body bug found during this build matters: the proxy forwarded the inbound body as an unread stream, so POSTs arrived at the Django/WSGI monolith empty, invisible to in-process mock-transport tests, caught only when Newman ran against a real socket. The fix: buffer the body so a correct Content-Length goes upstream. The lesson generalizes: equivalence has to be proven against the real backend over a real socket.

## [019] THE STRANGLER FIG · THE ACL · An anti-corruption layer keeps the new service clean (sldId 274)

p. 19

Figure 16.2: The ACL is a translation boundary, not just another request: notification-service's OrderPlacedEvent sits between the monolith's Kafka contract and the service's own owned schema.

> Contrast two ACL instances built here: the content-based router is a one-dimensional routing decision (pick a backend by path). inventory.proto is the harder case: a wire contract kept distinct from both the monolith's and the service's own domain vocabulary, with a drift guard that fails the build the moment the checked-in .proto and the generated stubs disagree.

## [020] THE STRANGLER FIG · EVENT-DRIVEN NOTIFICATION · The first extraction reacts to an event, not a call (sldId 275)

p. 20

Figure 17.2: One outbox row, two independent consumer groups, one flag choosing who answers the read, the first extraction with no synchronous dependency on the monolith at all.

> Notification is also the project's first owned schema from day one: no shared-table entanglement to unwind later, unlike review (which stays on the shared schema, a named deferral) or inventory (which needs a one-time CDC bridge). This is the cheapest possible extraction shape, and it's sequenced second for exactly that reason.

## [021] Data Across the Seam (sldId 276)

06

From a shared schema to owned data, without losing an event.

> Walks database-per-service, the transactional outbox, CDC as a temporary bridge, CQRS, and the ACID-to-ACD transaction boundary: the five data-ownership moves that together cure the shared-schema and synchronous-call smells named in the monolith's own smell list.

## [022] DATA · OWNED, NOT SHARED · Database-per-service is the goal (sldId 277)

p. 22

Figure 18.1: The three data-ownership postures this project built, in the order it built them: review stays on the shared schema (a named deferral), notification owns its schema from day one, inventory owns its schema too but needed a one-time CDC backfill to get there.

> All three postures are legitimate, not a hierarchy where only 'fully owned' counts as done: review's shared-schema deferral is a named decision, not an oversight, and it's still true at the end of the project. The point of this figure is that a real migration shows all three stages at once, in different services, simultaneously.

## [023] DATA · THE OUTBOX WRITE · Write the business row and the event row in one transaction (sldId 278)

p. 23

Figure 17.1: The outbox cure changes the last write inside checkout's transaction, not the transaction itself: a synchronous out-of-process send becomes one more row in the same commit.

> This pattern is used and reused across the whole system: it cures the dual-write hazard in the monolith's own checkout, then gets a second, more mature instance in payment-service's own outbox. A declined or failed checkout leaves zero outbox rows, confirmed by test.

## [024] DATA · THE OUTBOX RELAY · Relay the outbox row; the consumer dedupes idempotently (sldId 279)

p. 24

[chip] python · fastapi

```python
# examples/07-order-service/app/relay.py
async def _publish_one(self, session: AsyncSession, event: OutboxEvent) -> None:
    topic = self._topic_for(event.event_type)
    key = event.aggregate_id.encode("utf-8")
    value = json.dumps(event.payload).encode("utf-8")
    await self._producer.send_and_wait(topic, key=key, value=value)
    # A crash here -- after the publish, before the stamp -- re-sends this
    # row on the relay's next poll. AT-LEAST-ONCE, by design.
    await repository.mark_outbox_event_published(
        session, event.id, published_at=datetime.now(UTC)
    )
```

examples/07-order-service/app/relay.py: publish, then stamp published_at; the async mechanics behind this loop live in 201-FastAPI

> Keep this to the shape, not the asyncio.Task plumbing: 201-FastAPI owns that depth. The comment on this line names the failure mode directly: a crash between publish and stamp re-sends the same row. That's an at-least-once contract, and it's why every consumer of this event has to be idempotent on its own side; the next two slides show both ways this project made that true.

## [025] DATA · CDC AS A BRIDGE · Change data capture backfills, then gets torn down (sldId 280)

p. 25

Figure 19.2: CDC tails the Postgres write-ahead log for a one-time backfill plus a transition-window sync, then is retired on its own documented runbook: grep the CI gates today and Debezium is not there.

> This is the pattern this system shows at every stage of its own lifecycle: live during the inventory cutover window, then gone, by design, on a runbook (drain, delete connector, drop the replication slot and publication, disable the flag). Transaction log tailing was never meant to be permanent, and the project confirms it never became one.

## [026] DATA · CQRS · Split the write model from the read model where shapes diverge (sldId 281)

p. 26

Figure 21.1: CQRS, concretely: one write aggregate, one order_view projection, upserted in the same local transaction as every write; every GET is served exclusively from the projection.

> This is order-service's own read model, and it's the first CQRS projection the read path in this project depends on: every write path upserts it in the same transaction as the mutation, so there's no second async step that could leave the read side stale under normal operation. Appendix B has the rebuildable-projection figure that proves it's a cache, not a second source of truth.

## [027] DATA · ACID BECOMES ACD · Across services, eventual consistency with compensation (sldId 282)

p. 27

Figure 22.1: ACID → ACD: Atomicity, Consistency, and Durability survive for a smaller scope; Isolation is the one letter traded for a window the saga manages explicitly: a PENDING order visible and real before payment or shipping has an opinion on it.

> That Isolation gap is real. A PENDING order is a legitimate, visible state a reader can query before the saga resolves it; ACD names that window and gives it a state machine, the saga, instead of pretending the old single-transaction guarantee still holds.

## [028] Coordinating Across Services (sldId 283)

07

Sagas: two styles, same checkout, and failure as a first-class concern.

> Walks choreographed and orchestrated sagas side by side on the same checkout flow, plus the idempotent-compensation mechanism that makes a redelivered event or a retried RPC safe either way.

## [029] COORDINATING · TWO STYLES · Choreography and orchestration, same checkout (sldId 284)

p. 29

Figure 24.1: Choreography has no coordinator; orchestration has exactly one: the same checkout, solved two structurally opposite ways in the same codebase.

> This contrast matters: a project that only ever needed one style would be missing real teaching value. Payment's saga has no box anywhere that knows the whole sequence; shipping's saga re-embeds a DB-backed orchestrator that does.

## [030] COORDINATING · THE CHOREOGRAPHED SAGA · Payment reacts to the order-placed event (sldId 285)

p. 30

[chip] python · aiokafka

```python
# examples/05-payment-service/app/consumer.py
async def _consume_loop(self) -> None:
    assert self._consumer is not None
    async for record in self._consumer:
        try:
            event = OrderPlacedEvent.model_validate(record.value)
            await service.process_order_placed(self._session_factory, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            # one bad record must not kill the background task -- log and
            # keep consuming; it never silently stops delivery for every
            # order placed afterward.
            logger.exception("failed to process order.placed at offset %s", record.offset)
```

examples/05-payment-service/app/consumer.py: no box anywhere knows the whole sequence; it emerges from independent event subscriptions reacting one hop at a time

> There is no monolith original for this write path; the monolith still charges in-process, synchronously. This consumer is authored directly on aiokafka idioms, sitting on both sides of Kafka: it consumes order.placed and produces its own payment.captured/payment.declined from its own transactional outbox.

## [031] COORDINATING · THE ORCHESTRATED SAGA · Shipping conducts its own steps and compensations (sldId 286)

p. 31

[chip] python · fastapi

```python
# examples/06-shipping-service/app/orchestrator.py
STEPS = [
    {"name": "enrich", "compensate": None},
    {"name": "dispatch", "compensate": "cancel_shipment"},
    {"name": "book_carrier", "compensate": None},
    {"name": "emit", "compensate": None},
]

async def advance(session_factory, settings, saga_id: int) -> None:
    # one step, one transaction -- SELECT ... FOR UPDATE + an idempotent guard
    status = await _advance_one_step(session_factory, settings, saga_id)
    if status == SAGA_RUNNING:
        await advance(session_factory, settings, saga_id)
    elif status == SAGA_COMPENSATING:
        await compensate(session_factory, settings, saga_id)
```

examples/06-shipping-service/app/orchestrator.py: one coordinator, four steps; resume_running_sagas() crash-resumes from the persisted step_index

> A database-backed saga orchestrator on this project's async SQLAlchemy stack: select(Saga).with_for_update() instead of raw asyncpg FOR UPDATE. The crash-resume scan at startup is a durability upgrade over an in-memory coordinator: kill the process mid-saga, restart, and it resumes from the persisted step without re-running what already completed.

## [032] COORDINATING · IDEMPOTENT CONSUMERS · A redelivered event must not double-apply (sldId 287)

p. 32

Figure 17.3: At-least-once delivery, exactly-once effect: application-level check-then-insert handles the common case, a database partial-unique index backstops the race.

> Two layers, not one: the application-level check-then-insert is the common path, and the database's own partial unique index is what closes the narrow window where two redeliveries race the check itself. Both the monolith's own consumer and notification-service's consumer use this same two-layer shape.

## [033] COORDINATING · COMPENSATION, NOT ROLLBACK · Undo a committed step with a compensating action (sldId 288)

p. 33

Figure 23.3: A compensating Release survives redelivery at two independent layers: the Kafka-event status-transition guard and the RPC-layer compensations ledger.

> This closes a gap the gRPC Reserve/Release pair opened: once a reservation decrement lives in another service's own database, the free rollback a single transaction used to provide is gone, and this two-layer idempotency is what replaces it. Proven live: stock held constant across forced redelivery on both paths.

## [034] Communication, Contracts & the Chassis (sldId 289)

08

REST, gRPC, GraphQL, and the registry that keeps them compatible.

> Walks protocol fit across the finished system, the two contract mechanisms this project exercises (a byte-identical .proto with a drift guard, and a live Apicurio schema registry demo), and the FastAPI chassis every service runs on.

## [035] COMMUNICATION · PROTOCOL FIT · Pick the protocol by the shape of the call (sldId 290)

p. 35

Figure 26.1: Three protocols, one system: REST for every service's own surface, gRPC for the one hot synchronous path, GraphQL for bounded aggregation at a gateway with no data of its own.

> gRPC earned exactly one seam (order→inventory reservation), not every seam: it's the project's only strongly-typed, low-latency inter-service call, picked because strong typing and a tight latency budget mattered enough to justify a second wire protocol alongside REST.

## [036] CONTRACTS · THE gRPC CONTRACT · Inventory's contract is a .proto file, not a shared model (sldId 291)

p. 36

[chip] protobuf

```protobuf
// examples/04-inventory-service/proto/dev/patterncatalyst/inventory/v1/inventory.proto
service InventoryGrpcService {
  rpc CheckStock (CheckStockRequest) returns (StockReply);
  rpc Reserve (ReserveRequest) returns (ReserveReply);
  rpc Release (ReleaseRequest) returns (ReserveReply);
  rpc GetStock (GetStockRequest) returns (StockReply);
}

message StockReply {
  string stock_keeping_unit = 1;   // domain vocab: "sku"
  string display_name = 2;         // domain vocab: "name"
  int64 unit_price_cents = 3;      // domain vocab: "priceCents"
  int32 on_hand_qty = 4;           // domain vocab: "quantityOnHand"
  bool available = 5;
}
```

examples/04-inventory-service/proto/.../inventory.proto: a wire vocabulary kept distinct from the domain vocabulary on both sides of the seam

> The field names are the whole lesson: stock_keeping_unit/display_name/unit_price_cents are not sku/name/priceCents: matching vocabularies on both sides would defeat the ACL's purpose. A scripts/check-proto-drift.sh gate fails the build the moment the checked-in .proto and the generated stubs (vendored into three other services) disagree.

## [037] CONTRACTS · THE GRAPHQL GATEWAY · One query, five sources, fanned out (sldId 292)

p. 37

[chip] python · strawberry

```python
# examples/08-graphql-gateway/app/schema.py
@strawberry.type
class OrderView:
    id: strawberry.ID
    items: list[OrderItemView]

    @strawberry.field
    async def payments(self, info: strawberry.Info) -> list[PaymentView] | None:
        settings = info.context["settings"]
        rows = await fetch_payments(settings, str(self.id))
        return [_payment_from_rest(row) for row in rows]

@strawberry.type
class Query:
    @strawberry.field
    async def order(self, info: strawberry.Info, id: strawberry.ID) -> OrderView | None:
        data = await fetch_order(info.context["settings"], str(id))
        return _order_from_rest(data) if data is not None else None
```

examples/08-graphql-gateway/app/schema.py: one order(id) query, five federated sources, each field nullable so one downstream failure nulls a field, never the whole response

> Every federated field (payments, shipments, stock, reviews) is declared nullable, because a downstream outage should degrade to one null field plus an errors[] entry instead of a 500 for the whole query. This gateway has its own front door; it's never routed through the strangler proxy, and it owns no database of its own.

## [038] CONTRACTS · THE SCHEMA REGISTRY · Avro, wrapped in a registry-aware envelope (sldId 293)

p. 38

Figure 28.2: A hand-rolled wire envelope plus a round trip against a live Apicurio registry: register-or-resolve, encode and publish, consume, fetch the writer schema by global id, decode.

> This demo stays on pure-Python fastavro + aiokafka + Apicurio's v3 REST API rather than confluent-kafka[avro]: that choice (no librdkafka dependency) means hand-rolling the wire envelope, named as a consequence of the choice, not an oversight. It's scoped to one demonstrator, not retrofitted onto the six live event contracts, which still ship as hand-authored JSON and have stayed forward-compatible by discipline rather than registry enforcement, which is itself the case for why a registry would help.

## [039] THE CHASSIS · Config, health, logging, and tracing, as a convention (sldId 294)

p. 39

Figure 27.1: The chassis inside one FastAPI service: config and logging copied into every service by hand, health and error-mapping present on six of eight, tenacity retry on exactly the one call site that has needed it so far.

> This chassis is a convention, not a library: eight near-identical files, not one shared dependency. Config (frozen @dataclass + from_env()) and logging sit at 7-8 of 8; /health and errors.py sit at 6 of 8, each gap tied to a stated structural reason, not an unexplained one. The deeper chassis code (DI wiring, structured logging setup) is 201-FastAPI's job; this deck just names the shape.

## [040] Operating & Delivering (sldId 295)

09

Deploy, mesh, observe, and gate the supply chain.

> Walks the deployment topology, the service mesh's mTLS and tracing story, and the supply-chain gate that scans every built image before it ships: the cross-cutting concerns no single bounded context owns alone.

## [041] OPERATING · DEPLOY TOPOLOGY · Six services, one Kubernetes namespace (sldId 296)

p. 41

Figure 29.1: The mea namespace: eight Deployments/Services behind one NodePort edge, two shared StatefulSets, probes honoring each service's actual health surface rather than copied uniformly.

> Two services (strangler-proxy, review-service) get tcpSocket probes because they have no /health route; the other six get httpGet /health. That's the chassis scorecard showing up directly in the deployment manifest, not glossed over with a uniform probe that would lie about two services' real readiness.

## [042] OPERATING · THE MESH · mTLS and traffic identity, from the platform (sldId 297)

p. 42

Figure 30.1: The meshed mea namespace: mTLS STRICT on every sidecar-to-sidecar hop, one PERMISSIVE exception at the plaintext edge, two backends left unmeshed by design.

> Postgres, Kafka, and the observability backend stay unmeshed: meshing every workload isn't the goal, meshing the application traffic that benefits from mTLS and a service graph is. The one PERMISSIVE carve-out exists because the NodePort edge receives plaintext traffic from outside the mesh entirely, with no sidecar on the client side to negotiate mTLS with.

## [043] OPERATING · THE TRACE · One request, traced end to end across services (sldId 298)

p. 43

Figure 30.2: The hero trace: mesh spans give every one of eight services breadth with zero application code changed; app-level OpenTelemetry on three of eight adds the in-process depth the mesh cannot see.

> This is the property worth making explicit: the mesh and application-level OTel answer different questions. The mesh gives every hop a span, mTLS state, and a service graph automatically; it can't see a specific SQL statement or a business-logic branch. Three services (proxy, order, inventory) get that depth, chosen because the synchronous checkout→reserve path crosses no outbox and needs no extra trace-context plumbing; the Kafka saga hops stay mesh-visible only, named as a scoped-out horizon, not a gap nobody noticed.

## [044] DELIVERING · THE SUPPLY-CHAIN GATE · SBOM, scan, and a policy threshold that fails the build (sldId 299)

p. 44

[chip] bash · syft · grype

```bash
# examples/10-supply-chain/policy.yaml
fail-on: High          # fail the GATING target(s) on any High or Critical
gate-on: fixable        # a finding counts only when a fix path actually exists
targets:
  - name: order-service
    gate: required       # the "after" -- a fixable High/Critical fails the build
  - name: monolith
    gate: reported        # the frozen "before" -- reported, never blocks

# examples/10-supply-chain/demo.sh
syft "${BUILDER}:${image}" -o "cyclonedx-json=$sbom" -q
grype "sbom:$sbom" -c "$GRYPE_CFG" -o json -q > "$scan"
# tally fixable vs. total by severity, then apply fail-on to GATING targets only
```

examples/10-supply-chain/{policy.yaml,demo.sh}: SBOM, scan, and a policy threshold gating on fixable findings only

> The real result landed harder than planned. Both order-service and the frozen monolith scanned 35 High-severity findings in the shared UBI base layer, every one fix-state not-fixed, confirmed with skopeo that no newer patched tag exists to re-pin onto. gate-on: fixable means the gate still surfaces all 35 in grype's own output; it just stops blocking a merge on a CVE no change in this repository can fix. That's a narrower bar, not a lower one.

## [045] OPERATING · THE RESULT · One monolith, six services, no shared schema (sldId 300)

p. 45

Figure 26.3: The final topology: six services and a GraphQL gateway behind one flagless router, the monolith frozen and unwired.

> Flagless is the word to land on: every *_enabled boolean and the monolith fallback path were removed from the proxy as the one irreversible move in the whole project, taken only after a pre-cutover reversibility proof captured the full extracted topology against the bare monolith, both green.

## [046] The Pattern Language, Revisited (sldId 301)

10

Which patterns we used, and where to stop.

> Closes the main body with the pattern-language retrospective: forty-five rows walked against the finished system, three verdicts (earned, adapted, named-and-deferred), and the anti-pattern that explains why this project has eight services and not twenty.

## [047] THE PATTERN LANGUAGE MAP · Where each pattern lives in the catalog (sldId 302)

p. 47

Figure 32.1: The pattern language as one connected flow, colored by verdict: earned, adapted, and five further horizons named and scoped rather than built ahead of need.

> Cross-referenced by concept to sections 05-09: the strangler fig, the ACL plus the gRPC seam, the outbox, CQRS, and both saga shapes are earned outright; the chassis, contracts/registry, and mesh/observability are adapted: real, but narrower in scope than their textbook definition.

## [048] THE PATTERN SCORECARD · Used because it cured a pain we had; deferred is a verdict too (sldId 303)

p. 48

Figure 32.2: The system-wide pattern scorecard: eight patterns earned outright, five adapted into a narrower shape, six named and deferred with the condition that would change the answer.

> A verdict needs three outcomes, not two: 'built vs. not built' can't represent a schema registry that works but covers one event out of a dozen, or a chassis that's real but copied by hand eight times. Full event sourcing, a circuit breaker, a GitOps operator, Loki log aggregation, and Kafka saga-hop tracing are each named with the specific trigger that would earn their place, not a vague gesture at future work.

## [049] WHERE TO STOP · Over-decomposition is the seductive failure (sldId 304)

p. 49

- Over-decomposition is the seductive failure: a database split with no corresponding code split gives up the one thing a monolith provides automatically (atomic consistency) and gets independent deployability back for nothing.
- The tell is a coordinated release across services that were supposed to be independent; the cure is stopping at context-aligned services and splitting further only when a real seam demands it.
- Five named next horizons (a circuit breaker, full event sourcing, a GitOps operator, Loki log aggregation, tracing across a Kafka saga hop) are each a bounded increment with a stated trigger, not a rewrite.

> This is the slide to leave the audience on before the close: the finished system has eight services (six contexts plus the proxy plus the gateway) because that's where real smells ran out, not because twenty would have looked more impressive on an architecture diagram. A nanoservice-sprawl version of the same domain would have the same forty-five-pattern catalog to reach for, and would reach for most of it for the wrong reason.

## [050] 201 · CLOSE · The patterns, end to end: now go deeper (sldId 305)

p. 50

- The main body covered the full pattern arc at just-enough-code depth: seams, data ownership, coordination, contracts, and the operating model that keeps six services running as one system.
- For the async/FastAPI code deep dive (SQLAlchemy 2.0 sessions, the outbox relay as an asyncio task, grpc.aio, Pydantic v2 at the edges), see the 201-FastAPI companion.
- Appendix A (OpenShift/CRC parity) and Appendix B (the extended figure set) are reference depth: keep this deck open in another window while you work, rather than projecting them live.

> This is the handoff slide: the main body is complete at this point and the appendix is reference material, not a continuation of the narrative arc. If the audience is engineers about to implement, point them at 201-FastAPI next; if they're deciding whether to start a migration at all, point them back at the 101.

## [051] Appendix A: OpenShift/CRC Parity (sldId 306)

APP-A

Keep this open in another window.

> OpenShift/CRC parity material: the same eight services and manifests, re-homed onto OpenShift Local with Routes, SCCs, and OpenShift Service Mesh 3 instead of a plain NodePort and vanilla Istio. deploy/k8s, the app code, and the Containerfiles are unchanged: every OpenShift-specific concern is confined to openshift/ and this one appendix.

## [052] APPENDIX · OPENSHIFT TOPOLOGY · The same six services, on OpenShift Local (sldId 307)

p. 52

Figure 33.2: The mea project on OpenShift Local: three SCC postures, two Routes as the only edge: the same eight services, a different platform.

> Three SCC postures, not one: restricted-v2 for the eight app Deployments, nonroot-v2 for Postgres/Kafka under a dedicated service account, and anyuid (with only runAsUser 0 set) for grafana/otel-lgtm. The existing UBI10 images already satisfy restricted-v2 with no rebuild.

## [053] APPENDIX · IMAGE DELIVERY · In-cluster builds, no external registry required (sldId 308)

p. 53

Figure 33.1: Image delivery: a podman build-and-push pipeline on the host, pulled in-cluster from the integrated registry, with a mirror path for a CRC VM with no outbound network access.

> A --mirror-infra path exists specifically for an egress-less CRC VM: it pulls and re-pushes the Postgres and Kafka images so the whole stack can come up with zero outbound network dependency. The live CRC run surfaced and fixed several real portability defects in these scripts, including a rootless-podman permission failure that forced adding a docker build-and-push path.

## [054] APPENDIX · MESH mTLS AT THE EDGE · STRICT mTLS and a Route at the edge (sldId 309)

p. 54

Figure 33.3: STRICT mesh-wide, a PERMISSIVE carve-out at each Route, the Route itself the one unmeshed edge: OpenShift Service Mesh 3 parity with the minikube/Istio mesh.

> The injection mechanism differs by platform and the deck says so rather than letting a reader infer it: minikube uses a sidecar.istio.io/inject pod-template annotation; OSSM 3 on OpenShift uses an istio.io/rev label instead. Verified live: STRICT mTLS rejecting a plaintext caller with exit 56, and Kiali reporting MTLS_ENABLED.

## [055] Appendix B: Extended Pattern Variants (sldId 310)

APP-B

The deeper per-pattern figures that didn't fit the main 50.

> Every diagram from the house figure set not already used in the main body: the deeper per-pattern variants, sequence-level detail on both sagas, and the evidence figures behind the main body's summary claims. Reference depth, not a second narrative pass.

## [056] APPENDIX · SAGA CRASH-RESUME · The saga's state machine survives a crash (sldId 311)

p. 56

Figure 24.3: Resumable by construction: the saga_log row remembers what the process forgot; resume_running_sagas() picks up at the persisted step_index, not from scratch.

> Pair this with the orchestrator code slide; this figure is the proof, not just the claim: kill the process mid-saga, restart, and it resumes without re-invoking a step that already completed.

## [057] APPENDIX · THE CHASSIS SCORECARD · Which chassis capabilities each service adopted (sldId 312)

p. 57

Figure 27.2: Used, partial, and deferred, across all eight services: config and logging at 7-8 of 8, health and error-mapping at 6 of 8 each for a named structural reason, tenacity at 1 of 8, OpenTelemetry and a shared chassis library both named and deferred.

> The deferred row matters as much as the used row: a shared chassis library was not built; each service's config/logging/health code is copied and adapted by hand, a trade-off argued as correct for eight services that still redeploy independently of each other.

## [058] APPENDIX · SHIPPING RESILIENCE · Retries, timeouts, and the circuit breaker in the shipping chassis (sldId 313)

p. 58

Figure 25.1: What already runs (a gRPC deadline, outbox at-least-once, the proxy's 502 fail-safe, the orchestrator's own crash-resume), what's new (a tenacity retry-with-timeout on one HTTP call), and what's named but not yet built.

> The resilience this system has is distributed across existing mechanisms, not concentrated in one new named component: the only new mechanism added here was the tenacity wrapper around shipping's one outbound enrich() call.

## [059] APPENDIX · SCHEMA EVOLUTION · A compatible Avro schema change, end to end (sldId 314)

p. 59

Figure 28.3: Schema evolution against a live BACKWARD rule: an additive field with a default is accepted (200); a field retype is rejected (400) before a single message ships.

> Both outcomes were observed against a real, pinned Apicurio 3.3.3 instance: the HTTP status recorded is 400 (RuleViolationException); an earlier version of Apicurio returned 409 for the same rejection.

## [060] APPENDIX · SYNC-TO-ASYNC CONTRACT · The checkout call crosses from sync REST to an async event (sldId 315)

p. 60

Figure 23.1: The contract change: a 202 is a promise, not a faster 201, contrasting PAYMENT_MODE=synchronous's one round trip against choreographed's 202 PENDING a caller has to poll to resolve.

> This is the project's first change to a previously-stable response contract: the synchronous 201 path stays byte-for-byte unchanged, so the contract change is additive and flag-gated, not a breaking replacement.

## [061] APPENDIX · BEFORE THE REGISTRY · Hand-duplicated schemas were the starting smell (sldId 316)

p. 61

Figure 28.1: Two hand-duplicated copies of the same event contract, one already drifted, versus one schema registered once and resolved by every producer and consumer against the same registry.

> This project's drift is independently re-derived from its own producer/consumer code, not a replayed anecdote. The code has stayed forward-compatible by discipline (every field addition has been additive-and-optional) rather than by any enforcement mechanism.

## [062] APPENDIX · THE gRPC CONTRACT, VISUALLY · Inventory's protobuf ACL, as a diagram (sldId 317)

p. 62

Figure 19.1: The proto is the ACL: two separate domain vocabularies meet only at the wire.

> Visual companion to the gRPC code slide, useful when walking through why the wire vocabulary (stock_keeping_unit, display_name) is kept distinct from both the monolith's and inventory-service's own internal vocabulary.

## [063] APPENDIX · THE GRAPHQL FAN-OUT, VISUALLY · One query, five sources, as a diagram (sldId 318)

p. 63

Figure 26.2: One query, five sources, no data owned locally: a downstream failure nulls one field and appends one errors[] entry, never a crashed request.

> Visual companion to the GraphQL code slide: walk the five fetch targets (order REST, payment REST, shipment REST, review REST per item, inventory gRPC per item) and the nullability discipline that makes partial failure safe.

## [064] APPENDIX · MULTI-OUTBOX SAGA · A saga that spans more than one service's outbox (sldId 319)

p. 64

Figure 20.2: Two outboxes, chained: order-service's outbox feeds payment-service's consumer, which writes its own outbox, consumed in turn, a saga with no orchestrator anywhere in the chain.

> This is the project's first multi-service outbox choreography, and it generalizes the single-outbox pattern into a chain: one transaction, an at-least-once relay, an idempotent consumer, repeated at each hop.

## [065] APPENDIX · CONTENT-BASED ROUTING · The notification service routes by event content (sldId 320)

p. 65

Figure 16.1: One routing decision (a path-prefix predicate) generalized to header- and payload-based routing as the same mechanism scales to more seams.

> Today's implementation is a one-dimensional path-prefix match at the strangler proxy; this figure's side panel names header- and payload-based routing as generalizations of the same predicate, not a different mechanism.

## [066] APPENDIX · THE CHOREOGRAPHED SAGA, VISUALLY · Payment's reaction to checkout, as a sequence diagram (sldId 321)

p. 66

Figure 23.2: The choreographed saga top to bottom: every arrow is a reaction to an event, branching into three terminal outcomes, no orchestrator box anywhere.

> Visual companion to the choreography code slide: trace the three terminal outcomes (captured, declined, and the downstream shipping-failed refund hop); no single component ever holds the whole sequence in view.

## [067] APPENDIX · THE ORCHESTRATED SAGA, VISUALLY · Shipping's orchestration, as a sequence diagram (sldId 322)

p. 67

Figure 24.2: The orchestrated saga: one coordinator, four steps, one compensation decision on a book_carrier failure.

> Visual companion to the orchestration code slide: the SHIP-FAIL sentinel fires at step 3 (book_carrier), after dispatch has already persisted a Shipment row, which is exactly what gives the cancel_shipment compensation something real to undo.

## [068] APPENDIX · ORDER-ITEM SNAPSHOT · The order-item foreign key becomes an owned snapshot (sldId 323)

p. 68

Figure 18.2: From foreign key to snapshot: a live join becomes a denormalized sku/item_name/unit_price_cents copy, moved by an add-backfill-drop migration sequence.

> This is the concrete mechanics behind 'owned, not shared': a three-step migration (add the snapshot columns, backfill them, drop the foreign key) rather than a single breaking schema change.

## [069] APPENDIX · ORDER LIFECYCLE (AWAITING SHIPMENT / REFUND) · The order state machine's less-common branches (sldId 324)

p. 69

Figure 24.4: AWAITING_SHIPMENT is a real intermediate status, not an implementation detail, and the refund hop closes the stranded-payment gap a captured payment would otherwise leave behind.

> Before this status existed, a payment could be captured with no corresponding guarantee that shipping would ever resolve it; the refund hop (payment-service reacting to shipment.failed) is what closes that gap, named and closed rather than left as a known limitation.

## [070] APPENDIX · ORDER LIFECYCLE (PENDING TO TERMINAL) · The order state machine's main path (sldId 325)

p. 70

Figure 22.2: The state machine ACD introduces: three protected, idempotent terminal exits, plus one clearly named failure mode (a stuck PENDING, caught by a bounded-wait poll).

> Each of the three terminal exits (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) is reachable exactly once per order, guarded by the same idempotency discipline as the saga steps that lead to them.

## [071] APPENDIX · THE REBUILDABLE READ MODEL · The order view projection can be rebuilt from the log (sldId 326)

p. 71

Figure 21.2: A rebuildable read model: rebuild_order_view recomputes the projection from the aggregate at any time, and a projection-disabled negative test proves the read path never silently falls back to the write tables.

> That negative test shows the enforcement directly: with the projection disabled, reads go stale instead of silently querying the write tables, proof the read side has a real, enforced boundary, not just a convention.

## [072] APPENDIX · THE OUTBOX RELAY, AT LEAST ONCE · Delivery guarantees the relay makes (sldId 327)

p. 72

Figure 20.1: The bridge, the relay, and the counterpart that makes at-least-once survive contact with reality: an idempotent consumer on the other end, in whichever idiom fits the write.

> Visual companion to the outbox-relay code slide; the generalized shape behind every outbox instance in this project: one transaction, an at-least-once relay, and a consumer-side guarantee that's never optional.

## [073] APPENDIX · A LIGHTER RESERVE/RELEASE SAGA · A smaller saga shape for a smaller workflow (sldId 328)

p. 73

Figure 19.3: Reserve/release across the boundary: where the free rollback went once a decrement lives in another service's own database, and the compensating Release that replaces it.

> Before this seam existed, a single transaction.atomic() gave a free rollback across reserve, order, payment, and shipping; this figure shows exactly what has to replace that once the reservation decrement crosses a process boundary.

## [074] APPENDIX · REVIEW, SHIM VS. NATIVE · The review service's two extraction designs (sldId 329)

p. 74

Figure 15.1: The shim design (a thin FastAPI shim over the Django ORM, documented but never shipped) versus the native design (native async SQLAlchemy, no monolith import at all), the same read contract either way.

> The shim design was never committed as running code once two concrete problems surfaced while sketching it: bridging Django's synchronous ORM into FastAPI's async loop, and a backwards build-time dependency on the entire monolith just to reach one model. The real payoff is structural, not a startup-time number: shim vs. native import timing came back statistically indistinguishable.

## [075] APPENDIX · THE CUTOVER TIMELINE, VISUALLY · Six seams, in dependency order, as a timeline (sldId 330)

p. 75

Figure 14.3: The cutover evidence trail: one unedited Newman suite, four runs (flag off, flag on, flag reverted, and a forced-down negative that fails loudly by design).

> That fourth run is the one worth narrating: with the extracted service killed outright, the suite goes RED (6/6 assertions failed) rather than quietly passing, proof the equivalence gate enforces rather than rubber-stamps.

## [076] APPENDIX · THE SUPPLY-CHAIN GATE, VISUALLY · SBOM, scan, gate, as a pipeline diagram (sldId 331)

p. 76

Figure 31.1: The syft-to-grype-to-policy pipeline for both the gating target and the frozen monolith, plus the four additive CI checks converging on one repository ruleset.

> Visual companion to the supply-chain code slide: both scanned images produce the identical 265-match, 35-High result from their shared UBI base layer, which is itself evidence the finding is a base-image fact, not an order-service-specific regression.

## [077] APPENDIX · TWO CUTOVER DIMENSIONS · Reversibility and blast radius, scored per seam (sldId 332)

p. 77

Figure 19.4: Two independent cutover flags as a 2x2 grid: the two corners this project exercised, against the two split corners that are only safe during the CDC-backfilled transition window.

> Inventory's cutover has two independent flags (reads vs. reserve/release) rather than one combined switch; this figure is the grid of which combinations were exercised and which are only sound transiently, during the backfill window.

## [078] Appendix C: Reference (sldId 333)

APP-C

The runnable examples, the stack, and the terms used in this deck.

> Reference material for follow-along: the examples/ directory map, every stack version pinned across the project, and a glossary of the terms this deck used without re-defining each time.

## [079] APPENDIX · THE EXAMPLES · Eleven runnable examples, one per seam (sldId 334)

p. 79

- 00-monolith (the frozen before), 01-strangler-proxy, 02-review through 07-order-service (the six extractions, in rising order of difficulty).
- 08-graphql-gateway (the data-less aggregation gateway), 09-schema-registry-demo (the Apicurio round trip), 10-supply-chain (the SBOM/scan/policy gate).
- Every code slide in this deck draws from one of these directories: this is the index, not a summary; read the source for the rest.

> If someone wants to run anything live after this talk, this is the slide to screenshot: every directory name here is a real, independently runnable example with its own AGENTS.md and README, a complete project, not an excerpt assembled for the deck.

## [080] APPENDIX · STACK & VERSIONS · FastAPI, SQLAlchemy 2.0, aiokafka, Postgres, Kafka (sldId 335)

p. 80

- FastAPI 0.143.2 + uvicorn, SQLAlchemy 2.1.4 (asyncio) + asyncpg, Pydantic 2.14.1, Alembic, aiokafka, grpcio + protobuf, Strawberry GraphQL, tenacity; Python 3.14, managed by uv.
- The frozen monolith: Django 5.2 LTS + DRF, psycopg, gunicorn. Testing: pytest + pytest-django + pytest-asyncio, Testcontainers, Newman.
- The platform: Kubernetes via kustomize, Istio 1.31, OpenTelemetry + grafana/otel-lgtm, Apicurio 3.3.3, syft/grype, plus Helm and OpenShift Service Mesh 3 for the CRC appendix.

> Every version here is a real pin from a service's own pyproject.toml or a CI workflow, not a representative placeholder, useful as a quick compatibility check before someone tries to reproduce an example locally.

## [081] APPENDIX · GLOSSARY · Terms used in this deck (sldId 336)

p. 81

- Strangler fig: replace a system one seam at a time behind a router, never a rewrite. Seam: a boundary the domain already respects. ACL: a translation layer that keeps two vocabularies from leaking into each other.
- Outbox: write the domain row and the event row in one transaction. Saga: a multi-step operation across services that compensates on partial failure, choreographed or orchestrated. CQRS: a write model and a read model, split where their shapes diverge.
- ACD: the three letters of ACID a saga keeps, with Isolation traded for a window it manages explicitly. Chassis: the conventions every service in the system follows, copied by hand rather than shared as a library.

> Each term maps to a concept this deck develops in depth: seam and the ACL anchor the strangler fig, outbox and ACD anchor data ownership, saga and CQRS anchor cross-service coordination, and chassis anchors the communication and operating conventions.

## [082] CLOSING · GO DEEPER · Where to go from here (sldId 337)

p. 82

- For the ideas and the advantage case at architect altitude, see the 101 deck; for the async/FastAPI code deep dive underneath every pattern here, see 201-FastAPI.
- Every pattern in this deck is grounded in a runnable example in the repository, and every diagram a figure from the reference system; nothing here is illustrative-only.
- The pattern-coverage matrix behind this deck's scorecard slides is the single source of truth; check any claim in this deck against it.

> This is the deck's actual last slide: leave it up during Q&A. If a question goes deeper than just-enough-code depth, the direct answer for most of them is '201-FastAPI covers that'; if a question is about whether to start a migration at all, the 101 is the better reference.

## [083] SCAN TO EXPLORE · Take it with you (sldId 338)

p. 83

The reference implementation

Site, runnable FastAPI services, and the strangler-fig migration

```
patterncatalyst.github.io/modernizing-enterprise-applications-python
```

Workshops & Tutorials

The whole series: every workshop, tutorial, and deck in one place

```
patterncatalyst.github.io/patterncatalyst-workshops-tutorials-list
```

> This is the 201 patterns deck. The two codes take it with you: on the left, the reference implementation: the site, the runnable FastAPI services, and the strangler-fig migration. On the right, the Workshops and Tutorials hub: every workshop, tutorial, and deck in the series in one place. Both are public on the Pattern Catalyst GitHub organization.
