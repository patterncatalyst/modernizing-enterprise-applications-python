---
title: "Prerequisites & the Toolchain"
order: 1
part: "Setting Up"
description: "uv, Python 3.14, Django and FastAPI, Docker Engine and the compose observability stack, and a verify-your-setup gate."
---

The introduction promised a monolith you can actually run, extractions you
can actually watch happen, and a behavior-equivalence suite you can actually
fail and fix. None of that is a thought experiment past this point — starting
with the next chapter, every claim in this book is backed by code sitting in
this repository, and this chapter's entire job is to get that code building
and talking to itself on your machine before a single pattern gets discussed.
There is no new example directory here to point at; instead, this chapter
walks you through the toolchain and then through the one piece of code that
already exists at this point in the book — `examples/00-monolith/` — far
enough to prove it runs. Chapter 8 is where it gets explained properly; this
chapter's bar is lower and more mechanical: clone, install, start, and
confirm.

{% include excalidraw.html file="toolchain-and-repo-layout" alt="The local toolchain split into the two pieces every chapter needs (uv, managing the Python 3.14 interpreter, the virtual environment, and the lockfile; ruff and pytest as the dev-dependency group every service pulls in) and two ghosted later-scoped tools (grpcio-tools and a proto-drift check, both scoped to the Chapter 19 gRPC seam), alongside the compose stack's live services (Postgres, single-broker KRaft-mode Kafka, the Grafana LGTM bundle) and its two ghosted later services (Debezium Connect, the Apicurio schema registry), both landing in the same repository tree: examples/, tooling/, demos/, infra/, scripts/, and _docs/." caption="Figure 1.1 — The local toolchain and the repository layout it builds, runs, and stands up." %}

## What you need, and where it comes from

Five tools make an appearance across this book, and only two of them are
required for everything that follows. The rest are scoped to specific parts,
and it is worth knowing which is which before you install anything, because
installing tools you will not touch until Part 6 is wasted effort today.

**uv, and the Python 3.14 interpreter it manages.** Every Python example in
this book — the Django monolith, the FastAPI services, the GraphQL gateway —
targets Python 3.14, and every project's `pyproject.toml` pins
`requires-python = ">=3.14"` explicitly rather than leaving the interpreter
version to whatever happens to be on your `PATH`. **uv** is the one tool this
book treats as non-negotiable: it installs the pinned Python version itself
if you do not already have it, creates the project's virtual environment,
resolves and locks dependencies into a committed `uv.lock`, and runs commands
inside that environment without you ever activating it by hand. Install it
once, then let it do the rest:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
uv --version
```

From inside any project directory in this repository — `examples/00-monolith/`
is the first one you will use — `uv sync` reads that project's
`pyproject.toml` and `uv.lock` and builds a `.venv` with exactly the
dependencies the lockfile pins, down to the transitive ones; `uv run <cmd>`
runs a command inside that environment without a separate activation step.
You will type both constantly from here forward, so it is worth running them
once now rather than meeting them for the first time in Chapter 8:

```bash
cd examples/00-monolith
uv sync --group dev
uv run python --version
```

**Django and Django REST Framework — pinned per-project, installed by uv, not
by you.** The monolith's `pyproject.toml` pins `django==5.2.18` (the current
5.2 LTS patch release) and `djangorestframework==3.18.3`; `uv sync` installs
exactly those versions into the project's own virtual environment, and you
never run a separate `pip install django` step. The same is true of
**FastAPI** in every extracted service from Part 5 onward — each service's
own `pyproject.toml` pins its own FastAPI version, and `uv sync` inside that
service's directory is the only installation step. One consequence worth
internalizing now: the monolith and every extracted service each get their
own `.venv`, not a shared one, because each has its own lockfile and this
project runs no uv workspace (there is exactly one Python package per
`examples/` directory at this point in the book, so a workspace root would be
infrastructure with nothing yet to share).

**Docker Engine and the `docker compose` plugin — docker-primary,
podman-compatible.** The local stack (Postgres, Kafka, the Grafana LGTM
observability bundle, plus Debezium Connect and the Apicurio schema registry
once later chapters need them) runs on Docker Engine — the `docker-ce`
packages from Docker's own repository, talking to `/var/run/docker.sock`
through the docker context named `default`. The repository's own
`compose.yaml` is written against the plain Compose Specification, with no
engine-specific keys, so a `podman compose` invocation parses the identical
file if that is what you already have installed; this book is written and
verified against Docker Engine, and Podman compatibility is a stated
constraint the compose file honors rather than a second file anyone
maintains. Compose is the v2 CLI plugin, invoked as `docker compose` (a
space, not the hyphenated legacy `docker-compose` binary). The book is
written and verified on **Fedora and RHEL** hosts (bare metal or VM). Install
from Docker's repository — Fedora (dnf5) is shown; on RHEL the repository
line is
`sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo`:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"        # then log out and back in
```

