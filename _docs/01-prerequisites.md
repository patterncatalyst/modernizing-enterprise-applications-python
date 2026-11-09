---
title: "Prerequisites & the Toolchain"
order: 1
part: "Setting Up"
description: "uv, Python 3.14, Django and FastAPI, Docker Engine and the compose observability stack, and a verify-your-setup gate."
---

Every claim from here on is backed by code in the repository. The goal here is to get that code building and running on your machine: install the toolchain, bring up the infrastructure stack, start `examples/00-monolith/`, and confirm it with the equivalence suite. There's no new example directory.

{% include excalidraw.html file="toolchain-and-repo-layout" alt="The local toolchain split into the two pieces every chapter needs (uv, managing the Python 3.14 interpreter, the virtual environment, and the lockfile; ruff and pytest as the dev-dependency group every service pulls in) and two ghosted later-scoped tools (grpcio-tools and a proto-drift check, both scoped to the gRPC seam), alongside the compose stack's live services (Postgres, single-broker KRaft-mode Kafka, the Grafana LGTM bundle) and its two ghosted later services (Debezium Connect, the Apicurio schema registry), both landing in the same repository tree: examples/, tooling/, demos/, infra/, scripts/, and _docs/." caption="Figure 1.1: The local toolchain and the repository layout it builds, runs, and stands up." %}

## What you need

Only uv and Docker Engine are required for everything that follows. Newman is needed from the first extraction on. The rest is scoped to later parts, so don't install it yet.

### uv and Python 3.14

Every Python example targets Python 3.14, and every `pyproject.toml` pins `requires-python = ">=3.14"` instead of trusting whatever is on your `PATH`. **uv** installs the pinned interpreter, creates the virtual environment, locks dependencies into a committed `uv.lock` and runs commands inside the environment without activation:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
uv --version
```

Inside any project directory, `uv sync` builds a `.venv` from that project's `pyproject.toml` and `uv.lock`, transitive dependencies included, and `uv run <cmd>` runs in it:

```bash
cd examples/00-monolith
uv sync --group dev
uv run python --version
```

### Django, DRF and FastAPI

The monolith pins `django==5.2.18` (a 5.2 LTS patch release) and `djangorestframework==3.18.3`. Each extracted service pins its own FastAPI version. `uv sync` is the only install step; never run `pip install django`. The monolith and every service get their own `.venv`, because each has its own lockfile and the project uses no uv workspace: there's one Python package per `examples/` directory, so a workspace root would have nothing to share.

### Docker Engine and the compose plugin

The local stack (Postgres, Kafka, the Grafana LGTM observability bundle, plus Debezium Connect and the Apicurio schema registry when later chapters need them) runs on Docker Engine, the `docker-ce` packages from Docker's repository, on the `default` docker context and `/var/run/docker.sock`. `compose.yaml` uses only the plain Compose Specification, so `podman compose` parses the same file. Compose is the v2 plugin, `docker compose` with a space, not the legacy `docker-compose` binary. The project is written and verified on Fedora and RHEL hosts, bare metal or VM.

Fedora (dnf5) is shown. On RHEL, add the repository with `sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo`:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"        # then log out and back in
```

Remove `podman-docker` first if it's installed; it shadows the `docker` command. Then confirm the engine, the context and the plugin:

{% raw %}
```bash
docker context show        # default
docker version --format '{{.Server.Version}}'
docker compose version
```
{% endraw %}

On the default socket, test suites that start disposable containers find the engine with no `DOCKER_HOST`.

### Node.js and Newman

The behavior-equivalence suite is a Postman collection run by **Newman**, which runs on Node.js. No JavaScript application code appears anywhere. A recent LTS release (Node 22 or newer) is enough:

```bash
sudo dnf install -y nodejs npm
npm install -g newman
newman --version
```

### Git, and tools for later

Install Git to clone the repository and read the commits the ledger rows describe. Two tools are deferred: **`grpcio-tools`** generates the stubs for the inventory extraction's gRPC seam, and **minikube** hosts the finished system for the deployment and mesh chapters. Neither is part of the setup check.

Ruby and Bundler are needed only to build this Jekyll site locally; reading it needs a browser. The root `Gemfile` pins the gem versions GitHub Pages runs:

```bash
gem install bundler
bundle install
bundle exec jekyll serve
```

## Clone the repository and configure the stack

Clone the repository and copy the tracked template to a gitignored `.env`. The tracked `.env.example` holds safe, documented defaults; the `.env` is what you run against:

