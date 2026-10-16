# Debezium CDC — Kafka Connect + Postgres connector

> **Transition-only. Retire after cutover.** This connector exists for ONE
> purpose: a one-time initial-snapshot backfill (plus streaming sync while
> the extraction is in flight) of the monolith's shared `public.inventory_items`
> table into `examples/04-inventory-service`'s OWN `inventory` schema, during
> the window between "the inventory service exists" and "the monolith no
> longer writes `inventory_items` at all" (cutover). It is **not** part of
> the CI equivalence gate, and the running system must **not** depend on it
> once cutover completes — `scripts/retire-debezium.sh` deletes the
> connector and drops its replication slot/publication so WAL isn't
> retained indefinitely on `meap-postgres`. See "Retiring the connector"
> below. Re-registering it later (e.g. to replay the teaching demo against
> a fresh stack) is always safe — see "Registering the connector".

Python sibling of `~/Dev/modernizing-enterprise-applications/infra/debezium/`
(r05/ch.19 there; r04 here — this repo folds the inventory extraction into
a single iteration). Same tool decision, container names/ports adapted to
this repo's `meap-` prefix and `monolith`/`monolith`/`monolith` dev
credentials.

**Tool decision:** a standalone **Debezium Postgres connector** running on
Kafka Connect — not Debezium Embedded. A visible, inspectable connector
container is the clearer teaching artifact for log-tailing CDC, and the
stack already runs Kafka.

## Topology

```
meap-postgres (wal_level=logical)
      │  pgoutput, replication slot "meap_inventory_slot"
      ▼
meap-connect (Kafka Connect, quay.io/debezium/connect image)
      │  connector "meap-inventory-connector"
      ▼
meap-kafka topic "meap.public.inventory_items"
```

## Postgres: logical replication

`compose.yaml`'s `postgres` service starts with:

```
command: ["postgres", "-c", "wal_level=logical", "-c", "max_replication_slots=4", "-c", "max_wal_senders=4"]
```

This requires a Postgres **restart** to take effect (handled automatically
by `docker compose up -d`); the `postgres-data` named volume persists, so
no existing data is lost. The bootstrap superuser (`POSTGRES_USER` from
`.env`) already has `REPLICATION` privilege, so no separate grant/init
script is needed for a single-connector dev stack.

Anything else talking to this Postgres (the monolith's migrations, the
other extracted services' own schemas) is unaffected by `wal_level=logical`
— it only changes what's recorded in the WAL, not SQL semantics. The one
shared-infra effect: WAL volume grows slightly because logical decoding
keeps more information than the default `replica` level.

## Kafka Connect

The `connect` service (`compose.yaml`) runs `quay.io/debezium/connect`
(tag pinned in `.env`/`.env.example` as `CONNECT_IMAGE_TAG`) in distributed
mode, using Kafka Connect's own internal topics (`meap-connect-configs`,
`meap-connect-offsets`, `meap-connect-status`, replication factor 1 —
matches this single-broker stack).

**REST API port:** the container always binds `:8083` internally, but the
**host-side** port mapping is `${CONNECT_HOST_PORT:-8086}` (default host
port **8086**, not 8083) — `examples/03-notification-service`'s FastAPI
HTTP listener binds `localhost:8083` when it's running, and the two would
otherwise clash. Inside the compose network, other containers still reach
Connect at `http://connect:8083`.

Health check: `GET http://localhost:8083/connectors` inside the container
(curl is present in the `debezium/connect` image).

## The connector config: `inventory-connector.json`

`infra/debezium/inventory-connector.json` is a **template** —
`${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}` are
placeholders substituted from `.env` at registration time
(`scripts/register-debezium.sh`), so no credential is hardcoded in a
tracked file (secrets hygiene, OWASP/CIS) — even though this stack's dev
defaults for all three happen to be the literal string `monolith`.

Highlights:

| Field | Value | Why |
|---|---|---|
| `table.include.list` | `public.inventory_items` | only the table this extraction needs |
| `topic.prefix` | `meap` | resulting topic: `meap.public.inventory_items` |
| `plugin.name` | `pgoutput` | built into Postgres 10+, no extra decoder plugin to install |
| `slot.name` | `meap_inventory_slot` | the replication slot Debezium owns |
| `publication.name` | `meap_inventory_publication` | auto-created (`publication.autocreate.mode=filtered`), scoped to the include list |
| `snapshot.mode` | `initial` | snapshot existing rows once, then stream |
| `key.converter.schemas.enable` / `value.converter.schemas.enable` | `false` | schema-less JSON payloads — easier to grep in `scripts/verify-debezium.sh` and to read by hand |

