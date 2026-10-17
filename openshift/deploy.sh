#!/usr/bin/env bash
#
# deploy.sh -- install or upgrade the mea Helm chart on OpenShift Local and
# wait until every workload has rolled out (plus the bootstrap Job, DRQ-111).
#
#   ./openshift/deploy.sh
#   ./openshift/deploy.sh --set mesh.enabled=true   # extra helm flags
#
# Values set earlier are kept (--reset-then-reuse-values), so
# platform/install-mesh.sh and platform/install-observability.sh can each
# switch on their own flag without clobbering the other's.
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_crc
command -v helm >/dev/null 2>&1 || fail "helm not on PATH"
occ get project "$NS" >/dev/null 2>&1 || fail "project $NS missing: run ./openshift/install-infra.sh first"
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  occ get istag "$name:$IMAGE_TAG" -n "$NS" >/dev/null 2>&1 \
    || fail "image $name:$IMAGE_TAG missing in $NS: run ./openshift/build-and-push.sh"
done
occ get istag "monolith:$IMAGE_TAG" -n "$NS" >/dev/null 2>&1 \
  || fail "image monolith:$IMAGE_TAG missing in $NS: run ./openshift/build-and-push.sh (needed by the bootstrap Job)"

step "helm upgrade --install $RELEASE"
helm upgrade --install "$RELEASE" "$CHART_DIR" \
  --namespace "$NS" --kube-context "$OCP_CONTEXT" --reset-then-reuse-values \
  --set image.tag="$IMAGE_TAG" "$@" \
  || fail "helm upgrade --install failed"
ok "release $RELEASE applied"

step "Waiting for infra (Postgres + Kafka StatefulSets)"
for s in $(occ get statefulset -n "$NS" -l "app.kubernetes.io/part-of=$PROJECT" -o name); do
  occ rollout status "$s" -n "$NS" --timeout=300s >/dev/null || fail "$s not Ready"
  ok "$s Ready"
done

step "Waiting for the mea-bootstrap-public-schema Job"
# A Helm post-install/post-upgrade hook Job -- it runs after the
# StatefulSets and Deployments are created by this same `helm upgrade`, so
# give it the full 300s even though it is usually seconds.
occ wait job/mea-bootstrap-public-schema -n "$NS" --for=condition=complete --timeout=300s >/dev/null \
  || fail "bootstrap Job did not complete (oc logs job/mea-bootstrap-public-schema -n $NS)"
ok "shared public schema present (bootstrap Job complete)"

step "Waiting for the eight app Deployments"
# rollout status, not condition=Available: on an upgrade the old ReplicaSet
# stays Available until the new pods are Ready, so Available passes early.
for d in $(occ get deployment -n "$NS" -l "app.kubernetes.io/part-of=$PROJECT" -o name); do
  occ rollout status "$d" -n "$NS" --timeout=600s >/dev/null || fail "$d did not roll out (oc get pods -n $NS)"
done
ok "all deployments rolled out"

occ get pods -n "$NS" -l "app.kubernetes.io/part-of=$PROJECT" --field-selector=status.phase=Running \
  -o custom-columns='POD:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,UID:.spec.containers[0].securityContext.runAsUser,SCC:.metadata.annotations.openshift\.io/scc'
occ get routes -n "$NS" -o custom-columns='ROUTE:.metadata.name,HOST:.spec.host'
