// deck.js — "Modernizing Enterprise Applications (Python)" — 201-FastAPI
// (the async deep dive). The async stack underneath the patterns: SQLAlchemy
// 2.0/asyncpg, Pydantic v2, aiokafka + outbox relay, grpc.aio, chassis-as-
// convention, OTel. Code-deepest of the three decks.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// WAVE 2 — every content slide carries real code excerpted from examples/,
// full advantage-framed bullets, and thick speaker notes. Sections:
// A Async Foundation / B Pydantic v2 at the Edges / C Messaging the Async Way
// / D The Chassis as Convention + OTel / E Together / F Appendix (packaging,
// testing).

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing-201-FastAPI-r1.0.pptx";
const REV = "r1.0";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python) — 201-FastAPI (the async deep dive)";
let pageNum = 0;

function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
}

// ---- local content helpers (thin wrappers over the bundled deck-helpers) --
function content(eyebrow, title, bullets, notes, opts) {
  const s = S();
  addContentTitle(s, eyebrow, title);
  addBullets(s, bullets, opts || {});
  addNotes(s, notes);
  return s;
}
function diagram(eyebrow, title, png, caption, notes, opts) {
  const s = S();
  addDiagramSlide(s, eyebrow, title, png, caption, opts || {});
  addNotes(s, notes);
  return s;
}
function code(eyebrow, title, lang, lines, caption, notes, opts) {
  const s = S();
  addCodeSlide(s, eyebrow, title, lang, lines, caption, opts || {});
  addNotes(s, notes);
  return s;
}

