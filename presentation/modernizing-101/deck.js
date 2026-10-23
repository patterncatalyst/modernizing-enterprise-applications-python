// deck.js — "Modernizing Enterprise Applications (Python)" — 101 (the ideas).
// Concept-forward companion: the case for moving Django to FastAPI, one seam
// at a time. No deep code — that lives in the 201-fastapi deep dive.
// Red Hat house style, 16:9. Build: export NODE_PATH=$(npm root -g) && node deck.js
//
// Covers the authored chapters (strangler fig, content-based routing/ACL,
// shared-to-owned data, ACID→ACD, sagas, communication/chassis,
// deployment/mesh/supply-chain, the pattern language revisited). Arc: A Why
// & How / B The Migration / C Operating & Reflection (mirrors the Java 101
// sibling in shape; re-authored, not copied; FastAPI-native throughout).

"use strict";

const H = require("./deck-helpers.js");
const {
  COLOR, FONT, W, PNG, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide, addSectionDivider, addNotes,
} = H;

const OUT = "Modernizing_101-r1.1.pptx";
const REV = "r1.1";

const pres = newDeck();
pres.title = "Modernizing Enterprise Applications (Python): 101 (the ideas)";
let pageNum = 0;

function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
}

// ---- local stub helpers (thin wrappers over the bundled deck-helpers) -----
function content(eyebrow, title, bullets, notes, opts) {
  const s = S();
  addContentTitle(s, eyebrow, title);
  addBullets(s, bullets, opts || {});
  addNotes(s, notes);
  return s;
}
function twoCol(eyebrow, title, left, right, notes) {
  const s = S();
  addContentTitle(s, eyebrow, title);
  addTwoColBullets(s, left, right);
  addNotes(s, notes);
  return s;
}
function diagram(eyebrow, title, png, caption, notes, opts) {
  const s = S();
  addDiagramSlide(s, eyebrow, title, png, caption, opts || {});
  addNotes(s, notes);
  return s;
}

