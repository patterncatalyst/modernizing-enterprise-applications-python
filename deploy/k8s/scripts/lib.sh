#!/usr/bin/env bash
# shellcheck disable=SC2034
# deploy/k8s/scripts/lib.sh -- shared settings and checks for the minikube
# path. Sourced, not executed. (SC2034 "appears unused" is a false positive
# on every variable below -- each is read by the scripts that source this
# file, not by this file itself.)
#
# One profile (`mea`), the docker driver with the containerd runtime, on
# Docker Engine (docker-ce, context `default`). Every call names the profile
# explicitly (`minikube -p`, `kubectl --context`); kubectl's current-context
# is never read or changed, and `minikube config set` is never used.

PROFILE="${MEA_PROFILE:-mea}"
NAMESPACE="mea"
# Matches the kubectl pin this project's new CI gates use (ch.29/31 plan,
# surveyed 2026-10-17) -- override with KUBERNETES_VERSION if minikube's
# cached image for this exact patch isn't available yet.
K8S_VERSION="${KUBERNETES_VERSION:-v1.37.1}"
IMAGE_TAG="1.0"
MINIKUBE_MIN="v1.33.0"
# docker or podman -- both build Containerfile-based images; podman needs no
# daemon context check, docker does (see require_container_engine below).
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"

# NodePorts published to the host on 127.0.0.1 at profile creation. Keep in
# sync with deploy/k8s/overlays/minikube/kustomization.yaml (strangler-proxy)
# and deploy/k8s/observability/lgtm-service.yaml (lgtm-grafana, ch.30).
NODE_PORTS=(30888 30300)   # strangler-proxy REST edge, Grafana UI

# The eight workloads: <service name>:<examples/ directory>.
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

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ok: %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

kc() { command kubectl --context "$PROFILE" "$@"; }

require_tool() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 not in PATH. $2"
}

require_container_engine() {
  require_tool "$CONTAINER_ENGINE" "Install Docker Engine (docker-ce) or Podman, or set CONTAINER_ENGINE=podman|docker."
  if [[ "$CONTAINER_ENGINE" == "docker" ]]; then
    docker info >/dev/null 2>&1 || fail "cannot reach the Docker daemon. Fix: sudo systemctl enable --now docker"
  fi
}

require_profile_running() {
  minikube status -p "$PROFILE" >/dev/null 2>&1 \
    || fail "minikube profile $PROFILE is not running. Start it: deploy/k8s/scripts/setup-profile.sh"
}