Remove `podman-docker` first if it is installed — it shadows the `docker`
command. Then confirm the engine, the context, and the plugin:

{% raw %}
```bash
docker context show        # default
docker version --format '{{.Server.Version}}'
docker compose version
```
{% endraw %}

With the engine on the default socket, any later test suite that spins up
its own disposable containers finds it with no further configuration (no
`DOCKER_HOST` export needed).

**Node.js and Newman — for the behavior-equivalence suite.** The suite that
gates every extraction in this book from Part 5 onward is a Postman
collection run through **Newman**, Postman's command-line collection runner,
which itself runs on Node.js. You do not need Node for anything else in this
book — no JavaScript application code appears anywhere in the examples — so a
recent LTS release (Node 22 or newer) is sufficient —
`sudo dnf install -y nodejs npm` on Fedora and RHEL. Install Newman globally
once Node is in place:

```bash
npm install -g newman
newman --version
```

**Git**, for cloning the repository and following the ledger history this
book cites directly — Chapter 2 walks through the decision log and build
plan that record exactly why this project's choices were made, and you will
want `git log` working locally to read the commits those rows describe
rather than taking the book's word for it.

Two tools exist in this toolchain but are scoped to much later parts rather
than needed today, and installing them now would just be ahead-of-schedule
effort: **`grpcio-tools`**, which generates the Python
stubs for the inventory extraction's gRPC seam, is not needed until Chapter
19 in Part 6; **minikube**, the Kubernetes substrate this book deploys the
finished system onto, is reserved for Parts 9 and 10 and has no place in the
toolchain you are assembling right now. Neither is part of this chapter's
verify-your-setup gate, and neither will be mentioned again until the chapter
that actually needs it.

**Ruby and Bundler — only if you intend to build this Jekyll site locally.**
Reading the chapters does not require Ruby at all; this book is published as
a static GitHub Pages site and a browser is the only client most readers
need. If you want to preview chapter edits or regenerate diagrams on your own
machine, the root `Gemfile` pins Jekyll to the same gem versions GitHub Pages
runs in production, installed the ordinary Bundler way:

```bash
gem install bundler
bundle install
bundle exec jekyll serve
```

## Clone the repository and configure the stack

With uv and Docker Engine in place, start by cloning the repository and
copying the tracked environment template to a local, gitignored `.env` file.
This two-step pattern — a tracked `.env.example` with safe, documented
defaults, and a gitignored `.env` you actually run against — is how the
project keeps image tags and credentials both reproducible and out of
version control:

```bash
git clone https://github.com/patterncatalyst/modernizing-enterprise-applications-python.git
cd modernizing-enterprise-applications-python
cp .env.example .env
```