**Why no `schema.history.*` settings:** that mechanism exists for
connectors that need to replay DDL history to decode row changes against
an evolving table shape (MySQL's binlog, Oracle, SQL Server). The Postgres
connector's `pgoutput` plugin decodes rows using Postgres's own replication
protocol and the connector's live JDBC connection to the database — it has
no separate DDL-history topic to configure.

**`REPLICA IDENTITY FULL`:** Postgres's default `REPLICA IDENTITY`
(`DEFAULT`) only includes primary-key columns in the WAL's "old row" image,
so Debezium's `before` field on UPDATE/DELETE events would otherwise be
`null` except for `id`. `scripts/register-debezium.sh` runs
`ALTER TABLE public.inventory_items REPLICA IDENTITY FULL;` against
`meap-postgres` before registering the connector, so every UPDATE/DELETE
event carries a complete `before` row alongside `after`. This is a
runtime/session-level Postgres setting (not a schema/DDL change tracked by
the monolith's Django migrations) and is idempotent to re-run.

## Registering the connector

```bash
scripts/register-debezium.sh            # idempotent create-or-update, waits for RUNNING
scripts/register-debezium.sh --status   # just print GET /connectors/<name>/status
```

The script `PUT`s `infra/debezium/inventory-connector.json`'s `config`
object to `/connectors/meap-inventory-connector/config` — Kafka Connect's
`PUT .../config` endpoint creates the connector if it doesn't exist yet, or
updates it in place otherwise, so re-running is always safe.

## Retiring the connector (post-cutover)

```bash
scripts/retire-debezium.sh            # idempotent: delete connector, drop slot + publication
scripts/retire-debezium.sh --status   # report connector/slot/publication state, no changes
```

`scripts/retire-debezium.sh`:

1. `DELETE /connectors/meap-inventory-connector` against Kafka Connect
   (`:8086`). A `404` (already deleted) is treated as success — the script
   is idempotent.
2. Drops the replication slot `meap_inventory_slot` via
   `pg_drop_replication_slot(...)` against `meap-postgres`, guarded by an
   existence check (`pg_replication_slots`) so a re-run is a no-op.
3. Drops the publication `meap_inventory_publication` via
   `DROP PUBLICATION IF EXISTS`.

This does **not** touch the compose stack itself (`meap-postgres`,
`meap-connect`, `meap-kafka` all keep running) and does **not** revert
`wal_level=logical` on `meap-postgres` (harmless to leave set — see
"Postgres: logical replication" above; it only affects what's recorded in
the WAL, not SQL semantics, and other future connectors could reuse it).

**The inventory service's own data becomes stale-safe, not broken.** Per
the r04 build plan, `examples/04-inventory-service` reaches its end state
by its **own Alembic migration + own seed** of the 3 SKUs — it does not
depend on a running Debezium consumer to function correctly either before
or after cutover. CDC here backfills/syncs data for inspection and teaching
purposes during the transition window only; removing it changes nothing
about the inventory service's correctness.

## Verifying CDC end-to-end

```bash
scripts/verify-debezium.sh [sku]
```

Updates a row in `public.inventory_items` via `meap-postgres`, consumes the
resulting event off `meap.public.inventory_items` via
`kafka-console-consumer`, and asserts the sku appears in the captured
output.

## Replication-slot lifecycle (slot-leak mitigation)

A replication slot that nobody is draining holds WAL segments on disk
indefinitely — if the connector is deleted or dies without the slot being
dropped, WAL will grow unbounded.

- **Normal stop/start** (`docker compose stop`/`start`, `scripts/stack-down.sh`
  without `-v`): the slot persists in the `postgres-data` volume and Debezium
  resumes from its last confirmed LSN. This is expected and fine.
- **Deleting the connector** (`DELETE /connectors/meap-inventory-connector`):
  does **not** automatically drop the replication slot or publication. Drop
  them explicitly afterward:
  ```sql
  SELECT pg_drop_replication_slot('meap_inventory_slot');
  DROP PUBLICATION meap_inventory_publication;
  ```
- **`docker compose down -v`** (wipes `postgres-data`): removes the slot
  along with all Postgres state. Do not run this against a shared/working
  stack without intending a full reset.
- **At cutover: use `scripts/retire-debezium.sh`.** It deletes the
  connector and drops the slot/publication now that the inventory service
  is the sole writer of its own data and CDC is no longer needed — see
  "Retiring the connector" above.

## Known trade-off vs an application-level outbox

CDC reads the WAL directly — no application poll, no table scan, lower
latency than a polling outbox — at the cost of `wal_level=logical` on the
monolith's Postgres, a replication slot + publication to manage, and a
Kafka Connect/Debezium process to operate. Debezium Embedded
(library-in-service) would avoid the extra container but is a less visible
teaching artifact for log-tailing CDC — deliberately not used here.
