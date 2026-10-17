#!/usr/bin/env bash
#
# teardown.sh -- return OpenShift Local to a clean state, then stop it.
#
# This CRC is dedicated to mea while it runs, and is cleaned after every
# use, so teardown removes everything the openshift/ scripts added:
#   - the Helm release (the 8 app Deployments, the bootstrap Job, Postgres
#     and Kafka StatefulSets, the mea-infra ServiceAccount, the two Routes,
#     the PeerAuthentications) and the mea project itself (PVCs, ImageStreams);
#   - the platform control planes: Kiali, Istio and IstioCNI, the
#     otel-lgtm Deployment/Service/Route/ServiceAccount (applied directly,
#     outside the Helm release);
#   - every operator (OSSM 3, Kiali, the Red Hat build of OpenTelemetry):
#     Subscription, CSV, InstallPlans, the CRDs each CSV owns, and the
#     operator namespaces.
# Custom resources go while their operator still runs, so no finalizer is
# left waiting on an operator that is already gone.
#
#   ./openshift/teardown.sh                 # clean up, then crc stop
#   ./openshift/teardown.sh --keep-running  # clean up, leave CRC running
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

KEEP_RUNNING=false
[[ "${1:-}" == "--keep-running" ]] && KEEP_RUNNING=true

require_crc
gone() { ! occ get "$@" >/dev/null 2>&1; }
has_crd() { occ get crd "$1" >/dev/null 2>&1; }

# subscription-namespace subscription-name, in removal order (reverse of install)
OPERATORS=(
  "openshift-opentelemetry-operator opentelemetry-product"
  "openshift-operators kiali-ossm"
  "openshift-operators servicemeshoperator3"
)
OPERATOR_NAMESPACES=(openshift-opentelemetry-operator istio-system istio-cni)
PLATFORM_CRDS='\.(istio\.io|sailoperator\.io|kiali\.io|opentelemetry\.io)$'

step "1/7 Platform observability (raw manifests, outside the Helm release)"
if occ get deployment lgtm -n "$NS" >/dev/null 2>&1; then
  occ delete -n "$NS" -f "$OPENSHIFT_DIR/platform/observability/lgtm-service.yaml" --ignore-not-found >/dev/null 2>&1
  occ delete -n "$NS" -f "$OPENSHIFT_DIR/platform/observability/lgtm-deployment.yaml" --ignore-not-found >/dev/null 2>&1
  occ delete -n "$NS" -f "$OPENSHIFT_DIR/platform/observability/otelcol-configmap.yaml" --ignore-not-found >/dev/null 2>&1
  occ delete -n "$NS" -f "$OPENSHIFT_DIR/platform/observability/grafana-datasources-configmap.yaml" --ignore-not-found >/dev/null 2>&1
  ok "otel-lgtm removed"
fi
# The namespace-scoped ServiceAccount/RoleBindings (platform/observability/
# lgtm-serviceaccount.yaml, applied by install-infra.sh) go with the project
# in step 2; its one cluster-scoped object does not.
occ delete clusterrole mea-lgtm-prometheus-sd --ignore-not-found >/dev/null 2>&1

step "2/7 Helm release and project $NS"
if helm status "$RELEASE" -n "$NS" --kube-context "$OCP_CONTEXT" >/dev/null 2>&1; then
  helm uninstall "$RELEASE" -n "$NS" --kube-context "$OCP_CONTEXT" --wait >/dev/null || fail "helm uninstall"
  ok "release $RELEASE uninstalled"
fi
if occ get project "$NS" >/dev/null 2>&1; then
  occ delete project "$NS" --wait=false >/dev/null || fail "delete project"
  wait_for 600 "project $NS deleted" gone namespace "$NS"
else
  ok "no project"
fi

step "3/7 Platform control planes"
has_crd kialis.kiali.io && occ delete kiali --all -n istio-system --wait=true --timeout=300s >/dev/null 2>&1
has_crd istios.sailoperator.io && occ delete istio --all --wait=true --timeout=300s >/dev/null 2>&1
has_crd istiocnis.sailoperator.io && occ delete istiocni --all --wait=true --timeout=300s >/dev/null 2>&1
ok "Kiali, Istio, IstioCNI removed"

step "4/7 Operators"
for entry in "${OPERATORS[@]}"; do
  read -r ns sub <<<"$entry"
  csv="$(occ get subscriptions.operators.coreos.com "$sub" -n "$ns" -o jsonpath='{.status.installedCSV}' 2>/dev/null)"
  occ delete subscriptions.operators.coreos.com "$sub" -n "$ns" --ignore-not-found >/dev/null
  [[ -z "$csv" ]] && continue
  owned="$(occ get csv "$csv" -n "$ns" -o jsonpath='{range .spec.customresourcedefinitions.owned[*]}{.name}{"\n"}{end}' 2>/dev/null)"
  occ delete csv "$csv" -n "$ns" --wait=true >/dev/null 2>&1
  for ip in $(occ get installplan -n "$ns" -o json 2>/dev/null | jq -r --arg c "$csv" '.items[] | select(.spec.clusterServiceVersionNames | index($c)) | .metadata.name'); do
    occ delete installplan "$ip" -n "$ns" >/dev/null 2>&1
  done
  # shellcheck disable=SC2086
  [[ -n "$owned" ]] && occ delete crd $owned --ignore-not-found --wait=true >/dev/null 2>&1
  ok "$csv removed with $(wc -w <<<"$owned") CRD(s)"
done

step "5/7 Remaining CRDs"
crds="$(occ get crd -o name 2>/dev/null | grep -E "$PLATFORM_CRDS" || true)"
# shellcheck disable=SC2086
[[ -n "$crds" ]] && occ delete $crds --wait=true >/dev/null 2>&1
ok "no platform CRDs left"

step "6/7 Operator namespaces"
for ns in "${OPERATOR_NAMESPACES[@]}"; do
  if occ get namespace "$ns" >/dev/null 2>&1; then
    occ delete namespace "$ns" --wait=false >/dev/null
    wait_for 300 "namespace $ns deleted" gone namespace "$ns"
  fi
done

step "7/7 Leftover check"
leftover="$(
  occ get subscriptions.operators.coreos.com -A --no-headers 2>/dev/null
  occ get csv -n openshift-operators --no-headers 2>/dev/null | grep -v -E '^packageserver'
  occ get ns --no-headers -o name 2>/dev/null | grep -v -E '^namespace/(openshift|kube-|default$|hostpath-provisioner$)'
  occ get crd -o name 2>/dev/null | grep -E "$PLATFORM_CRDS"
)"
if [[ -z "$leftover" ]]; then
  ok "CRC is clean"
else
  printf '    note: still present (flag it; remove only with approval if another project left it):\n%s\n' "$leftover"
fi

if [[ "$KEEP_RUNNING" == false ]] && command -v crc >/dev/null 2>&1; then
  step "crc stop"
  if crc stop >/dev/null 2>&1; then
    ok "OpenShift Local stopped"
  else
    fail "crc stop"
  fi
fi
