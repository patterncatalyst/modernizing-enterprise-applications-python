---
title: "Bibliography"
layout: plan
permalink: /bibliography/
description: "The reference books this modernization course's patterns, rigor, and vocabulary draw on — nothing here is ported from them."
---

This course's pattern coverage, its migration playbook, and the vocabulary it
uses for seams, sagas, and data ownership draw on a small set of reference
works. They are reference works, not sources: no text or code from any of them
is reproduced in these chapters or the runnable examples. Each row links the
work, names what the book leans on it for, and the chapters where that shows up.

## Domain-Driven Design and finding the seams

| Title | Author(s) | Publisher | Year | What this book draws on | Chapters |
|---|---|---|---|---|---|
| [*Domain-Driven Design: Tackling Complexity in the Heart of Software*](https://www.informit.com/store/domain-driven-design-tackling-complexity-in-the-heart-9780321125217) | Eric Evans | Addison-Wesley | 2003 | Bounded contexts, ubiquitous language, aggregates, the anti-corruption layer — the vocabulary for where one service ends and the next begins. | 11, 16, 19 |
| [*Implementing Domain-Driven Design*](https://www.informit.com/store/implementing-domain-driven-design-9780133039894) | Vaughn Vernon | Addison-Wesley | 2013 | Aggregate design rules, domain events, and keeping the domain core free of framework (here: Django ORM) concerns. | 11, 12 |
| [*Learning Domain-Driven Design*](https://www.oreilly.com/library/view/learning-domain-driven-design/9781098100124/) | Vlad Khononov | O'Reilly | 2021 | The modern, pragmatic framing of subdomain types and context mapping used to classify the six contexts. | 11, 13 |
| [*Balancing Coupling in Software Design*](https://www.informit.com/store/balancing-coupling-in-software-design-universal-design-9780137353538) | Vlad Khononov | Addison-Wesley | 2024 | The three dimensions of coupling (integration strength, distance, volatility) that drive the "when not to split" argument. | 13 |
| *Structured Design* | Larry Constantine & Ed Yourdon | Yourdon Press | 1979 | The classic coupling taxonomy (content → data) scored against the monolith's real seams. | 13 |

## Microservices, the strangler fig, and the patterns

| Title | Author(s) | Publisher | Year | What this book draws on | Chapters |
|---|---|---|---|---|---|
| [*StranglerFigApplication*](https://martinfowler.com/bliki/StranglerFigApplication.html) | Martin Fowler | martinfowler.com | 2004 | The incremental-replacement thesis the whole migration is built on — strangle, don't rewrite. | 14 |
| [*Monolith to Microservices*](https://www.oreilly.com/library/view/monolith-to-microservices/9781492047834/) | Sam Newman | O'Reilly | 2019 | The extraction playbook: seam-by-seam migration, the strangler pattern applied, splitting the database. | 03, 04, 14, 18 |
| [*Building Microservices*, 2nd ed.](https://www.oreilly.com/library/view/building-microservices-2nd/9781492034018/) | Sam Newman | O'Reilly | 2021 | Service boundaries, independent deployability, and the operational traits a service earns. | 03, 29–31 |
| [*Microservices Patterns*](https://www.manning.com/books/microservices-patterns) | Chris Richardson | Manning | 2018 | The pattern catalog this book implements in Python: transactional outbox, choreographed and orchestrated sagas, CQRS, API composition. | 20–26 |
| [*Enterprise Integration Patterns*](https://www.enterpriseintegrationpatterns.com/) | Gregor Hohpe & Bobby Woolf | Addison-Wesley | 2003 | The messaging vocabulary — content-based routing, the message channel, the translator — behind the event-driven seams. | 16, 17 |

## Reliability, data, and operating the result

| Title | Author(s) | Publisher | Year | What this book draws on | Chapters |
|---|---|---|---|---|---|
| [*Release It!*, 2nd ed.](https://pragprog.com/titles/mnee2/release-it-second-edition/) | Michael Nygard | Pragmatic Bookshelf | 2018 | Timeouts, retries, circuit breakers, bulkheads — the resilience chassis around the saga hops. | 25 |
| [*Designing Data-Intensive Applications*](https://dataintensive.net/) | Martin Kleppmann | O'Reilly | 2017 | Log-based change data capture, idempotency, and the consistency trade-offs of moving from one ACID database to many. | 18, 19, 22 |
| [*Site Reliability Engineering*](https://sre.google/sre-book/table-of-contents/) | Betsy Beyer, et al. | O'Reilly | 2016 | The golden signals and the service-level thinking behind the mesh/observability chapter. | 30 |

*Verification status: <span class="status status--verified">verified</span>. Conceptual reading-list page — the works above are named as references the chapters draw on, with no text or code reproduced from them.*
