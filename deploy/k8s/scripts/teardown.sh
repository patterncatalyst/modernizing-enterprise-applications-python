#!/usr/bin/env bash
# deploy/k8s/scripts/teardown.sh -- stop the `mea` profile (state and loaded
# images are kept). --delete removes the profile entirely.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_tool minikube ""
if [[ "${1:-}" == "--delete" ]]; then
  step "minikube delete -p $PROFILE"
  minikube delete -p "$PROFILE"
else
  step "minikube stop -p $PROFILE"
  minikube stop -p "$PROFILE"
fi
