#!/usr/bin/env bash
# demos/demo-final-topology.sh — r07 DECOMMISSION end-to-end proof: brings up
# the FINAL, monolith-free topology (Postgres, Kafka, review-, notification-,
# inventory-, payment-, shipping-, order-service, the GraphQL gateway, and
# the strangler proxy as a FLAGLESS edge router), runs the full Newman
# CONTRACT suite (all 6 context contracts + 4 checkout scenarios + the
# GraphQL Gateway Contract folder) against it, then tears everything down.
#
# This is the end state every prior demo-*-cutover.sh script in this
# directory was building toward: `examples/00-monolith` is NOT started here
# at all (not even as a WSGI process) -- it is frozen, in-repo, and no longer
# part of the running topology (see its own README.md's "FROZEN STATUS
# (r07)" section). The ONE Django management command this script still runs
# is `manage.py migrate && manage.py seed` -- a one-time, one-shot SCHEMA
# SETUP step (creates the shared Postgres schema/seed data
# `02-review-service` and `03-notification-service` still read from), not a
# live server process. Nothing in this script ever starts `manage.py
# runserver`/gunicorn, `outbox_relay`, `order_placed_consumer`, or
# `order_saga_listener` -- those monolith-side processes are retired; every
# saga reaction they used to drive now lives in `07-order-service`'s own
# `app/consumer.py`.
#
# Mirrors demos/demo-shipping-cutover.sh's style (Docker-primary, resolve
# paths off this script's own location, throwaway containers, self-contained
# teardown on exit/error/Ctrl-C via `trap ... EXIT`) with two more standalone
# services (order-service, the GraphQL gateway) and a flagless proxy -- no
# `STRANGLER_*_ENABLED` vars anywhere, because there is no flag left to set.
#
# See tooling/newman/GOLDEN-BASELINE-r07.md's "STEP C" section for the full
# recorded contract-suite run this script reproduces, and
# examples/01-strangler-proxy/CUTOVER.md's "Order seam (r07)" section for the
# reversibility proof recorded immediately before this irreversible cut.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

POSTGRES_IMAGE_TAG="${POSTGRES_IMAGE_TAG:-18.6-alpine}"
KAFKA_IMAGE_TAG="${KAFKA_IMAGE_TAG:-4.3.1}"
KAFKA_CLUSTER_ID="${KAFKA_CLUSTER_ID:-MkU3OEVBNTcwNTJENDM2Qk}"

PG_CONTAINER="meap-demo-final-topology-pg"
KAFKA_CONTAINER="meap-demo-final-topology-kafka"
LOG_DIR="$(mktemp -d /tmp/mea-final-topology-demo.XXXXXX)"
PIDS=()

if command -v docker >/dev/null 2>&1; then
  ENGINE=docker
elif command -v podman >/dev/null 2>&1; then
  ENGINE=podman
else
  echo "Neither docker nor podman is available." >&2
  exit 1
fi

log()  { echo "[demo-final-topology] $*"; }

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

# ── One-shot schema setup (NOT a live process) ──────────────────────────
# The shared schema + seed data review-/notification-service still read
# from (customers, auth_user, the three demo SKUs). `examples/00-monolith`
# is otherwise never started in this script -- see the module docstring.
log "One-shot: migrating + seeding the shared schema (examples/00-monolith is NOT started as a server)..."
( cd examples/00-monolith && .venv/bin/python manage.py migrate && .venv/bin/python manage.py seed ) \
  >"$LOG_DIR/schema-setup.log" 2>&1

# ── review-service (:8001) ──────────────────────────────────────────────
log "Starting review-service..."
start_bg "$LOG_DIR/review.log" examples/02-review-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
wait_for_http "http://localhost:8001/api/reviews?sku=SKU-WIDGET-001" review-service

