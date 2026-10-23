---
title: "Outline"
layout: plan
permalink: /docs/00-outline/
description: "What this book covers and how it is organized: 34 chapters across twelve parts, modernizing a Django monolith to FastAPI with an agentic development lifecycle."
---

This book modernizes a believable Django monolith into FastAPI services, one
seam at a time, using an agentic development lifecycle. The full arc is below.

**Part 0: Setting Up**

- [Introduction & How to Use This Book](../00-introduction/)
- [Prerequisites & the Toolchain](../01-prerequisites/)
- [The Project Ledger](../02-project-ledger/)

**Part 1: Why Modernize**

- [Modernization as Engineering, Not Fashion](../03-modernization-as-engineering/)
- [Strategies & Assessment](../04-strategies-and-assessment/)

**Part 2: The Agentic Development Lifecycle (ADLC)**

- [From SDLC to ADLC](../05-from-sdlc-to-adlc/)
- [Agents, Skills & MCP Tools in the Loop](../06-agents-skills-mcp/)
- [The ADLC Safety Net](../07-adlc-safety-net/)

**Part 3: The Reference Monolith**

- [Designing the Monolith](../08-designing-the-monolith/)
- [The Deliberate Smells](../09-deliberate-smells/)
- [Testing the Monolith (the Equivalence Suite)](../10-testing-the-monolith/)

**Part 4: Finding the Seams**

- [Strategic & Tactical DDD + Hexagonal](../11-ddd-and-hexagonal/)
- [Event Storming the Monolith](../12-event-storming/)
- [Coupling, the Modular Monolith & When Not to Split](../13-coupling-and-modular-monolith/)

**Part 5: The Strangler Fig in Practice**

- [The Strangler Fig Pattern](../14-strangler-fig-pattern/)
- [Extraction 1: Review Service](../15-extraction-1-review-service/)
- [Content-Based Routing & the Anti-Corruption Layer](../16-content-based-routing-acl/)
- [Extraction 2: Notification Service (Going Event-Driven)](../17-extraction-2-notification-service/)

**Part 6: Data Across the Seam**

- [From Shared Data to Owned Data](../18-shared-data-to-owned-data/)
- [CDC, Transaction Log Tailing & Extraction 3: Inventory](../19-cdc-and-extraction-3-inventory/)
- [The Outbox Pattern, Done Right](../20-outbox-pattern-done-right/)
- [Event Sourcing & CQRS](../21-event-sourcing-and-cqrs/)
- [ACID → ACD: Living Without Isolation](../22-acid-to-acd/)

**Part 7: Coordinating Across Services**

- [Distributed Transactions, the Saga & Extraction 4: Payment (choreographed)](../23-saga-and-extraction-4-payment/)
- [Orchestrated Sagas & Extraction 5: Shipping (FastAPI Saga Coordinator)](../24-extraction-5-shipping-service/)
- [Failure Modes & the Resilience Chassis](../25-failure-modes-and-resilience/)

**Part 8: Communication & Contracts**

- [Communication Styles & Extraction 6: Order + GraphQL Gateway](../26-communication-and-extraction-6-order/)
- [The FastAPI Chassis](../27-quarkus-microprofile-chassis/)
- [Contracts & the Service Registry](../28-contracts-and-service-registry/)

**Part 9: Operating the Modernized System**

- [Deployment Patterns](../29-deployment-patterns/)
- [Mesh, Observability & Distributed Tracing](../30-mesh-observability-tracing/)

**Part 10: Delivering & Reflection**

- [CI/CD, GitOps, Progressive Delivery & Supply Chain](../31-cicd-gitops-supply-chain/)
- [The Pattern Language, Revisited](../32-pattern-language-revisited/)

**Part 11: Appendices**

- [Appendix A: Deploying to OpenShift](../33-appendix-openshift/)
