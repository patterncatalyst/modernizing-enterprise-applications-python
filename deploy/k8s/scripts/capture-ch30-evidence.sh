#!/usr/bin/env bash
# deploy/k8s/scripts/capture-ch30-evidence.sh -- drive a handful of
# synchronous checkouts against a LIVE `mea` mesh and capture the 3 files
# ch.30's footer cites as evidence, into deploy/k8s/observability/evidence/:
#
#   ch30-hero-trace.json   -- one Tempo trace spanning strangler-proxy ->
#                              order-service -> inventory-service (gRPC).
#   ch30-istioctl-mtls.txt -- istioctl's mTLS description of an order-service
#                              pod, plus the `kubectl get pods` 2/2 column.
#   ch30-metrics.txt       -- istio_requests_total for order-/inventory-
#                              service, queried from Mimir (Prometheus-
#                              compatible) via svc/lgtm.
#
# Run AFTER the full ch.30 bring-up: setup-profile.sh, install-istio.sh,
# build-images.sh, deploy.sh -- this script only reads from that already-live
# cluster, it does not install or deploy anything itself.
#
# Every capture is real or absent: a step that cannot find its evidence
# writes a `*.MISSING.txt` explaining what to retry and this script exits
# non-zero. Nothing here fabricates a trace ID, a metrics value, or
# istioctl output.
#
# Usage:
#   deploy/k8s/scripts/capture-ch30-evidence.sh
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

EVIDENCE_DIR="$REPO_ROOT/deploy/k8s/observability/evidence"
EDGE_URL="http://127.0.0.1:30888"
CHECKOUT_COUNT=5

# Happy-path checkout body, taken verbatim from
# tooling/newman/mea.postman_collection.json, "Scenario 1 -- Happy-Path
# Checkout" / "1b. Checkout in-stock" (also mirrored by the Order/
# Notification Context Contract requests in the same collection). SKU-
# WIDGET-001 is seeded stock, CARD-VISA is the non-sentinel payment method,
# and the address carries neither the DECLINE nor SHIP-FAIL sentinel the
# same collection uses for its negative scenarios.
CHECKOUT_BODY='{
  "customerId": 1,
  "items": [ { "sku": "SKU-WIDGET-001", "quantity": 1 } ],
  "paymentMethod": "CARD-VISA",
  "shippingAddress": "1 Evidence Capture Way, Testville"
}'

mtls_file="$EVIDENCE_DIR/ch30-istioctl-mtls.txt"
metrics_file="$EVIDENCE_DIR/ch30-metrics.txt"
trace_file="$EVIDENCE_DIR/ch30-hero-trace.json"

missing() {
  # missing <file-stem> <reason...> -- write a *.MISSING.txt note instead of
  # a fabricated evidence file, and remember to fail at the end.
  local stem="$1"; shift
  local note="$EVIDENCE_DIR/${stem}.MISSING.txt"
  {
    printf 'Capture failed: %s\n\n' "$stem"
    printf '%s\n' "$@"
    printf '\nRe-run: deploy/k8s/scripts/capture-ch30-evidence.sh\n'
  } >"$note"
  echo "  wrote $note" >&2
  had_failure=1
}

had_failure=0

# Query Tempo/Mimir from INSIDE the cluster -- NO port-forward. The lgtm pod
# is unmeshed and carries curl; exec a curl there against its own localhost
# (Tempo :3200, Mimir :9090). Args are passed straight to curl. The only
# host-reachable endpoint this script uses is the strangler-proxy NodePort
# (30888) for the checkouts; everything else is in-cluster exec.
lgtm_exec() { kc -n "$NAMESPACE" exec "deploy/lgtm" -- curl -sS --max-time 20 "$@"; }

mkdir -p "$EVIDENCE_DIR"

require_tool kubectl ""
require_tool istioctl "Install istioctl -- see deploy/k8s/scripts/install-istio.sh's header for the pinned version."
require_tool curl ""
require_tool jq "Install jq -- used to parse Tempo/Prometheus JSON responses."

