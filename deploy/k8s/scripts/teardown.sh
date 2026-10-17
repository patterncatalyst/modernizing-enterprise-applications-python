#!/usr/bin/env bash
# deploy/k8s/scripts/teardown.sh -- remove the Istio mesh + LGTM
# observability resources (ch.30) and the app overlay from the `mea`
# profile, then stop it (state and loaded images are kept). --delete
# removes the profile entirely.
#
# Explicit resource removal matters even though `minikube delete` would
# also destroy everything: `minikube stop` SUSPENDS the profile rather than
# destroying it, so the Istio control plane (webhooks, CRDs) and the LGTM
# backend would otherwise persist across a stop/start cycle. `istioctl
# uninstall --purge` is the correct way to remove an `istioctl install`-ed
# control plane (it is operator-reconciled, not a plain `kubectl delete -k`
# target -- see deploy/k8s/istio/istio-install.yaml's header) -- removing
# the overlay first takes the app Deployments out of the mesh (and deletes
# the LGTM backend) before the control plane goes away.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_tool minikube ""

if minikube status -p "$PROFILE" >/dev/null 2>&1; then
  step "Removing the activated overlay (app workloads + istio CRs + observability)"
  kc delete -k "$REPO_ROOT/deploy/k8s/overlays/minikube" --ignore-not-found --wait=false || true

  if command -v istioctl >/dev/null 2>&1 && kc -n istio-system get deployment istiod >/dev/null 2>&1; then
    step "istioctl uninstall --purge (removing the Istio control plane)"
    istioctl uninstall --context "$PROFILE" --purge -y || true
    kc delete namespace istio-system --ignore-not-found --wait=false || true
  fi
else
  step "Profile $PROFILE is not running; nothing to remove in-cluster"
fi

if [[ "${1:-}" == "--delete" ]]; then
  step "minikube delete -p $PROFILE"
  minikube delete -p "$PROFILE"
else
  step "minikube stop -p $PROFILE"
  minikube stop -p "$PROFILE"
fi
