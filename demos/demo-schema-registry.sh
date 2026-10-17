#!/usr/bin/env bash
# demos/demo-schema-registry.sh — ch.28 (DRQ-038 follow-up, DRQ-076/DRQ-033)
# Avro + Apicurio Schema Registry DEMONSTRATOR proof: brings up a throwaway
# Kafka + Apicurio pair, runs examples/09-schema-registry-demo's own CLI
# progression (register/resolve the v1 Avro schema -> round-trip
# produce/consume -> attach a BACKWARD compatibility rule -> v2 ACCEPTED ->
# v3 REJECTED) against them, then tears everything down.
#
# Pure-Python (DRQ-033): fastavro + aiokafka + a plain httpx client against
# Apicurio's v3 REST API — NOT confluent-kafka, NOT a Java/Quarkus serde.
# ADDITIVE ONLY: this demo never touches the live JSON event flows
# (examples/00-monolith through examples/07-order-service, DRQ-036/038) — it
# publishes to its own order.events.avro.demo topic and registers against
# its own order-placed-value Apicurio artifact.
#
# Mirrors demos/demo-final-topology.sh's style (Docker-primary, resolve
# paths off this script's own location, throwaway containers, self-contained
# teardown on exit/error/Ctrl-C via `trap ... EXIT`) but needs no Postgres —
# this module owns no database of its own.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

KAFKA_IMAGE_TAG="${KAFKA_IMAGE_TAG:-4.3.1}"
APICURIO_IMAGE_TAG="${APICURIO_IMAGE_TAG:-3.3.3}"
KAFKA_CLUSTER_ID="${KAFKA_CLUSTER_ID:-MkU3OEVBNTcwNTJENDM2Qk}"
APICURIO_HOST_PORT="${APICURIO_HOST_PORT:-8095}"

KAFKA_CONTAINER="meap-demo-schema-registry-kafka"
APICURIO_CONTAINER="meap-demo-schema-registry-apicurio"
LOG_DIR="$(mktemp -d /tmp/mea-schema-registry-demo.XXXXXX)"

if command -v docker >/dev/null 2>&1; then
  ENGINE=docker
elif command -v podman >/dev/null 2>&1; then
  ENGINE=podman
else
  echo "Neither docker nor podman is available." >&2
  exit 1
fi

log()  { echo "[demo-schema-registry] $*"; }

cleanup() {
  log "Tearing down..."
  "$ENGINE" rm -f "$KAFKA_CONTAINER" "$APICURIO_CONTAINER" >/dev/null 2>&1 || true
  log "Host left clean. Logs were kept at $LOG_DIR (delete manually if not needed)."
}
trap cleanup EXIT

wait_for_http() {
  local url="$1" name="$2" tries=60
  until curl -sf -o /dev/null "$url"; do
    tries=$((tries - 1))
    if [ "$tries" -le 0 ]; then
      echo "Timed out waiting for $name ($url)" >&2
      return 1
    fi
    sleep 1
  done
}

log "Log directory: $LOG_DIR"

# ── Throwaway Kafka + Apicurio (examples/09 ONLY — see compose.yaml's
# apicurio service header note) ─────────────────────────────────────────
log "Starting throwaway Kafka ($KAFKA_IMAGE_TAG) + Apicurio ($APICURIO_IMAGE_TAG)..."
"$ENGINE" rm -f "$KAFKA_CONTAINER" "$APICURIO_CONTAINER" >/dev/null 2>&1 || true

"$ENGINE" run -d --name "$KAFKA_CONTAINER" -p 9092:9092 \
  -e KAFKA_NODE_ID=1 \
  -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT \
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  -e CLUSTER_ID="$KAFKA_CLUSTER_ID" \
  "apache/kafka:${KAFKA_IMAGE_TAG}" >/dev/null

"$ENGINE" run -d --name "$APICURIO_CONTAINER" -p "${APICURIO_HOST_PORT}:8080" \
  -e APICURIO_STORAGE_KIND=sql \
  -e APICURIO_STORAGE_SQL_KIND=h2 \
  "quay.io/apicurio/apicurio-registry:${APICURIO_IMAGE_TAG}" >/dev/null

log "Waiting for Kafka..."
sleep 10  # KRaft single-node boot; cheaper than scripting a broker-api-versions probe for a demo script

log "Waiting for Apicurio..."
wait_for_http "http://localhost:${APICURIO_HOST_PORT}/apis/registry/v3/system/info" "Apicurio"

export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export REGISTRY_URL="http://localhost:${APICURIO_HOST_PORT}/apis/registry/v3"

# ── Sync the demo module (idempotent if .venv already exists) ───────────
log "Syncing examples/09-schema-registry-demo..."
( cd examples/09-schema-registry-demo && uv sync --group dev ) >"$LOG_DIR/uv-sync.log" 2>&1

# ── Run the progression: register/resolve v1 -> round trip -> v2 accept ->
# v3 reject (app/demo_cli.py) ────────────────────────────────────────────
log "Running the schema-registry-demo CLI progression..."
( cd examples/09-schema-registry-demo && uv run python -m app.demo_cli )

log "ALL CHECKS PASSED."
