#!/usr/bin/env bash
# scripts/stack-down.sh — tear down the r01 local infra/observability stack.
#
# Docker-primary, podman-compatible: tries `docker compose` first, falls back
# to `podman compose` if docker isn't installed. By default preserves named
# volumes (postgres-data, kafka-data) so seed data / topics survive a
# restart. Pass -v to wipe them (e.g. to recover from a Kafka KRaft
# cluster-ID mismatch after changing KAFKA_CLUSTER_ID).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  echo "Neither 'docker compose' nor 'podman compose' is available: install Docker Engine (docker-ce + docker-compose-plugin) or Podman (podman-compose)." >&2
  exit 1
fi

ENV_FILE=.env
[ -f "$ENV_FILE" ] || ENV_FILE=.env.example

if [ "${1:-}" = "-v" ]; then
  echo "Stopping stack and wiping volumes (postgres-data, kafka-data)..."
  "${COMPOSE[@]}" --env-file "$ENV_FILE" down -v
else
  echo "Stopping stack (volumes preserved; pass -v to wipe them)..."
  "${COMPOSE[@]}" --env-file "$ENV_FILE" down
fi
