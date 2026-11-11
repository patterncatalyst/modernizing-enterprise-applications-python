---
title: "Bibliography"
layout: plan
permalink: /bibliography/
description: "The reference books this modernization course's patterns, rigor, and vocabulary draw on. Nothing here is ported from them."
---

This course's pattern coverage, its migration playbook, and the vocabulary it
uses for seams, sagas, and data ownership draw on a small set of reference
works. They are reference works, not sources: no text or code from any of them
is reproduced in these chapters or the runnable examples. Each row links the
work, names what the book leans on it for, and the chapters where that shows up.

## Domain-Driven Design and finding the seams

<table class="bib bib--books">
  <colgroup><col style="width:62%"><col style="width:24%"><col style="width:14%"></colgroup>
  <thead><tr><th>Title</th><th>Author(s)</th><th>Year</th></tr></thead>
  <tbody>
    <tr><td><a href="https://www.informit.com/store/domain-driven-design-tackling-complexity-in-the-heart-9780321125217" rel="noopener"><em>Domain-Driven Design: Tackling Complexity in the Heart of Software</em></a><br><small>Addison-Wesley. Bounded contexts, ubiquitous language, aggregates, the anti-corruption layer, the vocabulary for where one service ends and the next begins. Chapters: <a href="{{ '/docs/11-ddd-and-hexagonal/' | relative_url }}" rel="noopener">Strategic &amp; Tactical DDD + Hexagonal</a>; <a href="{{ '/docs/16-content-based-routing-acl/' | relative_url }}" rel="noopener">Content-Based Routing &amp; the Anti-Corruption Layer</a>; <a href="{{ '/docs/19-cdc-and-extraction-3-inventory/' | relative_url }}" rel="noopener">CDC, Transaction Log Tailing &amp; Extraction 3: Inventory</a></small></td><td>Eric Evans</td><td>2003</td></tr>
    <tr><td><a href="https://www.informit.com/store/implementing-domain-driven-design-9780133039894" rel="noopener"><em>Implementing Domain-Driven Design</em></a><br><small>Addison-Wesley. Aggregate design rules, domain events, and keeping the domain core free of framework (here: Django ORM) concerns. Chapters: <a href="{{ '/docs/11-ddd-and-hexagonal/' | relative_url }}" rel="noopener">Strategic &amp; Tactical DDD + Hexagonal</a>; <a href="{{ '/docs/12-event-storming/' | relative_url }}" rel="noopener">Event Storming the Monolith</a></small></td><td>Vaughn Vernon</td><td>2013</td></tr>
    <tr><td><a href="https://www.oreilly.com/library/view/learning-domain-driven-design/9781098100124/" rel="noopener"><em>Learning Domain-Driven Design</em></a><br><small>O'Reilly. The modern, pragmatic framing of subdomain types and context mapping used to classify the six contexts. Chapters: <a href="{{ '/docs/11-ddd-and-hexagonal/' | relative_url }}" rel="noopener">Strategic &amp; Tactical DDD + Hexagonal</a>; <a href="{{ '/docs/13-coupling-and-modular-monolith/' | relative_url }}" rel="noopener">Coupling, the Modular Monolith &amp; When Not to Split</a></small></td><td>Vlad Khononov</td><td>2021</td></tr>
    <tr><td><a href="https://www.informit.com/store/balancing-coupling-in-software-design-universal-design-9780137353538" rel="noopener"><em>Balancing Coupling in Software Design</em></a><br><small>Addison-Wesley. The three dimensions of coupling (integration strength, distance, volatility) that drive the "when not to split" argument. Chapters: <a href="{{ '/docs/13-coupling-and-modular-monolith/' | relative_url }}" rel="noopener">Coupling, the Modular Monolith &amp; When Not to Split</a></small></td><td>Vlad Khononov</td><td>2024</td></tr>
    <tr><td><em>Structured Design</em><br><small>Yourdon Press. The classic coupling taxonomy (content → data) scored against the monolith's real seams. Chapters: <a href="{{ '/docs/13-coupling-and-modular-monolith/' | relative_url }}" rel="noopener">Coupling, the Modular Monolith &amp; When Not to Split</a></small></td><td>Larry Constantine &amp; Ed Yourdon</td><td>1979</td></tr>
  </tbody>
</table>

## Microservices, the strangler fig, and the patterns

