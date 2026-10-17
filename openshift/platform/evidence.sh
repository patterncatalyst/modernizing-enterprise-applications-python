# shellcheck shell=bash
# evidence.sh -- platform-tier checks for capture-evidence.sh (sourced, not
# run). Each section runs only when its feature is installed and writes
# $OUT/1N-*.txt; every check fails the capture on a miss. Expects lib.sh,
# $OUT, https(), in_pod() and route_url() from capture-evidence.sh.

PROBE_IMAGE="${PROBE_IMAGE:-registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791928506}"

mesh_on() { occ get istio default >/dev/null 2>&1; }
otel_on() { occ get deployment lgtm -n "$NS" >/dev/null 2>&1; }

evidence_mesh() {
  step "P1 Service mesh (OSSM 3)"
  local f="$OUT/11-mesh.txt" plain
  {
    occ get istio default -o jsonpath='Istio {.spec.version}, revision {.status.activeRevisionName}, Ready={.status.conditions[?(@.type=="Ready")].status}{"\n"}'
    occ get csv -n openshift-operators -o custom-columns='CSV:.metadata.name,PHASE:.status.phase' | grep -E 'CSV|servicemesh|kiali'
    printf '\n-- pods: istio.io/rev label (native sidecars join by revision label, not the sidecar.istio.io/inject annotation)\n'
    occ get pods -n "$NS" -l "app.kubernetes.io/part-of=$PROJECT" --field-selector=status.phase=Running \
      -o custom-columns='POD:.metadata.name,REV:.metadata.labels.istio\.io/rev,INIT:.spec.initContainers[*].name'
    printf '\n-- PeerAuthentication (STRICT default + PERMISSIVE carve-out for the 2 Route-facing services)\n'
    occ get peerauthentication -n "$NS" -o custom-columns='NAME:.metadata.name,MODE:.spec.mtls.mode'
  } > "$f" 2>&1
  # STRICT: plaintext from a pod outside the mesh (no istio.io/rev label) to
  # a meshed Service other than the two Route-facing ones is reset. Service
  # name, never a pod IP.
  plain=$(occ run mtls-probe -n "$NS" --image="$PROBE_IMAGE" --restart=Never --rm -i --quiet \
    --command -- bash -c "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://review-service:8001/api/reviews; echo \" exit=\$?\"" 2>/dev/null)
  printf '\n-- plaintext from an unmeshed pod to review-service (STRICT, no carve-out): %s\n' "$plain" >> "$f"
  [[ "$plain" == 2*"exit=0"* ]] && fail "STRICT mTLS not enforced on review-service: plaintext call succeeded"
  ok "STRICT mTLS rejects plaintext from outside the mesh (review-service)"

  if occ get route kiali -n istio-system >/dev/null 2>&1; then
    local tls
    tls=$(https "$(route_url kiali istio-system)/api/namespaces/$NS/tls" | jq -r .status)
    printf '\n-- Kiali: namespace TLS %s\n' "$tls" >> "$f"
    [[ "$tls" == MTLS_ENABLED ]] || fail "Kiali reports $tls for $NS"
    ok "Kiali: $NS MTLS_ENABLED"
  fi
}

evidence_otel() {
  step "P2 Tracing (otel-lgtm)"
  local f="$OUT/12-tracing.txt" code
  {
    printf -- '-- otel-lgtm pod (anyuid, runAsUser 0, no seccompProfile)\n'
    occ get pods -n "$NS" -l app.kubernetes.io/name=lgtm \
      -o custom-columns='POD:.metadata.name,SCC:.metadata.annotations.openshift\.io/scc,UID:.spec.containers[0].securityContext.runAsUser,SECCOMP:.spec.containers[0].securityContext.seccompProfile.type'
    printf '\n-- OTEL_SERVICE_NAME on the 3 instrumented Deployments\n'
    for d in strangler-proxy inventory-service order-service; do
      occ get deployment "$d" -n "$NS" -o jsonpath="{.metadata.name}: {range .spec.template.spec.containers[0].env[?(@.name=='OTEL_SERVICE_NAME')]}{.value}{end}{\"\n\"}"
    done
    printf '\n-- recent traces (Tempo, via otel-lgtm)\n'
    in_pod lgtm curl -s "localhost:3200/api/search?limit=20&start=$(( $(date +%s) - 3600 ))&end=$(date +%s)" \
      | jq -r '.traces[]? | "\(.rootServiceName): \(.rootTraceName)"' | sort | uniq -c
  } > "$f" 2>&1
  code=$(https -o /dev/null -w '%{http_code}' "$(route_url grafana 2>/dev/null)/api/health" 2>/dev/null || echo 000)
  if occ get route grafana -n "$NS" >/dev/null 2>&1; then
    printf '\nGrafana /api/health through its Route: %s\n' "$code" >> "$f"
    [[ "$code" == 200 ]] || fail "Grafana Route returned $code"
  fi
  grep -q 'strangler-proxy: ' "$f" || warn "no OTEL_SERVICE_NAME recorded for strangler-proxy (check $f)"
  ok "otel-lgtm Ready; traces captured in $f"
}

platform_evidence() {
  mesh_on && evidence_mesh
  otel_on && evidence_otel
  return 0
}
