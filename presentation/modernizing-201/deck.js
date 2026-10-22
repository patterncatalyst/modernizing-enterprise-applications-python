// deck.js — "Modernizing Enterprise Applications (Python)" — 201 (the patterns).
// Full technical pattern set across the strangler-fig migration; just-enough
// code (the async mechanics live in 201-fastapi). MAIN body: 50 slides across
// 10 sections, plus Appendix A (OpenShift/CRC, 4), B (extended figures, 23),
// C (reference, 5) = 82 slides.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// WAVE 2 CONTENT PASS — every slide is authored against the real chapters
// (_docs/14-33), the reconciliation ledger (_plans/reconciliation.md), the
// pattern-coverage matrix (_plans/build-plan.md §C), and the real examples/
// source files named in each code slide's caption. Diagram captions are
// drawn from the published figure alt-text/caption pairs in the chapters
// that introduce each figure, not invented fresh for the deck.

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing-201-r1.0.pptx";
const REV = "r1.0";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python) — 201 (the patterns)";
let pageNum = 0;
let mainCount = 0;    // slides counted toward the ~50-main cap
let appendixCount = 0; // slides after the MAIN/APPENDIX boundary

let inAppendix = false;
function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); if (inAppendix) appendixCount += 1; else mainCount += 1; return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
  if (inAppendix) appendixCount += 1; else mainCount += 1;
}

// ---- local stub helpers (thin wrappers over the bundled deck-helpers) -----
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
function code(eyebrow, title, lang, codeLines, caption, notes, opts) {
  const s = S();
  addCodeSlide(s, eyebrow, title, lang, codeLines, caption, opts || {});
  addNotes(s, notes);
  return s;
}

