---
title: "Strategies & Assessment"
order: 4
part: "Why Modernize"
description: "Lift and Shift, Modernize and Extend and Rip and Rewrite, the strategic-value by change-frequency 2x2, and four criteria that set the order of extraction."
---

## Learning objectives

By the end of this chapter you can:

- Choose between Lift and Shift, Modernize and Extend and Rip and Rewrite for a given system.
- Place a system on the value-versus-change 2x2 and score it on the ease-of-migration rubric.
- Order bounded contexts for extraction by coupling, change frequency, risk and data entanglement.
- Re-score the remaining contexts after every extraction instead of fixing the order up front.

## Why this matters

Two questions follow once a reason to modernize exists: which strategy fits, and in what sequence to cut the system apart. They fail differently. The wrong strategy modernizes the wrong thing the wrong way. The right strategy in the wrong sequence spends the first three months proving that the hardest part of the system is hard, which was true before the project started.

## The strategy menu

Every option sits on one spectrum: how much of the system's shape survives, against how much of its behavior must.

| Strategy | What changes | What it buys | Main risk |
| --- | --- | --- | --- |
| **Lift and Shift** | Where it runs. Containerize the Django deployable and move it; code, data model and integrations stay. | The least complex option and often the fastest measurable cost benefit. | Nothing structural: the shared schema is still shared and the deployable still single. |
| **Modernize and Extend** | Internal structure (module boundaries, data ownership, deployment topology) while external behavior is preserved. The monolith stays intact while a new layer grows beside it and traffic cuts over incrementally. | Each step ships and can be verified against production behavior. The strangler fig lives here. | Sequencing: on a valuable, hard-to-touch system, the order of the cuts becomes the hard problem. |
| **Rip and Rewrite** | Everything. New software against the same or changed requirements. | The cleanest result on paper. | A long stretch where the new system doesn't do what the old one does, no way to verify partial progress, and the second-system effect: the rewrite grows to fix everything wrong with the original. |

{% include excalidraw.html file="migration-strategy-spectrum" alt="Four migration strategies compared side by side: big-bang rewrite (highest risk, one long cutover), the strangler fig (the choice here, incremental and independently verifiable), branch-by-abstraction (an in-process seam toggle), and parallel-run (a live shadow comparison of two running paths)." caption="Figure 4.1: The migration-strategy spectrum, from big-bang rewrite to the strangler fig" %}

Lift and Shift fits a system of modest strategic value and low change frequency: a real win in weeks without betting the project on a codebase nobody understands deeply. Rip and Rewrite fits only when the required rate of change has outgrown what incremental modernization can keep up with, which the reference monolith, an ordinary candidate by design, does not meet.

## The value-versus-change 2x2

Plot a candidate's **strategic value** against its **change frequency**. High on both is where incremental re-architecture pays, because every later feature lands faster once the architecture stops fighting the team. Low on both is Lift and Shift territory, or leave the system alone.

{% include excalidraw.html file="modernization-value-vs-change-2x2" alt="A four-quadrant plot of strategic value against change frequency. High value, high change frequency favors incremental re-architecture. Low value, low change frequency favors Lift and Shift or Retain. The reference monolith is plotted high on strategic value (the order-taking and fulfillment path for a shipping business) and, on the ease-of-migration rubric, difficult on data (one shared schema with cross-app foreign keys) and moderate everywhere else." caption="Figure 4.2: Where the reference monolith lands on the value-versus-change quadrant" %}

A second axis, the **ease-of-migration rubric**, scores code, configuration, data, secrets, network topology and system type as easy, moderate or difficult. A system can be critical and difficult at once, and then sequencing, not strategy, is the hard problem.

