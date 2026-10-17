#!/usr/bin/env bash
#
# install-observability.sh -- tracing on OpenShift Local. The Red Hat build
# of OpenTelemetry operator is installed and pinned (DRQ-109) for parity
# with the platform tier, but its Instrumentation CR (auto-injecting a
# language agent) is NOT applied here: unlike the Java sibling, this
# project's three traced services (strangler-proxy, inventory-service,
# order-service) already carry their own `opentelemetry-instrument`
# (opentelemetry-distro, zero-code) wrapper in their Containerfile CMD
# (r10/ch.30) -- reusing that wiring keeps the app contract identical
# between minikube and OpenShift, rather than adding a second,
# operator-injected instrumentation path for the same three services. The
# operator's presence is recorded for the pin; its CR is the noted,
# available-but-unused OpenShift-native alternative.
#
# This script deploys grafana/otel-lgtm:0.36.0 (the same all-in-one image as
# ch.30's minikube backend) as a plain Deployment under
# platform/observability/, exposes it with a Grafana Route, and flips the
# chart's observability.otlp.enabled flag so the three services point their
# OTEL_EXPORTER_OTLP_ENDPOINT at it.
#
#   ./openshift/platform/install-observability.sh
set -uo pipefail
# shellcheck source=../lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
PLATFORM="$OPENSHIFT_DIR/platform"

OTEL_CSV="opentelemetry-operator.v0.158.0-2"

require_crc
helm status "$RELEASE" -n "$NS" --kube-context "$OCP_CONTEXT" >/dev/null 2>&1 || fail "core not deployed: run deploy.sh first"

step "1/4 Red Hat build of OpenTelemetry operator (pinned, CR not applied -- see header)"
install_operator "$PLATFORM/subscriptions/opentelemetry-subscription.yaml" openshift-opentelemetry-operator \
  opentelemetry-product "$OTEL_CSV"

step "2/4 otel-lgtm (anyuid, runAsUser:0 only -- no seccompProfile, or admission flips back to restricted-v2)"
occ apply -n "$NS" -f "$PLATFORM/observability/lgtm-serviceaccount.yaml" >/dev/null || fail "apply lgtm-serviceaccount.yaml"
occ apply -n "$NS" -f "$PLATFORM/observability/otelcol-configmap.yaml" >/dev/null || fail "apply otelcol-configmap.yaml"
occ apply -n "$NS" -f "$PLATFORM/observability/grafana-datasources-configmap.yaml" >/dev/null || fail "apply grafana-datasources-configmap.yaml"
occ apply -n "$NS" -f "$PLATFORM/observability/lgtm-deployment.yaml" >/dev/null || fail "apply lgtm-deployment.yaml"
occ apply -n "$NS" -f "$PLATFORM/observability/lgtm-service.yaml" >/dev/null || fail "apply lgtm-service.yaml"
occ rollout status deployment/lgtm -n "$NS" --timeout=600s >/dev/null || fail "otel-lgtm not Ready"
ok "otel-lgtm Ready (SCC $(occ get pod -n "$NS" -l app.kubernetes.io/name=lgtm -o jsonpath='{.items[0].metadata.annotations.openshift\.io/scc}'))"

step "3/4 Flip observability.otlp.enabled on the 3 instrumented services"
"$OPENSHIFT_DIR/deploy.sh" --set observability.otlp.enabled=true >/dev/null \
  || fail "deploy.sh with observability.otlp.enabled failed"
for d in strangler-proxy inventory-service order-service; do
  # OTEL_SDK_DISABLED / OTEL_EXPORTER_OTLP_ENDPOINT come from the mea-app-config
  # ConfigMap via envFrom; a ConfigMap change does not restart running pods, so
  # the flip only takes effect after an explicit rollout restart.
  occ rollout restart "deployment/$d" -n "$NS" >/dev/null || fail "$d rollout restart failed"
  occ rollout status "deployment/$d" -n "$NS" --timeout=300s >/dev/null || fail "$d did not roll out"
done
ok "strangler-proxy/inventory-service/order-service now export OTLP to lgtm.$NS.svc.cluster.local:4317"

step "4/4 Kiali -> otel-lgtm Prometheus"
if occ get kiali kiali -n istio-system >/dev/null 2>&1; then
  # OpenShift Local runs no user-workload Prometheus. With the mesh on, the
  # otelcol in otel-lgtm scrapes the sidecars (port 15090, see
  # otelcol-configmap.yaml's prometheus/istio-mesh job), so point Kiali at
  # its bundled Prometheus (:9090) instead.
  occ patch kiali kiali -n istio-system --type merge -p \
    "{\"spec\":{\"external_services\":{\"prometheus\":{\"enabled\":true,\"url\":\"http://lgtm.$NS.svc.cluster.local:9090\"}}}}" >/dev/null \
    || fail "patch Kiali"
  sleep 10
  occ rollout status deployment/kiali -n istio-system --timeout=300s >/dev/null || fail "Kiali not Ready after the patch"
  ok "Kiali uses http://lgtm.$NS.svc.cluster.local:9090"
else
  ok "mesh not installed -- Kiali/Prometheus wiring skipped (run install-mesh.sh first for that)"
fi
printf '\n    Grafana: https://%s\n' "$(occ get route grafana -n "$NS" -o jsonpath='{.spec.host}' 2>/dev/null || echo 'no Route -- see platform/observability/lgtm-service.yaml')"