Open `.env` and skim it before moving on; it is short and every line is
commented. It pins the image tags — Postgres (`18.6-alpine`), single-broker
KRaft-mode Kafka (`4.3.1`), and the database name, user, and password this
local stack uses — along with the host ports. None of these values are
secret (the password is literally `monolith`), but pinning them in one
tracked file rather than hard-coding them into `compose.yaml` itself is what
lets a later chapter bump an image tag in one place and have every script,
every CI job, and every service's own configuration pick the change up
without a search-and-replace across the repository. The file's own header
also records when each tag was last re-verified upstream with
`skopeo list-tags`, so a stale pin is a dated, checkable fact rather than a
guess.

## Bring up the infrastructure stack

The project's local infrastructure — Postgres, single-broker KRaft-mode Kafka
(no ZooKeeper, needed from the event-driven extractions in Part 6 onward),
and the Grafana LGTM observability bundle (Loki, Grafana, Tempo, Mimir, and
an embedded OpenTelemetry Collector) — is defined once in the root
`compose.yaml` and brought up with a single helper script:

```bash
scripts/stack-up.sh
```

Read what that script actually does rather than treating it as a black box,
because the mechanics matter the first time something does not come up
cleanly. It resolves its own location so it works regardless of your current
directory, copies `.env.example` to `.env` for you if you skipped the step
above, picks `docker compose` if it is available and falls back to
`podman compose` otherwise, then runs `compose --env-file .env up -d` and
polls `compose ps` in a loop until every service's healthcheck reports
`healthy` (or sixty retries elapse, in which case it prints whatever state it
last saw and gets out of your way rather than hanging forever). When the
script finishes, it prints the addresses you will use for the rest of this
chapter:

```text
Postgres:   localhost:5432 (see .env for db/user/password)
Kafka:      localhost:9092 (host) / kafka:9094 (compose network) — not used by the monolith yet
Grafana:    http://localhost:3000 — not used by the monolith yet
Prometheus: http://localhost:19090 (host 19090; Cockpit owns 9090 on Fedora Server and RHEL)
```

Only Postgres matters for what follows in this chapter — Kafka and the LGTM
bundle exist in the same `compose.yaml` so later chapters have a broker and
an observability backend to target without a second infrastructure change,
but the monolith you are about to run does not touch either one yet. When you
are done for the session, tear the stack down with the matching script,
which by default preserves the named Postgres and Kafka volumes so your seed
data and topics survive a restart:

```bash
scripts/stack-down.sh        # stop containers, keep volumes
scripts/stack-down.sh -v     # stop containers, wipe volumes (fresh state)
```

## Build and run the monolith

With Postgres up, install the monolith's dependencies and run its database
migrations and seed command with uv, from inside its own project directory:

```bash
cd examples/00-monolith
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
```

The `seed` management command is this project's own, not a Django default —
it loads two customers, three inventory items, one confirmed order, and two
reviews, giving every endpoint something real to return the first time you
call it rather than an empty table. By default the monolith expects
`DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith`, which
matches the stack `scripts/stack-up.sh` just brought up; override it via
`.env` or the environment if you are pointing at a different Postgres
instance. With migrations applied and seed data loaded, start the
development server:

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

The monolith binds to port **8000**. A
`GET http://localhost:8000/api/reviews?sku=SKU-WIDGET-001` against the
freshly seeded database should return a non-empty JSON array; if it does, the
monolith is up and seeded correctly, and you have just confirmed the one
piece of running code this chapter asked you to prove.

## Run the equivalence suite against the monolith

With the monolith reachable on port 8000, run the same check every extraction
chapter in this book runs before it trusts a change: the
**behavior-equivalence suite**, a Newman collection captured once against the
running monolith and re-run, completely unmodified, against whatever backend
you point it at later. Install Newman if you have not already
(`npm install -g newman`), then run the collection directly against the
monolith, parameterized entirely by the environment file that supplies its
`baseUrl`:

```bash
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json
```

A clean run reports every assertion passing — smoke checks, a full
happy-path checkout, an out-of-stock rejection, and the review context's own
read/write contract. If any assertion fails, the output names exactly which
request and which expectation broke, which is the entire point of
externalizing this check into a re-runnable artifact instead of a "looks
right to me" judgment call: a failing run here, right now, with nothing else
going on, is the cheapest possible place to catch a misconfigured port, an
un-migrated table, or a server that silently failed to start, before you
carry that mistake into a chapter that assumes a working baseline.

