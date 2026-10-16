#!/usr/bin/env bash
# demos/demo-payment-cutover.sh — r05 CUTOVER end-to-end proof: brings up the
# FULL topology (Postgres, Kafka, inventory-service, payment-service,
# review-service, notification-service, the monolith in CHOREOGRAPHED payment
# mode, the strangler proxy with every flag on), runs the full Newman suite
# through the proxy to prove the async checkout cutover, then tears
# everything down.
#
# Mirrors scripts/stack-up.sh's style (Docker-primary, resolve paths off this
# script's own location, throwaway containers) but is self-contained: this
# demo manages its OWN throwaway Postgres/Kafka containers (separate from the
# scripts/stack-up.sh compose stack) and its own service processes, and tears
# every one of them down on exit — including on error or Ctrl-C (`trap ...
# EXIT`) — so re-running this script never requires manual cleanup first.
#
# See tooling/newman/GOLDEN-BASELINE.md's "r05 CUTOVER" section for the full
# recorded run this script reproduces, and examples/05-payment-service/
# CUTOVER.md for the two cutover dimensions (checkout contract + payment
# ownership) this proves.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

POSTGRES_IMAGE_TAG="${POSTGRES_IMAGE_TAG:-18.6-alpine}"
KAFKA_IMAGE_TAG="${KAFKA_IMAGE_TAG:-4.3.1}"
KAFKA_CLUSTER_ID="${KAFKA_CLUSTER_ID:-MkU3OEVBNTcwNTJENDM2Qk}"

PG_CONTAINER="meap-demo-payment-cutover-pg"
KAFKA_CONTAINER="meap-demo-payment-cutover-kafka"
LOG_DIR="$(mktemp -d /tmp/mea-payment-cutover-demo.XXXXXX)"
PIDS=()

if command -v docker >/dev/null 2>&1; then
  ENGINE=docker
elif command -v podman >/dev/null 2>&1; then
  ENGINE=podman
else
  echo "Neither docker nor podman is available." >&2
  exit 1
fi

log()  { echo "[demo-payment-cutover] $*"; }

cleanup() {
  log "Tearing down..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  # Give background asyncio tasks (Kafka consumers/relays) a moment to exit
  # their signal handlers cleanly before the containers under them vanish.
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    wait "$pid" 2>/dev/null || true
  done
  "$ENGINE" rm -f "$PG_CONTAINER" "$KAFKA_CONTAINER" >/dev/null 2>&1 || true
  log "Host left clean. Logs were kept at $LOG_DIR (delete manually if not needed)."
}
trap cleanup EXIT

start_bg() {
  # start_bg <logfile> <cwd> <cmd...> — runs cmd in cwd, backgrounded, with
  # stdout/stderr captured to logfile; records the pid for cleanup().
  local logfile="$1" dir="$2"
  shift 2
  ( cd "$dir" && exec "$@" ) >"$logfile" 2>&1 &
  PIDS+=("$!")
}

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

# ── Throwaway Postgres + Kafka ──────────────────────────────────────────
log "Starting throwaway Postgres ($POSTGRES_IMAGE_TAG) + Kafka ($KAFKA_IMAGE_TAG)..."
"$ENGINE" rm -f "$PG_CONTAINER" "$KAFKA_CONTAINER" >/dev/null 2>&1 || true

"$ENGINE" run -d --name "$PG_CONTAINER" -p 5432:5432 \
  -e POSTGRES_USER=monolith -e POSTGRES_PASSWORD=monolith -e POSTGRES_DB=monolith \
  "postgres:${POSTGRES_IMAGE_TAG}" >/dev/null

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

log "Waiting for Postgres..."
for _ in $(seq 1 30); do
  "$ENGINE" exec "$PG_CONTAINER" pg_isready -U monolith -d monolith >/dev/null 2>&1 && break
  sleep 1
done
log "Waiting for Kafka..."
sleep 10  # KRaft single-node boot; cheaper than scripting a broker-api-versions probe for a demo script

export DATABASE_URL="postgresql://monolith:monolith@localhost:5432/monolith"
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"

