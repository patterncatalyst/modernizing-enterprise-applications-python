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
fwd_pids=()

cleanup() {
  for pid in "${fwd_pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

start_port_forward() {
  # start_port_forward <svc> <local-port>:<remote-port> <log-file> -- start a
  # background `kubectl port-forward`, block until the local port accepts a
  # connection (or fail), and record the pid for cleanup on exit.
  local svc="$1" ports="$2" log="$3"
  local local_port="${ports%%:*}"
  kc -n "$NAMESPACE" port-forward "svc/${svc}" "$ports" >"$log" 2>&1 &
  local pid=$!
  fwd_pids+=("$pid")
  for _ in $(seq 1 30); do
    (exec 3<>"/dev/tcp/127.0.0.1/${local_port}") 2>/dev/null && { exec 3>&-; return 0; }
    sleep 1
  done
  fail "port-forward svc/${svc} ${ports} never came up -- see ${log}"
}

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

step "Sleeping 10s so spans flush to Tempo and the otelcol scrape cycles for metrics"
sleep 10

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

step "Capturing istio_requests_total from Mimir (svc/lgtm:9090)"
start_port_forward lgtm 19090:9090 /tmp/mea-evidence-prometheus-portforward.log

prom_query='istio_requests_total{destination_service=~"order-service.*|inventory-service.*"}'
prom_response=""
prom_path=""
for path in "/prometheus/api/v1/query" "/api/v1/query"; do
  resp="$(curl -sG "http://127.0.0.1:19090${path}" --data-urlencode "query=${prom_query}" || true)"
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
    "Manual check: kubectl --context $PROFILE -n $NAMESPACE port-forward svc/lgtm 9090:9090, then curl both path prefixes yourself."
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

step "Capturing the hero trace from Tempo (svc/lgtm:3200)"
start_port_forward lgtm 13200:3200 /tmp/mea-evidence-tempo-portforward.log

search_response="$(curl -sG 'http://127.0.0.1:13200/api/search' \
  --data-urlencode 'tags=service.name=order-service' \
  --data-urlencode 'limit=20' || true)"

trace_id=""
if [[ -n "$search_response" ]] && jq -e '.traces' >/dev/null 2>&1 <<<"$search_response"; then
  # Walk candidate traces newest-first and keep the first one whose own
  # trace payload shows spans from all three services in the synchronous
  # path -- the search response alone doesn't carry per-trace span service
  # names, so each candidate needs its own /api/traces/<id> fetch to check.
  candidate_ids="$(jq -r '.traces[].traceID' <<<"$search_response")"
  while read -r candidate; do
    [[ -z "$candidate" ]] && continue
    candidate_trace="$(curl -s "http://127.0.0.1:13200/api/traces/${candidate}" || true)"
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
    "No trace found in the last 20 Tempo search results for service.name=order-service that also includes spans from strangler-proxy and inventory-service." \
    "Tempo's search API response shape can differ by version -- inspect it by hand:" \
    "  kubectl --context $PROFILE -n $NAMESPACE port-forward svc/lgtm 3200:3200" \
    "  curl -sG 'http://127.0.0.1:3200/api/search' --data-urlencode 'tags=service.name=order-service' --data-urlencode 'limit=20' | jq ." \
    "Then fetch the chosen trace: curl -s http://127.0.0.1:3200/api/traces/<traceID> | jq . > $trace_file" \
    "If the result set is empty, the checkouts this script drove may not have flushed to Tempo yet -- wait and retry, or confirm OTEL_EXPORTER_OTLP_ENDPOINT points at svc/lgtm (base/app-config.yaml)."
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