## Finding your way around the repository

Before moving on, it is worth a quick orientation pass over the top-level
directories you will keep returning to. None of this needs to be memorized —
you will have walked every one of these paths by the time you reach Part 3 —
but knowing roughly what lives where now will save you a few `find` commands
later.

| Directory | What's in it |
|---|---|
| `examples/` | One runnable project per hands-on chapter — the monolith, the strangler proxy, each extracted service — committed in full, not as snippets. |
| `tooling/` | Shared developer tooling that spans examples, starting with `tooling/newman/` — the behavior-equivalence suite's collection and environments. |
| `demos/` | Thin, documented wrapper scripts that drive the examples for a reader, rather than raw tool invocations buried in prose. |
| `infra/` | Configuration consumed by `compose.yaml` — the OpenTelemetry Collector config, Grafana datasource provisioning, and database init scripts. |
| `scripts/` | Project-level automation — `stack-up.sh` / `stack-down.sh` for the local infrastructure, plus the diagram generator used across chapters. |
| `_docs/` | The chapters themselves — this file is `_docs/01-prerequisites.md`. |
| `_plans/` | The project's own ADLC ledger — `decisions.md`, `build-plan.md`, and `reconciliation.md` — introduced properly as a reader-facing concept in the next chapter. |

## Ports at a glance

You will see this address recur across most of Part 3, so it is worth
having it in one place rather than re-deriving it from `compose.yaml` and the
monolith's own settings every time. Later parts introduce one new port per
extracted service as each one is built; this chapter only asks you to run
the first.

| Service | Port | Source |
|---|---|---|
| Monolith (Django) | 8000 | `examples/00-monolith` |
| Postgres | 5432 | `compose.yaml`, `.env.example` |
| Kafka | 9092 (host) / 9094 (compose network) | `compose.yaml`, `.env.example` — not used until Part 6 |
| Grafana (LGTM bundle) | 3000 | `compose.yaml` — OTLP on 4317/4318, Prometheus on host **19090** (container 9090 — Cockpit owns host 9090 on Fedora Server and RHEL) — not used until Part 9 |

## What you learned

- uv is the one required toolchain piece for every Python project in this
  book: it installs the pinned Python 3.14 interpreter, builds each
  project's own virtual environment from its own lockfile, and runs commands
  inside it without a separate activation step.
- Django 5.2 LTS and DRF power the monolith; FastAPI powers every extracted
  service from Part 5 onward — each pinned per-project and installed by
  `uv sync`, never by a system-wide `pip install`.
- Docker Engine with the `docker compose` plugin is docker-primary and
  podman-compatible: `compose.yaml` uses only the plain Compose
  Specification, so either engine's compose plugin parses the same file.
- `scripts/stack-up.sh` brings up Postgres, Kafka, and the Grafana LGTM
  bundle from one `compose.yaml`, gated by real healthchecks rather than a
  fixed sleep — though only Postgres matters for the monolith you just ran.
- The behavior-equivalence suite — one Newman collection, parameterized
  entirely by its environment file — is the same check every later
  extraction chapter runs; getting it green here means you are starting
  Part 3 from a verified baseline, not a hopeful one.

The next chapter, **"The Project Ledger,"** introduces the three documents
this project uses as its own memory across the chapters you are about to
read — `decisions.md`, `build-plan.md`, and `reconciliation.md` — and shows
you how to keep the same kind of ledger for your own migration.

---
*Verification status: <span class="status status--verified">verified</span>. Conceptual chapter — the toolchain and commands it describes are reproducible from the project's own tracked files (`compose.yaml`, `.env.example`, `scripts/stack-up.sh`/`stack-down.sh`, `examples/00-monolith/README.md`); bring the stack up and confirm the Newman run above is green on a fresh clone before continuing to Part 3.*