// ===== COVER ==================================================================
{
  const s = pres.addSlide();
  pageNum += 1; mainCount += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 201", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 13, bold: true, color: COLOR.red, charSpacing: 5, align: "left", valign: "middle" });
  s.addText([{ text: "The patterns," , options: { breakLine: true } },
             { text: "end to end" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The full technical pattern set behind the Django-to-FastAPI migration: seams, data ownership, coordination, contracts, and operating the result.",
    { x: 6.00, y: 4.65, w: 6.80, h: 1.05, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 201 — the patterns deck, for engineers and architects implementing a strangler-fig migration. It walks the full pattern set this project actually shipped at just-enough-code depth; the deep async/FastAPI mechanics (SQLAlchemy 2.0 sessions, the outbox relay as an asyncio task, grpc.aio, Pydantic v2 at the edges) live in the 201-FastAPI companion. The main body is 50 slides across ten sections; Appendix A (OpenShift/CRC parity), B (the extended figure set), and C (reference) are deeper material to keep open in another window, not slides to project live.");
}

// ===== AGENDA ==================================================================
{
  const s = S();
  addContentTitle(s, "201 · THE PATTERNS", "The implementation, one section per part — plus an appendix");
  addTwoColBullets(s,
    ["01–02 — Why modernize, the restraint case, and the ADLC + equivalence gate",
     "03–04 — The reference monolith, its smells, and finding the seams with DDD",
     "05 — The strangler fig in practice: proxy, ACL, event-driven notification",
     "06 — Data across the seam: owned data, the outbox, CDC, CQRS, ACID→ACD",
     "07 — Coordinating across services: both saga shapes, idempotent compensation"],
    ["08 — Communication, contracts, and the chassis: REST, gRPC, GraphQL, the registry",
     "09 — Operating and delivering: deploy topology, the mesh, the trace, the supply-chain gate",
     "10 — The pattern language, revisited: what earned its place, and where to stop",
     { text: "Appendix A — OpenShift/CRC parity", muted: true },
     { text: "Appendix B / C — extended figures + reference", muted: true }]);
  addNotes(s, "Ten sections, same order the book builds in: why/how, the ADLC, the monolith, DDD seam-finding, the strangler fig, data, coordination, contracts, operating, and the pattern-language retrospective. Appendix A carries OpenShift/CRC parity; B carries every figure that didn't fit the 50-slide main body; C is the examples index, stack pins, and a glossary. Cross-references in this deck are by concept, never by slide number, so the deck stays correct if a section is trimmed for time.");
}

// ===== SECTION 01 — WHY MODERNIZE =============================================
divider("01", "Why Modernize", "The case for change, and the discipline to leave most of it alone.",
  "Opens with the why-modernize case, then immediately the restraint case — this project extracted six services because five concrete smells demanded it, not because a target architecture was decided up front. That discipline is the throughline for the whole deck.");

content("WHY MODERNIZE · THE CASE", "Modernize because change got expensive",
  ["A Django monolith holding six bounded contexts in one shared Postgres schema makes every change touch everything else — one deployable, one release train, one blast radius.",
   "The target is independent deployability, not a service count: a change to shipping should never require testing or redeploying payment.",
   "This deck walks the full pattern set that gets there — the strangler fig, owned data, both saga shapes, contracts, and the operating model that keeps the result running as one system."],
  "Frame this as the business case before any pattern name appears: coupling is a cost, measured in how many things have to move together for one change. The monolith isn't bad engineering — it's the believable common ancestor every real legacy system starts from. The case for moving is narrower and stronger than 'microservices are better': it's that specific changes get safer and cheaper once the coupling that forced them together is gone.");

content("WHY MODERNIZE · RESTRAINT", "And when not to modernize at all",
  ["Stable, low-value contexts are the cheapest ones to leave alone — encapsulate a seam before extracting it, and extract only when a concrete change gets safer or cheaper.",
   "Every extraction in this project traces to a named coupling smell already in the monolith, not to a target architecture decided in advance.",
   "The test at every seam: does this specific change get safer or cheaper — never whether the result looks more modern."],
  "This is the restraint case, and it matters because the next 48 slides could otherwise read as 'decompose everything.' Six services came out of five documented smells, not a service-count plan — the pattern-language retrospective in section 10 returns to this with the receipts: six extractions against five smells, applied consistently, not invoked once and abandoned.");

// ===== SECTION 02 — THE ADLC + EQUIVALENCE GATE ===============================
divider("02", "The ADLC + the Equivalence Gate", "The lifecycle — and the automated check — that make agent-driven change safe.",
  "Introduces the Agentic Development Lifecycle this whole book was built with, and the automated equivalence gate every cutover has to pass before a flag is allowed to flip. This project itself — ten build iterations, three ledger files — is the worked example.");

content("THE ADLC · FROM SDLC", "The human moves up a level",
  ["The agent authors the change; the human frames the seam, sets the acceptance bar, and gates the merge — the same division of labor across all ten build iterations behind this book.",
   "The method rests on an automated equivalence gate, not on trust in a model's output: every cutover re-runs the same Newman contract suite the monolith already had to pass.",
   "No Quarkus Agent MCP or Camel MCP equivalent exists for this Python stack — unlike the Java sibling's tooling, the Map and Generate phases here substitute manual reconnaissance plus the lgtm-python skill's scaffold conventions, named as a real difference rather than glossed over."],
  "This is the one place in the deck that explicitly contrasts with the Java sibling book, and it's worth saying out loud: there's no live dev-mode reload loop as tight as Quarkus's for this stack, and no MCP server that already knows FastAPI/aiokafka the way quarkus-agent knows Quarkus. The gap is named in the chapter rather than worked around quietly.");

content("THE ADLC · THE LOOP", "Frame, Map, Plan, Generate, Verify, Operate, Reconcile",
  ["Seven phases, one seam at a time: Frame states the outcome, Map does reconnaissance, Plan produces a gated step plan, Generate writes the code, Verify runs the gated equivalence check, Operate rolls out behind a flag, Reconcile records what shipped against what was planned.",
   "Two human gates carry the whole method: approve the plan before any code exists, and sign off on equivalence before the flag flips.",
   "Reconcile is where the record lives — three real corrections surfaced across ten iterations (a configuration mechanism, a ConfigMap's real shape, a harder-than-expected CVE scan) because the validation pass read the actual files, not the plan's description of them."],
  "Walk the seven phases against a concrete example if there's time: the ch.27 chassis chapter's own plan assumed pydantic-settings as the configuration mechanism — the Verify/Reconcile phase caught that no service ever adopted it (every service uses a frozen @dataclass with from_env()) by grepping all eight config.py files directly, not by re-trusting the plan. That correction is itself evidence the loop works.");

code("THE ADLC · THE EQUIVALENCE GATE", "The behaviour-equivalence suite pins observable behaviour",
  "python · pytest",
  ["# examples/00-monolith/tests/test_checkout.py",
   "def test_decline_sentinel_returns_402_and_rolls_back_stock(api_client, customer, widget):",
   "    before = widget.quantity_on_hand",
   "    response = _checkout(api_client, customer, widget.sku, 1, \"CARD-DECLINE\", address)",
   "    assert response.status_code == 402",
   "    assert response.json()[\"error\"] == \"PAYMENT_DECLINED\"",
   "    widget.refresh_from_db()",
   "    # net-zero: the atomic() rolled back the inventory reservation too.",
   "    assert widget.quantity_on_hand == before",
   "",
   "def test_ship_fail_sentinel_rolls_back_entire_checkout(api_client, customer, widget):",
   "    response = _checkout(api_client, customer, widget.sku, 1, \"CARD-VISA\", \"SHIP-FAIL Lane\")",
   "    assert response.status_code == 422",
   "    widget.refresh_from_db()",
   "    assert widget.quantity_on_hand == before  # net-zero stock, SMELL[ch.22]",
   "",
   "# examples/00-monolith/tests/test_smoke.py -- one assertion per /api/* surface",
   "def test_inventory_serves(api_client, widget):",
   "    response = api_client.get(\"/api/inventory\")",
   "    assert response.status_code == 200"],
  "examples/00-monolith/tests/test_checkout.py + test_smoke.py — the suite every cutover re-runs, old position and new, before a flag is allowed to flip",
  "This is the same unedited Newman/pytest suite re-run at every single cutover across all six extractions — the point isn't that it's a big suite, it's that it never gets edited to make a cutover pass. test_ship_fail_sentinel is the one worth lingering on: it proves the whole checkout's transaction.atomic() rolls back, including the inventory reservation, leaving stock net-zero — the exact behavior ACID→ACD in section 06 has to replace with an explicit compensation.");

// ===== SECTION 03 — THE REFERENCE MONOLITH + SMELLS ===========================
divider("03", "The Reference Monolith", "Six bounded contexts, one shared schema, and planted coupling smells.",
  "Introduces the Django reference monolith this whole migration starts from — a fresh Django 5.2 LTS + DRF build, not a decomposed system with the extractions undone. Six deliberate smells, each tagged in the code, each cured by a specific later chapter.");

code("THE MONOLITH · ARCHITECTURE", "One Django project, six apps, one shared schema",
  "python · django",
  ["# examples/00-monolith/config/settings.py",
   "INSTALLED_APPS = [",
   "    \"common.apps.CommonConfig\",",
   "    \"order.apps.OrderConfig\",",
   "    \"inventory.apps.InventoryConfig\",",
   "    \"payment.apps.PaymentConfig\",",
   "    \"shipping.apps.ShippingConfig\",",
   "    \"notification.apps.NotificationConfig\",",
   "    \"review.apps.ReviewConfig\",",
   "]",
   "",
   "# SMELL[ch.18]: every app above migrates into ONE shared Postgres schema --",
   "# the coupling chapters 18-19 unwind, context by context.",
   "DATABASES = {",
   "    \"default\": {",
   "        \"ENGINE\": \"django.db.backends.postgresql\",",
   "        \"NAME\": (_parsed_db_url.path or \"/monolith\").lstrip(\"/\"),",
   "        \"USER\": _parsed_db_url.username or \"monolith\",",
   "    }",
   "}"],
  "examples/00-monolith/config/settings.py — six Django apps, one shared Postgres schema, the coupling every later chapter unwinds",
  "Every app in INSTALLED_APPS is a full bounded context, not a module convenience — order/inventory/payment/shipping/notification/review map 1:1 onto the six services this book eventually extracts, in rising order of difficulty. The DATABASES block is the smell this deck's data section (06) spends the most slides curing.");

content("THE MONOLITH · SMELLS", "Each smell maps to the pattern that removes it",
  ["Six deliberate smells, each tagged # SMELL[ch.NN] in the code: a shared schema, a god checkout service, one ACID transaction spanning every context, a synchronous notification call inside that transaction, no anti-corruption layer, and auth tangled into an otherwise independent context.",
   "Each smell maps to the chapter and pattern that cures it — the shared schema to owned data (06), the single transaction to a saga (07), the synchronous call to an outbox (06).",
   "By the end of the extraction roadmap every smell but the two kept for the frozen baseline is struck through in the project's own SMELLS.md, crossed out as each cure landed rather than just described as fixed."],
  "This slide is the map the rest of the main body keeps returning to: section 05 cures smell #5 (no ACL) and #6 (review tangled in auth), section 06 cures #1 and #4 (shared schema, synchronous send), section 07 cures #2 and #3 (god service, one ACID transaction). If time is short, this is the one slide worth not skipping — everything downstream is a cure for something named here.");

// ===== SECTION 04 — FINDING THE SEAMS (DDD) ===================================
divider("04", "Finding the Seams", "Event storming, bounded contexts, and the coupling ladder.",
  "Introduces domain-driven seam-finding as the technique that precedes every extraction in this book. The six bounded contexts aren't an architecture diagram handed down from above — they're what falls out of event storming the checkout flow.");

content("FINDING THE SEAMS · EVENT STORMING", "Lay out the events, then cluster by aggregate",
  ["Lay out what actually happens in a checkout — order placed, stock reserved, payment captured, shipment dispatched, customer notified — before any code moves.",
   "The clusters that fall out are the bounded contexts this book extracts in rising order of difficulty: review, notification, inventory, payment, shipping, order.",
   "A seam drawn around a cluster of events is a seam a reader can explain in one sentence — a seam drawn around a file structure usually can't."],
  "This is light on ceremony: event storming here isn't a multi-day workshop artifact, it's the discipline of naming what happened before naming what owns it. The six-context list isn't arbitrary — it's the same vocabulary (OrderDto/OrderStatus/StockDto/Topics) carried through from the monolith's own Django apps into every extracted service.");

content("FINDING THE SEAMS · BOUNDED CONTEXTS", "A real seam has a clean boundary",
  ["A real seam has a boundary the domain already respects — the data crossing it is data the domain already exchanged, so the anti-corruption layer at that boundary has almost nothing left to translate.",
   "Service count follows the domain, not the other way around: this project stopped at six contexts plus a data-less gateway because that's where the real seams ran out, not because a target number was hit.",
   "The modular-monolith-with-decomposed-databases trap is the warning sign for the opposite failure — splitting a schema before splitting the coupling that made it one schema in the first place."],
  "Section 10's pattern-language retrospective returns to this trap by name: a database split with no corresponding code split is strictly worse than the monolith it replaced, because it gives up atomic consistency and gets independent deployability back for nothing. Flag that connection now so it lands later.");

// ===== SECTION 05 — THE STRANGLER FIG (PROXY / ACL / EVENT-DRIVEN) ============
divider("05", "The Strangler Fig in Practice", "A proxy in front, an ACL at the seam, events to notify.",
  "Walks the strangler-fig mechanics this migration actually used: a thin ASGI reverse-proxy façade, an anti-corruption layer at each boundary, and the first event-driven extraction with no synchronous dependency on the monolith at all.");

diagram("THE STRANGLER FIG · THE FOUR MOVES", "Observe, seam, divert, retire",
  "strangler-four-moves",
  "Figure 14.1 — The strangler fig's four moves, in the order that matters: intercept, route, incrementally replace, retire — with a reversibility window spanning the first three and a warning against retiring too early.",
  "The warning on retiring too early is the whole point of this figure: this project kept the monolith frozen-in-repo (a reference branch plus tags) all the way through the sixth extraction, and only removed the fallback path once every context had its own equivalence gate green. Retire is a one-way door; the other three moves aren't.");

diagram("THE STRANGLER FIG · PROXY ROUTING", "The edge router chooses old or new by flag",
  "strangler-proxy-routing",
  "Figure 14.2 — Content-based routing: the STRANGLER_REVIEW_ENABLED flag off vs. on, both topologies routing through the same proxy against the same shared schema.",
  "The proxy is a Starlette + httpx.AsyncClient streaming ASGI reverse-proxy, not a Camel route — there's no Python equivalent of a dedicated integration-routing framework, so this is a project-first implementation. Worth naming the chunked-body bug found during this build: the proxy forwarded the inbound body as an unread stream, so POSTs arrived at the Django/WSGI monolith empty — invisible to in-process mock-transport tests, caught only when Newman ran against a real socket. The fix: buffer the body so a correct Content-Length goes upstream. The lesson generalizes — equivalence has to be proven against the real backend over a real socket.");

diagram("THE STRANGLER FIG · THE ACL", "An anti-corruption layer keeps the new service clean",
  "acl-contract-seam",
  "Figure 16.2 — The ACL is a translation boundary, not just another request: notification-service's OrderPlacedEvent sits between the monolith's Kafka contract and the service's own owned schema.",
  "Contrast the two ACL instances this book actually built: ch.16's is a one-dimensional routing decision (pick a backend by path); ch.19's inventory.proto is the harder case, a wire contract kept distinct from both the monolith's and the service's own domain vocabulary, with a drift guard that fails the build the moment the checked-in .proto and the generated stubs disagree. Section 08 returns to that proto in detail.");

diagram("THE STRANGLER FIG · EVENT-DRIVEN NOTIFICATION", "The first extraction reacts to an event, not a call",
  "event-driven-notification-topology",
  "Figure 17.2 — One outbox row, two independent consumer groups, one flag choosing who answers the read — the first extraction with no synchronous dependency on the monolith at all.",
  "Notification is also the project's first owned schema from day one — no shared-table entanglement to unwind later, unlike review (which stays on the shared schema, a named deferral) or inventory (which needs a one-time CDC bridge). This is the cheapest possible extraction shape, and it's sequenced second for exactly that reason.");

// ===== SECTION 06 — DATA ACROSS THE SEAM ======================================
divider("06", "Data Across the Seam", "From a shared schema to owned data — without losing an event.",
  "Walks database-per-service, the transactional outbox, CDC as a temporary bridge, CQRS, and the ACID-to-ACD transaction boundary — the five data-ownership moves that together cure smells #1 and #4 from section 03.");

diagram("DATA · OWNED, NOT SHARED", "Database-per-service is the goal",
  "shared-data-vs-owned-data",
  "Figure 18.1 — The three data-ownership postures this project actually built, in the order it built them: review stays on the shared schema (a named deferral), notification owns its schema from day one, inventory owns its schema too but needed a one-time CDC backfill to get there.",
  "All three postures are legitimate, not a hierarchy where only 'fully owned' counts as done — review's shared-schema deferral is a named decision, not an oversight, and it's still true at the end of the project. The point of this figure is that a real migration shows all three stages at once, in different services, simultaneously.");

diagram("DATA · THE OUTBOX WRITE", "Write the business row and the event row in one transaction",
  "outbox-write-in-transaction",
  "Figure 17.1 — The outbox cure changes the LAST write inside checkout's transaction, not the transaction itself: a synchronous out-of-process send becomes one more row in the same commit.",
  "This is the single highest-leverage pattern in the whole book, used and reused: it cures the dual-write hazard in the monolith's own checkout, then gets a second, more mature instance in payment-service's own outbox. A declined or failed checkout leaves zero outbox rows — proven by test, not asserted.");

code("DATA · THE OUTBOX RELAY", "Relay the outbox row; the consumer dedupes idempotently",
  "python · fastapi",
  ["# examples/07-order-service/app/relay.py",
   "async def _publish_one(self, session: AsyncSession, event: OutboxEvent) -> None:",
   "    topic = self._topic_for(event.event_type)",
   "    key = event.aggregate_id.encode(\"utf-8\")",
   "    value = json.dumps(event.payload).encode(\"utf-8\")",
   "    await self._producer.send_and_wait(topic, key=key, value=value)",
   "    # A crash here -- after the publish, before the stamp -- re-sends this",
   "    # row on the relay's next poll. AT-LEAST-ONCE, by design.",
   "    await repository.mark_outbox_event_published(",
   "        session, event.id, published_at=datetime.now(UTC)",
   "    )"],
  "examples/07-order-service/app/relay.py — publish, then stamp published_at; the async mechanics behind this loop live in 201-FastAPI",
  "Keep this to the shape, not the asyncio.Task plumbing — 201-FastAPI owns that depth. The comment on this line names the failure mode directly: a crash between publish and stamp re-sends the same row. That's a deliberate at-least-once contract, and it's why every consumer of this event has to be idempotent on its own side — the next two slides show both ways this project made that true.");

diagram("DATA · CDC AS A BRIDGE", "Change data capture backfills, then gets torn down",
  "cdc-backfill-then-retire",
  "Figure 19.2 — CDC tails the Postgres write-ahead log for a one-time backfill plus a transition-window sync, then is retired on its own documented runbook — grep the CI gates today and Debezium is not there.",
  "This is the pattern this book can show at every stage of its own lifecycle: live during the inventory cutover window, then gone, by design, on a runbook (drain, delete connector, drop the replication slot and publication, disable the flag). Transaction log tailing was never meant to be permanent, and the project confirms it never became one.");

diagram("DATA · CQRS", "Split the write model from the read model where shapes diverge",
  "order-cqrs-write-read-split",
  "Figure 21.1 — CQRS, concretely: one write aggregate, one order_view projection, upserted in the same local transaction as every write; every GET is served exclusively from the projection.",
  "This is order-service's own read model, and it's the first CQRS projection the read path in this project depends on — every write path upserts it in the same transaction as the mutation, so there's no second async step that could leave the read side stale under normal operation. Appendix B has the rebuildable-projection figure that proves it's a cache, not a second source of truth.");

diagram("DATA · ACID BECOMES ACD", "Across services, eventual consistency with compensation",
  "acid-to-acd-boundary",
  "Figure 22.1 — ACID → ACD: Atomicity, Consistency, and Durability survive for a smaller scope; Isolation is the one letter traded for a window the saga manages explicitly — a PENDING order visible and real before payment or shipping has an opinion on it.",
  "Say the cost out loud, in the open: that Isolation gap is real, not hand-waved. A PENDING order is a legitimate, visible state a reader can query before the saga resolves it — ACD names that window and gives it a state machine (section 07's sagas) instead of pretending the old single-transaction guarantee still holds.");

// ===== SECTION 07 — COORDINATING ACROSS SERVICES ==============================
divider("07", "Coordinating Across Services", "Sagas — two styles, same checkout — and failure as a first-class concern.",
  "Walks choreographed and orchestrated sagas side by side on the same checkout flow, plus the idempotent-compensation mechanism that makes a redelivered event or a retried RPC safe either way.");

diagram("COORDINATING · TWO STYLES", "Choreography and orchestration, same checkout",
  "choreography-vs-orchestration-contrast",
  "Figure 24.1 — Choreography has no coordinator; orchestration has exactly one — the same checkout, solved two structurally opposite ways in the same codebase.",
  "This contrast is deliberate, not incidental — a project that only ever needed one style wouldn't have this chapter's teaching value. Payment's saga (next slide) has no box anywhere that knows the whole sequence; shipping's saga (the slide after) re-embeds a DB-backed orchestrator that does.");

code("COORDINATING · THE CHOREOGRAPHED SAGA", "Payment reacts to the order-placed event",
  "python · aiokafka",
  ["# examples/05-payment-service/app/consumer.py",
   "async def _consume_loop(self) -> None:",
   "    assert self._consumer is not None",
   "    async for record in self._consumer:",
   "        try:",
   "            event = OrderPlacedEvent.model_validate(record.value)",
   "            await service.process_order_placed(self._session_factory, event)",
   "        except asyncio.CancelledError:",
   "            raise",
   "        except Exception:",
   "            # one bad record must not kill the background task -- log and",
   "            # keep consuming; it never silently stops delivery for every",
   "            # order placed afterward.",
   "            logger.exception(\"failed to process order.placed at offset %s\", record.offset)"],
  "examples/05-payment-service/app/consumer.py — no box anywhere knows the whole sequence; it emerges from independent event subscriptions reacting one hop at a time",
  "There is no monolith original for this write path — the monolith still charges in-process, synchronously. This consumer is authored directly on aiokafka idioms, sitting on both sides of Kafka: it consumes order.placed and produces its own payment.captured/payment.declined from its own transactional outbox.");

code("COORDINATING · THE ORCHESTRATED SAGA", "Shipping conducts its own steps and compensations",
  "python · fastapi",
  ["# examples/06-shipping-service/app/orchestrator.py",
   "STEPS = [",
   "    {\"name\": \"enrich\", \"compensate\": None},",
   "    {\"name\": \"dispatch\", \"compensate\": \"cancel_shipment\"},",
   "    {\"name\": \"book_carrier\", \"compensate\": None},",
   "    {\"name\": \"emit\", \"compensate\": None},",
   "]",
   "",
   "async def advance(session_factory, settings, saga_id: int) -> None:",
   "    # one step, one transaction -- SELECT ... FOR UPDATE + an idempotent guard",
   "    status = await _advance_one_step(session_factory, settings, saga_id)",
   "    if status == SAGA_RUNNING:",
   "        await advance(session_factory, settings, saga_id)",
   "    elif status == SAGA_COMPENSATING:",
   "        await compensate(session_factory, settings, saga_id)"],
  "examples/06-shipping-service/app/orchestrator.py — one coordinator, four steps; resume_running_sagas() crash-resumes from the persisted step_index",
  "Adapted from the house cloud-native-design-patterns saga orchestrator onto this project's async SQLAlchemy stack — select(Saga).with_for_update() instead of raw asyncpg FOR UPDATE. The crash-resume scan at startup is a durability upgrade over the role this plays in the Java sibling's in-memory coordinator: kill the process mid-saga, restart, and it resumes from the persisted step without re-running what already completed.");

diagram("COORDINATING · IDEMPOTENT CONSUMERS", "A redelivered event must not double-apply",
  "idempotent-consumer-dedupe",
  "Figure 17.3 — At-least-once delivery, exactly-once effect: application-level check-then-insert handles the common case, a database partial-unique index backstops the race.",
  "Two layers, not one — the application-level check-then-insert is the common path, and the database's own partial unique index is what closes the narrow window where two redeliveries race the check itself. Both the monolith's own consumer and notification-service's consumer use this same two-layer shape.");

diagram("COORDINATING · COMPENSATION, NOT ROLLBACK", "Undo a committed step with a compensating action",
  "idempotent-compensation-two-layers",
  "Figure 23.3 — A compensating Release survives redelivery at two independent layers: the Kafka-event status-transition guard and the RPC-layer compensations ledger.",
  "This closes a gap the gRPC Reserve/Release pair opened back in section 06 — once a reservation decrement lives in another service's own database, the free rollback a single transaction used to provide is gone, and this two-layer idempotency is what replaces it. Proven live: stock held constant across forced redelivery on both paths.");

// ===== SECTION 08 — COMMUNICATION, CONTRACTS & THE CHASSIS ====================
divider("08", "Communication, Contracts & the Chassis", "REST, gRPC, GraphQL — and the registry that keeps them compatible.",
  "Walks protocol fit across the finished system, the two contract mechanisms this project actually exercises (a byte-identical .proto with a drift guard, and a live Apicurio schema registry demo), and the FastAPI chassis every service runs on.");

diagram("COMMUNICATION · PROTOCOL FIT", "Pick the protocol by the shape of the call",
  "rest-grpc-graphql-protocol-fit",
  "Figure 26.1 — Three protocols, three different problems, used side by side in one system: REST for every service's own surface, gRPC for the one hot synchronous path, GraphQL for bounded aggregation at a gateway with no data of its own.",
  "The discipline worth naming: gRPC earned exactly one seam (order→inventory reservation), not every seam — it's the project's only strongly-typed, low-latency inter-service call, picked because strong typing and a tight latency budget mattered enough to justify a second wire protocol alongside REST.");

code("CONTRACTS · THE gRPC CONTRACT", "Inventory's contract is a .proto file, not a shared model",
  "protobuf",
  ["// examples/04-inventory-service/proto/dev/patterncatalyst/inventory/v1/inventory.proto",
   "service InventoryGrpcService {",
   "  rpc CheckStock (CheckStockRequest) returns (StockReply);",
   "  rpc Reserve (ReserveRequest) returns (ReserveReply);",
   "  rpc Release (ReleaseRequest) returns (ReserveReply);",
   "  rpc GetStock (GetStockRequest) returns (StockReply);",
   "}",
   "",
   "message StockReply {",
   "  string stock_keeping_unit = 1;   // domain vocab: \"sku\"",
   "  string display_name = 2;         // domain vocab: \"name\"",
   "  int64 unit_price_cents = 3;      // domain vocab: \"priceCents\"",
   "  int32 on_hand_qty = 4;           // domain vocab: \"quantityOnHand\"",
   "  bool available = 5;",
   "}"],
  "examples/04-inventory-service/proto/.../inventory.proto — a wire vocabulary kept distinct from the domain vocabulary on both sides of the seam",
  "The field names are the whole lesson: stock_keeping_unit/display_name/unit_price_cents are not sku/name/priceCents — matching vocabularies on both sides would mean the ACL isn't earning its keep. A scripts/check-proto-drift.sh gate fails the build the moment the checked-in .proto and the generated stubs (vendored into three other services) disagree.");

code("CONTRACTS · THE GRAPHQL GATEWAY", "One query, five sources, fanned out",
  "python · strawberry",
  ["# examples/08-graphql-gateway/app/schema.py",
   "@strawberry.type",
   "class OrderView:",
   "    id: strawberry.ID",
   "    items: list[OrderItemView]",
   "",
   "    @strawberry.field",
   "    async def payments(self, info: strawberry.Info) -> list[PaymentView] | None:",
   "        settings = info.context[\"settings\"]",
   "        rows = await fetch_payments(settings, str(self.id))",
   "        return [_payment_from_rest(row) for row in rows]",
   "",
   "@strawberry.type",
   "class Query:",
   "    @strawberry.field",
   "    async def order(self, info: strawberry.Info, id: strawberry.ID) -> OrderView | None:",
   "        data = await fetch_order(info.context[\"settings\"], str(id))",
   "        return _order_from_rest(data) if data is not None else None"],
  "examples/08-graphql-gateway/app/schema.py — one order(id) query, five federated sources, each field nullable so one downstream failure nulls a field, never the whole response",
  "Every federated field — payments, shipments, stock, reviews — is declared nullable, because a downstream outage should degrade to one null field plus an errors[] entry instead of a 500 for the whole query. This gateway has its own front door; it's never routed through the strangler proxy, and it owns no database of its own.");

diagram("CONTRACTS · THE SCHEMA REGISTRY", "Avro, wrapped in a registry-aware envelope",
  "avro-wire-envelope-registry-flow",
  "Figure 28.2 — A hand-rolled wire envelope plus a round trip against a live Apicurio registry: register-or-resolve, encode and publish, consume, fetch the writer schema by global id, decode.",
  "This demo stays on pure-Python fastavro + aiokafka + Apicurio's v3 REST API rather than confluent-kafka[avro] — that choice (no librdkafka dependency) means hand-rolling the wire envelope, named as a consequence of the choice, not an oversight. It's scoped to one demonstrator, not retrofitted onto the six live event contracts, which still ship as hand-authored JSON and have stayed forward-compatible by discipline rather than registry enforcement — which is itself the case for why a registry would help.");

diagram("THE CHASSIS", "Config, health, logging, and tracing — as a convention",
  "fastapi-chassis-anatomy",
  "Figure 27.1 — The chassis inside one FastAPI service: config and logging copied into every service by hand, health and error-mapping present on six of eight, tenacity retry on exactly the one call site that has needed it so far.",
  "This chassis is a convention, not a library — eight near-identical files, not one shared dependency. Config (frozen @dataclass + from_env()) and logging sit at 7-8 of 8; /health and errors.py sit at 6 of 8, each gap tied to a stated structural reason, not an unexplained one. The deeper chassis code — DI wiring, structured logging setup — is 201-FastAPI's job; this deck just names the shape.");

// ===== SECTION 09 — OPERATING & DELIVERING ====================================
divider("09", "Operating & Delivering", "Deploy, mesh, observe, and gate the supply chain.",
  "Walks the deployment topology, the service mesh's mTLS and tracing story, and the supply-chain gate that scans every built image before it ships — the cross-cutting concerns no single bounded context owns alone.");

diagram("OPERATING · DEPLOY TOPOLOGY", "Six services, one Kubernetes namespace",
  "deploy-k8s-namespace-topology",
  "Figure 29.1 — The mea namespace: eight Deployments/Services behind one NodePort edge, two shared StatefulSets, probes honoring each service's actual health surface rather than copied uniformly.",
  "Two services (strangler-proxy, review-service) get tcpSocket probes because they have no /health route — the other six get httpGet /health. That's the chassis scorecard from section 08 showing up directly in the deployment manifest, not glossed over with a uniform probe that would silently lie about two services' real readiness.");

diagram("OPERATING · THE MESH", "mTLS and traffic identity, from the platform",
  "mesh-mtls-topology",
  "Figure 30.1 — The meshed mea namespace: mTLS STRICT on every sidecar-to-sidecar hop, one PERMISSIVE exception at the plaintext edge, two backends left unmeshed by design.",
  "Postgres, Kafka, and the observability backend stay unmeshed — meshing every workload isn't the goal, meshing the application traffic that benefits from mTLS and a service graph is. The one PERMISSIVE carve-out exists because the NodePort edge receives plaintext traffic from outside the mesh entirely, with no sidecar on the client side to negotiate mTLS with.");

diagram("OPERATING · THE TRACE", "One request, traced end to end across services",
  "mesh-hero-trace-waterfall",
  "Figure 30.2 — The hero trace: mesh spans give every one of eight services breadth with zero application code changed; app-level OpenTelemetry on three of eight adds the in-process depth the mesh cannot see.",
  "This is the property worth making explicit: the mesh and application-level OTel answer different questions. The mesh gives every hop a span, mTLS state, and a service graph automatically; it can't see a specific SQL statement or a business-logic branch. Three services (proxy, order, inventory) get that depth, chosen because the synchronous checkout→reserve path crosses no outbox and needs no extra trace-context plumbing — the Kafka saga hops stay mesh-visible only, named as a scoped-out horizon, not a gap nobody noticed.");

code("DELIVERING · THE SUPPLY-CHAIN GATE", "SBOM, scan, and a policy threshold that fails the build",
  "bash · syft · grype",
  ["# examples/10-supply-chain/policy.yaml",
   "fail-on: High          # fail the GATING target(s) on any High or Critical",
   "gate-on: fixable        # a finding counts only when a fix path actually exists",
   "targets:",
   "  - name: order-service",
   "    gate: required       # the \"after\" -- a fixable High/Critical fails the build",
   "  - name: monolith",
   "    gate: reported        # the frozen \"before\" -- reported, never blocks",
   "",
   "# examples/10-supply-chain/demo.sh",
   "syft \"${BUILDER}:${image}\" -o \"cyclonedx-json=$sbom\" -q",
   "grype \"sbom:$sbom\" -c \"$GRYPE_CFG\" -o json -q > \"$scan\"",
   "# tally fixable vs. total by severity, then apply fail-on to GATING targets only"],
  "examples/10-supply-chain/{policy.yaml,demo.sh} — SBOM, scan, and a policy threshold gating on fixable findings only",
  "The real result landed harder than planned: both order-service and the frozen monolith scanned 35 High-severity findings in the shared UBI base layer, every one fix-state not-fixed — confirmed with skopeo that no newer patched tag exists to re-pin onto. gate-on: fixable means the gate still surfaces all 35 in grype's own output; it just stops blocking a merge on a CVE no change in this repository can fix. That's a narrower bar, not a lower one.");

diagram("OPERATING · THE RESULT", "One monolith, six services, no shared schema",
  "final-monolith-free-topology",
  "Figure 26.3 — The final topology: six services and a GraphQL gateway behind one flagless router, the monolith frozen and unwired.",
  "Flagless is the word to land on: every *_enabled boolean and the monolith fallback path were removed from the proxy as the one deliberate, irreversible move in the whole project — taken only after a pre-cutover reversibility proof captured the full extracted topology against the bare monolith, both green.");

// ===== SECTION 10 — THE PATTERN LANGUAGE, REVISITED ===========================
divider("10", "The Pattern Language, Revisited", "Which patterns we used — and where to stop.",
  "Closes the main body with the pattern-language retrospective: forty-five rows walked against the finished system, three verdicts (earned, adapted, named-and-deferred), and the anti-pattern that explains why this project has eight services and not twenty.");

diagram("THE PATTERN LANGUAGE MAP", "Where each pattern lives in the catalog",
  "pattern-language-map",
  "Figure 32.1 — The pattern language as one connected flow, colored by verdict: earned, adapted, and five further horizons named and scoped rather than built ahead of need.",
  "Cross-referenced by concept to sections 05-09: the strangler fig, the ACL plus the gRPC seam, the outbox, CQRS, and both saga shapes are earned outright; the chassis, contracts/registry, and mesh/observability are adapted — real, but narrower in scope than their textbook definition.");

diagram("THE PATTERN SCORECARD", "Used because it cured a pain we had; deferred is a verdict too",
  "book-pattern-scorecard",
  "Figure 32.2 — The book-wide pattern scorecard, matching build-plan.md section C: eight patterns earned outright, five adapted into a narrower shape, six named and deferred with the condition that would change the answer.",
  "A verdict needs three outcomes, not two — 'built vs. not built' can't represent a schema registry that works but covers one event out of a dozen, or a chassis that's real but copied by hand eight times. Full event sourcing, a circuit breaker, a GitOps operator, Loki log aggregation, and Kafka saga-hop tracing are each named with the specific trigger that would earn their place, not a vague gesture at future work.");

content("WHERE TO STOP", "Over-decomposition is the seductive failure",
  ["Over-decomposition is the seductive failure: a database split with no corresponding code split gives up the one thing a monolith provides automatically — atomic consistency — and gets independent deployability back for nothing.",
   "The tell is a coordinated release across services that were supposed to be independent; the cure is stopping at context-aligned services and splitting further only when a real seam demands it.",
   "Five named next horizons — a circuit breaker, full event sourcing, a GitOps operator, Loki log aggregation, tracing across a Kafka saga hop — are each a bounded increment with a stated trigger, not a rewrite."],
  "This is the slide to leave the audience on before the close: the finished system has eight services (six contexts plus the proxy plus the gateway) because that's where real smells ran out, not because twenty would have looked more impressive on an architecture diagram. A nanoservice-sprawl version of the same domain would have the same forty-five-pattern catalog to reach for, and would reach for most of it for the wrong reason.");

// ===== CLOSE (end of MAIN body — ~50 slides through here) =====================
content("201 · CLOSE", "The patterns, end to end — now go deeper",
  ["The main body covered the full pattern arc at just-enough-code depth: seams, data ownership, coordination, contracts, and the operating model that keeps six services running as one system.",
   "For the async/FastAPI code deep dive — SQLAlchemy 2.0 sessions, the outbox relay as an asyncio task, grpc.aio, Pydantic v2 at the edges — see the 201-FastAPI companion.",
   "Appendix A (OpenShift/CRC parity) and Appendix B (the extended figure set) are reference depth — keep this deck open in another window while you work, rather than projecting them live."],
  "This is the handoff slide — the main body is complete at this point and the appendix is reference material, not a continuation of the narrative arc. If the audience is engineers about to implement, point them at 201-FastAPI next; if they're deciding whether to start a migration at all, point them back at the 101.");

// ===============================================================================
// APPENDIX — overflow starts here. Slides below do NOT count against the
// ~50-slide MAIN cap (tracked separately as appendixCount).
// ===============================================================================
inAppendix = true;

// ----- APPENDIX A — OpenShift/CRC Parity --------------------------------------
divider("APP-A", "Appendix A — OpenShift/CRC Parity", "Keep this open in another window.",
  "OpenShift/CRC parity material: the same eight services and manifests from section 09, re-homed onto OpenShift Local with Routes, SCCs, and OpenShift Service Mesh 3 instead of a plain NodePort and vanilla Istio. deploy/k8s, the app code, and the Containerfiles are unchanged — every OpenShift-specific concern is confined to openshift/ and this one appendix chapter.");

diagram("APPENDIX · OPENSHIFT TOPOLOGY", "The same six services, on OpenShift Local",
  "openshift-crc-topology",
  "Figure 33.2 — The mea project on OpenShift Local: three SCC postures, two Routes as the only edge — the same eight services, a different platform.",
  "Three SCC postures, not one: restricted-v2 for the eight app Deployments, nonroot-v2 for Postgres/Kafka under a dedicated service account, and anyuid (with only runAsUser 0 set) for grafana/otel-lgtm. The existing UBI10 images already satisfy restricted-v2 with no rebuild.");

diagram("APPENDIX · IMAGE DELIVERY", "In-cluster builds, no external registry required",
  "openshift-image-delivery",
  "Figure 33.1 — Image delivery: a podman build-and-push pipeline on the host, pulled in-cluster from the integrated registry, with a mirror path for a CRC VM with no outbound network access.",
  "A --mirror-infra path exists specifically for an egress-less CRC VM — it pulls and re-pushes the Postgres and Kafka images so the whole stack can come up with zero outbound network dependency. The live CRC run surfaced and fixed several real portability defects in these scripts, including a rootless-podman permission failure that forced adding a docker build-and-push path.");

diagram("APPENDIX · MESH mTLS AT THE EDGE", "STRICT mTLS and a Route at the edge",
  "openshift-mesh-mtls-edge",
  "Figure 33.3 — STRICT mesh-wide, a PERMISSIVE carve-out at each Route, the Route itself the one unmeshed edge — OpenShift Service Mesh 3 parity with the minikube/Istio mesh in section 09.",
  "The injection mechanism differs by platform and the deck says so rather than letting a reader infer it: minikube uses a sidecar.istio.io/inject pod-template annotation; OSSM 3 on OpenShift uses an istio.io/rev label instead. Verified live: STRICT mTLS rejecting a plaintext caller with exit 56, and Kiali reporting MTLS_ENABLED.");

// ----- APPENDIX B — Extended Pattern Variants & the Full Figure Set ----------
divider("APP-B", "Appendix B — Extended Pattern Variants", "The deeper per-pattern figures that didn't fit the main 50.",
  "Every diagram from the house figure set not already used in the main body — the deeper per-pattern variants, sequence-level detail on both sagas, and the evidence figures behind the main body's summary claims. Reference depth, not a second narrative pass.");

diagram("APPENDIX · SAGA CRASH-RESUME", "The saga's state machine survives a crash",
  "saga-state-machine-crash-resume",
  "Figure 24.3 — Resumable by construction: the saga_log row remembers what the process forgot; resume_running_sagas() picks up at the persisted step_index, not from scratch.",
  "Pair this with section 07's orchestrator code slide — this figure is the proof, not just the claim: kill the process mid-saga, restart, and it resumes without re-invoking a step that already completed.");
diagram("APPENDIX · THE CHASSIS SCORECARD", "Which chassis capabilities each service adopted",
  "chassis-scorecard",
  "Figure 27.2 — Used, partial, and deferred, across all eight services: config and logging at 7-8 of 8, health and error-mapping at 6 of 8 each for a named structural reason, tenacity at 1 of 8, OpenTelemetry and a shared chassis library both named and deferred.",
  "The deferred row matters as much as the used row: a shared chassis library was not built — each service's config/logging/health code is copied and adapted by hand, a trade-off argued as correct for eight services that still redeploy independently of each other.");
diagram("APPENDIX · SHIPPING RESILIENCE", "Retries, timeouts, and the circuit breaker in the shipping chassis",
  "shipping-resilience-chassis",
  "Figure 25.1 — What already runs (a gRPC deadline, outbox at-least-once, the proxy's 502 fail-safe, the orchestrator's own crash-resume), what's new (a tenacity retry-with-timeout on one HTTP call), and what's named but not yet built.",
  "The resilience this system actually has is distributed across existing mechanisms, not concentrated in one new named component — the only new mechanism this chapter added was the tenacity wrapper around shipping's one outbound enrich() call.");
diagram("APPENDIX · SCHEMA EVOLUTION", "A compatible Avro schema change, end to end",
  "avro-compatibility-evolution",
  "Figure 28.3 — Schema evolution against a live BACKWARD rule: an additive field with a default is accepted (200); a field retype is rejected (400) before a single message ships.",
  "Both outcomes were observed against a real, pinned Apicurio 3.3.3 instance, not inferred from documentation — the actual HTTP status (400 RuleViolationException) is what's recorded, including a note that an earlier version of Apicurio returned 409 for the same kind of rejection.");
diagram("APPENDIX · SYNC-TO-ASYNC CONTRACT", "The checkout call crosses from sync REST to an async event",
  "checkout-sync-to-async-contract",
  "Figure 23.1 — The contract change: a 202 is a promise, not a faster 201 — PAYMENT_MODE=synchronous's one round trip versus choreographed's 202 PENDING a caller has to poll to resolve.",
  "This is the project's first deliberate change to a previously-stable response contract — the synchronous 201 path stays byte-for-byte unchanged, so the contract change is additive and flag-gated, not a breaking replacement.");
diagram("APPENDIX · BEFORE THE REGISTRY", "Hand-duplicated schemas were the starting smell",
  "hand-duplicated-vs-registry-schema",
  "Figure 28.1 — Two hand-duplicated copies of the same event contract, one already drifted, versus one schema registered once and resolved by every producer and consumer against the same registry.",
  "The real drift this project documents isn't a replayed anecdote from the Java sibling — it's independently re-derived from this project's own producer/consumer code, which turns out to have stayed forward-compatible by discipline (every field addition has been additive-and-optional) rather than by any enforcement mechanism.");
diagram("APPENDIX · THE gRPC CONTRACT, VISUALLY", "Inventory's protobuf ACL, as a diagram",
  "inventory-grpc-proto-acl",
  "Figure 19.1 — The proto IS the ACL: two separate domain vocabularies meet only at the wire.",
  "Visual companion to section 08's gRPC code slide — useful when walking through why the wire vocabulary (stock_keeping_unit, display_name) is kept distinct from both the monolith's and inventory-service's own internal vocabulary.");
diagram("APPENDIX · THE GRAPHQL FAN-OUT, VISUALLY", "One query, five sources, as a diagram",
  "graphql-gateway-five-source-fanout",
  "Figure 26.2 — One query, five sources, no data owned locally: a downstream failure nulls one field and appends one errors[] entry — never a crashed request.",
  "Visual companion to section 08's GraphQL code slide — walk the five fetch targets (order REST, payment REST, shipment REST, review REST per item, inventory gRPC per item) and the nullability discipline that makes partial failure safe.");
diagram("APPENDIX · MULTI-OUTBOX SAGA", "A saga that spans more than one service's outbox",
  "multi-outbox-saga-topology",
  "Figure 20.2 — Two outboxes, chained: order-service's outbox feeds payment-service's consumer, which writes its own outbox, consumed in turn — a saga with no orchestrator anywhere in the chain.",
  "This is the project's first multi-service outbox choreography, and it generalizes the single-outbox pattern from section 06 into a chain: one transaction, an at-least-once relay, an idempotent consumer, repeated at each hop.");
diagram("APPENDIX · CONTENT-BASED ROUTING", "The notification service routes by event content",
  "notification-content-based-routing",
  "Figure 16.1 — One routing decision — a path-prefix predicate — generalized to header- and payload-based routing as the same mechanism scales to more seams.",
  "Today's implementation is a one-dimensional path-prefix match at the strangler proxy; this figure's side panel names header- and payload-based routing as generalizations of the same predicate, not a different mechanism.");
diagram("APPENDIX · THE CHOREOGRAPHED SAGA, VISUALLY", "Payment's reaction to checkout, as a sequence diagram",
  "choreographed-payment-saga-sequence",
  "Figure 23.2 — The choreographed saga top to bottom: every arrow is a reaction to an event, branching into three terminal outcomes, no orchestrator box anywhere.",
  "Visual companion to section 07's choreography code slide — trace the three terminal outcomes (captured, declined, and the downstream shipping-failed refund hop) and notice that no single component ever holds the whole sequence in view.");
diagram("APPENDIX · THE ORCHESTRATED SAGA, VISUALLY", "Shipping's orchestration, as a sequence diagram",
  "orchestrated-shipping-saga-sequence",
  "Figure 24.2 — The orchestrated saga: one coordinator, four steps, one compensation decision on a book_carrier failure.",
  "Visual companion to section 07's orchestration code slide — the SHIP-FAIL sentinel fires at step 3 (book_carrier), after dispatch has already persisted a Shipment row, which is exactly what gives the cancel_shipment compensation something real to undo.");
diagram("APPENDIX · ORDER-ITEM SNAPSHOT", "The order-item foreign key becomes an owned snapshot",
  "orderitem-fk-to-snapshot",
  "Figure 18.2 — From foreign key to snapshot: a live join becomes a denormalized sku/item_name/unit_price_cents copy, moved by an add-backfill-drop migration sequence.",
  "This is the concrete mechanics behind 'owned, not shared' from section 06 — a three-step migration (add the snapshot columns, backfill them, drop the foreign key) rather than a single breaking schema change.");
diagram("APPENDIX · ORDER LIFECYCLE (AWAITING SHIPMENT / REFUND)", "The order state machine's less-common branches",
  "order-lifecycle-awaiting-shipment-refund",
  "Figure 24.4 — AWAITING_SHIPMENT is a real intermediate status, not an implementation detail, and the refund hop closes the stranded-payment gap a captured payment would otherwise leave behind.",
  "Before this status existed, a payment could be captured with no corresponding guarantee that shipping would ever resolve it — the refund hop (payment-service reacting to shipment.failed) is what closes that gap, named and closed rather than left as a known limitation.");
diagram("APPENDIX · ORDER LIFECYCLE (PENDING TO TERMINAL)", "The order state machine's main path",
  "order-pending-to-terminal-lifecycle",
  "Figure 22.2 — The state machine ACD introduces: three protected, idempotent terminal exits, plus one clearly named failure mode (a stuck PENDING, caught by a bounded-wait poll).",
  "Each of the three terminal exits (CONFIRMED, SHIPPING_FAILED, PAYMENT_DECLINED) is reachable exactly once per order, guarded by the same idempotency discipline as the saga steps that lead to them.");
diagram("APPENDIX · THE REBUILDABLE READ MODEL", "The order view projection can be rebuilt from the log",
  "order-view-rebuildable-projection",
  "Figure 21.2 — A rebuildable read model: rebuild_order_view recomputes the projection from the aggregate at any time, and a projection-disabled negative test proves the read path never silently falls back to the write tables.",
  "That negative test shows the enforcement directly: with the projection disabled, reads go stale instead of silently querying the write tables — proof the read side has a real, enforced boundary, not just a convention.");
diagram("APPENDIX · THE OUTBOX RELAY, AT LEAST ONCE", "Delivery guarantees the relay actually makes",
  "outbox-relay-at-least-once",
  "Figure 20.1 — The bridge, the relay, and the counterpart that makes at-least-once survive contact with reality: an idempotent consumer on the other end, in whichever idiom fits the write.",
  "Visual companion to section 06's outbox-relay code slide — the generalized shape behind every outbox instance in this project: one transaction, an at-least-once relay, and a consumer-side guarantee that's never optional.");
diagram("APPENDIX · A LIGHTER RESERVE/RELEASE SAGA", "A smaller saga shape for a smaller workflow",
  "reserve-release-saga-lite",
  "Figure 19.3 — Reserve/release across the boundary: where the free rollback went once a decrement lives in another service's own database, and the compensating Release that replaces it.",
  "Before this seam existed, a single transaction.atomic() gave a free rollback across reserve, order, payment, and shipping — this figure shows exactly what has to replace that once the reservation decrement crosses a process boundary.");
diagram("APPENDIX · REVIEW, PHASE A VS. PHASE B", "The review service's two extraction phases",
  "review-phase-a-vs-phase-b",
  "Figure 15.1 — Phase A (a thin FastAPI shim over the Django ORM, documented but never shipped) versus Phase B (native async SQLAlchemy, no monolith import at all) — the same read contract either way.",
  "Phase A was never committed as running code once two concrete problems surfaced while sketching it: bridging Django's synchronous ORM into FastAPI's async loop, and a backwards build-time dependency on the entire monolith just to reach one model. The real payoff is structural, not a startup-time number — Phase A/B import timing came back statistically indistinguishable.");
diagram("APPENDIX · THE CUTOVER TIMELINE, VISUALLY", "Six seams, in dependency order, as a timeline",
  "strangler-cutover-timeline",
  "Figure 14.3 — The cutover evidence trail: one unedited Newman suite, four runs — flag off, flag on, flag reverted, and a forced-down negative that fails loudly by design.",
  "That fourth run is the one worth narrating: with the extracted service killed outright, the suite goes RED (6/6 assertions failed) rather than quietly passing — proof the equivalence gate actually gates, not just a green checkmark that never turns red.");
diagram("APPENDIX · THE SUPPLY-CHAIN GATE, VISUALLY", "SBOM, scan, gate — as a pipeline diagram",
  "supply-chain-gate-pipeline",
  "Figure 31.1 — The syft-to-grype-to-policy pipeline for both the gating target and the frozen monolith, plus the four additive CI checks converging on one repository ruleset.",
  "Visual companion to section 09's supply-chain code slide — note that both scanned images produce the identical 265-match, 35-High result from their shared UBI base layer, which is itself evidence the finding is a base-image fact, not an order-service-specific regression.");
diagram("APPENDIX · TWO CUTOVER DIMENSIONS", "Reversibility and blast radius, scored per seam",
  "two-cutover-dimensions",
  "Figure 19.4 — Two independent cutover flags as a 2x2 grid: the two corners this project actually exercised, against the two split corners that are only safe during the CDC-backfilled transition window.",
  "Inventory's cutover has two independent flags (reads vs. reserve/release) rather than one combined switch — this figure is the grid of which combinations were actually exercised and which are only sound transiently, during the backfill window.");

// ----- APPENDIX C — Reference (examples, stack, glossary) --------------------
divider("APP-C", "Appendix C — Reference", "The runnable examples, the stack, and the terms used in this deck.",
  "Reference material for follow-along: the examples/ directory map, every stack version pinned across the project, and a glossary of the terms this deck used without re-defining each time.");

content("APPENDIX · THE EXAMPLES", "Eleven runnable examples, one per seam",
  ["00-monolith (the frozen before), 01-strangler-proxy, 02-review through 07-order-service (the six extractions, in rising order of difficulty).",
   "08-graphql-gateway (the data-less aggregation gateway), 09-schema-registry-demo (the Apicurio round trip), 10-supply-chain (the SBOM/scan/policy gate).",
   "Every code slide in this deck draws from one of these directories — this is the index, not a summary; read the source for the rest."],
  "If someone wants to run anything live after this talk, this is the slide to screenshot — every directory name here is a real, independently runnable example with its own AGENTS.md and README — a complete project, not an excerpt assembled for the deck.");

content("APPENDIX · STACK & VERSIONS", "FastAPI, SQLAlchemy 2.0, aiokafka, Postgres, Kafka",
  ["FastAPI 0.143.2 + uvicorn, SQLAlchemy 2.1.4 (asyncio) + asyncpg, Pydantic 2.14.1, Alembic, aiokafka, grpcio + protobuf, Strawberry GraphQL, tenacity — Python 3.14, managed by uv.",
   "The frozen monolith: Django 5.2 LTS + DRF, psycopg, gunicorn. Testing: pytest + pytest-django + pytest-asyncio, Testcontainers, Newman.",
   "The platform: Kubernetes via kustomize, Istio 1.31, OpenTelemetry + grafana/otel-lgtm, Apicurio 3.3.3, syft/grype — plus Helm and OpenShift Service Mesh 3 for the CRC appendix."],
  "Every version here is a real pin from a service's own pyproject.toml or a CI workflow, not a representative placeholder — useful as a quick compatibility check before someone tries to reproduce a chapter locally.");

content("APPENDIX · GLOSSARY", "Terms used in this deck",
  ["Strangler fig: replace a system one seam at a time behind a router, never a rewrite. Seam: a boundary the domain already respects. ACL: a translation layer that keeps two vocabularies from leaking into each other.",
   "Outbox: write the domain row and the event row in one transaction. Saga: a multi-step operation across services that compensates on partial failure, choreographed or orchestrated. CQRS: a write model and a read model, split where their shapes diverge.",
   "ACD: the three letters of ACID a saga keeps, with Isolation traded for a window it manages explicitly. Chassis: the conventions every service in the system follows, copied by hand rather than shared as a library."],
  "Cross-referenced by concept to the section where each term was introduced — seam and ACL in section 04-05, outbox and ACD in section 06, saga and CQRS in sections 06-07, chassis in section 08.");

content("CLOSING · GO DEEPER", "Where to go from here",
  ["For the ideas and the advantage case at architect altitude, see the 101 deck; for the async/FastAPI code deep dive underneath every pattern here, see 201-FastAPI.",
   "Every pattern in this deck is grounded in a runnable example in the repository, and every diagram in a figure from the published chapters — nothing here is illustrative-only.",
   "The pattern-coverage matrix in build-plan.md section C is the single source of truth this deck's scorecard slides draw from — check any claim in this deck against it."],
  "This is the deck's actual last slide — leave it up during Q&A. If a question goes deeper than just-enough-code depth, the direct answer for most of them is '201-FastAPI covers that'; if a question is about whether to start a migration at all, the 101 is the better reference.");

pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum, "main:", mainCount, "appendix:", appendixCount))
  .catch(e => { console.error(e); process.exit(1); });
