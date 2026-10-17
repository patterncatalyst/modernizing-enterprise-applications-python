#!/usr/bin/env bash
# deploy/k8s/scripts/install-istio.sh -- install Istio into the `mea`
# profile from deploy/k8s/istio/istio-install.yaml (ch.30).
#
# istioctl must match this chapter's pin (major.minor; see $ISTIO_VERSION
# below) -- the client installs a control plane of ITS OWN version, so a
# mismatched istioctl on PATH would silently install the wrong Istio.
# Download: https://istio.io/downloadIstio | ISTIO_VERSION=<pin> sh -
#
# Run after setup-profile.sh and before deploy.sh (the activated minikube
# overlay's `sidecar.istio.io/inject` labels only take effect on pods
# created or restarted AFTER istiod's webhook is live).
#
# Usage:
#   deploy/k8s/scripts/install-istio.sh
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

ISTIO_VERSION="${ISTIO_VERSION:-1.31.2}"

require_tool istioctl "Install istioctl ${ISTIO_VERSION}: curl -L https://istio.io/downloadIstio | ISTIO_VERSION=${ISTIO_VERSION} sh -"
require_profile_running

client="$(istioctl version --remote=false 2>/dev/null | awk '{print $NF}')"
client_minor="${client%.*}"
pin_minor="${ISTIO_VERSION%.*}"
[[ "$client_minor" == "$pin_minor" ]] \
  || fail "istioctl is ${client:-unknown}; this chapter pins ${ISTIO_VERSION} (major.minor ${pin_minor} required)"

step "istioctl install (Istio ${client}, context ${PROFILE})"
istioctl install -y --context "$PROFILE" -f "$REPO_ROOT/deploy/k8s/istio/istio-install.yaml"

step "Waiting for istiod"
kc -n istio-system rollout status deployment/istiod --timeout=300s

step "Waiting for the ingress gateway"
kc -n istio-system rollout status deployment/istio-ingressgateway --timeout=300s

ok "Istio ${client} ready"
printf '\nNext: deploy/k8s/scripts/build-images.sh && deploy/k8s/scripts/deploy.sh\n'
printf 'Verify mesh injection + mTLS on a running pod once deployed:\n'
printf '  istioctl x describe pod -n %s <pod-name>\n' "$NAMESPACE"