// ===== COVER ==================================================================
{
  const s = pres.addSlide();
  pageNum += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201-FASTAPI", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 12, bold: true, color: COLOR.red, charSpacing: 4, align: "left", valign: "middle" });
  s.addText([{ text: "The async", options: { breakLine: true } },
             { text: "deep dive" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The async stack underneath the patterns: SQLAlchemy 2.0/asyncpg, Pydantic v2, aiokafka and the outbox relay, grpc.aio, the chassis as convention, and OTel.",
    { x: 6.00, y: 4.55, w: 6.80, h: 1.15, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 201-FastAPI deep dive, built for the Python engineers who write the services, not the architects sizing the migration. Where the 201 shows just enough code to carry each pattern, this deck opens every file: the async SQLAlchemy 2.0/asyncpg session, the Pydantic v2 models at every edge, the aiokafka producer and consumer, the outbox relay running as a background asyncio task, grpc.aio on both sides of the inventory contract, the FastAPI chassis as a repeated convention rather than a shared library, and the OpenTelemetry instrumentation wired into three of the eight services. Every code slide is excerpted from the real examples/ tree in this repository, not a paraphrase — the file path is on every caption so you can go open it yourself. The arc: the async foundation, Pydantic v2 at the edges, messaging the async way, the chassis plus OTel, a together section that traces one checkout end to end, and an appendix on packaging and testing. Advantage framing throughout: async buys you concurrency without a thread pool, Pydantic buys you validation at the boundary instead of scattered through the service, and the outbox buys you a crash-safe handoff to Kafka. Thirty to forty minutes, assumes the audience already has FastAPI and asyncio fundamentals.");
}

// ===== AGENDA ==================================================================
{
  const s = S();
  addContentTitle(s, "201-FASTAPI · THE ASYNC DEEP DIVE", "The stack underneath every pattern in the 201");
  addTwoColBullets(s,
    ["The async foundation — SQLAlchemy 2.0, asyncpg, the unit of work, and the outbox write in the same transaction as the business row",
     "Pydantic v2 at the edges — request/response models, the ACL translation, the GraphQL edge, and the sync-to-async contract",
     "Messaging the async way — aiokafka producer and consumer, the outbox relay as a background asyncio task, grpc.aio, the registry envelope"],
    ["The chassis as convention, plus OTel — config/logging/health/errors/resilience repeated per service, and zero-code instrumentation on three of them",
     "Together — one checkout's full async path through the orchestrated saga, the choreographed saga, CQRS, and a crash mid-flight",
     "Appendix — packaging with uv and UBI10, and testing with pytest, Testcontainers, and Newman"]);
  addNotes(s, "Six sections, forty-two slides. The first three sections build upward — storage, validation, messaging — because each one depends on the last: the outbox write only matters once you've seen the async session commit it, and the relay only matters once you've seen the outbox row it polls. The chassis section is where the Java sibling's framework-level chassis gets replaced by eight copies of the same convention — that's not a gap, it's this stack's actual shape, and the slide set says so with numbers instead of hand-waving. Together stitches four of the earlier diagrams into one continuous request. The appendix is reference material: packaging and testing apply uniformly and don't need their own narrative arc. Point out up front that every code slide names its source file — this deck is a tour of the real examples/ tree, not a slide-deck approximation of it.");
}

// ===== SECTION A — THE ASYNC FOUNDATION =======================================
divider("A", "The Async Foundation", "SQLAlchemy 2.0, asyncpg, the unit of work, and the outbox write.",
  "Opens the async-foundation section. Four ideas, in order: the async engine and session factory every service builds once at startup; the unit-of-work function that commits the business row and the outbox row together, never one without the other; the Alembic migration that is the schema's own contract, service by service, with no shared database; and the outbox write itself, which is what makes the Kafka publish a separate, retryable concern instead of a point of failure inside the request. Everything downstream in this deck — the relay, the consumers, the saga orchestrator — depends on this section landing first.");

code("ASYNC FOUNDATION · THE ASYNC SESSION", "An async engine and session factory, once per service",
  "python · sqlalchemy", [
    "# examples/07-order-service/app/db.py",
    "from sqlalchemy.ext.asyncio import (",
    "    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,",
    ")",
    "",
    "def create_engine(database_url: str | None = None) -> AsyncEngine:",
    "    return create_async_engine(",
    "        resolve_database_url(database_url),   # postgresql:// -> +asyncpg://",
    "        pool_pre_ping=True,",
    "        connect_args={\"server_settings\": {\"search_path\": \"order_svc,public\"}},",
    "    )",
    "",
    "def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:",
    "    return async_sessionmaker(engine, expire_on_commit=False)",
    "",
    "async def get_session(request: Request) -> AsyncIterator[AsyncSession]:",
    "    # one session per request, from the factory the lifespan built at startup",
    "    factory = request.app.state.session_factory",
    "    async with factory() as session:",
    "        yield session",
  ], "examples/07-order-service/app/db.py — every standalone service in this project repeats this file nearly byte for byte, changing only its schema name.",
  "The engine is built once, at lifespan startup, and handed to every request as a FastAPI dependency — no per-request engine construction, no blocking connection setup on the request path. asyncpg is the driver underneath SQLAlchemy's async engine, resolved from a plain postgresql:// URL so the same DATABASE_URL env var works whether a human is running psql against it or the app is connecting through SQLAlchemy. The search_path server setting is the one per-service difference: order-service sets order_svc because order is a reserved SQL keyword and would need defensive quoting on every unqualified reference otherwise — documented once in this file instead of re-litigated at every call site. expire_on_commit=False matters for an async session specifically: the default would force a lazy-load round trip the next time an attribute is touched after commit, and a lazy load after the session's event loop context has moved on is exactly the kind of bug that's easy to introduce and hard to trace back to this one setting. This is the floor everything else in the deck stands on.");

code("ASYNC FOUNDATION · THE UNIT OF WORK", "The repository commits the business row and the outbox row together",
  "python · sqlalchemy", [
    "# examples/07-order-service/app/repository.py",
    "async def create_order_with_outbox_and_view(",
    "    session, *, customer, items, shipping_address, payment_method, created_at,",
    ") -> Order:",
    "    order = Order(customer_id=customer.id, status=\"PENDING\", ...)",
    "    session.add(order)",
    "    await session.flush()          # INSERT ... RETURNING populates order.id",
    "",
    "    order_items = [OrderItem(order_id=order.id, **item) for item in items]",
    "    session.add_all(order_items)",
    "",
    "    view = OrderView(order_id=order.id, status=order.status, ...)",
    "    session.add(view)              # the CQRS read model, same transaction",
    "",
    "    outbox_event = OutboxEvent(",
    "        aggregate_type=\"order\", aggregate_id=str(order.id),",
    "        event_type=\"order.placed\", payload=payload, published_at=None,",
    "    )",
    "    session.add(outbox_event)",
    "",
    "    await session.flush()",
    "    await session.commit()         # aggregate + view + outbox, one transaction",
    "    return order",
  ], "examples/07-order-service/app/repository.py — the only module that touches the ORM classes directly; every write function here owns its own commit.",
  "Three tables, one commit: the order aggregate, the order_view CQRS projection, and the outbox row that will eventually become the order.placed Kafka event. The flush after adding the order is what SQLAlchemy needs to run the INSERT and populate order.id before the order_items and the outbox payload can reference it — flush is not commit, it just forces the pending SQL to run inside the still-open transaction. The guarantee this buys: a reader can never observe the aggregate without its matching view row, and the outbox row is never written without the aggregate landing too, because all three live or die on the same COMMIT. This is the same shape SQLAlchemy's synchronous unit-of-work pattern uses — the only thing async adds is the await in front of flush and commit, because asyncpg's wire protocol is non-blocking and SQLAlchemy's async engine exposes that as coroutines instead of hiding it behind a thread pool.");

code("ASYNC FOUNDATION · MIGRATIONS AS A CONTRACT", "Alembic owns the schema, service by service",
  "python · alembic", [
    "# examples/07-order-service/migrations/versions/0001_create_order_schema.py",
    "SCHEMA = \"order_svc\"            # not \"order\" -- a reserved SQL keyword",
    "",
    "def upgrade() -> None:",
    "    op.execute(f\"CREATE SCHEMA IF NOT EXISTS {SCHEMA}\")",
    "",
    "    op.create_table(\"orders\",",
    "        sa.Column(\"id\", sa.BigInteger(), primary_key=True, autoincrement=True),",
    "        sa.Column(\"customer_id\", sa.BigInteger(), sa.ForeignKey(f\"{SCHEMA}.customers.id\")),",
    "        sa.Column(\"status\", sa.String(32), nullable=False),",
    "        ..., schema=SCHEMA)",
    "",
    "    op.create_table(\"order_view\",   # the CQRS read model, one row per order",
    "        sa.Column(\"order_id\", sa.BigInteger(), primary_key=True),",
    "        sa.Column(\"items\", sa.JSON(), nullable=False),",
    "        ..., schema=SCHEMA)",
    "",
    "    op.create_table(\"outbox\", ..., schema=SCHEMA)",
    "    op.create_index(\"idx_order_outbox_unpublished\", \"outbox\", [\"created_at\"],",
    "        schema=SCHEMA, postgresql_where=sa.text(\"published_at IS NULL\"))",
  ], "examples/07-order-service/migrations/versions/0001_create_order_schema.py — five tables, two families: command-side and the order_view read side.",
  "Every standalone service owns a separate Postgres schema in the same shared instance, and Alembic is the only thing that ever creates or changes it — no shared database migration, no schema a second service reaches into. order_svc is the one naming wrinkle to flag here: order is a reserved word in the SQL standard, and CREATE SCHEMA order would still parse but every unqualified reference near a FROM, JOIN, or DDL clause becomes a quoting problem from then on — the search_path setting, every table_args schema key, Alembic's own version_table_schema, all of it. Picking order_svc once, in this one file's constant, avoids re-fighting that on every line elsewhere. The partial index on outbox — WHERE published_at IS NULL — is what keeps the relay's poll query cheap as the table grows: a crash-safe outbox is worthless if the unpublished-row scan degrades into a full table scan after a few million rows.");

diagram("ASYNC FOUNDATION · THE OUTBOX WRITE", "Write the outbox row in the same transaction",
  "outbox-write-in-transaction",
  "An async SQLAlchemy 2.0 session commits the business row and the outbox row together, or neither.",
  "This diagram is the picture of the code two slides back: one COMMIT, three rows, no partial state possible. Walk the failure case out loud — if the process crashes between session.add(outbox_event) and session.commit(), Postgres rolls the whole transaction back, so there is no order with a missing outbox row and no outbox row for an order that never landed. That atomicity is the entire reason the outbox pattern works without a distributed transaction across Postgres and Kafka: the hard part (don't lose the event, don't double-apply the business change) gets solved entirely inside one database's ACID guarantee, and Kafka only has to deal with redelivery, which is a much easier problem than exactly-once delivery across two systems. Point out that this is a database transaction, not a Kafka transaction — Kafka never appears in this picture at all.");

diagram("ASYNC FOUNDATION · THE RELAY, AT LEAST ONCE", "The relay is what makes a crash survivable",
  "outbox-relay-at-least-once",
  "The relay loop publishes at least once; the consumer side (section C) dedupes.",
  "The relay is a separate background loop, polling the same outbox table the previous slide committed to, publishing each unpublished row to Kafka, then stamping published_at in its own short transaction. The crash window is specific and named, not hand-waved: if the process dies after the Kafka publish succeeds but before the published_at stamp commits, the next poll sees the row as still unpublished and sends it again. That is a deliberate at-least-once contract, not a bug — the alternative (stamp first, publish second) would risk losing the event entirely on the same crash, which is strictly worse for an order-placed notification than a duplicate. This is the hinge slide for the whole deck: every consumer you'll see in section C has to assume redelivery is possible, and every one of them is built to cope with it.");

// ===== SECTION B — PYDANTIC V2 AT THE EDGES ===================================
divider("B", "Pydantic v2 at the Edges", "Models, settings, validation, and the ACL translation.",
  "Opens the Pydantic v2 section. Five ideas: service settings as a plain frozen dataclass (not a Pydantic model — the correction worth making up front, since the obvious guess is wrong); the request/response schema models FastAPI validates against automatically; the anti-corruption-layer translation as a thin Pydantic boundary; the GraphQL gateway's Strawberry types as the edge's own typed contract; and the sync-to-async crossing where one Pydantic shape backs both the HTTP request body and the Kafka event payload. The throughline: validate once, at the boundary, in a typed model — never scatter manual dict-key checks through business logic.");

code("PYDANTIC V2 · SETTINGS, AND WHERE IT ISN'T PYDANTIC", "A frozen dataclass, read from the environment at call time",
  "python · dataclasses", [
    "# examples/07-order-service/app/config.py",
    "@dataclass(frozen=True)",
    "class Settings:",
    "    http_port: int",
    "    database_url: str",
    "    kafka_bootstrap_servers: str",
    "    inventory_grpc_target: str",
    "    outbox_poll_ms: int",
    "    grpc_timeout_s: float",
    "",
    "    @classmethod",
    "    def from_env(cls) -> Settings:",
    "        return cls(",
    "            http_port=int(os.environ.get(\"HTTP_PORT\", 8088)),",
    "            database_url=os.environ.get(\"DATABASE_URL\", _DEFAULT_DATABASE_URL),",
    "            grpc_timeout_s=float(os.environ.get(\"GRPC_TIMEOUT_S\", 5.0)),",
    "            ...",
    "        )",
  ], "examples/07-order-service/app/config.py — every standalone service repeats this shape; it is a dataclass, not a pydantic.BaseSettings model.",
  "This is the one place in the deck worth correcting a reasonable assumption: this project does not use Pydantic's BaseSettings for service configuration, anywhere, in any of the eight services. Settings is a plain frozen dataclass with a from_env() classmethod that reads os.environ at call time rather than at import time — the reason that matters is testability: a test can set an env var right before constructing a Settings or building an app, and from_env() picks it up fresh every time it's called, where a module-level singleton built at import would already have frozen the wrong values. Pydantic v2 is reserved for the wire models in the next few slides — request bodies, response bodies, and event payloads — where validation against untrusted input earns its cost. A handful of environment variables, coerced with int() and float(), doesn't need a validation framework on top of it. Knowing where a framework is skipped by design is as useful as knowing where it's reached for.");

code("PYDANTIC V2 · REQUEST/RESPONSE MODELS", "Validation at the edge, not scattered through the service",
  "python · pydantic", [
    "# examples/07-order-service/app/schemas.py",
    "class OrderCreate(BaseModel):",
    "    model_config = ConfigDict(populate_by_name=True)",
    "    customer_id: int = Field(alias=\"customerId\")",
    "    items: list[OrderLineIn] = Field(min_length=1)",
    "    payment_method: str = Field(alias=\"paymentMethod\")",
    "    shipping_address: str = Field(alias=\"shippingAddress\")",
    "",
    "class OrderOut(BaseModel):",
    "    model_config = ConfigDict(populate_by_name=True)",
    "    id: int",
    "    customer_id: int = Field(alias=\"customerId\")",
    "    total_cents: int = Field(alias=\"totalCents\")",
    "    items: list[OrderItemOut]",
    "",
    "def order_view_to_out(view: OrderView) -> OrderOut:",
    "    # the one place that bridges order_view.order_id -> OrderOut.id",
    "    return OrderOut(id=view.order_id, customerId=view.customer_id, ...)",
  ], "examples/07-order-service/app/schemas.py — camelCase wire contracts over snake_case Python fields, via Field(alias=...).",
  "FastAPI validates OrderCreate automatically on every POST — a missing field, a quantity below Field(ge=1), or an empty items list never reaches a handler function at all; it comes back as a 422 with a field-level error before any business logic runs. The alias pattern is the wire-contract trick worth lingering on: Python fields stay snake_case for every tool that cares about PEP 8, while the JSON on the wire is camelCase, because the field population reads customerId off the request body but the Python code everywhere else just writes order.customer_id. order_view_to_out is called out as the one function that bridges the read model's column name, order_id, onto the API's frozen field name, id — routes never construct OrderOut by hand, specifically so that bridge only exists in one place. There is no shared schema module across services — each one hand-authors its own structurally identical copy of a consumed event's shape, which is the real cost of a JSON contract with no schema registry (that gap is exactly what section C's registry envelope slide closes, for the one demo that opts into it).");

diagram("PYDANTIC V2 · ACL TRANSLATION", "Translate at the boundary, not throughout the service",
  "acl-contract-seam",
  "The anti-corruption layer as a thin Pydantic translation at the boundary, not a scattered one.",
  "The inventory gRPC contract uses its own wire vocabulary — stock_keeping_unit, on_hand_qty, unit_price_cents — kept distinct from order-service's internal sku/quantity/unit_price_cents naming by design, a gap to preserve rather than clean up, because it's what forces a real translation step to exist instead of the two shapes happening to agree by accident. The translation lives in exactly one place per service — order-service's inventory client translates the raw proto types into plain dataclasses before anything else in the service ever sees them, and no raw proto message is allowed to escape that module. Pydantic plays the same role at the REST edges: OrderCreate and OrderOut are each a single, narrow seam where wire format meets domain type, so a consumed event's shape changing never means hunting through business logic for every place a raw dict key was read.");

code("PYDANTIC V2 · THE GRAPHQL EDGE", "Strawberry types are the edge's own validated shape",
  "python · strawberry", [
    "# examples/08-graphql-gateway/app/schema.py",
    "@strawberry.type",
    "class OrderItemView:",
    "    sku: str",
    "    quantity: int",
    "    unit_price_cents: int",
    "",
    "    @strawberry.field",
    "    async def stock(self, info: strawberry.Info) -> StockView | None:",
    "        settings = info.context[\"settings\"]",
    "        data = await fetch_stock(settings, self.sku)   # gRPC, resolved lazily",
    "        return _stock_from_grpc(data)",
    "",
    "def build_schema(settings: Settings) -> strawberry.Schema:",
    "    return strawberry.Schema(",
    "        query=Query,",
    "        extensions=[",
    "            lambda: QueryDepthLimiter(max_depth=settings.max_query_depth),",
    "            lambda: MaxTokensLimiter(max_token_count=settings.max_query_tokens),",
    "        ],",
    "    )",
  ], "examples/08-graphql-gateway/app/schema.py — the gateway's only resolver module; fields resolve lazily, only when a client's selection set asks for them.",
  "Strawberry types are this edge's own typed contract, the GraphQL-side equivalent of a Pydantic model: a field declared int or str is validated against that type the moment a resolver returns a value, and Strawberry converts the Python snake_case field names to camelCase in the schema automatically, matching the same wire convention the REST services already use. stock is resolved per order item, lazily — a query that never asks for stock never calls inventory-service's gRPC GetStock at all, which is the N+1-avoidance argument for a field-level resolver over eagerly joining everything up front. The depth and token limiters are built as factory lambdas rather than shared instances specifically because passing a shared instance is deprecated in this version of strawberry-graphql — an instance would get reused across requests instead of built fresh per request, which matters once a limiter is tracking any per-request state.");

diagram("PYDANTIC V2 · THE GRAPHQL FAN-OUT", "One validated query, five sources underneath",
  "graphql-gateway-five-source-fanout",
  "The gateway's single typed query fans out to five backing services, each field resolved and nulled independently.",
  "One order(id) query can touch all five extracted services: order-service for the base read model, payment-service and shipping-service over REST for payments and shipments, review-service over REST for per-item reviews, and inventory-service over gRPC for per-item stock. Every one of those four federated fields is declared nullable, a choice that matters because GraphQL's own null-propagation rule bubbles a non-null field's failure up to the nearest nullable ancestor. If stock were declared non-null and inventory-service were down, the whole order would come back null instead of just that one field. Each resolver lets a DownstreamUnavailable exception propagate uncaught rather than swallowing it into a silently empty list — that's what keeps the response's errors array populated instead of hiding a partial failure as a normal-looking answer.");

diagram("PYDANTIC V2 · SYNC TO ASYNC", "The checkout call crosses from a sync request to an async event",
  "checkout-sync-to-async-contract",
  "The Pydantic model that is the contract on both sides of that crossing: OrderCreate in, OrderPlacedEvent out.",
  "One request, two Pydantic models, one crossing: the client's HTTP POST validates against OrderCreate, and the event order-service's own outbox eventually publishes validates against OrderPlacedEvent on the far side — the two models don't share a class, but every downstream consumer (payment-service, notification-service) treats OrderPlacedEvent as a frozen contract. This is the moment the request/response cycle ends and the choreography begins: POST /api/orders returns 202, not 201 or 200, because the order is PENDING the moment the handler returns — the aggregate, the outbox row, and the order_view projection are already committed, but payment hasn't been charged yet and won't be until payment-service's own consumer reacts to the event this slide is about. 202 is the status code that matches that architecture precisely.");

// ===== SECTION C — MESSAGING THE ASYNC WAY ====================================
divider("C", "Messaging the Async Way", "aiokafka, the relay as an asyncio task, grpc.aio, and the registry envelope.",
  "Opens the messaging section — the mechanical core of the deep dive. Order: an aiokafka producer publishing a registry-aware envelope (the schema-registry demo), an aiokafka consumer reacting to a choreographed event (payment-service), the outbox relay running as a background asyncio.Task alongside the FastAPI app (the mechanic the 201 only gestures at), idempotent dedupe against redelivery, compensation modeled as just another consumer, the grpc.aio contract and server for the one synchronous call in the system, and the Avro/registry wire envelope. Every consumer and relay in this section runs as an asyncio.Task started from the app's own lifespan — there is no separate worker process, no Celery, no second deployment artifact.");

code("MESSAGING · THE AIOKAFKA PRODUCER", "An async producer publishes the registry-aware envelope",
  "python · aiokafka", [
    "# examples/09-schema-registry-demo/app/producer.py",
    "class OrderAvroProducer:",
    "    def __init__(self, registry, bootstrap_servers, *, topic=TOPIC, artifact_id=ARTIFACT_ID):",
    "        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)",
    "        self._schema = parsed_schema()",
    "",
    "    async def start(self) -> None:",
    "        await self._producer.start()",
    "        registered = await self._registry.register_or_resolve(",
    "            self._artifact_id, load_schema_json(),",
    "        )",
    "        self._global_id = registered.global_id   # idempotent: v1 once, resolved after",
    "",
    "    async def send(self, event: DemoOrderPlaced) -> int:",
    "        avro_bytes = encode_order_placed(event, self._schema)",
    "        envelope = encode_envelope(self._global_id, avro_bytes)",
    "        key = str(event.order_id).encode(\"utf-8\")",
    "        await self._producer.send_and_wait(self._topic, key=key, value=envelope)",
    "        return self._global_id",
  ], "examples/09-schema-registry-demo/app/producer.py — a teaching surface for the Avro/registry mechanics, standalone from the real order.placed event.",
  "AIOKafkaProducer.start() opens the broker connection once; send_and_wait() awaits the broker's acknowledgment before returning, which is what makes this producer's success return value trustworthy rather than fire-and-forget. register_or_resolve is idempotent by construction — the first call creates the Apicurio artifact's version 1, and every later call with the same schema text resolves back to the existing registration instead of creating a duplicate, so restarting this demo never grows the registry. Note the scope: this module is a standalone demonstrator with no database and no outbox of its own, publishing directly to its own order.events.avro.demo topic — it's here to show the registry envelope mechanics clearly, not to replace the JSON order.placed event every other service already depends on.");

code("MESSAGING · THE AIOKAFKA CONSUMER", "An async consumer reacts to the choreographed event",
  "python · aiokafka", [
    "# examples/05-payment-service/app/consumer.py",
    "class OrderPlacedConsumer:",
    "    async def start(self) -> None:",
    "        self._consumer = AIOKafkaConsumer(",
    "            self._settings.order_placed_topic,",
    "            bootstrap_servers=self._settings.kafka_bootstrap_servers,",
    "            group_id=self._settings.consumer_group,",
    "            auto_offset_reset=\"earliest\",",
    "            enable_auto_commit=True,",
    "            value_deserializer=lambda raw: json.loads(raw.decode(\"utf-8\")),",
    "        )",
    "        await self._consumer.start()",
    "        self._task = asyncio.create_task(self._consume_loop(), name=\"order-placed-consumer\")",
    "",
    "    async def _consume_loop(self) -> None:",
    "        async for record in self._consumer:",
    "            try:",
    "                event = OrderPlacedEvent.model_validate(record.value)",
    "                await service.process_order_placed(self._session_factory, event)",
    "            except asyncio.CancelledError:",
    "                raise",
    "            except Exception:",
    "                logger.exception(\"failed to process record at offset %s\", record.offset)",
  ], "examples/05-payment-service/app/consumer.py — no Django original to lift; authored directly on aiokafka idioms.",
  "group_id binds every replica of payment-service to the same consumer group, so across a replica set exactly one replica charges any given order — Kafka's own partition-assignment protocol handles that, the code doesn't coordinate it manually. auto_offset_reset=\"earliest\" means a fresh deployment with no prior committed offset backfills from the start of the topic instead of only seeing events published after it joins, which matters for a service that might be redeployed or scaled after the topic already has history. The except Exception clause is the detail to slow down on: a single malformed or unprocessable record logs and the loop keeps running, because letting one bad record crash this background task would silently stop payment processing for every order placed afterward — asyncio.CancelledError is re-raised immediately above it, because that one exception means a caller is shutting the task down on its own terms, not a processing failure to swallow. This consumer, and the relay on the next slide, both run as background asyncio.Tasks launched from the same lifespan that builds the session factory — one process, two concerns, running concurrently on one event loop.");

code("MESSAGING · THE RELAY AS AN ASYNCIO TASK", "The outbox relay runs as a background asyncio task",
  "python · asyncio", [
    "# examples/06-shipping-service/app/relay.py",
    "class OutboxRelay:",
    "    async def start(self) -> None:",
    "        self._producer = AIOKafkaProducer(bootstrap_servers=self._settings.kafka_bootstrap_servers)",
    "        await self._producer.start()",
    "        self._task = asyncio.create_task(self._relay_loop(), name=\"shipping-outbox-relay\")",
    "",
    "    async def _relay_loop(self) -> None:",
    "        poll_s = self._settings.outbox_poll_ms / 1000",
    "        while True:",
    "            try:",
    "                published_any = await self._publish_one_batch()",
    "            except Exception:",
    "                logger.exception(\"outbox relay: batch failed, will retry on next poll\")",
    "                published_any = False",
    "            if not published_any:",
    "                await asyncio.sleep(poll_s)",
    "",
    "    async def _publish_one(self, session, event) -> None:",
    "        await self._producer.send_and_wait(topic, key=key, value=value)",
    "        # a crash here -- published, not yet stamped -- re-sends on the next poll",
    "        await repository.mark_outbox_event_published(session, event.id, published_at=...)",
  ], "examples/06-shipping-service/app/relay.py — a simple polling relay, not Debezium/CDC; mirrors payment-service's relay byte for byte except its two topics.",
  "This is the async mechanic the 201 only gestures at: there is no separate relay process, no sidecar, no CDC connector reading the write-ahead log — it's one more asyncio.Task, started from the same lifespan as the HTTP server and the Kafka consumer, sharing the same event loop and the same session factory. asyncio.sleep(poll_s) only runs when the batch was empty, so a busy outbox gets drained back-to-back without waiting out the full poll interval, while an idle one doesn't spin. The exception handling mirrors the consumer's: a transient database or broker hiccup is logged and retried on the next tick rather than killing the task, because a relay that dies silently on one bad batch stops publishing every event after it. The comment on the crash window is the key detail from the earlier outbox-at-least-once diagram made concrete in code — publish happens before the stamp, so a crash between them republishes, and that's the documented tradeoff, not an oversight.");

diagram("MESSAGING · IDEMPOTENT DEDUPE", "A redelivered message must not double-apply",
  "idempotent-consumer-dedupe",
  "The dedupe key and the async transaction that makes the check-and-apply atomic.",
  "Order-service's own saga reactions show the pattern clearly: transition_order_status_with_view runs an UPDATE with a WHERE status = expected_status guard and a RETURNING clause, in one transaction. If a payment.captured event gets redelivered after it already resolved the order, the second UPDATE matches zero rows — the status already moved past expected_status — and the function returns None, the same safe no-op path a legitimate unknown-order lookup takes. Two concurrent deliveries racing each other resolve the same way: only one UPDATE can match the row while it's still in expected_status, so the database itself is the final arbiter, not an in-process lock. Payment-service's own dedupe uses a different mechanic for the same guarantee — check-then-insert backed by a unique index on order_id — proving the idea generalizes: a redelivered message is a normal, expected event, and the guard against double-applying it lives in the database's own transactional semantics, not in trusting Kafka to deliver exactly once.");

diagram("MESSAGING · COMPENSATION AS A CONSUMER", "A compensating action is just another async consumer",
  "idempotent-compensation-two-layers",
  "The compensation handler, idempotent at two layers, implemented as an async consumer.",
  "Inventory-service's Release RPC is the compensating half of Reserve: when checkout fails after a successful reservation — most often a payment decline — the caller restores the stock it had claimed. Release carries an optional idempotency_key, and when a caller supplies one, a redelivered compensation with the same key is a no-op that returns the current stock instead of over-restoring it a second time, via an INSERT ... ON CONFLICT DO NOTHING against a unique index, in the same transaction as the conditional re-increment — the same database-level dedupe discipline as the previous slide, applied to an inverse action instead of a forward one. The two-layer framing in the figure is the two places idempotency has to hold independently: the RPC call itself (the idempotency key) and the saga step that triggers it (shipping-service's own compensation path only runs cancel_shipment once per saga, gated by the orchestrator's own step-completion tracking) — a compensation that only guards one of those two layers can still double-fire through the other.");

diagram("MESSAGING · THE gRPC.AIO CONTRACT", "Inventory's protobuf contract, seen from the async client",
  "inventory-grpc-proto-acl",
  "The .proto contract that grpc.aio generates an async stub from, and the ACL vocabulary gap it crosses.",
  "This is the one synchronous call in the entire choreography: order-service reserves stock over gRPC, waits on the reply, and only then commits the order aggregate — every other inter-service interaction in this deck is async, over Kafka. The proto's wire vocabulary (stock_keeping_unit, on_hand_qty, unit_price_cents) is kept apart from order-service's own internal naming (sku, quantity, unit_price_cents) by design, so the translation layer on the next slide has real work to do instead of the two shapes coincidentally matching. grpc.aio generates an async stub from this same .proto that a synchronous grpc stub would generate from — the contract doesn't change, only the calling convention does: await stub.Reserve(request) instead of a blocking call, which is what lets order-service hold this call inside its own event loop without a dedicated thread.");

code("MESSAGING · THE gRPC.AIO SERVER", "An async gRPC server behind the same FastAPI chassis",
  "python · grpc.aio", [
    "# examples/04-inventory-service/app/grpc_server.py",
    "class InventoryGrpcServiceServicer(inventory_pb2_grpc.InventoryGrpcServiceServicer):",
    "    def __init__(self, session_factory):",
    "        self._session_factory = session_factory   # same factory the HTTP side uses",
    "",
    "    async def Reserve(self, request, context):",
    "        sku, qty = request.stock_keeping_unit, request.requested_qty",
    "        async with self._session_factory() as session:",
    "            rowcount = await repository.reserve(session, sku, qty)  # one conditional UPDATE",
    "            item = await repository.get_by_sku(session, sku)",
    "        return inventory_pb2.ReserveReply(",
    "            stock_keeping_unit=sku,",
    "            reservation_ok=rowcount == 1,",
    "            on_hand_qty=item.quantity_on_hand if item else 0,",
    "        )",
  ], "examples/04-inventory-service/app/grpc_server.py — one engine, two protocol surfaces; no Django original to lift, the monolith's reserve was a different mechanism entirely.",
  "This gRPC server runs inside the same process as inventory-service's FastAPI app, sharing the same async session factory the HTTP routes use — one engine, two protocol surfaces, started as a grpc.aio.server() task on the same event loop from the same lifespan. Each RPC opens its own short-lived session rather than sharing a request-scoped one, because gRPC calls aren't bound to FastAPI's request/response cycle the way HTTP routes are — there's no natural per-request scope to hook a session into, so a session per call keeps each RPC's unit of work self-contained. Reserve's concurrency safety comes from a single conditional UPDATE statement, not a read-then-write: rowcount == 1 means the row matched and was decremented atomically; a concurrent caller racing for the same last unit of stock gets rowcount == 0 and a clean reservation_ok=false, with no read-then-write window for two callers to both believe they succeeded.");

diagram("MESSAGING · THE REGISTRY ENVELOPE", "Avro, wrapped for safe schema evolution",
  "avro-wire-envelope-registry-flow",
  "The wire envelope every async producer and consumer agrees on: a magic byte, an 8-byte global schema id, then the Avro bytes.",
  "The envelope is a small, hand-rolled framing format — one magic byte, an 8-byte Apicurio global schema id, then the raw Avro-encoded bytes with no embedded schema of their own — defined in exactly one module so producer and consumer never hand-roll their own pack/unpack logic independently. The schema id travels with every message, which is what lets a consumer resolve the exact schema version a given message was written against, even after the registry has multiple versions of the same artifact — that's the core value a registry adds over a hand-maintained JSON contract: schema evolution with a server that can enforce compatibility rules, instead of every consumer hoping a producer's new field addition doesn't break it. Keep the scope narrow in how this gets framed: this is a demonstrator for the mechanics, standalone from the real order.placed JSON event every other service in this deck already uses — it shows what adopting a registry would look like, it hasn't replaced anything yet.");

// ===== SECTION D — THE CHASSIS AS CONVENTION + OTEL ===========================
divider("D", "The Chassis as Convention, plus OTel", "Config, logging, health, and errors as convention; OTel as the trace.",
  "Opens the chassis section. The framing to set up front: there is no shared chassis library here, because there is no framework-level dependency-injection container or build-system BOM the way the Java sibling has — each of the eight services copies and adapts the same files by hand. That's reported as a scorecard with real numbers (used/partial/deferred), not glossed over. Six slides: config/logging/health as the repeated convention, errors and the one resilience wrapper this system actually has, the chassis anatomy diagram, the resilience topology (what already runs, what's new, what's named and not built), the zero-code OTel instrumentation on three services with the SQLAlchemy-instrumentor caveat named precisely, and the closing scorecard.");

code("CHASSIS · CONFIG, LOGGING, HEALTH", "The same shape, repeated as a convention across services",
  "python · fastapi", [
    "# examples/06-shipping-service/app/config.py",
    "@dataclass(frozen=True)",
    "class Settings:",
    "    http_port: int",
    "    database_url: str",
    "    order_base_url: str        # r07 re-point: order-service's own order_view",
    "    monolith_base_url: str     # documented operator-only fallback, not read by enrich()",
    "    outbox_poll_ms: int",
    "    enrich_timeout_s: float",
    "",
    "    @classmethod",
    "    def from_env(cls) -> Settings:",
    "        return cls(",
    "            http_port=int(os.environ.get(\"HTTP_PORT\", 8087)),",
    "            order_base_url=os.environ.get(\"ORDER_BASE_URL\", _DEFAULT_ORDER_BASE_URL),",
    "            ...",
    "        )",
  ], "examples/06-shipping-service/app/config.py — seven of eight services repeat this exact shape; review-service predates the convention.",
  "The chassis here is a code-presence question, not a dependency question: config as a frozen dataclass plus from_env(), stdlib RotatingFileHandler logging to a per-service log file, and a GET /health route are each copied into service after service rather than imported from one shared package. monolith_base_url is worth a beat: it's a documented, operator-only fallback, kept and logged at startup but never read by the actual enrich() call path — an operator can point ORDER_BASE_URL itself at the frozen monolith during an incident without a code change, but nothing in this service fails over to it automatically. That's the right amount of safety net for a decommission window: present, named, and never silently engaged. Chapter 27's own scorecard counts this precisely — config is used on 7 of 8 services (review-service predates the convention), logging on all 8, and a Containerfile on all 8 — numbers worth having on hand before the scorecard diagram two slides from now.");

code("CHASSIS · ERRORS & RESILIENCE AS CONVENTION", "A typed error hierarchy, and the one retry this system has", "python · fastapi", [
    "# examples/04-inventory-service/app/errors.py",
    "class ApiError(Exception):",
    "    status_code: int = 500",
    "    error_code: str = \"ERROR\"",
    "",
    "class ResourceNotFound(ApiError):",
    "    status_code = 404",
    "    error_code = \"NOT_FOUND\"",
    "",
    "def install_exception_handlers(app: FastAPI) -> None:",
    "    @app.exception_handler(ApiError)",
    "    async def _handle_api_error(request, exc: ApiError) -> JSONResponse:",
    "        return JSONResponse(status_code=exc.status_code,",
    "            content=_error_body(exc.error_code, exc.message))",
    "",
    "# examples/06-shipping-service/app/enrich_client.py -- the one retry in this system",
    "@retry(",
    "    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),",
    "    stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4),",
    ")",
    "async def fetch_shipping_address(order_id: int) -> str: ...",
  ], "examples/04-inventory-service/app/errors.py + examples/06-shipping-service/app/enrich_client.py — grep this project's examples/ tree for tenacity and this is the only hit.",
  "ApiError and its subclasses map every domain failure onto one uniform JSON body — {error, message, timestamp} — once per service, via a single exception handler; six of the eight services carry this file, the two gaps (strangler-proxy and the GraphQL gateway) each for a structural reason named in the scorecard rather than an oversight. The tenacity retry is scoped as narrowly as a resilience mechanism can be: it wraps exactly one outbound call, shipping-service's synchronous enrich step reaching order-service mid-saga, and it only retries httpx.TransportError or httpx.TimeoutException — connection refused, DNS failure, a blown per-call timeout. A non-2xx response or a 2xx missing the field the saga needs raises immediately as a different exception and is never retried, because that's a contract violation, not a transient blip, and retrying a wrong answer three times just produces the same wrong answer three times slower. No other service wraps an outbound call this way because no other service makes the kind of synchronous, mid-saga HTTP call that needs it.");

diagram("CHASSIS · ANATOMY", "DI wiring and the shape every service shares",
  "fastapi-chassis-anatomy",
  "Dependency injection, lifespan, and the chassis anatomy common to every service.",
  "FastAPI's own Depends() mechanism is the dependency-injection layer here — get_session as a per-request dependency, settings built once and attached to app.state — there's no separate DI container to configure. The lifespan context manager is where the real wiring happens: it builds the engine and session factory, starts the Kafka consumer and the outbox relay as background tasks, and on shutdown cancels both cleanly before the process exits. The ghost box in this figure — OpenTelemetry/Prometheus, a circuit breaker, a shared chassis library — names what hasn't been built rather than pretending the chassis is complete; that distinction (built vs. named-but-not-built) is what the next two slides back up with a real count.");

diagram("CHASSIS · RESILIENCE TOPOLOGY", "What already runs, what's new, and what's still named, not built",
  "shipping-resilience-chassis",
  "Four mechanisms this system already depends on, one new mechanism this chapter adds, and two patterns named as deferred, with the reason for each.",
  "Four resilience mechanisms already existed before anyone called them that: a bounded gRPC deadline on the inventory client since the reservation call was first written, the outbox's at-least-once delivery guarantee, the conditional-UPDATE idempotent dedupe on saga reactions, and the saga orchestrator's own crash-resume durability (section E's closing example). Tenacity's retry is the one new piece this system adds on top. A circuit breaker and a bulkhead are named and explicitly not built — a circuit breaker buys a state machine that stops calling a dependency that has demonstrated it won't succeed, instead of retrying it on every call forever, and that's real value, but nothing in this system's own traffic has yet produced the sustained failure rate that would justify the added complexity. The framing to land: resilience mechanisms here were each built to solve a correctness problem a specific extraction already had, not added speculatively because a catalog says a distributed system should have them — the day a circuit breaker is justified, it's a decorator at one call site, not a redesign.");

diagram("CHASSIS · OTEL, ZERO-CODE ON THREE SERVICES", "opentelemetry-distro auto-instruments; no manual spans, by choice",
  "mesh-hero-trace-waterfall",
  "The hero trace from a synchronous, connected request path, produced entirely by zero-code auto-instrumentation into the LGTM stack.",
  "OTel in this project is zero-code only — opentelemetry-distro plus the exact set of opentelemetry-instrumentation-* packages opentelemetry-bootstrap resolves for each service's own dependencies, pinned in pyproject.toml, with the Containerfile's entrypoint wrapped as opentelemetry-instrument uvicorn app.main:app. There is no hand-authored tracer.start_as_current_span anywhere in this codebase; every span in the hero trace comes from an auto-instrumentor, not an application developer reaching for the OTel API directly. The hero trace traces one synchronous path end to end — the client through strangler-proxy, strangler-proxy's httpx call to order-service, and order-service's grpc.aio call to inventory-service's Reserve — chosen specifically because it's the one connected request/response chain in the system; the four Kafka saga hops stay mesh-only because propagating trace context through an outbox row and restoring it in the relay is real additional work this chapter named and didn't take on. Name the version-skew caveat precisely: opentelemetry-instrumentation-sqlalchemy's own dependency metadata caps its support at sqlalchemy<2.1.0, and order-service and inventory-service both pin sqlalchemy[asyncio]==2.1.4 — kept at that version because this project upgrades the tool rather than downgrading the pin when the two disagree. The SQLAlchemy instrumentor loads, finds no version it recognizes, and declines to patch — one warning line at startup, no crash. opentelemetry-instrumentation-asyncpg carries no such cap and instruments the real driver underneath SQLAlchemy's async engine, so every database span in the hero trace names the raw SQL asyncpg executed, with none of SQLAlchemy's own ORM-level attributes attached — the database work is fully visible, described at the driver's level rather than the ORM's.");

diagram("CHASSIS · THE SCORECARD", "Which chassis capabilities each service actually adopted",
  "chassis-scorecard",
  "Config, health, errors, resilience, OTel — scored per service across three bands: used, partial, and deferred.",
  "Three bands, real counts: USED on every service — config via from_env() on 7 of 8 (review-service predates the convention), stdlib logging on 8 of 8, a Containerfile on 8 of 8. PARTIAL, with a named reason per gap — GET /health on 6 of 8 (absent from the proxy and review-service), the uniform errors.py mapping on 6 of 8 (absent from the proxy and the GraphQL gateway, each for a structural reason), tenacity on exactly 1 of 8. DEFERRED, with zero footprint before this chapter — OpenTelemetry (now on 3 of 8, the previous slide's three services), a circuit breaker or bulkhead (named in planning prose, no code anywhere), and a true shared chassis library (every file here is copied and hand-adapted per service, never imported from one shared package). The closing point for the whole section: a scorecard with real per-service counts is worth more than a claim that the chassis is complete, because it tells a reader exactly what to expect from the ninth service someone builds next.");

// ===== SECTION E — TOGETHER ====================================================
divider("E", "Together", "One request's full async path, start to finish.",
  "Traces one checkout through five diagrams already introduced individually, now stitched together as one continuous story: the orchestrated shipping saga, the choreographed payment saga, the async CQRS write/read split, a crash mid-saga and its resume, and the simplest path (notification) as the closer. No new code in this section — it's where everything from sections A through D gets pointed back to as pieces of one request.");

diagram("TOGETHER · THE ORCHESTRATED PATH", "Checkout to shipped, one async path at a time",
  "orchestrated-shipping-saga-sequence",
  "The full async call sequence from the orchestrator through its compensations.",
  "Shipping-service's saga is a four-step state machine — enrich, dispatch, book_carrier, emit — each step its own transaction, each guarded by a SELECT ... FOR UPDATE row lock plus an idempotent completion check before it runs. A SHIP-FAIL sentinel (lifted byte for byte from the monolith's own dispatch rule) fires inside book_carrier, after dispatch has already persisted a Shipment row — that ordering gives the compensation, cancel_shipment, something real to undo. advance() recurses forward through the steps until COMPLETED or hands off to compensate(), which walks only the already-completed steps in reverse and writes the terminal shipment.failed outbox event in the same transaction as the COMPENSATED status flip — never a saga marked done with no outcome event queued.");

diagram("TOGETHER · THE CHOREOGRAPHED PATH", "The same checkout, reacting instead of conducting",
  "choreographed-payment-saga-sequence",
  "The same workflow traced through choreography instead of orchestration.",
  "Payment-service has no orchestrator at all — it just reacts. The order.placed consumer from section C fires process_order_placed, which runs a deterministic DECLINE rule (lifted byte for byte from the monolith's own charge logic) and always produces a Payment row and an outcome event, capture or decline, never an exception. That's the structural contrast with the orchestrated path on the previous slide: shipping-service's saga is a state machine that knows about all four of its own steps and their compensations; payment-service only knows how to answer one event, publish one outcome, and let whoever's downstream — shipping-service, order-service's own saga reactions — decide what that outcome means for them. Same checkout, same Kafka topic as the trigger, two different coordination shapes.");

diagram("TOGETHER · CQRS, ASYNC", "The write path and the read projection, both async", "order-cqrs-write-read-split",
  "The async write path and the async projection rebuild, together.",
  "Order-service's five tables split cleanly into two families: the write aggregate (orders, order_items, customers, the outbox) and the one read table, order_view, that every GET handler queries exclusively — app/routes.py never imports Order or OrderItem at all. Every write function that touches the aggregate also upserts order_view in the same transaction, which is the unit-of-work slide from section A paying off here specifically: a reader can never observe an order whose view hasn't caught up, because there's no commit where one exists without the other. rebuild_order_view exists as an explicit escape hatch — the projection is rebuildable from current aggregate state at any time, never a second source of truth that could drift from the write side and need reconciling.");

diagram("TOGETHER · CRASH-RESUME", "Kill the process mid-saga; it resumes from the outbox", "saga-state-machine-crash-resume",
  "The crash-resume test that proves the async relay and the saga state machine agree after a restart.",
  "This is the proof, not just the claim: the integration test seeds a Saga row directly with status=RUNNING, step_index=1, and a context already carrying step 0's output — exactly the row a real process would leave behind if it died right after committing enrich but before attempting dispatch. resume_running_sagas(), the same call the app's lifespan makes on every startup, is invoked, and the test monkeypatches fetch_shipping_address to raise if it's ever called again — proving step 0 is not re-run, because step_index=1 says it already completed. The saga then reaches COMPLETED, with exactly one shipment.dispatched outbox row, proving steps 2 through 4 do run and pick up exactly where the simulated crash left off. Tie this back to section A's unit-of-work and section C's at-least-once relay: durability here isn't a separate mechanism, it's those two ideas combined — persisted step state plus a relay that always eventually publishes what got committed.");

diagram("TOGETHER · THE EVENT-DRIVEN PATH", "Notification reacts to the same event stream", "event-driven-notification-topology",
  "The lowest-risk async path, end to end, as the closing example.",
  "Notification-service is the simplest consumer in the whole system: it only ever consumes order.placed, it never produces an event of its own, and it has no outbox to maintain. That asymmetry makes it the right closer, because it shows the pattern set scales down as cleanly as it scales up — not every service needs a relay, a saga, or a CQRS split; a pure reactor just needs the same idempotent-consumer discipline from section C's dedupe slide and nothing more. Closing the Together section here, on the lowest-complexity path, is a reminder that the deep mechanics in sections A through D are there when a service's job calls for them, not a tax every service pays regardless of what it actually does.");

// ===== SECTION F — APPENDIX (PACKAGING + TESTING) =============================
divider("F", "Appendix — Packaging & Testing", "uv, UBI10, and the Containerfile; pytest, Testcontainers, and Newman.",
  "Packaging and testing conventions that apply uniformly across every service in this deck, kept out of the main narrative because they don't vary service to service the way the async mechanics do. Two code slides — the Containerfile/pyproject.toml packaging convention, and the crash-resume integration test's seeding helper — plus one bullets slide on Newman's contract checks at the REST edge.");

code("APPENDIX · PACKAGING", "uv-managed dependencies, built on UBI10", "containerfile", [
    "# examples/07-order-service/Containerfile",
    "ARG UBI_PYTHON_IMAGE=registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791928506",
    "ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1",
    "",
    "FROM ${UV_IMAGE} AS uv",
    "FROM ${UBI_PYTHON_IMAGE} AS builder",
    "COPY --from=uv /uv /uvx /usr/local/bin/",
    "COPY pyproject.toml uv.lock ./",
    "RUN uv sync --locked --no-install-project --no-dev   # deps cache independently of app code",
    "COPY app ./app",
    "RUN uv sync --locked --no-dev",
    "",
    "FROM ${UBI_PYTHON_IMAGE}",
    "COPY --from=builder /app /app",
    "USER 1001:0                 # non-root, arbitrary-UID compatible",
    "EXPOSE 8088",
    "CMD [\"sh\", \"-c\", \"alembic upgrade head && exec opentelemetry-instrument uvicorn app.main:app --host 0.0.0.0 --port 8088\"]",
  ], "examples/07-order-service/Containerfile + pyproject.toml — multi-stage, non-root, the same shape every service in this project shares.",
  "Two-stage build: a builder stage that resolves dependencies before the app code is copied in, so a code change never invalidates the dependency-install cache layer, and a slim runtime stage that copies only the finished /app tree out of it. UBI10 publishes only a -minimal Python 3.14 image, which has no shadow-utils for useradd — so instead of creating a user, the Containerfile fixes group ownership on /app and runs as UID 1001 with GID 0, the same arbitrary-UID-compatible pattern every container in this project uses, OpenShift-ready without any OpenShift-specific flag. The CMD line is where the OTel wrapper from the previous section actually lands: opentelemetry-instrument wraps only the uvicorn process, after alembic upgrade head has already run, so the migration step itself produces no span — and OTEL_SDK_DISABLED=true by default means this wrapper is a true no-op everywhere outside a cluster whose config has turned it on explicitly.");

code("APPENDIX · TESTING", "pytest + Testcontainers exercise the real async stack", "python · pytest", [
    "# examples/06-shipping-service/tests/integration/test_crash_resume.py",
    "async def _seed_crashed_saga(session_factory, *, order_id, address) -> int:",
    "    # a Saga row as if enrich (step 0) already committed, then the process died",
    "    saga = Saga(order_id=order_id, status=SAGA_RUNNING, step_index=1,",
    "                context={\"enrich\": {\"address\": address}}, ...)",
    "    session.add(saga)",
    "    await session.commit()",
    "    return saga.id",
    "",
    "async def test_resume_running_sagas_continues_from_persisted_step_index(...):",
    "    monkeypatch.setattr(enrich_client, \"fetch_shipping_address\", _must_not_be_called)",
    "    saga_id = await _seed_crashed_saga(session_factory, order_id=order_id, address=\"...\")",
    "    resumed_count = await orchestrator.resume_running_sagas(session_factory, settings)",
    "    assert resumed_count == 1",
    "    assert enrich_calls == []   # step 0 is never re-run",
  ], "examples/06-shipping-service/tests/integration/test_crash_resume.py — a real, isolated Testcontainers Postgres, not the throwaway dev Postgres the unit layer shares.",
  "Every standalone service splits tests into two independent layers: a Kafka-free, gRPC-free unit layer against a real but already-migrated Postgres, and an integration layer where Testcontainers stands up its own isolated Postgres and Kafka per test run, independent of whatever dev database happens to be running locally. This crash-resume test is the proof behind the Together section's crash-resume diagram — it simulates a crash by inserting a Saga row directly, bypassing the normal handler entirely, then calls the exact same resume_running_sagas() function the app's own lifespan calls on every real startup. Asserting enrich_calls == [] is what makes this a real proof instead of a happy-path check that only shows the saga eventually finishes — it specifically fails loudly if resume ever re-runs a step the persisted state says already completed.");

content("APPENDIX · REST CONTRACT CHECKS", "Newman exercises the REST edges from outside the process",
  ["A Newman/Postman collection in tooling/newman/ checks each service's REST contract from outside the process — real HTTP requests against a running service, asserting on status codes and response shapes, with no knowledge of the async internals underneath.",
   "This is the same behavioral-contract idea the 201's equivalence gate applies at the whole-system level, scoped down to one service's edge: a contract test doesn't care whether a response was built from asyncpg, SQLAlchemy's ORM layer, or a CQRS projection — only that the camelCase JSON shape and status code match what the monolith's own equivalent endpoint returned.",
   "Running the async-mechanics tests from this deck (pytest + Testcontainers) and the contract tests (Newman) together covers two different failure modes: pytest catches a wrong async implementation detail before it ships; Newman catches a contract drift a unit test inside the service would never notice, because the service agrees with itself but no longer agrees with its own documented wire shape."],
  "Newman closes the appendix on a tool that checks the system from the outside, which is a useful contrast to everything else in this deck, which has been code opened from the inside. The equivalence-gate connection is worth making explicit for anyone who's seen the 201: the same instinct — don't trust a migration until you've proven the observable behavior matches — shows up here at a much smaller scope, one service's HTTP edge, with a much lighter tool. Point out that this collection runs in CI on every change to a service's routes, so a contract drift surfaces in a pull request, not in a production incident.");

// ===== CLOSE ===================================================================
content("201-FASTAPI · CLOSE", "The async stack, end to end",
  ["Every pattern in the 201 rests on the async mechanics walked in this deck: an async SQLAlchemy 2.0/asyncpg session and its unit-of-work commit, Pydantic v2 validating every edge, aiokafka and a relay running as a background asyncio task, grpc.aio on the one synchronous call, a chassis repeated as convention across eight services, and zero-code OTel on three of them.",
   "For the pattern set at just-enough-code depth — what each pattern buys and when to reach for it — see the 201. For the advantage case and the strangler journey at altitude, aimed at the decision before any code gets written, see the 101.",
   "The common thread across all three decks: async buys concurrency without a thread pool, the outbox buys a crash-safe handoff between a database commit and a Kafka publish, and a chassis built as a copied convention rather than a shared framework keeps every one of these eight services small enough to read start to finish in one sitting."],
  "Closing summary and hand-off back to the 201 and the 101. The point worth leaving the room with: nothing in this deck was special-cased for a slide — every code excerpt came from a file that's still sitting in examples/ today, runnable with uv sync and pytest exactly as shown. If there's time for one live demonstration, kill a shipping-service process mid-saga, as the crash-resume test does programmatically, and restart it against the same Postgres — watching the saga pick up from its persisted step_index is a more convincing close than any slide in this deck.");


/* --- Scan to explore (QR codes) --- */
{
  const s = S();
  addContentTitle(s, "SCAN TO EXPLORE", "Take it with you");

  s.addImage({ path: `${ASSETS}/qr-modernizing-site.png`, x: 2.30, y: 1.78, w: 3.10, h: 3.10 });
  s.addText("The reference implementation", { x: 1.55, y: 4.98, w: 4.60, h: 0.40,
    fontFace: FONT.title, fontSize: 18, bold: true, color: COLOR.ink, align: "center", valign: "middle" });
  s.addText("Site, runnable FastAPI services, and the strangler-fig migration", { x: 1.45, y: 5.40, w: 4.80, h: 0.72,
    fontFace: FONT.body, fontSize: 13, italic: true, color: COLOR.caption, align: "center", valign: "top" });
  s.addText("patterncatalyst.github.io/modernizing-enterprise-applications-python", { x: 1.45, y: 6.12, w: 4.80, h: 0.32,
    fontFace: FONT.mono, fontSize: 9, color: COLOR.red, align: "center", valign: "middle" });

  s.addImage({ path: `${ASSETS}/qr-hub.png`, x: 7.93, y: 1.78, w: 3.10, h: 3.10 });
  s.addText("Workshops & Tutorials", { x: 7.18, y: 4.98, w: 4.60, h: 0.40,
    fontFace: FONT.title, fontSize: 18, bold: true, color: COLOR.ink, align: "center", valign: "middle" });
  s.addText("The whole series: every workshop, tutorial, and deck in one place", { x: 7.08, y: 5.40, w: 4.80, h: 0.72,
    fontFace: FONT.body, fontSize: 13, italic: true, color: COLOR.caption, align: "center", valign: "top" });
  s.addText("patterncatalyst.github.io/patterncatalyst-workshops-tutorials-list", { x: 7.08, y: 6.12, w: 4.80, h: 0.32,
    fontFace: FONT.mono, fontSize: 9, color: COLOR.red, align: "center", valign: "middle" });

  addNotes(s, "This is the async FastAPI implementation deck. The two codes take it with you: on the left, the reference implementation: the site, the runnable FastAPI services, and the strangler-fig migration. On the right, the Workshops and Tutorials hub: every workshop, tutorial, and deck in the series in one place. Both are public on the Pattern Catalyst GitHub organization.");
}


pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum))
  .catch(e => { console.error(e); process.exit(1); });
