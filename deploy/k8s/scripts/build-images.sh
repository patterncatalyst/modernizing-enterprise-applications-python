#!/usr/bin/env bash
# deploy/k8s/scripts/build-images.sh -- build each service's Containerfile
# image and load it into the `mea` minikube profile.
#
# `docker build -f examples/<dir>/Containerfile -t mea/<svc>:1.0` ->
# `minikube -p mea image load mea/<svc>:1.0`. No registry: the minikube
# overlay sets imagePullPolicy: Never. A Deployment that already exists is
# restarted so it picks up the reloaded image.
#
# Usage:
#   deploy/k8s/scripts/build-images.sh                 # all eight services
#   deploy/k8s/scripts/build-images.sh order-service   # just these
# CONTAINER_ENGINE=podman uses podman instead of docker.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_container_engine
require_tool minikube ""
require_profile_running

want=("$@")
for entry in "${SERVICES[@]}"; do
  svc="${entry%%:*}"; dir="$REPO_ROOT/examples/${entry#*:}"
  if (( ${#want[@]} )) && [[ " ${want[*]} " != *" $svc "* ]]; then continue; fi
  image="mea/${svc}:${IMAGE_TAG}"
  step "$svc: $CONTAINER_ENGINE build -f $dir/Containerfile -t $image"
  "$CONTAINER_ENGINE" build -q -f "$dir/Containerfile" -t "$image" "$dir" >/dev/null
  step "$svc: minikube -p $PROFILE image load $image"
  minikube -p "$PROFILE" image load "$image"
  minikube -p "$PROFILE" image ls 2>/dev/null | grep -qE "(^|/)mea/${svc}:${IMAGE_TAG}\$" \
    || fail "$image not present in the node after load"
  ok "$image loaded"
  if kc -n "$NAMESPACE" get deployment "$svc" >/dev/null 2>&1; then
    kc -n "$NAMESPACE" rollout restart "deployment/$svc"
  fi
done
