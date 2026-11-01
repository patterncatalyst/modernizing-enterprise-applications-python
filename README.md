# Modernizing Enterprise Applications — Python

Incrementally strangle a **Django monolith** into **FastAPI microservices**, gated
every step of the way by an executable behavior-equivalence suite, and driven by an
**Agentic Development Lifecycle (ADLC)**.

This is the Python-language sibling of
[modernizing-enterprise-applications](https://github.com/patterncatalyst/modernizing-enterprise-applications)
(Java: Spring Boot → Quarkus + Apache Camel). Same e-commerce / shipping domain, same six
extractions, same methodology — a different stack.

## What's here

A chapter-based book (Jekyll / GitHub Pages), a runnable monorepo (the smelly Django
monolith plus the FastAPI services it is strangled into), and a three-deck presentation
set (101 / 201 / 201-fastapi).

## Status

🚧 Bootstrapping — iteration **r01** (walking skeleton) in progress.

## Stack

uv · Python 3.14 · FastAPI · Django · pydantic v2 · SQLAlchemy / asyncpg · aiokafka ·
grpcio · Strawberry GraphQL · OpenTelemetry → Grafana LGTM · Postgres · Kafka · Newman.

## License

This project is dual-licensed to separate the code from the writing:

- **Code** — everything under `examples/`, plus build and helper scripts and
  inline code snippets — is licensed under the **Apache License 2.0**
  ([`LICENSE`](LICENSE)).
- **Content** — the tutorial and book prose (chapters under `_docs/`),
  diagrams and images under `assets/`, and the slide decks under
  `presentation/` — is licensed under **Creative Commons Attribution 4.0
  International (CC BY 4.0)** ([`LICENSE-docs.md`](LICENSE-docs.md)).

Copyright 2026 PatternCatalyst (Robert Sedor).

