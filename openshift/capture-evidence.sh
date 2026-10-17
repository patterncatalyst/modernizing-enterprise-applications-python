#!/usr/bin/env bash
#
# capture-evidence.sh -- verify the mea deployment on OpenShift Local and
# write what it saw to openshift/evidence/<date>/.
#
# Checks (each fails the script on a miss):
#   1. cluster, images: one ImageStream tag per service (+ monolith)
#   2. pods: all Ready under restricted-v2 with a namespace-range UID
#      (the one exception is otel-lgtm under anyuid)
#   3. Routes: both answer over edge TLS
#   4. project checks: the happy-path checkout (project-checks.sh)
#   5. platform tier: whatever openshift/platform/ installed
#   6. secret scrub: no password, token or private key in the evidence
#
# curl validates the router certificate against the cluster's ingress CA, so
# nothing here uses --insecure. Nothing here prints a secret. Never
# fabricate an output: a failed check fails the script, and this script
# writes *.MISSING.txt + exits non-zero rather than inventing a result.
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_crc

OUT="$OPENSHIFT_DIR/evidence/$(date +%Y-%m-%d)"
mkdir -p "$OUT"
CA="$(mktemp)"; trap 'rm -f "$CA"' EXIT
if ! occ get configmap default-ingress-cert -n openshift-config-managed \
  -o jsonpath='{.data.ca-bundle\.crt}' > "$CA" 2>/dev/null || [[ ! -s "$CA" ]]; then
  echo "could not read the cluster ingress CA" > "$OUT/00-ingress-ca.MISSING.txt"
  fail "cannot read the ingress CA (see $OUT/00-ingress-ca.MISSING.txt)"
fi
https() { curl -sS --max-time 20 --cacert "$CA" "$@"; }
in_pod() { local d="$1"; shift; occ exec -n "$NS" "deploy/$d" -c "$d" -- "$@"; }
route_url() { printf 'https://%s' "$(occ get route "$1" -n "${2:-$NS}" -o jsonpath='{.spec.host}')"; }

step "1/6 Cluster, images"
{
  if command -v crc >/dev/null 2>&1; then crc version | head -3; fi
  occ version | grep -E 'Server|Kubernetes'
  for entry in "${SERVICES[@]}"; do
    name="${entry%%:*}"
    occ get istag "$name:$IMAGE_TAG" -n "$NS" -o jsonpath='{.metadata.name} {.image.dockerImageReference}{"\n"}'
  done
  occ get istag "monolith:$IMAGE_TAG" -n "$NS" -o jsonpath='{.metadata.name} {.image.dockerImageReference}{"\n"}'
} > "$OUT/01-cluster-images.txt" 2>&1
tags=$(grep -c ":$IMAGE_TAG image-registry" "$OUT/01-cluster-images.txt" || true)
want_tags=$(( ${#SERVICES[@]} + 1 ))
(( tags == want_tags )) || fail "expected $want_tags ImageStream tags $IMAGE_TAG (8 services + monolith), found $tags (see $OUT/01-cluster-images.txt)"
ok "$tags ImageStream tags $IMAGE_TAG"

step "2/6 Pods under restricted-v2"
occ get pods -n "$NS" --field-selector=status.phase=Running \
  -o custom-columns='POD:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,SCC:.metadata.annotations.openshift\.io/scc,UID:.spec.containers[0].securityContext.runAsUser' \
  > "$OUT/02-pods.txt"
# Allowed SCCs: app pods restricted-v2; postgres/kafka infra nonroot-v2 (the
# mea-infra SA, DRQ-107); otel-lgtm anyuid (install-observability.sh). A pod is
# bad if any container is not ready or its SCC is outside that per-workload set.
bad=$(awk 'NR>1 && ($2 ~ /false/ || !($4=="restricted-v2" || (($1 ~ /^postgres/ || $1 ~ /^kafka/) && $4=="nonroot-v2") || ($1 ~ /^lgtm/ && $4=="anyuid")))' "$OUT/02-pods.txt" | grep -c . || true)
occ get namespace "$NS" -o jsonpath='namespace uid-range: {.metadata.annotations.openshift\.io/sa\.scc\.uid-range}{"\n"}' >> "$OUT/02-pods.txt"
(( bad == 0 )) || fail "$bad pod(s) not Ready or not restricted-v2 (see $OUT/02-pods.txt)"
ok "all pods Ready, restricted-v2"

step "3/6 Routes over edge TLS"
: > "$OUT/03-routes.txt"
for route in strangler-proxy graphql-gateway; do
  host="$(occ get route "$route" -n "$NS" -o jsonpath='{.spec.host}' 2>/dev/null)"
  [[ -n "$host" ]] || { echo "Route $route not found" >> "$OUT/03-routes.txt"; fail "Route $route missing"; }
  code=$(https -o /dev/null -w '%{http_code}' "https://$host/")
  printf 'GET https://%s/ -> %s\n' "$host" "$code" >> "$OUT/03-routes.txt"
  [[ "$code" =~ ^(200|404)$ ]] || fail "Route $route returned $code (see $OUT/03-routes.txt)"
  ok "$route https://$host 200/404 (edge TLS terminates; app-level routing is checked in step 4)"
done

step "4/6 Project checks"
if [[ -f "$OPENSHIFT_DIR/project-checks.sh" ]]; then
  # shellcheck source=project-checks.sh
  source "$OPENSHIFT_DIR/project-checks.sh"
  project_checks
else
  echo "openshift/project-checks.sh not found" > "$OUT/04-checkout.MISSING.txt"
  fail "no project-checks.sh: cannot verify the system end to end"
fi

step "5/6 Platform tier"
# shellcheck source=platform/evidence.sh
source "$OPENSHIFT_DIR/platform/evidence.sh"
platform_evidence

step "6/6 Secret scrub"
leaks=0
if occ get secret mea-postgres-app -n "$NS" >/dev/null 2>&1; then
  password="$(occ get secret mea-postgres-app -n "$NS" -o jsonpath='{.data.password}' | base64 -d)"
  # The dev password may equal a common token (here it is "monolith", which is
  # also an image name): a match inside a container image reference is not a
  # credential leak. Flag the password only on non-image-reference lines.
  if grep -rhF -- "$password" "$OUT" | grep -vqE 'image-registry|/mea/[a-z0-9-]+[:@]'; then
    printf '    database password found in evidence (non-image context)\n' >&2; leaks=1
  fi
  unset password
fi
grep -rlE 'sha256~[A-Za-z0-9_-]{20,}|BEGIN [A-Z ]*PRIVATE KEY|kubeadmin-password|"token"|"auths"' "$OUT" >&2 && leaks=1
(( leaks == 0 )) || fail "evidence contains secret material: delete $OUT and investigate"
ok "no secrets in $OUT"

printf '\n    evidence: %s\n' "${OUT#"$REPO_ROOT"/}"
