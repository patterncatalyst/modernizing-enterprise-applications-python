# inventory-service -- Cutover Notes (ch.19, DRQ-039/DRQ-040/DRQ-042)

This service has **two independent cutover dimensions** -- don't conflate
them. Flipping one does not require flipping the other, and in a real
rollout they land at different times.

## Dimension 1: the synchronous read/write surfaces (strangler proxy)

`../01-strangler-proxy` is the single front door for both the REST read
surface and (indirectly, via the monolith's own order-checkout code path)
the gRPC mutating surface:

- **REST**: `STRANGLER_INVENTORY_ENABLED=true` routes `GET /api/inventory*`
  to this service instead of the monolith's Django view. Pure read traffic,
  safe to flip independently and roll back instantly (flip the flag back) if
  this service's read path misbehaves.
- **gRPC**: once the monolith's own checkout code is refactored to call this
  service's `Reserve`/`Release`/`CheckStock`/`GetStock` RPCs instead of its
  in-process pessimistic-lock derived query (a monolith-side code change, not
  a strangler-proxy flag -- gRPC calls are service-to-service, not
  browser/client-facing HTTP the proxy intercepts), the monolith's checkout
  transaction boundary changes shape: a decrement that used to be part of
  the SAME local transaction as the order/payment/shipping writes is now a
  remote call with its own commit, which is why `Release`'s compensating
  re-increment exists at all (DRQ-042) -- see `README.md`'s "Release: an
  honest, documented limitation" section. **This cutover step requires the
  monolith-side checkout refactor to land first**; this service's gRPC
  server can be live and correct long before that refactor calls it.

Rollback for both: flip the relevant flag/call-site back. This service's own
`inventory` schema is NEVER the thing that gets rolled back -- it keeps
accepting `Reserve`/`Release` calls from whichever caller currently owns
checkout, so a rollback does not lose or corrupt reservations already made
through this service.

## Dimension 2: retiring the transition-only CDC consumer

`app/cdc_consumer.py` (flag-gated `INVENTORY_CDC_ENABLED`, default `false`)
exists ONLY to keep this service's `inventory.inventory_items` copy
synchronized with the monolith's `public.inventory_items` table **during the
window where the monolith is still partially the system of record** -- e.g.
if an operator ever needs to run this service's read surface strangled
(Dimension 1 flipped) while the monolith's checkout code has NOT yet been
refactored to call this service's gRPC `Reserve` (Dimension 1's gRPC half
not yet flipped), meaning the monolith's own writes to its table would
otherwise silently diverge from what this service serves on `GET
/api/inventory`.

### Retire runbook

Once BOTH of the following are true, the CDC consumer has no further job and
should be disabled permanently:

1. The monolith's checkout code calls this service's gRPC `Reserve`/`Release`
   exclusively (Dimension 1's gRPC half is flipped) -- this service's own
   `inventory.inventory_items` table is now the ONLY place stock mutations
   land, so there is nothing left on the monolith's side to stream from.
2. The monolith's `public.inventory_items` table (and the Django
   `inventory` app around it) is decommissioned, matching this project's
   strangler end-state posture for every other extracted context.

Steps:

1. Confirm no `op=c`/`op=u`/`op=d` events have arrived on
   `meap.public.inventory_items` for a full observation window (the
   monolith's table should be write-silent once step 1 above has landed) --
   `kcat -C -b <bootstrap> -t meap.public.inventory_items -o end -e` draining
   nothing new confirms this.
2. Set `INVENTORY_CDC_ENABLED=false` (the default -- this is a no-op if it
   was already off) and redeploy. There is no data migration step: this
   service's `inventory.inventory_items` table already holds the current,
   correct state (either backfilled by the consumer during the transition
   window, or seeded independently by `migrations/versions/0002_seed_inventory.py`
   for environments that never ran with CDC enabled at all, e.g. this
   project's default CI/dev posture).
3. Decommission the Debezium Postgres connector
   (`infra/debezium/inventory-connector.json`, if deployed) and the
   `meap.public.inventory_items` topic.
4. Remove `app/cdc_consumer.py`'s dependency footprint (`aiokafka`) from
   `pyproject.toml` in a follow-up change once this retire runbook has
   actually been executed against a real deployment -- NOT speculatively
   ahead of that, since a reachable rollback path during the transition
   window is the whole point of keeping it flag-gated rather than deleting
   it the moment the gRPC server goes live.

### Why this is flag-gated OFF by default, not flag-gated ON

This project's CI and local-dev posture never runs the monolith and this
service in a partial-cutover state long enough to need CDC sync -- the build
plan seeds this service's own schema directly
(`migrations/versions/0002_seed_inventory.py`) and exercises the gRPC/REST
surfaces against that seed. CDC is a REAL OPERATIONAL CONCERN for a staged
production rollout, not a testing concern, which is why it ships
disabled-by-default and untouched by `uv run pytest`.