The reference monolith is that combination: high strategic value (it's the order-taking and fulfillment path of a shipping business), difficult on data (one shared Postgres schema with cross-app foreign keys, catalogued in `examples/00-monolith/SMELLS.md`) and moderate everywhere else. It was scored the way a reader's own system should be, not built as a strawman that makes "split it" a foregone conclusion.

## Pattern: Strangler Fig

The commitment is incremental, strangler-fig re-architecture inside the Modernize and Extend family, gated at every step by a behavior-equivalence suite. Three properties make it fit a high-value, difficult-to-touch system.

- **Reversibility, held open as long as possible.** During a seam's reversibility window, a cutover is a feature flag, not a deployment. `STRANGLER_REVIEW_ENABLED`, read from the environment, decides whether `/api/reviews` traffic reaches the monolith or the extracted service. Flipping it back is a config change and a restart, until the monolith's own module is decommissioned. A bad bet costs a flag flip, not months of work. (The final proxy is flagless: each seam's flag was removed when its window closed.)
- **Continuous delivery of value.** Each extraction ships the moment its equivalence gate goes green: Review on its own service, then Notification on event-driven delivery. A rewrite that is ninety percent complete delivers none of its value.
- **Proof before commitment.** The same Newman collection, unedited, runs against the monolith and then against every extracted service in turn. A green run must pass before the next flag flips, which makes "equivalent" a checkable claim.

## Choosing the order of extraction

A strategy answers how to cut. It doesn't say what to cut first. A wrong order doesn't fail the migration; it teaches the team the wrong lessons in the wrong order, because the hardest seam was attempted before anyone practiced on an easy one. Four criteria, applied together, replace the guess.

| Criterion | Question | Reading |
| --- | --- | --- |
| **Coupling and cohesion** | How many other contexts does this one call synchronously, and how many call it? | Zero synchronous collaborators means it can be extracted and verified in isolation. A context wired into four others' internals drags all four along. Coupling is the strongest predictor of how much other work an extraction pulls in. |
| **Change frequency** | How often does the business change it? | A rarely touched context is a low-stakes place to validate a new mechanism. A context under constant development pays most from modernizing but is hurt most by a botched extraction, so take it once the mechanism is proven elsewhere. |
| **Risk and blast radius** | What breaks, and for whom, if this goes wrong? | Revenue path, cascade into untouched contexts and cost of reversing after rollout begins. A context that fails loudly and in isolation is a safer first bet than one that fails silently and spreads. |
| **Data entanglement** | Does it share tables or cross-context foreign keys? | Separate from code coupling: two contexts can be decoupled in the service layer and still welded at the database. A context with its own schema is cheaper to extract. |

No criterion is sufficient alone. A low-coupling context can be high-risk on the revenue path, and a rarely changed one can be deeply data-entangled. Score every candidate on all four and order from the lowest combined score to the highest. Strategic importance decides whether to modernize a system at all; it's the wrong signal for which seam to cut first, because the most important context is almost never the safest one to practice on.

## The order applied to the reference monolith

Applied to the monolith's six bounded contexts, the criteria give this sequence: **review, then notification, then inventory, then payment, then shipping, then order together with its GraphQL gateway.**

**Review goes first.** It is a REST-only leaf: nothing in order, inventory, payment, shipping or notification calls it, and it calls none of them. Its only entanglement is shared authentication with every other endpoint, despite no runtime dependency on anything that authentication protects. With near-zero coupling it can be extracted, put behind the strangler proxy and verified against the equivalence suite with nothing else able to confound the result. If it fails, the cause is the mechanism itself (proxy, equivalence gate, cutover flag), not a tangled neighbor. Nobody is impressed that reviews moved, and that's the point: the mechanism is proven once, end to end, on the lowest-risk subject.

**Notification second.** Nothing calls its output synchronously, but it sat inside the checkout path, invoked directly from order placement. That forces the next new mechanism: a transactional outbox in the monolith publishes the event reliably, and Notification becomes the first Kafka-consuming, event-driven service. Rising difficulty, not rising domain importance, is the ordering principle.

**Inventory third.** Order needs it synchronously at checkout, and its data lives in the shared schema. Data entanglement, not coupling, makes it harder than Notification. Extraction needs a change-data-capture backfill into a newly owned database before writes cut over, the first data-ownership problem in the sequence.

**Payment and shipping fourth and fifth.** Each removes a piece of the monolith's single transaction spanning checkout, which is where distributed-transaction safety stops being free. Payment forces a choreographed saga over Kafka; shipping solves the same problem with a database-backed orchestrator. Back to back, they teach both coordination styles on one codebase.

**Order, with its GraphQL gateway, last.** It is the highest-coupling, highest-risk context: the order-placement path reaches directly into inventory, payment, shipping and notification code, and the five earlier extractions each remove one of those dependencies. By then the proxy, the equivalence gate and the agent loop that produces each extraction have been exercised five times.

{% include excalidraw.html file="strangler-evolution-arc" alt="Four left-to-right snapshots of the system's topology over the course of the migration: one Django deployable with six in-process apps and one shared schema; the same monolith with the ASGI strangler proxy standing in front, every call still passing through unchanged; review and notification live as FastAPI services behind the proxy while four contexts still answer from the shrinking monolith; and the fully extracted end state, a flagless edge router in front of all six services plus the GraphQL gateway, with the monolith decommissioned from the running topology and kept frozen as the 'before' referent." caption="Figure 4.3: The evolution arc the migration executes, snapshot by snapshot" %}

## Re-scoring after each extraction

The sequence is specific to this monolith. The discipline generalizes: score the remaining candidates against all four criteria again after each extraction, instead of committing to a six-context order up front. Inventory's data-entanglement problem wasn't as visible before Review and Notification had proven the mechanism on simpler subjects. Each extraction is reconnaissance into how the next seam behaves, and event storming finds seams the criteria alone can miss. Expect the order for the first two contexts to look obvious in hindsight and the order for the last two to depend on what the first four taught you about where the real coupling lives.

> **Decision**
>
> Pick Modernize and Extend when the system is valuable, changing and hard to touch. Order the cuts by lowest combined score on coupling, change frequency, risk and data entanglement, and re-score after every extraction.

> **🤖 Explore with your agent**
>
> "Read `examples/00-monolith/SMELLS.md` and the imports in `order`, `inventory`, `payment`, `shipping`, `notification` and `review`. Score all six contexts on coupling, change frequency, risk and data entanglement, rank them lowest score first, and say which one to extract first and why."
>
> Check: the reply puts review first and says no other app imports it; confirm with `grep -rnE "(from|import) +review" examples/00-monolith/{order,inventory,payment,shipping,notification} --include='*.py'`, which prints nothing.
