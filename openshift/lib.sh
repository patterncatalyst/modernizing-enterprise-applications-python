# shellcheck shell=bash
# shellcheck disable=SC2034
# lib.sh -- shared helpers for the openshift/ scripts (sourced, not run).
# (SC2034 "appears unused" is a false positive on every variable below --
# each is read by the scripts that source this file, not by this file
# itself.)
#
# Every script talks to OpenShift Local through the "crc-admin" kubeconfig
# context that `crc start` writes, so no password is ever typed, printed or
# stored. Run `eval "$(crc oc-env)"` first if `oc` is not on PATH.

PROJECT="mea"
NS="${PROJECT_NAMESPACE:-$PROJECT}"
RELEASE="${RELEASE:-$PROJECT}"
OCP_CONTEXT="${OCP_CONTEXT:-crc-admin}"
OPENSHIFT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$OPENSHIFT_DIR/.." && pwd)"
CHART_DIR="$OPENSHIFT_DIR/helm/$PROJECT"
# Image tag build-and-push.sh produces and the chart deploys.
IMAGE_TAG="${IMAGE_TAG:-v1}"
# Internal-registry external host (the exposed default Route), used only by
# build-and-push.sh/install-infra.sh for the podman push/login step.
REGISTRY_HOST="${REGISTRY_HOST:-default-route-openshift-image-registry.apps-crc.testing}"
# In-cluster pull path -- matches helm/mea/values.yaml's image.registry.
REGISTRY_INTERNAL="image-registry.openshift-image-registry.svc:5000"

# The eight app workloads: <service name>:<examples/ directory>. Same
# service names as deploy/k8s/scripts/lib.sh and the chart's
# values.yaml `services:` keys.
SERVICES=(
  strangler-proxy:01-strangler-proxy
  review-service:02-review-service
  notification-service:03-notification-service
  inventory-service:04-inventory-service
  payment-service:05-payment-service
  shipping-service:06-shipping-service
  order-service:07-order-service
  graphql-gateway:08-graphql-gateway
)
# The frozen monolith -- built and pushed too (DRQ-111's bootstrap Job runs
# it), never deployed as its own workload.
MONOLITH_DIR="00-monolith"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \xe2\x9c\x93 %s\n' "$1"; }
warn() { printf '    ! %s\n' "$1" >&2; }
fail() { printf '\n\xe2\x9c\x97 %s\n' "$1" >&2; exit 1; }

occ() { command oc --context "$OCP_CONTEXT" "$@"; }

# require_single_cluster: one local cluster at a time. A running minikube
# profile competes with the CRC VM for memory; stop it first.
require_single_cluster() {
  command -v minikube >/dev/null 2>&1 || return 0
  local running
  running="$(minikube profile list -o json 2>/dev/null \
    | jq -r '.valid[]? | select(.Status == "OK" or .Status == "Running") | .Name' 2>/dev/null)"
  [[ -z "$running" ]] || fail "minikube profile(s) running: $running. Stop them first (minikube stop -p <profile>); run one local cluster at a time"
}

# require_crc: oc on PATH, the crc-admin context reachable, and the API
# server is OpenShift Local's. Fails fast instead of touching another
# cluster.
require_crc() {
  command -v oc >/dev/null 2>&1 || fail "oc not on PATH: run eval \"\$(crc oc-env)\""
  command -v jq >/dev/null 2>&1 || fail "jq not on PATH"
  require_single_cluster
  if command -v crc >/dev/null 2>&1; then
    crc status 2>/dev/null | grep -q 'OpenShift:.*Running' || fail "OpenShift Local is not running: crc start"
  fi
  oc config get-contexts "$OCP_CONTEXT" >/dev/null 2>&1 \
    || fail "no kubeconfig context $OCP_CONTEXT (crc start writes it)"
  local api
  api="$(occ whoami --show-server 2>/dev/null)" || fail "cannot reach the OpenShift API"
  [[ "$api" == *api.crc.testing* ]] || fail "context $OCP_CONTEXT reaches '${api:-nothing}', not OpenShift Local (api.crc.testing). Is CRC running?"
}

