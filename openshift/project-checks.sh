# shellcheck shell=bash
# project-checks.sh -- the E2E checkout check for mea (sourced by
# capture-evidence.sh, not run). Drives the exact happy-path payload
# tooling/newman/mea.postman_collection.json's "Scenario 1 -- Happy-Path
# Checkout" uses, through the strangler-proxy Route, and asserts the order
# reaches its terminal CONFIRMED state -- this is the pass/fail the footer's
# `verified` badge depends on (DRQ-104).
#
# Available from capture-evidence.sh: lib.sh helpers (step, ok, fail,
# wait_for), $OUT, https (curl with the ingress CA), in_pod <deploy> <cmd...>
# (oc exec into the service's own container), route_url <route> [ns].
#
# Rules: drive the system only through its Route (the strangler-proxy edge,
# never a port-forward or an in-pod curl that bypasses it); never write a
# secret; the sentinel values (SKU-WIDGET-001, CARD-VISA, a non-SHIP-FAIL
# address) are the same ones the Newman contract suite uses, not invented
# here.

project_checks() {
  local f="$OUT/04-checkout.txt" base order_id status attempt resp

  base="$(route_url strangler-proxy)"
  [[ -n "${base#https://}" ]] || fail "strangler-proxy Route not found"

  step "4/6 Project checks: happy-path checkout through $base"
  : > "$f"

  printf -- '-- POST %s/api/orders\n' "$base" >> "$f"
  resp="$(https -s -o /tmp/mea-order-resp.json -w '%{http_code}' -X POST "$base/api/orders" \
    -H 'Content-Type: application/json' \
    -d '{"customerId": 1, "items": [{"sku": "SKU-WIDGET-001", "quantity": 1}], "paymentMethod": "CARD-VISA", "shippingAddress": "1 Equivalence Suite Way, Testville"}')"
  cat /tmp/mea-order-resp.json >> "$f"
  printf '\nhttp_status=%s\n' "$resp" >> "$f"
  [[ "$resp" == 201 || "$resp" == 202 ]] || fail "POST /api/orders returned $resp, expected 201 or 202 (see $f)"

  order_id="$(jq -r '.id // .orderId // empty' /tmp/mea-order-resp.json)"
  rm -f /tmp/mea-order-resp.json
  [[ -n "$order_id" ]] || fail "no order id in the checkout response (see $f)"
  ok "order $order_id accepted ($resp)"

  step "Polling for the terminal CONFIRMED status"
  status=""
  for attempt in $(seq 1 30); do
    status="$(https -s "$base/api/orders/$order_id" | jq -r '.status // empty')"
    printf 'poll %02d: status=%s\n' "$attempt" "$status" >> "$f"
    [[ "$status" == "CONFIRMED" ]] && break
    [[ "$status" == "PAYMENT_DECLINED" || "$status" == "SHIPPING_FAILED" ]] \
      && fail "order $order_id reached terminal status $status, expected CONFIRMED (see $f)"
    sleep 2
  done
  [[ "$status" == "CONFIRMED" ]] || fail "order $order_id did not reach CONFIRMED within 60s (last status: $status; see $f)"
  ok "order $order_id reached CONFIRMED"

  printf -- '-- GET %s/api/orders/%s (final)\n' "$base" "$order_id" >> "$f"
  https -s "$base/api/orders/$order_id" >> "$f"
  printf '\n' >> "$f"
}
