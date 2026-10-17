---
title: "Reading List"
layout: plan
permalink: /bibliography/
description: "The reference books this modernization course's patterns, rigor, and vocabulary draw on — nothing here is ported from them."
---

This course's pattern coverage, its migration playbook, and the vocabulary it
uses for seams, sagas, and data ownership draw on a small set of reference
works. They are reference works, not sources: no text or code from any of them
is reproduced in these chapters or the runnable examples. Each row names what
the book leans on it for and the chapters where that shows up.

## Domain-Driven Design and finding the seams

| Work | Author(s) | What this book draws on | Chapters |
|---|---|---|---|
| *Domain-Driven Design: Tackling Complexity in the Heart of Software* | Eric Evans | Bounded contexts, ubiquitous language, aggregates, the anti-corruption layer — the vocabulary for where one service ends and the next begins. | 11, 16, 19 |
| *Implementing Domain-Driven Design* | Vaughn Vernon | Aggregate design rules, domain events, and keeping the domain core free of framework (here: Django ORM) concerns. | 11, 12 |
| *Learning Domain-Driven Design* | Vlad Khononov | The modern, pragmatic framing of subdomain types and context mapping used to classify the six contexts. | 11, 13 |
| *Balancing Coupling in Software Design* | Vlad Khononov | The three dimensions of coupling (integration strength, distance, volatility) that drive the "when not to split" argument. | 13 |
| *Structured Design* | Larry Constantine & Ed Yourdon | The classic coupling taxonomy (content → data) scored against the monolith's real seams. | 13 |

## Microservices, the strangler fig, and the patterns

| Work | Author(s) | What this book draws on | Chapters |
|---|---|---|---|
| "StranglerFigApplication" | Martin Fowler | The incremental-replacement thesis the whole migration is built on — strangle, don't rewrite. | 14 |
| *Monolith to Microservices* | Sam Newman | The extraction playbook: seam-by-seam migration, the strangler pattern applied, splitting the database. | 03, 04, 14, 18 |
| *Building Microservices* | Sam Newman | Service boundaries, independent deployability, and the operational traits a service earns. | 03, 29–31 |
| *Microservices Patterns* | Chris Richardson | The pattern catalog this book implements in Python: transactional outbox, choreographed and orchestrated sagas, CQRS, API composition. | 20–26 |
| *Enterprise Integration Patterns* | Gregor Hohpe & Bobby Woolf | The messaging vocabulary — content-based routing, the message channel, the translator — behind the event-driven seams. | 16, 17 |

## Reliability, data, and operating the result

| Work | Author(s) | What this book draws on | Chapters |
|---|---|---|---|
| *Release It!* | Michael Nygard | Timeouts, retries, circuit breakers, bulkheads — the resilience chassis around the saga hops. | 25 |
| *Designing Data-Intensive Applications* | Martin Kleppmann | Log-based change data capture, idempotency, and the consistency trade-offs of moving from one ACID database to many. | 18, 19, 22 |
| *Site Reliability Engineering* | Betsy Beyer et al. (eds.) | The golden signals and the service-level thinking behind the mesh/observability chapter. | 30 |

*Verification status: <span class="status status--unverified">unverified</span>. Conceptual reading-list page — the works above are named as references the chapters draw on, with no text or code reproduced from them.*
