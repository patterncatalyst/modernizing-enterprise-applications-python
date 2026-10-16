#!/usr/bin/env bash
# scripts/verify-debezium.sh — prove Debezium CDC is actually flowing for
# public.inventory_items: UPDATE a row in Postgres, then consume the
# resulting change event off its Kafka CDC topic.
#
# r04 (inventory extraction) DoD check — see infra/debezium/README.md.
#
# Usage:
#   scripts/verify-debezium.sh [sku]        # defaults to the first seeded sku
#
# Requires: the stack up and the connector RUNNING (scripts/register-debezium.sh).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV_FILE=".env"
[ -f "$ENV_FILE" ] || ENV_FILE=".env.example"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

TOPIC_PREFIX="meap"
TABLE="inventory_items"
TOPIC="${TOPIC_PREFIX}.public.${TABLE}"

SKU="${1:-}"
if [ -z "$SKU" ]; then
  SKU=$(docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tA \
    -c "SELECT sku FROM ${TABLE} ORDER BY id LIMIT 1;")
fi
SKU="$(echo "$SKU" | xargs)"

if [ -z "$SKU" ]; then
  echo "No rows found in ${TABLE} to exercise — seed data first." >&2
  exit 1
fi

echo "Starting a background consumer on topic '${TOPIC}' (new messages only)..."
CONSUMER_OUT="$(mktemp)"
docker exec meap-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic "$TOPIC" \
  --timeout-ms 20000 \
  --property print.key=true \
  > "$CONSUMER_OUT" 2>/dev/null &
CONSUMER_PID=$!

# Give the consumer a moment to attach before we mutate the row.
sleep 2

echo "UPDATE-ing sku='${SKU}' in public.${TABLE} via meap-postgres ..."
docker exec meap-postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "UPDATE ${TABLE} SET quantity_on_hand = quantity_on_hand - 1, updated_at = now() WHERE sku = '${SKU}';"

echo "Waiting for the consumer to capture the change event..."
wait "$CONSUMER_PID" || true

echo
echo "=== Captured event(s) from ${TOPIC} ==="
cat "$CONSUMER_OUT"
echo "========================================"

EVENT_COUNT=$(grep -c "\"sku\":\"${SKU}\"" "$CONSUMER_OUT" || true)
if [ "${EVENT_COUNT:-0}" -ge 1 ]; then
  echo "OK: observed a CDC event for sku=${SKU} on ${TOPIC}."
else
  echo "WARNING: no event for sku=${SKU} observed on ${TOPIC} within the timeout." >&2
  rm -f "$CONSUMER_OUT"
  exit 1
fi

rm -f "$CONSUMER_OUT"
