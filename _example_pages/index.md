---
title: "Examples"
layout: plan
permalink: /examples/
description: "Every runnable example in this repo, mapped to the chapter it supports."
---

Every hands-on chapter in this book points at a matching directory under
[`examples/`](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples)
in the repo. `00-monolith` is the Django system the whole book decomposes, and
each later directory is a FastAPI service extracted from it — the same code the
chapters quote. The monolith is Django; every extracted service is
Python/FastAPI.

| Example | What it shows | Chapter |
|---|---|---|
| [00-monolith](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/00-monolith) | The Django 5.2 + DRF monolith — all six bounded contexts in one project, one Postgres schema, checkout as one synchronous function. The walking skeleton the book strangles. | [Ch8]({{ '/docs/08-designing-the-monolith/' | relative_url }}) |
| [01-strangler-proxy](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/01-strangler-proxy) | A thin ASGI reverse proxy in front of the monolith, so bounded contexts peel off one seam at a time behind a flag. | [Ch14]({{ '/docs/14-strangler-fig-pattern/' | relative_url }}) |
| [02-review-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/02-review-service) | The `review` context extracted onto its own FastAPI service — lift onto FastAPI, then re-author to idiomatic. | [Ch15]({{ '/docs/15-extraction-1-review-service/' | relative_url }}) |
| [03-notification-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/03-notification-service) | The `notification` context extracted as a net-new, event-driven FastAPI service consuming `order.placed`. | [Ch17]({{ '/docs/17-extraction-2-notification-service/' | relative_url }}) |
| [04-inventory-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/04-inventory-service) | The `inventory` context extracted with two protocol surfaces, fed from the monolith by log-based change data capture. | [Ch19]({{ '/docs/19-cdc-and-extraction-3-inventory/' | relative_url }}) |
| [05-payment-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/05-payment-service) | The `payment` context extracted as a choreographed saga participant, write path net-new. | [Ch23]({{ '/docs/23-saga-and-extraction-4-payment/' | relative_url }}) |
| [06-shipping-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/06-shipping-service) | The `shipping` context extracted as an orchestrated saga step. | [Ch24]({{ '/docs/24-extraction-5-shipping-service/' | relative_url }}) |
| [07-order-service](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/07-order-service) | The `order` context — the god `place_order()` and its saga reactions — extracted CQRS from day one, with its own transactional outbox. | [Ch26]({{ '/docs/26-communication-and-extraction-6-order/' | relative_url }}) |
| [08-graphql-gateway](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/08-graphql-gateway) | A data-less Strawberry GraphQL aggregation gateway composing the extracted services into one read view. | [Ch26]({{ '/docs/26-communication-and-extraction-6-order/' | relative_url }}) |
| [09-schema-registry-demo](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/09-schema-registry-demo) | An Avro + Apicurio schema-registry demonstrator, additive to the project's JSON event flows. | [Ch28]({{ '/docs/28-contracts-and-service-registry/' | relative_url }}) |
| [10-supply-chain](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/10-supply-chain) | The supply-chain gate — SBOM generation, CVE scan, and policy-as-code over the images this project builds. | [Ch31]({{ '/docs/31-cicd-gitops-supply-chain/' | relative_url }}) |

## Running the examples

The services run together as one stack, not as isolated snippets. From the repo
root, `scripts/stack-up.sh` builds and starts the monolith, the strangler proxy,
and the extracted services over `compose.yaml`; the Newman contract suite in
`tooling/newman/` asserts behaviour equivalence across the seam; and
`scripts/stack-down.sh` tears it back down.

```bash
./scripts/stack-up.sh        # build + start the stack
# ... exercise it; run the Newman contract suite ...
./scripts/stack-down.sh      # stop + clean up
```

Each directory under `examples/` has its own `README.md` with the specifics for
that service. The supply-chain gate (`10-supply-chain`) is self-contained and
runs on its own with `./demo.sh`. See
[Prerequisites]({{ '/docs/01-prerequisites/' | relative_url }}) for the full
toolchain setup.
