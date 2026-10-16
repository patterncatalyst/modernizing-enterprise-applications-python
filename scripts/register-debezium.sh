#!/usr/bin/env bash
# scripts/register-debezium.sh — register (or update) the Debezium Postgres
# CDC connector against the Kafka Connect REST API.
#
# r04 (inventory extraction) — see infra/debezium/README.md. Transition-only
# CDC: this is NOT part of the CI equivalence gate and the running system
# does not depend on it after cutover.
#
# Idempotent: PUT /connectors/<name>/config creates the connector if it does
# not exist yet, or updates its config in place if it does — safe to re-run.
#
# Usage:
#   scripts/register-debezium.sh              # register + wait for RUNNING
#   scripts/register-debezium.sh --status      # just print current status
#
# Requires: curl, jq, envsubst (gettext). The stack must already be up
# (scripts/stack-up.sh) with postgres + kafka + connect healthy.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load env (.env preferred; fall back to the tracked template so the script
# still works before a developer has copied .env.example -> .env).
ENV_FILE=".env"
[ -f "$ENV_FILE" ] || ENV_FILE=".env.example"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

CONNECT_URL="http://localhost:${CONNECT_HOST_PORT:-8086}"
CONFIG_TEMPLATE="infra/debezium/inventory-connector.json"
CONNECTOR_NAME="$(jq -r '.name' "$CONFIG_TEMPLATE")"

status_only=false
if [ "${1:-}" = "--status" ]; then
  status_only=true
fi

print_status() {
  echo "GET ${CONNECT_URL}/connectors/${CONNECTOR_NAME}/status"
  curl -sf "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/status" | jq .
}

if [ "$status_only" = true ]; then
  print_status
  exit 0
fi

echo "Setting REPLICA IDENTITY FULL on public.inventory_items (so Debezium emits a full"
echo "before-image on UPDATE/DELETE, not just the Postgres default primary-key-only"
echo "before-image) ..."
docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "ALTER TABLE public.inventory_items REPLICA IDENTITY FULL;"

echo "Registering connector '${CONNECTOR_NAME}' against ${CONNECT_URL} ..."

# Substitute POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (and any other
# ${VAR} placeholders) from the environment, then POST just the inner
# "config" object (PUT .../config expects the config map, not the envelope).
envsubst < "$CONFIG_TEMPLATE" > /tmp/meap-inventory-connector.rendered.json
jq '.config' /tmp/meap-inventory-connector.rendered.json > /tmp/meap-inventory-connector.config.json
rm -f /tmp/meap-inventory-connector.rendered.json

http_code=$(curl -s -o /tmp/meap-inventory-connector.response.json -w '%{http_code}' \
  -X PUT "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/config" \
  -H 'Content-Type: application/json' \
  -d @/tmp/meap-inventory-connector.config.json)

if [ "$http_code" != "200" ] && [ "$http_code" != "201" ]; then
  echo "Connector registration failed (HTTP ${http_code}):" >&2
  cat /tmp/meap-inventory-connector.response.json >&2
  exit 1
fi

echo "Registration accepted (HTTP ${http_code}). Waiting for RUNNING state..."

for i in $(seq 1 30); do
  state=$(curl -sf "${CONNECT_URL}/connectors/${CONNECTOR_NAME}/status" 2>/dev/null | jq -r '.connector.state' 2>/dev/null || true)
  if [ "$state" = "RUNNING" ]; then
    echo "Connector state: RUNNING"
    print_status
    exit 0
  fi
  sleep 2
done

echo "Connector did not reach RUNNING within the timeout; current status:" >&2
print_status || true
exit 1