step "Checking the mea profile is reachable"
require_profile_running
kc -n "$NAMESPACE" get namespace >/dev/null 2>&1 \
  || fail "namespace $NAMESPACE not found. Run deploy/k8s/scripts/deploy.sh first."

not_ready="$(kc -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
  | awk '{split($2,a,"/"); if (a[1] != a[2]) print $1}')"
if [[ -n "$not_ready" ]]; then
  fail "these pods are not fully Ready (expect 2/2 once the mesh is up): ${not_ready//$'\n'/, }. Run deploy/k8s/scripts/deploy.sh and wait for rollout, then retry."
fi
ok "all pods in $NAMESPACE report every container Ready"

step "Driving $CHECKOUT_COUNT synchronous checkouts through $EDGE_URL/api/orders"
for i in $(seq 1 "$CHECKOUT_COUNT"); do
  code="$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST "$EDGE_URL/api/orders" \
    -H 'Content-Type: application/json' \
    -d "$CHECKOUT_BODY" || echo "curl-failed")"
  echo "  checkout $i: HTTP $code"
done

step "Sleeping 30s so spans flush to Tempo (ingester -> queryable) and the otelcol scrape cycles for metrics"
sleep 30

step "Capturing mTLS evidence (istioctl + pod READY column)"
order_pod="$(kc -n "$NAMESPACE" get pod -l app.kubernetes.io/name=order-service \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$order_pod" ]]; then
  missing "ch30-istioctl-mtls" \
    "No pod found with label app.kubernetes.io/name=order-service in namespace $NAMESPACE." \
    "Confirm deploy.sh completed: kubectl --context $PROFILE -n $NAMESPACE get pods"
else
  {
    printf '# istioctl x describe pod -n %s %s\n\n' "$NAMESPACE" "$order_pod"
    istioctl x describe pod -n "$NAMESPACE" "$order_pod" 2>&1 || true
    printf '\n# istioctl authn tls-check %s.%s (best-effort; not all Istio versions ship this subcommand)\n\n' "$order_pod" "$NAMESPACE"
    istioctl authn tls-check "${order_pod}.${NAMESPACE}" 2>&1 || true
    printf '\n# kubectl --context %s -n %s get pods (2/2 READY = app + istio-proxy sidecar)\n\n' "$PROFILE" "$NAMESPACE"
    kc -n "$NAMESPACE" get pods
  } >"$mtls_file"
  ok "wrote $mtls_file"
fi

step "Capturing istio_requests_total from Mimir (in-cluster svc/lgtm:9090, no port-forward)"
prom_query='istio_requests_total{destination_service=~"order-service.*|inventory-service.*"}'
prom_response=""
prom_path=""
for path in "/prometheus/api/v1/query" "/api/v1/query"; do
  resp="$(lgtm_exec -G "http://localhost:9090${path}" --data-urlencode "query=${prom_query}" || true)"
  if [[ -n "$resp" ]] && jq -e '.status == "success"' >/dev/null 2>&1 <<<"$resp"; then
    prom_response="$resp"
    prom_path="$path"
    break
  fi
done

if [[ -z "$prom_response" ]]; then
  missing "ch30-metrics" \
    "Neither /prometheus/api/v1/query nor /api/v1/query returned a successful response from svc/lgtm:9090." \
    "Confirm the otelcol prometheus/istio-mesh receiver has scraped at least once (it runs on an interval -- wait a minute and retry) and that lgtm-deployment.yaml's Mimir path prefix hasn't changed." \
    "Manual check (no port-forward): kubectl --context $PROFILE -n $NAMESPACE exec deploy/lgtm -- curl -sG http://localhost:9090/prometheus/api/v1/query --data-urlencode 'query=${prom_query}'"
else
  result_count="$(jq -r '.data.result | length' <<<"$prom_response")"
  if [[ "$result_count" == "0" ]]; then
    missing "ch30-metrics" \
      "Query succeeded via ${prom_path} but returned zero series for: ${prom_query}" \
      "The checkouts this script just drove may not have produced mesh traffic yet, or order-service/inventory-service aren't meshed (check the 2/2 READY column in ch30-istioctl-mtls.txt). Wait for the next otelcol scrape interval and retry."
  else
    {
      printf '# query path: %s\n' "$prom_path"
      printf '# query: %s\n\n' "$prom_query"
      jq '.' <<<"$prom_response"
    } >"$metrics_file"
    ok "wrote $metrics_file (via ${prom_path}, ${result_count} series)"
  fi
