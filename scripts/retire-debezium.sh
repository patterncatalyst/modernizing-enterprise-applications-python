#!/usr/bin/env bash
# scripts/retire-debezium.sh — retire (delete) the Debezium Postgres CDC
# connector and drop its replication slot + publication now that the
# monolith no longer writes `inventory_items` (post-cutover, r04 inventory
# extraction). See infra/debezium/README.md.
#
# CDC here was transition-only infrastructure: it initial-snapshot
# backfilled, then kept current, examples/04-inventory-service's view of
# the monolith's `public.inventory_items` table DURING the cutover window.
# examples/04-inventory-service reaches its end state via its own Alembic
# migration + own seed, not via a running Debezium consumer, so retiring
# this connector changes nothing about the inventory service's
# correctness. Leaving its replication slot registered would retain WAL on
# meap-postgres indefinitely (disk-fill risk) for no benefit.
#
# Idempotent: safe to re-run. DELETE on a connector that is already gone
# returns 404, which this script treats as already-retired (not a failure);
# pg_drop_replication_slot/DROP PUBLICATION are guarded with existence
# checks so a second run is a no-op.
#
# Usage:
#   scripts/retire-debezium.sh              # delete connector + drop slot/publication
#   scripts/retire-debezium.sh --status      # just report current state (no changes)
#
# Requires: curl, jq, docker (meap-postgres, meap-connect must be reachable).
# Does NOT touch the compose stack itself — no `compose down`, no `-v`, no
# removal of meap-postgres/meap-connect/meap-kafka. Only this one connector
# + its slot/publication are retired.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV_FILE=".env"
[ -f "$ENV_FILE" ] || ENV_FILE=".env.example"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

CONNECT_URL="http://localhost:${CONNECT_HOST_PORT:-8086}"
CONFIG_TEMPLATE="infra/debezium/inventory-connector.json"
CONNECTOR_NAME="$(jq -r '.name' "$CONFIG_TEMPLATE")"
SLOT_NAME="meap_inventory_slot"
PUBLICATION_NAME="meap_inventory_publication"

report_status() {
  echo "=== Connector ==="
  if curl -sf "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/status" 2>/dev/null; then
    echo
  else
    echo "(not registered — ${CONNECTOR_NAME} absent from ${CONNECT_URL}/connectors)"
  fi
  echo
  echo "=== Replication slot (${SLOT_NAME}) ==="
  docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT slot_name, active, wal_status FROM pg_replication_slots WHERE slot_name = '${SLOT_NAME}';"
  echo "=== Publication (${PUBLICATION_NAME}) ==="
  docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT pubname FROM pg_publication WHERE pubname = '${PUBLICATION_NAME}';"
}

if [ "${1:-}" = "--status" ]; then
  report_status
  exit 0
fi

echo "Deleting connector '${CONNECTOR_NAME}' from ${CONNECT_URL} (idempotent) ..."
http_code=$(curl -s -o /tmp/meap-inventory-connector.delete.json -w '%{http_code}' \
  -X DELETE "${CONNECT_URL}/connectors/${CONNECTOR_NAME}")

case "$http_code" in
  204)
    echo "Connector deleted (HTTP 204)."
    ;;
  404)
    echo "Connector already absent (HTTP 404) — nothing to delete."
    ;;
  *)
    echo "Unexpected response deleting connector (HTTP ${http_code}):" >&2
    cat /tmp/meap-inventory-connector.delete.json >&2
    exit 1
    ;;
esac
rm -f /tmp/meap-inventory-connector.delete.json

# Deleting the connector does NOT automatically drop the replication slot
# or publication (infra/debezium/README.md, "Replication-slot lifecycle") —
# an un-drained slot retains WAL on meap-postgres indefinitely. Drop both
# explicitly; both statements are guarded so a re-run is a no-op.
#
# Immediately after DELETE, Postgres may still show the slot "active" for a
# moment (Connect's replication connection takes a beat to close) --
# pg_drop_replication_slot fails loudly on an active slot, so retry briefly
# instead of racing it.
echo "Dropping replication slot '${SLOT_NAME}' on meap-postgres (if present) ..."
slot_dropped=false
for attempt in $(seq 1 10); do
  if docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c "
DO \$\$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '${SLOT_NAME}') THEN
    PERFORM pg_drop_replication_slot('${SLOT_NAME}');
  END IF;
END
\$\$;
" 2>/tmp/meap-slot-drop.err; then
    slot_dropped=true
    break
  fi
  if ! grep -q "is active for PID" /tmp/meap-slot-drop.err; then
    cat /tmp/meap-slot-drop.err >&2
    rm -f /tmp/meap-slot-drop.err
    exit 1
  fi
  echo "  slot still active (attempt ${attempt}/10) -- waiting for Connect's replication connection to close ..."
  sleep 2
done
rm -f /tmp/meap-slot-drop.err
if [ "$slot_dropped" != true ]; then
  echo "Slot '${SLOT_NAME}' did not become droppable within the timeout." >&2
  exit 1
fi

echo "Dropping publication '${PUBLICATION_NAME}' on meap-postgres (if present) ..."
docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "DROP PUBLICATION IF EXISTS ${PUBLICATION_NAME};"

echo
echo "Retirement complete. Current state:"
report_status