# ── inventory-service (:8084 HTTP / :9004 gRPC) ─────────────────────────
log "Migrating + starting inventory-service..."
( cd examples/04-inventory-service && .venv/bin/python -m alembic upgrade head ) >"$LOG_DIR/inventory-migrate.log" 2>&1
start_bg "$LOG_DIR/inventory.log" examples/04-inventory-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8084
wait_for_http http://localhost:8084/health inventory-service

# ── payment-service (:8085) — its own order.placed consumer + outbox relay ─
log "Migrating + starting payment-service..."
( cd examples/05-payment-service && .venv/bin/python -m alembic upgrade head ) >"$LOG_DIR/payment-migrate.log" 2>&1
start_bg "$LOG_DIR/payment.log" examples/05-payment-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8085
wait_for_http http://localhost:8085/health payment-service

# ── review-service (:8001) — shares the monolith's schema, no migration ──
log "Starting review-service..."
start_bg "$LOG_DIR/review.log" examples/02-review-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# ── notification-service (:8002) ────────────────────────────────────────
log "Migrating + starting notification-service..."
( cd examples/03-notification-service && .venv/bin/python -m alembic upgrade head ) >"$LOG_DIR/notification-migrate.log" 2>&1
start_bg "$LOG_DIR/notification.log" examples/03-notification-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8002

# ── monolith (:8000) — CHOREOGRAPHED payment, gRPC inventory ────────────
log "Migrating + seeding + starting the monolith (PAYMENT_MODE=choreographed)..."
( cd examples/00-monolith && .venv/bin/python manage.py migrate && .venv/bin/python manage.py seed ) \
  >"$LOG_DIR/monolith-migrate.log" 2>&1

export INVENTORY_MODE=grpc
export INVENTORY_GRPC_TARGET=localhost:9004
export PAYMENT_MODE=choreographed

start_bg "$LOG_DIR/monolith.log" examples/00-monolith \
  .venv/bin/python -m gunicorn config.wsgi -b 0.0.0.0:8000
wait_for_http http://localhost:8000/api/orders monolith

log "Starting the monolith's saga background processes (outbox_relay, order_placed_consumer, order_saga_listener)..."
start_bg "$LOG_DIR/outbox_relay.log" examples/00-monolith \
  .venv/bin/python manage.py outbox_relay
start_bg "$LOG_DIR/order_placed_consumer.log" examples/00-monolith \
  .venv/bin/python manage.py order_placed_consumer
start_bg "$LOG_DIR/order_saga_listener.log" examples/00-monolith \
  .venv/bin/python manage.py order_saga_listener

unset INVENTORY_MODE INVENTORY_GRPC_TARGET PAYMENT_MODE

# Let the three Kafka consumers above complete their group-join/rebalance
# before any checkout fires, same margin the GOLDEN-BASELINE.md runs used.
sleep 5

# ── strangler proxy (:8888) — every flag on ─────────────────────────────
log "Starting the strangler proxy (all flags on)..."
export STRANGLER_REVIEW_ENABLED=true
export STRANGLER_NOTIFICATION_ENABLED=true
export STRANGLER_INVENTORY_ENABLED=true
export STRANGLER_PAYMENT_ENABLED=true
export STRANGLER_MONOLITH_BASE_URL=http://localhost:8000
export STRANGLER_REVIEW_BASE_URL=http://localhost:8001
export STRANGLER_NOTIFICATION_BASE_URL=http://localhost:8002
export STRANGLER_INVENTORY_BASE_URL=http://localhost:8084
export STRANGLER_PAYMENT_BASE_URL=http://localhost:8085
start_bg "$LOG_DIR/proxy.log" examples/01-strangler-proxy \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8888
wait_for_http http://localhost:8888/api/inventory proxy

log "Full topology is up. Running the choreographed suite through the proxy..."
echo

set +e
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/proxy.postman_environment.json \
  --env-var paymentContractEnabled=true \
  --env-var inventoryContractEnabled=true \
  --env-var notificationContractEnabled=true
NEWMAN_EXIT=$?
set -e

echo
if [ "$NEWMAN_EXIT" -eq 0 ]; then
  log "GREEN — the choreographed payment cutover (r05) is proven end-to-end."
else
  log "RED (newman exit $NEWMAN_EXIT) — see the output above and $LOG_DIR/*.log."
fi

exit "$NEWMAN_EXIT"
