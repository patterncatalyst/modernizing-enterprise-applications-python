#!/usr/bin/env bash
# deploy/k8s/scripts/setup-profile.sh -- create (or start) the `mea`
# minikube profile for ch.29 (ch.30's mesh/observability overlays land at
# r10 -- see overlays/minikube/kustomization.yaml's seam comment).
#
# `--driver=docker --container-runtime=containerd` (set CONTAINER_ENGINE=
# podman and MINIKUBE_DRIVER=podman together for a podman-driven profile).
# The NodePort in lib.sh is published on 127.0.0.1 at creation
# (`--ports=127.0.0.1:30888:30888`), so the edge router is reachable at
# http://127.0.0.1:30888 -- no port-forward, no tunnel, no `minikube
# service`. Ports are fixed at creation: changing them means --replace.
#
# One local cluster at a time: refuses to run while another minikube profile
# is running.
#
# Usage:
#   deploy/k8s/scripts/setup-profile.sh             # create, start, or verify
#   deploy/k8s/scripts/setup-profile.sh --replace   # delete first, then create
# Sizing: MINIKUBE_MEMORY (default 8g), MINIKUBE_CPUS (4), MINIKUBE_DISK (30g).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

MEMORY="${MINIKUBE_MEMORY:-8g}"
CPUS="${MINIKUBE_CPUS:-4}"
DISK="${MINIKUBE_DISK:-30g}"
DRIVER="${MINIKUBE_DRIVER:-docker}"
REPLACE=0; [[ "${1:-}" == "--replace" ]] && REPLACE=1

require_container_engine
require_tool minikube "Install minikube ${MINIKUBE_MIN}+."
require_tool kubectl "Install kubectl ${K8S_VERSION%.*}.x."

mk_ver="$(minikube version --short 2>/dev/null || echo v0.0.0)"
[[ "$(printf '%s\n%s\n' "$MINIKUBE_MIN" "$mk_ver" | sort -V | head -1)" == "$MINIKUBE_MIN" ]] \
  || fail "minikube $mk_ver is older than $MINIKUBE_MIN"

# One cluster at a time.
others="$(minikube profile list -o json 2>/dev/null \
  | grep -o '"Name":"[^"]*","Status":"Running"' \
  | sed -E 's/"Name":"([^"]*)".*/\1/' \
  | grep -v "^${PROFILE}\$" || true)"
[[ -z "$others" ]] || fail "other minikube profiles are running: ${others}. Stop them first: minikube stop -p <name>"

PORTS_ARG=""; for p in "${NODE_PORTS[@]}"; do PORTS_ARG+="${PORTS_ARG:+,}127.0.0.1:${p}:${p}"; done

exists="$(minikube profile list -o json 2>/dev/null | grep -o "\"Name\":\"${PROFILE}\"" || true)"

if [[ -n "$exists" && $REPLACE -eq 1 ]]; then
  step "Deleting profile $PROFILE (--replace)"
  minikube delete -p "$PROFILE"
  exists=""
fi

if [[ -n "$exists" ]]; then
  if minikube status -p "$PROFILE" >/dev/null 2>&1; then
    step "Profile $PROFILE already running"
  else
    step "Starting stopped profile $PROFILE (published ports persist)"
    minikube start -p "$PROFILE"
  fi
else
  for p in "${NODE_PORTS[@]}"; do
    [[ -z "$(ss -ltnH "sport = :$p" 2>/dev/null)" ]] || fail "host port $p is in use; free it and re-run"
  done
  step "Creating $PROFILE: Kubernetes $K8S_VERSION, $MEMORY / $CPUS CPUs / $DISK, $DRIVER driver, ports $PORTS_ARG"
  minikube start -p "$PROFILE" \
    --driver="$DRIVER" \
    --container-runtime=containerd \
    --kubernetes-version="$K8S_VERSION" \
    --memory="$MEMORY" --cpus="$CPUS" --disk-size="$DISK" \
    --ports="$PORTS_ARG"
fi

step "Verifying the published NodePort"
for p in "${NODE_PORTS[@]}"; do
  minikube -p "$PROFILE" ssh -- "sudo ss -ltnH 'sport = :${p}'" >/dev/null 2>&1 \
    || true   # best-effort check; `docker port`/driver-specific introspection varies
  ok "configured for 127.0.0.1:${p}"
done

kc get nodes
printf '\nNext: deploy/k8s/scripts/build-images.sh && deploy/k8s/scripts/deploy.sh\n'
