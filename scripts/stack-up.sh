#!/usr/bin/env bash
# scripts/stack-up.sh — bring up the r01 local infra/observability stack.
#
# Docker-primary, podman-compatible: tries `docker compose` first, falls back
# to `podman compose` if docker isn't installed. Never the legacy hyphenated
# `docker-compose` v1 binary. Run from anywhere; paths are resolved relative
# to this script's location so it works from any cwd.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example (edit it if you need different pins/ports)." >&2
  cp .env.example .env
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  echo "Neither 'docker compose' nor 'podman compose' is available: install Docker Engine (docker-ce + docker-compose-plugin) or Podman (podman-compose)." >&2
  exit 1
fi

echo "Starting stack (${COMPOSE[*]}, --env-file .env)..."
"${COMPOSE[@]}" --env-file .env up -d

echo
echo "Waiting for services to report healthy..."
for i in $(seq 1 60); do
  statuses=$("${COMPOSE[@]}" ps --format '{{.Health}}' 2>/dev/null || true)
  if [ -n "$statuses" ] && ! echo "$statuses" | grep -qv -E '^(healthy)?$'; then
    break
  fi
  sleep 2
done

"${COMPOSE[@]}" ps
echo
echo "Postgres:   localhost:${POSTGRES_PORT:-5432} (see .env for db/user/password)"
echo "Kafka:      localhost:${KAFKA_HOST_PORT:-9092} (host) / kafka:9094 (compose network) — not used by r01 yet"
echo "Grafana:    http://localhost:3000 — not used by r01 yet"
echo "Prometheus: http://localhost:${PROMETHEUS_HOST_PORT:-19090} (host 19090; Cockpit owns 9090) — not used by r01 yet"
