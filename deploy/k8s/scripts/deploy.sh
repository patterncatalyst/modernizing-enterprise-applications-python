#!/usr/bin/env bash
# deploy/k8s/scripts/deploy.sh -- apply the minikube overlay to the `mea`
# profile, wait for every workload to roll out, and bootstrap
# review-service's shared `public` schema. Run setup-profile.sh and
# build-images.sh first.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_tool kubectl ""
require_profile_running

step "kubectl --context $PROFILE apply -k deploy/k8s/overlays/minikube"
kc apply -k "$REPO_ROOT/deploy/k8s/overlays/minikube"

step "Waiting for infra (Postgres + Kafka StatefulSets)"
kc -n "$NAMESPACE" rollout status statefulset/postgres --timeout=300s
kc -n "$NAMESPACE" rollout status statefulset/kafka --timeout=300s

# review-service (examples/02-review-service) runs no Alembic migration of
# its own -- it reads the monolith's shared `public` schema
# (reviews/customers/inventory_items/auth_user), created and seeded by the
# (frozen, not-deployed-here) monolith's own `manage.py migrate`/
# `manage.py seed` (examples/00-monolith). Run that once, on a fresh
# database, through a local port-forward -- exactly what
# examples/02-review-service/README.md documents as the one-time setup step,
# just aimed at the in-cluster Postgres instead of a local one.
step "Bootstrapping review-service's shared public schema (fresh database only)"
already_present="$(kc -n "$NAMESPACE" exec statefulset/postgres -- \
  psql -U monolith -d monolith -tAc "SELECT to_regclass('public.reviews') IS NOT NULL" 2>/dev/null || echo f)"
if [[ "$already_present" == "t" ]]; then
  echo "  public schema already present"
else
  require_tool uv "Install uv -- see examples/00-monolith/README.md's Prerequisites."
  fwd_port=15432
  kc -n "$NAMESPACE" port-forward svc/postgres "${fwd_port}:5432" >/tmp/mea-postgres-portforward.log 2>&1 &
  fwd_pid=$!
  trap 'kill "$fwd_pid" 2>/dev/null || true' EXIT
  for _ in $(seq 1 30); do
    (exec 3<>"/dev/tcp/127.0.0.1/${fwd_port}") 2>/dev/null && { exec 3>&-; break; }
    sleep 1
  done
  (
    cd "$REPO_ROOT/examples/00-monolith"
    export DATABASE_URL="postgresql://monolith:monolith@127.0.0.1:${fwd_port}/monolith"
    uv run python manage.py migrate
    uv run python manage.py seed
  )
  kill "$fwd_pid" 2>/dev/null || true
  trap - EXIT
  ok "public schema migrated + seeded"
fi

step "Waiting for the eight services"
for entry in "${SERVICES[@]}"; do
  kc -n "$NAMESPACE" rollout status "deployment/${entry%%:*}" --timeout=420s
done

kc -n "$NAMESPACE" get pods
printf '\nEdge router: curl -s http://127.0.0.1:30888/api/inventory\n'
printf 'GraphQL gateway (in-cluster only, no NodePort): kubectl --context %s -n %s port-forward svc/graphql-gateway 8090:8090\n' "$PROFILE" "$NAMESPACE"