# ── notification-service (:8002) — order.placed consumer ────────────────
log "Migrating + starting notification-service..."
( cd examples/03-notification-service && .venv/bin/python -m alembic upgrade head ) \
  >"$LOG_DIR/notification-migrate.log" 2>&1
start_bg "$LOG_DIR/notification.log" examples/03-notification-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
wait_for_http http://localhost:8002/health notification-service

# ── inventory-service (:8084 HTTP / :9004 gRPC) ─────────────────────────
log "Migrating + starting inventory-service..."
( cd examples/04-inventory-service && .venv/bin/python -m alembic upgrade head ) \
  >"$LOG_DIR/inventory-migrate.log" 2>&1
start_bg "$LOG_DIR/inventory.log" examples/04-inventory-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8084
wait_for_http http://localhost:8084/health inventory-service

# ── payment-service (:8085) — order.placed consumer, shipment.failed
#    refund consumer, outbox relay ───────────────────────────────────────
log "Migrating + starting payment-service..."
( cd examples/05-payment-service && .venv/bin/python -m alembic upgrade head ) \
  >"$LOG_DIR/payment-migrate.log" 2>&1
start_bg "$LOG_DIR/payment.log" examples/05-payment-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8085
wait_for_http http://localhost:8085/health payment-service

# ── shipping-service (:8087) — payment.captured consumer, DB-backed saga
#    orchestrator, outbox relay; enrich RE-POINTED at order-service (r07) ──
log "Migrating + starting shipping-service (ORDER_BASE_URL=:8088)..."
( cd examples/06-shipping-service && .venv/bin/python -m alembic upgrade head ) \
  >"$LOG_DIR/shipping-migrate.log" 2>&1
( cd "$PROJECT_ROOT/examples/06-shipping-service" && ORDER_BASE_URL=http://localhost:8088 \
  exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8087 ) \
  >"$LOG_DIR/shipping.log" 2>&1 &
PIDS+=("$!")
wait_for_http http://localhost:8087/health shipping-service

# ── order-service (:8088) — CQRS command+read, 4 lifted saga reactions,
#    own order.placed outbox, gRPC client of inventory-service ─────────────
log "Migrating + starting order-service..."
( cd examples/07-order-service && .venv/bin/python -m alembic upgrade head ) \
  >"$LOG_DIR/order-migrate.log" 2>&1
start_bg "$LOG_DIR/order.log" examples/07-order-service \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8088
wait_for_http http://localhost:8088/health order-service

# ── GraphQL gateway (:8090) — data-less aggregation, REST+gRPC federation ──
log "Starting the GraphQL gateway..."
start_bg "$LOG_DIR/gateway.log" examples/08-graphql-gateway \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
wait_for_http http://localhost:8090/health graphql-gateway

log "Letting consumer groups settle (rebalance margin)..."
sleep 6

# ── strangler proxy (:8888) — FLAGLESS edge router, no monolith anywhere ──
log "Starting the strangler proxy (flagless -- every /api/* prefix to its one owning service)..."
start_bg "$LOG_DIR/proxy.log" examples/01-strangler-proxy \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8888
wait_for_http http://localhost:8888/api/orders proxy

log "Full monolith-free topology is up. Running the contract suite through the proxy..."
echo

set +e
newman run tooling/newman/mea.postman_collection.json \
  -e tooling/newman/proxy.postman_environment.json
NEWMAN_EXIT=$?
set -e

echo
if [ "$NEWMAN_EXIT" -eq 0 ]; then
  log "GREEN — the monolith-free end state is proven end-to-end: 4 checkout scenarios, all 6"
  log "context contracts, and the GraphQL Gateway Contract folder, all green through the flagless proxy."
else
  log "RED (newman exit $NEWMAN_EXIT) — see the output above and $LOG_DIR/*.log. Every service in this"
  log "topology is a fresh, newly-migrated instance with no monolith anywhere, so a RED here is a"
  log "genuine regression to investigate, not a flag/ordering artifact."
fi

exit "$NEWMAN_EXIT"