```bash
git clone https://github.com/patterncatalyst/modernizing-enterprise-applications-python.git
cd modernizing-enterprise-applications-python
cp .env.example .env
```

The file pins the image tags (Postgres `18.6-alpine`, single-broker KRaft-mode Kafka `4.3.1`), the database name, user and password (`monolith`, not a secret) and the host ports. One tracked file means a later change to an image tag reaches every script, CI job and service configuration without a search-and-replace. A header records when each tag was last checked upstream with `skopeo list-tags`, so a stale pin is a dated, checkable fact.

## Bring up the infrastructure stack

The root `compose.yaml` defines Postgres, single-broker KRaft-mode Kafka (no ZooKeeper; used from the event-driven extractions on) and the Grafana LGTM bundle (Loki, Grafana, Tempo, Mimir and an embedded OpenTelemetry Collector). One script starts it:

```bash
scripts/stack-up.sh
```

The script works from any directory, copies `.env.example` to `.env` if you skipped that step, uses `docker compose` and falls back to `podman compose`, runs `compose --env-file .env up -d`, and polls `compose ps` until every healthcheck reports `healthy` or sixty retries pass, then prints what it last saw instead of hanging. On success it prints the addresses:

```text
Postgres:   localhost:5432 (see .env for db/user/password)
Kafka:      localhost:9092 (host) / kafka:9094 (compose network) (not used by the monolith yet)
Grafana:    http://localhost:3000 (not used by the monolith yet)
Prometheus: http://localhost:19090 (host 19090; Cockpit owns 9090) (not used by the monolith yet)
```

Only Postgres matters for the monolith. Kafka and the LGTM bundle are there so later chapters need no second infrastructure change. Tear down with the matching script, which keeps the named Postgres and Kafka volumes by default:

```bash
scripts/stack-down.sh        # stop containers, keep volumes
scripts/stack-down.sh -v     # stop containers, wipe volumes (fresh state)
```

## Build, run, observe

Install the monolith's dependencies, migrate and seed from its own directory:

```bash
cd examples/00-monolith
uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed
uv run python manage.py runserver 0.0.0.0:8000
```

`seed` is a project command, not a Django default. It loads two customers, three inventory items, one confirmed order and two reviews, so every endpoint has something to return. The monolith reads `DATABASE_URL=postgresql://monolith:monolith@localhost:5432/monolith` by default, which matches the stack; override it in `.env` or the environment for a different Postgres.

The monolith binds to port **8000**. `GET http://localhost:8000/api/reviews?sku=SKU-WIDGET-001` returns a non-empty JSON array when it's up and seeded.

Then run the equivalence suite, the check every extraction runs before trusting a change. It's a Newman collection captured once against the monolith and re-run unmodified against whatever backend you point it at; its `baseUrl` comes entirely from the environment file:

```bash
newman run tooling/newman/mea.postman_collection.json \
    -e tooling/newman/local.postman_environment.json
```

A clean run passes every assertion: smoke checks, a full happy-path checkout, an out-of-stock rejection and the review context's read/write contract. A failure names the request and the expectation that broke. Failing here, with nothing else going on, is the cheapest place to catch a wrong port, an unmigrated table or a server that never started.

## Repository layout

| Directory | What's in it |
|---|---|
| `examples/` | One runnable project per hands-on chapter (the monolith, the strangler proxy, each extracted service), committed in full, not as snippets |
| `tooling/` | Developer tooling shared across examples, starting with `tooling/newman/`: the equivalence suite's collection and environments |
| `demos/` | Thin, documented wrapper scripts that drive the examples |
| `infra/` | Configuration consumed by `compose.yaml`: the OpenTelemetry Collector config, Grafana datasource provisioning, database init scripts |
| `scripts/` | Project automation: `stack-up.sh` and `stack-down.sh`, plus the diagram generator |
| `_docs/` | The chapters, for example `_docs/01-prerequisites.md` |

## Ports

Each extracted service adds one port as it's built.

| Service | Port | Source |
|---|---|---|
| Monolith (Django) | 8000 | `examples/00-monolith` |
| Postgres | 5432 | `compose.yaml`, `.env.example` |
| Kafka | 9092 (host) / 9094 (compose network) | `compose.yaml`, `.env.example`; used from the event-driven extractions on |
| Grafana (LGTM bundle) | 3000 | `compose.yaml`; OTLP on 4317/4318, Prometheus on host **19090** (container 9090; Cockpit owns host 9090 on Fedora Server and RHEL); used from the tracing chapters on |

The next chapter introduces the project ledger, the records this project keeps as memory across chapters and a template for your own migration.
