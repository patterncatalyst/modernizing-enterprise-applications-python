#!/usr/bin/env bash
#
# install-mesh.sh -- OpenShift Service Mesh 3 for the mea project: the OSSM
# 3 and Kiali operators, the IstioCNI and Istio control plane (pinned to
# v1.30.5, DRQ-109), and the chart's mesh flag (native sidecars via the
# istio.io/rev pod-template LABEL -- Sail's revisioned webhook ignores the
# classic sidecar.istio.io/inject annotation the minikube path uses --
# STRICT mTLS by default, PERMISSIVE for the two Route-facing services).
#
#   ./openshift/platform/install-mesh.sh
set -uo pipefail
# shellcheck source=../lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
PLATFORM="$OPENSHIFT_DIR/platform"

# Newest CSVs in their channels at plan time (2026-10-17); re-check before a
# live run:
#   oc get packagemanifest servicemeshoperator3 -n openshift-marketplace \
#     -o jsonpath='{range .status.channels[*]}{.name}  {.currentCSV}{"\n"}{end}'
OSSM_CSV="servicemeshoperator3.v3.4.3"
KIALI_CSV="kiali-operator.v2.27.5"

require_crc
helm status "$RELEASE" -n "$NS" --kube-context "$OCP_CONTEXT" >/dev/null 2>&1 || fail "core not deployed: run deploy.sh first"

step "1/4 Operators"
install_operator "$PLATFORM/subscriptions/servicemesh3-subscription.yaml" openshift-operators servicemeshoperator3 "$OSSM_CSV"
install_operator "$PLATFORM/subscriptions/kiali-subscription.yaml" openshift-operators kiali-ossm "$KIALI_CSV"

step "2/4 Istio control plane"
occ apply -f "$PLATFORM/mesh/istio.yaml" >/dev/null || fail "apply Istio/IstioCNI"
occ wait istiocni/default --for=condition=Ready --timeout=300s >/dev/null || fail "IstioCNI not Ready"
ok "IstioCNI Ready"
occ wait istio/default --for=condition=Ready --timeout=600s >/dev/null || fail "Istio not Ready"
ok "Istio $(occ get istio default -o jsonpath='{.spec.version}') Ready (revision $(occ get istio default -o jsonpath='{.status.activeRevisionName}'))"

step "3/4 Sidecars and mTLS"
"$OPENSHIFT_DIR/deploy.sh" --set mesh.enabled=true >/dev/null || fail "deploy.sh with mesh.enabled failed"
ok "release upgraded with mesh.enabled=true"

step "4/4 Kiali"
sed "s/__NAMESPACE__/$NS/g" "$PLATFORM/mesh/kiali.yaml" | occ apply -f - >/dev/null || fail "apply Kiali"
wait_for 600 "Kiali deployment created" occ get deployment kiali -n istio-system
occ rollout status deployment/kiali -n istio-system --timeout=600s >/dev/null || fail "Kiali not Ready"
ok "Kiali https://$(occ get route kiali -n istio-system -o jsonpath='{.spec.host}')"
printf '\n    next: ./openshift/platform/install-observability.sh (Kiali needs its Prometheus)\n'