// ===== COVER ==================================================================
{
  const s = pres.addSlide();
  pageNum += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("MODERNIZING ENTERPRISE APPLICATIONS (PYTHON) · 101", { x: 6.00, y: 1.98, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 13, bold: true, color: COLOR.red, charSpacing: 5, align: "left", valign: "middle" });
  s.addText([{ text: "Django to FastAPI,", options: { breakLine: true } },
             { text: "one seam at a time" }], {
    x: 5.95, y: 2.42, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The case for modernizing a Django monolith into async FastAPI services, and the strangler-fig method that gets there without a rewrite.",
    { x: 6.00, y: 4.65, w: 6.80, h: 1.05, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 5.85, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "This is the 101, the ideas deck for modernizing a Django monolith into FastAPI services. It opens with why change got expensive inside a coupled system, walks the strangler fig method that makes a live, incremental cutover safe, and closes with how the finished system runs, what the modernization actually measures, and which patterns from the broader catalog earned a lasting place. There is no async implementation detail on these slides: that is the FastAPI deep dive's job, but every idea here maps to a chapter and a running service in this book's own codebase, so nothing on this deck is hypothetical. The audience is architects, leads, and engineers deciding whether and how to start a modernization of their own, and the goal is that by the close they can explain the method to someone else without reaching for this deck again.");
}

// ===== AGENDA ==================================================================
twoCol("101 · THE IDEAS", "The whole argument, in one sitting",
  ["Why modernize, and when restraint is the right call",
   "The strangler fig: growing the new system around the old",
   "Finding the seams the domain already has",
   "Data ownership and coordination as ideas, not mechanics"],
  ["Communication across the seam: REST, gRPC, GraphQL, events",
   "Operating the result: the mesh, the trace, the measurable win",
   "The modernization, scored against the pattern language",
   "Where to stop, and where the deeper material lives"],
  "The agenda runs three acts. The first act makes the case for modernizing and is equally clear about when not to. Restraint is as much a part of this method as action. The second act walks the migration itself as a sequence of ideas: a reversible proxy in front of the monolith, bounded contexts as the place seams actually live, data ownership as the hardest coupling to break, and two different ways to coordinate a workflow once a single database transaction can no longer coordinate alone. The third act steps back from any one extraction to cover how the finished system is operated, what the modernization measurably bought, and which patterns from the wider catalog earned their place versus which stayed named and deferred.");

// ===== ACT A — WHY & HOW ======================================================
divider("A", "Why, and How", "The case for change, and the method that makes it safe.",
  "This act opens the why-modernize argument and closes by introducing the strangler fig as the method that makes changing a live system safe. The throughline is that modernization is a means to an end, removing the coupling that makes real change expensive, never a goal in its own right, and the strangler fig is what lets that removal happen without betting the whole system on a single cutover event.");

content("WHY MODERNIZE · THE CASE", "Modernize because change got expensive",
  ["The monolith's own faults make the business case concrete: a single checkout function reaching directly into four other contexts, and one database transaction spanning all of them, so a change anywhere risks breaking everything everywhere.",
   "The target is independent deployability, not a service count: six teams shipping on six schedules beats one team coordinating a release across six contexts every time.",
   "A shared Postgres schema is coupling the database itself enforces: foreign keys that block a delete, joins that cross team boundaries. No amount of careful code organization removes it without the schema actually splitting."],
  "This slide opens the why-modernize case. The system this book works from seeded five concrete faults into an otherwise ordinary Django monolith: a checkout function that reaches directly into four other contexts' code, one database transaction wrapping all of it so a failure anywhere rolls back everything in that one shared transaction, and a shared schema with foreign keys crossing team boundaries. None of that is a strawman. It is the ordinary shape a monolith takes after years of the fastest path winning. The argument for modernizing is not abstract: every one of those faults makes a specific, everyday change more expensive and riskier than it has to be, and the goal of everything that follows is removing them one at a time, not chasing a service count for its own sake.");

content("WHY MODERNIZE · RESTRAINT", "And when not to modernize at all",
  ["A stable, rarely-touched system is the cheapest system there is: leave it exactly as it is and spend the migration budget where coupling is actually costing money.",
   "Encapsulate before you extract: a clean interface around a module that still lives inside the monolith buys most of the decoupling benefit without the operational cost of standing up a new service.",
   "Every real extraction in this project was triggered by a named problem the monolith already had, a shared-table race, a synchronous call buried inside a transaction, never by a target architecture chosen in advance."],
  "This slide makes the restraint case, and it matters as much as the one before it. Modernization is a means, not a virtue in itself: the test for any one seam is whether a real, recurring change gets safer or cheaper once that seam is cut, not whether the result looks more like microservices on a diagram. A system nobody is actively changing is the cheapest system in the portfolio exactly as it stands; the move there is to encapsulate its rough edges, not extract it into a new deployable. Every one of the six extractions this book actually performed was pulled by a specific, pre-existing problem in the monolith, never by a target service count decided ahead of time, and that discipline is what keeps a modernization from turning into decomposition for its own sake.");

diagram("THE STRANGLER FIG · THE METHOD", "Grow the new system around the old",
  "strangler-four-moves",
  "Four ordered moves: intercept, route, replace, retire, with one reversibility window spanning the first three; retiring the old code is the single move this method refuses to let you make early.",
  "This diagram introduces the strangler fig as the alternative to a rewrite. The name comes from the tree that germinates around a host and grows into a free-standing structure while the host keeps doing its job the entire time. The metaphor fits because a big-bang rewrite has nothing equivalent: it bets the whole migration on one cutover event, and if something was missed, there is usually no way back. The strangler fig instead replaces that one high-stakes bet with many small, independently reversible ones: stand up a new service, prove it behaves identically to the piece of the monolith it replaces, cut traffic over, and only retire the old code once the cutover has held. Nothing is deleted until it no longer needs to exist, so nothing has to be rebuilt to recover from a bad cutover.");

// ===== ACT B — THE MIGRATION ==================================================
divider("B", "The Migration", "Grow the new system around the old, one seam at a time.",
  "This act is the migration told as a sequence of ideas rather than a sequence of code changes: a proxy that can hand any request to a different backend without a client noticing, a domain that tells you where its own seams already are, data ownership as the half of decomposition that actually hurts, and two different ways to coordinate a workflow once a single database transaction is no longer available to hold it together.");

diagram("THE STRANGLER FIG · PROXY ROUTING", "A proxy in front, one seam out at a time",
  "strangler-proxy-routing",
  "One process sits in front of the monolith and decides which backend answers, by configuration alone, never by anything a request carries: flip the setting to cut a seam over, flip it back to undo the cutover completely.",
  "This is the mechanism behind every cutover in this book. A single proxy intercepts every request before the monolith does, and a plain operator-controlled setting, never anything read out of the request itself, decides which backend actually answers. That last constraint matters for more than tidiness: if the routing decision could be influenced by a header or a path a caller controls, it would be handing an attacker a request-driven redirect to an arbitrary destination. Because the decision is pure configuration, every cutover is a flag flip, not a deployment, and reversing one is exactly as cheap as making it. That reversibility is what turns each of the six extractions later in this book into a small, bounded bet instead of a second big-bang rewrite in disguise.");

content("FINDING THE SEAMS", "Seams are discovered, not invented",
  ["Event storming and domain-driven bounded contexts are how a seam gets named precisely before anything is cut: guessing here is expensive to undo later.",
   "The service count follows the domain: six independently deployable services came out of six bounded contexts the monolith already had, not a number picked in advance.",
   "Routing answers who should see a request; it has nothing to say about what that service is allowed to assume about the data inside it. That second question is where the next idea picks up."],
  "Seams are discovered, not invented. The method here is domain-driven: event storming and bounded-context analysis are how a team names, with precision, where one coherent area of the business ends and another begins, before any code moves. Get that boundary wrong and the cost shows up later, as two new services that still have to change together. The service count in this book's finished system, six services plus a gateway, was never a target; it fell out of naming the bounded contexts the monolith already had. And it's worth being precise about what routing alone buys: it decides which process sees a request, nothing more. The moment a seam needs to decouple two services' data, not just their processes, a different idea has to take over, and that idea is the anti-corruption layer.");

diagram("DATA ACROSS THE SEAM", "Lead with owned data, not the shared schema",
  "shared-data-vs-owned-data",
  "Each service owns its own Postgres schema and its own migrations: the monolith's shared tables follow, with a translation contract standing in for the foreign key a service gives up when it stops sharing a database.",
  "Shared-database coupling is the hardest coupling in a monolith to break, because the database itself enforces it, not something you can route around in code. As long as two contexts share a schema, a foreign key will block a delete across a team boundary, and every query that needs a joined answer has to cross what should be two services' data. Database-per-service fixes that, but it isn't free: giving up the foreign key means giving up the database's own referential-integrity guarantee at that boundary, and the two sides now have to agree on an invariant by contract, a frozen event shape, a versioned schema, rather than have Postgres enforce it for them. What that buys back is real independence: each service's schema can migrate, scale, and be re-indexed without anyone outside that service ever noticing or coordinating a release around it.");

diagram("COORDINATING", "Two ways to run a workflow across services",
  "choreography-vs-orchestration-contrast",
  "Choreography and orchestration solve the same cross-service workflow with opposite control flow: independent services reacting to events, or one coordinator naming every step. Either way, an explicit compensating action replaces the rollback a shared transaction used to provide automatically.",
  "Once a workflow crosses a service boundary, the free rollback a single database transaction used to provide disappears: there is no longer one write-ahead log spanning every write, and nothing can undo a commit that already landed somewhere else. Two patterns rebuild that guarantee by hand, and they differ in where the decision logic lives. In a choreographed saga, there is no coordinator at all: every participant reacts only to events it already subscribes to, and the sequence emerges from those reactions; a payment service and an order process can each be redeployed without the other changing a line, because the only contract between them is the shape of a couple of event topics. In an orchestrated saga, one coordinator calls each participant in turn and decides the next step from the result. Neither is categorically better: this book uses both, for different seams, specifically so the choice is visible as a choice.");

diagram("COMMUNICATION · PROTOCOL FIT", "REST, gRPC, and GraphQL each earn their seam",
  "rest-grpc-graphql-protocol-fit",
  "REST for a service's own request/reply surface, gRPC for the one strongly-typed hot path that cannot tolerate ambiguity, GraphQL for aggregating several services into one client answer: the protocol follows the shape of the call, never habit.",
  "A system with more than one service needs more than one way for those services to talk, and this book uses three, side by side, each earning its seam rather than being the default everywhere. REST is the contract for any service's own read/write surface: the request/reply exchange a caller waits on. A strongly typed, versioned call, stock reservation during checkout, where ambiguity is not acceptable, gets a contract-first, binary-efficient protocol instead. And a client that wants one order's data plus its payments, its shipments, and its reviews in a single round trip gets a dataless aggregation layer that fans out to every source lazily and tolerates a partial failure as a null field rather than a crashed request. None of the three replaces the others: each solves a different problem the others don't.");

diagram("THE CUTOVER TIMELINE", "Six seams, in dependency order", "strangler-cutover-timeline",
  "Each of the six seams stays behind its own reversible setting until an automated equivalence suite proves the new service matches the old one, request for request: only then does the old code path retire for good.",
  "This is the evidence trail that makes every claim in this deck checkable rather than asserted. The same behavior-equivalence test suite, captured once against the original monolith, gets re-pointed at whichever backend is live for a given seam, never rewritten per cutover, only re-targeted. Flip a setting on, run the suite, see it pass against the new service; flip it back off, run the suite again, see it pass against the monolith exactly as before. That symmetry is the proof that the cutover is reversible in practice, not just in theory. Only the very last step in this timeline is irreversible by design: deleting the old code once every seam has held in production long enough that falling back to it is no longer a live option anyone needs.");

// ===== ACT C — OPERATING & REFLECTION =========================================
divider("C", "Operating & Reflection", "Run the result, measure the win, and know when to stop.",
  "This act steps back from any single extraction and asks what the finished system does as a whole: how it runs day to day once every service exists side by side, what the modernization actually measures, and which patterns from the wider catalog earned a lasting role versus which were named and left for later. It closes with the discipline that keeps six services from drifting into twenty.");

content("THE CHASSIS AS CONVENTION", "The chassis is a convention, not a framework",
  ["The chassis, covering configuration, logging, health checks, uniform error handling, and retry policy, is a convention every service follows, not a framework a team has to adopt.",
   "A convention copied by hand into eight small files is cheap to keep in sync; a shared library is a ninth dependency every service then has to version and roll out together: that coordination cost should wait until drift actually causes a bug, not before.",
   "Once the mesh is in place, the platform answers the operational questions: service identity, encrypted traffic, per-request metrics, so application code never has to."],
  "Strip away what each service does differently and ask what's left that every one of them does the same way, and the answer is the chassis: configuration, logging, a health endpoint, a uniform error shape, a retry policy. There is no shared dependency that turns one of those on with a single line: each capability becomes real the moment a service's own code implements it, and in this book that convention is written once and then copied, by hand, into the next service. That sounds like duplication, and it is, but the trade pays off: eight copies of a short, simple function are cheap to keep synchronized; one shared internal library is a second dependency every service now has to bump and test on its own schedule, which undoes the very independence the whole modernization was for. The platform picks up the rest once a mesh is in place: identity, encryption, and metrics, with zero application code written to get them.");

diagram("OPERATING · THE MESH", "mTLS and traffic identity, once services own their data",
  "mesh-mtls-topology",
  "Mutual TLS on every pod-to-pod hop, switched on for the whole namespace from a single resource, with one deliberate plaintext exception at the single edge a client reaches directly: no service's own code changed to get there.",
  "A service mesh puts a proxy in front of every workload's network traffic and moves a specific set of cross-cutting concerns out of application code entirely: encryption between services, per-hop metrics, and distributed trace spans for every request that crosses it. None of that requires a service to import a library or even know the mesh exists: a client still dials the same host and port it always did; the only thing that changes is which process actually terminates that connection. Turning on mutual TLS for an entire set of services becomes one resource instead of a per-service configuration effort, and the single exception, a plaintext edge where an external client first arrives, is scoped narrowly and explicitly, not left open by oversight. What a mesh does not buy is insight into what happens inside a service's own process, which is exactly the gap the next idea closes.");

diagram("OPERATING · THE TRACE", "One request, traced end to end", "mesh-hero-trace-waterfall",
  "One checkout request, traced end to end across three service hops: mesh-level spans giving breadth on every service, application-level spans giving depth on the handful that need it.",
  "The proof that a mesh and application tracing solve different problems is a single connected trace. A request enters at the one front door this system has always had, and from there every hop, through the edge proxy, into the order-processing service, across to the inventory service for a stock reservation, carries one trace header that both the mesh's own spans and the application's own spans attach to. The mesh spans show up for every service in the system, whether or not that service was ever instrumented, because the proxy produces them automatically. The application spans show up only where someone chose to add that depth, and they're what reveal two separate database writes happening inside what the mesh sees as a single request-response pair. Together they answer a question neither layer answers alone: not just that a request crossed three services, but what each one actually did while it had it.");

diagram("THE MEASURABLE WIN", "The modernization, made measurable", "supply-chain-gate-pipeline",
  "Same base image, same underlying exposure on both sides: the real win is a gate that scopes a merge decision to what a team can actually fix, so the service still being developed is held to a standard the frozen monolith was never going to meet.",
  "It would be a tidy story if the modernized service simply had fewer vulnerabilities than the monolith, but the real evidence is more useful than that: both images are built on the identical base layer, carry the identical unresolved component findings, and neither side's own application dependencies contribute a serious finding of either. The win is not component count, it's a policy, committed as a readable file, that gates a merge only on findings a team can actually act on, so a service someone still maintains is never blocked indefinitely by an upstream issue with no available fix. The frozen monolith is scanned and reported on the same pipeline, but by design never blocks on a finding nobody can do anything about. A supply-chain gate like this is what turns an invisible exposure into something a pull request reviewer can see and make a call on.");

diagram("THE RESULT", "One monolith, six independent services", "final-monolith-free-topology",
  "Six independently deployable services and a dataless aggregation gateway, reached through one router with no monolith left to fall back to: the original monolith stays in the repository, frozen and disconnected, never deleted.",
  "This is the end state every earlier idea in this deck was building toward: six services, each owning its own data, plus a gateway that owns none and exists purely to aggregate, all reached through the same router that started this whole method, now with every fallback setting removed and nothing left behind it to fall back to. The monolith itself is not deleted, it stays in the repository, frozen and unwired, a record of where the system started rather than a system still in service. That distinction matters: the strangler fig's whole promise was that the old system keeps standing until the new one has fully taken its place, and this is what fulfilling that promise looks like at the end rather than partway through.");

diagram("REFLECTION · THE PATTERN MAP", "Where each pattern lives in the language",
  "pattern-language-map",
  "Every pattern used across the migration, laid out as one connected flow and colored by verdict, earned, adapted, or named and deferred, with a ghost row naming the further horizons each deferred pattern would extend toward.",
  "Stepping back at the end, it's worth walking the full pattern catalog this modernization could have drawn from and checking, pattern by pattern, what it actually used. Three verdicts cover every row: earned, meaning the pattern shipped in roughly the shape the literature describes it and the system would be worse without it; adapted, meaning it shipped but in a narrower or differently scoped form than its usual description; and named-and-deferred, meaning the pattern was not built yet, with the condition that would change that answer stated alongside it. A catalog with no deferred column would be describing a different, less real project than the one actually built here: deferred is a verdict, not a gap to apologize for.");

diagram("REFLECTION · THE SCORECARD", "A pattern belongs when it cures a pain you have",
  "book-pattern-scorecard",
  "A pattern belongs in the finished system when it cures a pain the monolith actually had: used, adapted, or set aside for a stated reason, each verdict checkable against the running code rather than asserted from a diagram.",
  "The scorecard underneath the pattern map is what keeps this deck's claims checkable rather than aspirational. Every earned pattern, the strangler fig, the transactional outbox, both saga shapes, shipped because a named, specific problem in the monolith demanded it, not because a reference architecture suggested it. Every adapted pattern shipped in a scoped-down form for a stated reason, like a chassis implemented as a copied convention instead of a shared library, or a mesh with full observability depth on a handful of services instead of all of them. And every deferred pattern, a circuit breaker, full event sourcing, a delivery operator, is named explicitly, with the condition that would justify building it written down next to it. That discipline, applied consistently across every row, is what separates a modernization that can defend its own decisions from one that just looks modernized on a diagram.");

content("REFLECTION · WHERE TO STOP", "Over-decomposition is the seductive failure",
  ["The tell for over-decomposition is a coordinated release: if two of your new services still have to ship together, the boundary was drawn in the wrong place.",
   "A sprawl of tiny services carries the same pattern catalog as a well-bounded system and reaches for most of it for the wrong reason: more services to coordinate, more network calls, no independence gained in return.",
   "This system settled on six services and a gateway not because that number was a target, but because that's where the monolith's own real problems ran out."],
  "Every pattern in this catalog is available to reach for again, which makes it worth closing on the discipline that keeps reaching for them from becoming a trap. The distributed-monolith failure mode looks decomposed from the outside, multiple schemas, multiple deployables, while every piece still has to change in lockstep, because nothing about the split actually removed the coupling that made the system one thing in the first place. It is strictly worse than the monolith it replaced: a shared database at least gave atomic consistency without having to ask for it; a decomposed system that didn't earn its split gives that up and gets no independence in return. The discipline that avoided it here was simple to state and consistently applied: every real extraction in this book was triggered by a specific, named problem the monolith already had, never by a target architecture decided in advance.");

// ===== CLOSE ===================================================================
content("101 · CLOSE", "One monolith, six services, a method that verifies itself",
  ["The claim held end to end: a Django monolith with six tightly coupled contexts became six independently deployable FastAPI services that own their data and coordinate without a central conductor.",
   "Every cutover along the way stayed reversible until an automated equivalence suite proved it safe: the strangler fig is what made that possible without a single rewrite event.",
   "For the full pattern set and the running system behind every idea on these slides, see the 201; for the async code underneath it, see the FastAPI deep dive."],
  "Bring it back to the one claim this whole deck exists to support: a coupled Django monolith became six independently deployable FastAPI services, each owning its own data and coordinating with the others without any central conductor, and every single cutover along the way stayed reversible until an automated suite proved it safe to commit to. That's the strangler fig's whole case in one sentence, incremental, verified, and reversible beats a single high-stakes rewrite bet, every time the system has to keep running while it changes. Everything on these slides maps to a real chapter and a real running service; nothing here was hypothetical. For the complete pattern set and the system behind every idea in this deck, the 201 is the next stop, and for the async code underneath the patterns themselves, that's the FastAPI deep dive.");


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

  addNotes(s, "This is the 101 deck. The two codes take it with you: on the left, the reference implementation: the site, the runnable FastAPI services, and the strangler-fig migration that decomposes the monolith step by step. On the right, the Workshops and Tutorials hub: every workshop, tutorial, and deck in the series in one place. Both are public on the Pattern Catalyst GitHub organization.");
}


pres.writeFile({ fileName: OUT })
  .then(p => console.log("WROTE", p, "slides:", pageNum))
  .catch(e => { console.error(e); process.exit(1); });