fi

step "Capturing the hero trace from Tempo (in-cluster svc/lgtm:3200, no port-forward)"
# The checkout trace is rooted at strangler-proxy's POST server span. A plain
# recency/tag search is swamped by the OutboxRelay + SagaConsumer background
# DB-op traces (each asyncpg poll is its own root trace), so target the request
# trace directly with TraceQL, then keep the newest candidate that spans all
# three services.
search_response="$(lgtm_exec -G 'http://localhost:3200/api/search' \
  --data-urlencode 'q={ name =~ "POST.*" && rootServiceName = "strangler-proxy.mea" }' \
  --data-urlencode 'limit=20' || true)"

trace_id=""
if [[ -n "$search_response" ]] && jq -e '.traces' >/dev/null 2>&1 <<<"$search_response"; then
  # Each candidate needs its own /api/traces/<id> fetch to confirm its span
  # service set (the search response doesn't carry per-trace service names).
  candidate_ids="$(jq -r '.traces[].traceID' <<<"$search_response")"
  while read -r candidate; do
    [[ -z "$candidate" ]] && continue
    candidate_trace="$(lgtm_exec "http://localhost:3200/api/traces/${candidate}" || true)"
    [[ -z "$candidate_trace" ]] && continue
    # Recursive-descent extraction (rather than a fixed `.batches[]...` or
    # `.resourceSpans[]...` path) so this survives the OTLP-JSON shape
    # differences between Tempo versions the capture is run against.
    services="$(jq -r '[.. | objects | select(has("key") and .key=="service.name") | .value.stringValue] | unique | join(",")' <<<"$candidate_trace" 2>/dev/null || true)"
    if [[ "$services" == *strangler-proxy* && "$services" == *order-service* && "$services" == *inventory-service* ]]; then
      trace_id="$candidate"
      printf '%s' "$candidate_trace" | jq '.' >"$trace_file"
      break
    fi
  done <<<"$candidate_ids"
fi

if [[ -z "$trace_id" ]]; then
  missing "ch30-hero-trace" \
    "No POST trace rooted at strangler-proxy (also spanning order-service + inventory-service) found in Tempo." \
    "The 3 instrumented services must export (OTEL_SDK_DISABLED=false, OTEL_EXPORTER_OTLP_ENDPOINT -> svc/lgtm:4317) and a checkout must have run and flushed (ingester -> queryable can lag ~30s)." \
    "Manual check (no port-forward):" \
    "  kubectl --context $PROFILE -n $NAMESPACE exec deploy/lgtm -- curl -sG 'http://localhost:3200/api/search' --data-urlencode 'q={ name =~ \"POST.*\" && rootServiceName = \"strangler-proxy.mea\" }' | jq ." \
    "  then: kubectl ... exec deploy/lgtm -- curl -s http://localhost:3200/api/traces/<traceID> | jq . > $trace_file"
fi

step "Summary"
for f in "$trace_file" "$mtls_file" "$metrics_file"; do
  if [[ -f "$f" ]]; then
    printf '  %s (%s bytes)\n' "$f" "$(wc -c <"$f" | tr -d ' ')"
  else
    stem="${f%.*}"
    printf '  MISSING: %s -- see %s.MISSING.txt\n' "$f" "$stem"
  fi
done
if [[ -n "$trace_id" ]]; then
  printf '  trace ID: %s\n' "$trace_id"
fi

if [[ "$had_failure" -ne 0 ]]; then
  fail "one or more evidence files could not be captured -- see the *.MISSING.txt notes above, fix the cause, and re-run."
fi

printf '\nHand these 3 files back for ch.30: %s, %s, %s\n' "$trace_file" "$mtls_file" "$metrics_file"
