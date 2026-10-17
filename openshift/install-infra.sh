#!/usr/bin/env bash
#
# install-infra.sh -- everything the mea project needs before images can be
# pushed and the Helm chart installed: the project itself, the integrated
# registry's default Route exposed (so build-and-push.sh has a host to push
# to), and the one SCC role binding the chart does NOT own.
#
# The mea-infra ServiceAccount (postgres/kafka, nonroot-v2) is created by
# the chart itself (helm/mea/templates/serviceaccount-infra.yaml) -- this
# script deliberately does not pre-create it, so a later `helm install`
# never collides with an object Helm did not create ("exists and cannot be
# imported into the release"). The otel-lgtm ServiceAccount (anyuid), by
# contrast, belongs to the platform tier's raw manifests
# (platform/observability/), never to the Helm release, so it is safe -- and
# needed up front -- to provision here.
#
# Idempotent: re-running skips what already exists. Undo with teardown.sh.
#
#   eval "$(crc oc-env)"
#   ./openshift/install-infra.sh
#   INVENTORY_ONLY=true ./openshift/install-infra.sh   # just the foreign-operator check
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

INVENTORY_ONLY="${INVENTORY_ONLY:-false}"

require_crc

step "1/4 Project $NS"
if occ get project "$NS" >/dev/null 2>&1; then
  ok "project $NS exists"
else
  occ new-project "$NS" --display-name="Modernizing Enterprise Applications (Python)" >/dev/null \
    || fail "oc new-project $NS"
  ok "project $NS created"
fi

step "2/4 Integrated registry default Route"
if occ get route default-route -n openshift-image-registry >/dev/null 2>&1; then
  ok "registry default Route already exposed"
else
  occ patch configs.imageregistry.operator.openshift.io/cluster --type merge \
    -p '{"spec":{"defaultRoute":true}}' >/dev/null || fail "expose the registry default Route"
  wait_for 120 "registry default Route created" occ get route default-route -n openshift-image-registry
fi
exposed_host="$(occ get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}')"
[[ "$exposed_host" == "$REGISTRY_HOST" ]] \
  || warn "registry route is $exposed_host, not $REGISTRY_HOST -- set REGISTRY_HOST=$exposed_host for build-and-push.sh"
ok "registry reachable at $exposed_host"

step "3/4 SCC: otel-lgtm ServiceAccount -> anyuid (platform tier, pre-provisioned)"
occ apply -n "$NS" -f "$OPENSHIFT_DIR/platform/observability/lgtm-serviceaccount.yaml" >/dev/null \
  || fail "apply platform/observability/lgtm-serviceaccount.yaml"
ok "ServiceAccount lgtm bound to anyuid (used only once install-observability.sh runs)"

if [[ "$INVENTORY_ONLY" == true ]]; then
  step "4/4 Foreign operators/namespaces (inventory only)"
else
  step "4/4 Foreign operators/namespaces"
fi
# This CRC is dedicated to one project while it runs (lgtm-crc convention).
# Flag anything left by another project's unfinished teardown; never remove
# it here without the user's approval -- that is what the --remove-foreign
# flag below is for.
foreign_subs="$(occ get subscriptions.operators.coreos.com -A -o json 2>/dev/null \
  | jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name)"')"
foreign_ns="$(occ get ns --no-headers -o name 2>/dev/null \
  | grep -v -E '^namespace/(openshift|kube-|default$|hostpath-provisioner$)' \
  | grep -vx "namespace/$NS" || true)"
if [[ -z "$foreign_subs" && -z "$foreign_ns" ]]; then
  ok "no foreign operators or namespaces -- CRC is clean"
else
  printf '    note: found on this CRC already (not removed automatically):\n'
  [[ -n "$foreign_subs" ]] && printf '      subscriptions: %s\n' "$foreign_subs"
  [[ -n "$foreign_ns" ]] && printf '      namespaces: %s\n' "$(tr '\n' ' ' <<<"$foreign_ns")"
  if [[ "${REMOVE_FOREIGN:-false}" == true ]]; then
    warn "REMOVE_FOREIGN=true set -- this does not remove anything automatically; run the other project's own teardown.sh instead"
  else
    warn "if this CRC was not freshly torn down by another project, run that project's teardown.sh first (REMOVE_FOREIGN=true does not override this)"
  fi
fi

printf '\n    next: ./openshift/build-and-push.sh, then ./openshift/deploy.sh\n'