<table class="bib bib--books">
  <colgroup><col style="width:62%"><col style="width:24%"><col style="width:14%"></colgroup>
  <thead><tr><th>Title</th><th>Author(s)</th><th>Year</th></tr></thead>
  <tbody>
    <tr><td><a href="https://martinfowler.com/bliki/StranglerFigApplication.html" rel="noopener"><em>StranglerFigApplication</em></a><br><small>martinfowler.com. The incremental-replacement thesis the whole migration is built on, strangle, don't rewrite. Chapters: <a href="{{ '/docs/14-strangler-fig-pattern/' | relative_url }}" rel="noopener">The Strangler Fig Pattern</a></small></td><td>Martin Fowler</td><td>2004</td></tr>
    <tr><td><a href="https://www.oreilly.com/library/view/monolith-to-microservices/9781492047834/" rel="noopener"><em>Monolith to Microservices</em></a><br><small>O'Reilly. The extraction playbook: seam-by-seam migration, the strangler pattern applied, splitting the database. Chapters: <a href="{{ '/docs/03-modernization-as-engineering/' | relative_url }}" rel="noopener">Modernization as Engineering, Not Fashion</a>; <a href="{{ '/docs/04-strategies-and-assessment/' | relative_url }}" rel="noopener">Strategies &amp; Assessment</a>; <a href="{{ '/docs/14-strangler-fig-pattern/' | relative_url }}" rel="noopener">The Strangler Fig Pattern</a>; <a href="{{ '/docs/18-shared-data-to-owned-data/' | relative_url }}" rel="noopener">From Shared Data to Owned Data</a></small></td><td>Sam Newman</td><td>2019</td></tr>
    <tr><td><a href="https://www.oreilly.com/library/view/building-microservices-2nd/9781492034018/" rel="noopener"><em>Building Microservices</em>, 2nd ed.</a><br><small>O'Reilly. Service boundaries, independent deployability, and the operational traits a service earns. Chapters: 03, 29-31</small></td><td>Sam Newman</td><td>2021</td></tr>
    <tr><td><a href="https://www.manning.com/books/microservices-patterns" rel="noopener"><em>Microservices Patterns</em></a><br><small>Manning. The pattern catalog this book implements in Python: transactional outbox, choreographed and orchestrated sagas, CQRS, API composition. Chapters: 20-26</small></td><td>Chris Richardson</td><td>2018</td></tr>
    <tr><td><a href="https://www.enterpriseintegrationpatterns.com/" rel="noopener"><em>Enterprise Integration Patterns</em></a><br><small>Addison-Wesley. The messaging vocabulary (content-based routing, the message channel, the translator) behind the event-driven seams. Chapters: <a href="{{ '/docs/16-content-based-routing-acl/' | relative_url }}" rel="noopener">Content-Based Routing &amp; the Anti-Corruption Layer</a>; <a href="{{ '/docs/17-extraction-2-notification-service/' | relative_url }}" rel="noopener">Extraction 2: Notification Service (Going Event-Driven)</a></small></td><td>Gregor Hohpe &amp; Bobby Woolf</td><td>2003</td></tr>
  </tbody>
</table>

## Reliability, data, and operating the result

<table class="bib bib--books">
  <colgroup><col style="width:62%"><col style="width:24%"><col style="width:14%"></colgroup>
  <thead><tr><th>Title</th><th>Author(s)</th><th>Year</th></tr></thead>
  <tbody>
    <tr><td><a href="https://pragprog.com/titles/mnee2/release-it-second-edition/" rel="noopener"><em>Release It!</em>, 2nd ed.</a><br><small>Pragmatic Bookshelf. Timeouts, retries, circuit breakers, bulkheads, the resilience chassis around the saga hops. Chapters: <a href="{{ '/docs/25-failure-modes-and-resilience/' | relative_url }}" rel="noopener">Failure Modes &amp; the Resilience Chassis</a></small></td><td>Michael Nygard</td><td>2018</td></tr>
    <tr><td><a href="https://dataintensive.net/" rel="noopener"><em>Designing Data-Intensive Applications</em></a><br><small>O'Reilly. Log-based change data capture, idempotency, and the consistency trade-offs of moving from one ACID database to many. Chapters: <a href="{{ '/docs/18-shared-data-to-owned-data/' | relative_url }}" rel="noopener">From Shared Data to Owned Data</a>; <a href="{{ '/docs/19-cdc-and-extraction-3-inventory/' | relative_url }}" rel="noopener">CDC, Transaction Log Tailing &amp; Extraction 3: Inventory</a>; <a href="{{ '/docs/22-acid-to-acd/' | relative_url }}" rel="noopener">ACID to ACD: Living Without Isolation</a></small></td><td>Martin Kleppmann</td><td>2017</td></tr>
    <tr><td><a href="https://sre.google/sre-book/table-of-contents/" rel="noopener"><em>Site Reliability Engineering</em></a><br><small>O'Reilly. The golden signals and the service-level thinking behind the mesh/observability chapter. Chapters: <a href="{{ '/docs/30-mesh-observability-tracing/' | relative_url }}" rel="noopener">Mesh, Observability &amp; Distributed Tracing</a></small></td><td>Betsy Beyer, et al.</td><td>2016</td></tr>
  </tbody>
</table>

*Verification status: <span class="status status--verified">verified</span>. Conceptual reading-list page: the works above are named as references the chapters draw on, with no text or code reproduced from them.*