# require_crc_size <cpus> <memory-MiB>: the VM is configured at least this
# large. Sizing only takes effect while CRC is stopped (crc config set ...).
require_crc_size() {
  local want_cpu="$1" want_mem="$2" cpu mem
  command -v crc >/dev/null 2>&1 || { warn "crc not on PATH; cannot verify sizing"; return 0; }
  cpu="$(crc config get cpus 2>/dev/null | awk '{print $NF}')"
  mem="$(crc config get memory 2>/dev/null | awk '{print $NF}')"
  [[ "$cpu" =~ ^[0-9]+$ && "$mem" =~ ^[0-9]+$ ]] || { warn "could not read crc cpus/memory; continuing"; return 0; }
  (( cpu >= want_cpu && mem >= want_mem )) \
    || fail "CRC is sized ${cpu} vCPU / ${mem} MiB; this needs ${want_cpu} / ${want_mem}: crc stop; crc config set cpus $want_cpu; crc config set memory $want_mem; crc start"
}

# wait_for <seconds> <description> <command...>: poll every 5s until the
# command succeeds.
wait_for() {
  local timeout="$1" what="$2"; shift 2
  local waited=0
  until "$@" >/dev/null 2>&1; do
    (( waited >= timeout )) && fail "timed out after ${timeout}s waiting for $what"
    sleep 5; waited=$(( waited + 5 ))
  done
  ok "$what"
}

# install_operator <manifest> <namespace> <package> <csv>
# Applies an OLM manifest (Subscription, plus Namespace and OperatorGroup
# when the operator lives outside openshift-operators) whose Subscription
# pins <csv> with installPlanApproval: Manual and startingCSV, approves only
# the InstallPlan that lists <csv>, and waits for the CSV to succeed.
# Idempotent. Any other InstallPlan (an upgrade OLM proposes later) stays
# unapproved, so the version never moves without an edit here.
install_operator() {
  local manifest="$1" ns="$2" pkg="$3" csv="$4"
  _csv_ok() { [[ "$(occ get csv "$csv" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null)" == Succeeded ]]; }
  _plan() {
    occ get installplan -n "$ns" -o json 2>/dev/null | jq -r --arg c "$csv" \
      '.items[] | select(.spec.clusterServiceVersionNames | index($c)) | .metadata.name' | head -1
  }
  _plan_proposed() { [[ -n "$(_plan)" ]]; }
  if _csv_ok; then ok "$csv already Succeeded"; return 0; fi
  # redhat-operators reports READY before it serves packages (about a
  # minute after crc start), so wait for the package itself.
  wait_for 300 "OperatorHub serves $pkg" occ get packagemanifest "$pkg" -n openshift-marketplace
  occ apply -f "$manifest" >/dev/null || fail "apply $manifest"
  wait_for 300 "InstallPlan for $csv proposed" _plan_proposed
  occ patch installplan "$(_plan)" -n "$ns" --type merge -p '{"spec":{"approved":true}}' >/dev/null \
    || fail "approve InstallPlan for $csv"
  wait_for 600 "$csv Succeeded" _csv_ok
}

# refuse_foreign_subscription <package> <expected-ns>/<expected-name> <csv>
# This CRC is dedicated to one project. A Subscription for the same package
# left by another project means the cluster was not cleaned up: stop.
refuse_foreign_subscription() {
  local pkg="$1" want="$2" csv="$3" existing
  existing="$(occ get subscriptions.operators.coreos.com -A -o json 2>/dev/null | jq -r --arg p "$pkg" \
    '.items[] | select(.spec.name == $p) | "\(.metadata.namespace)/\(.metadata.name) \(.status.installedCSV // "")"')"
  [[ -z "$existing" || "$existing" == "$want $csv" || "$existing" == "$want " ]] \
    || fail "a $pkg Subscription already exists ($existing); this CRC is dedicated to $PROJECT: run the other project's teardown first"
}

# helm_values_json: the release's user-supplied values, as JSON.
helm_values_json() { helm get values "$RELEASE" -n "$NS" --kube-context "$OCP_CONTEXT" -o json; }
