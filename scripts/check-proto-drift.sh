#!/usr/bin/env bash
set -euo pipefail

# Drift guard for the inventory ACL proto (r04/ch.19, extended r07): asserts
# the canonical proto and EVERY vendored copy are byte-identical. Intended to
# be called from CI / pre-commit. Exits non-zero on drift or if any copy is
# missing.
#
# Four copies as of r07 -- one canonical, three vendored:
#   canonical: examples/04-inventory-service/proto/.../inventory.proto
#   vendored:  examples/00-monolith/order/proto/.../inventory.proto      (r04)
#   vendored:  examples/07-order-service/proto/.../inventory.proto       (r07)
#   vendored:  examples/08-graphql-gateway/proto/.../inventory.proto     (r07)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

PROTO_FILE_REL="dev/patterncatalyst/inventory/v1/inventory.proto"
CANONICAL="${ROOT_DIR}/examples/04-inventory-service/proto/${PROTO_FILE_REL}"

declare -A VENDORED=(
  [monolith]="${ROOT_DIR}/examples/00-monolith/order/proto/${PROTO_FILE_REL}"
  [order-service]="${ROOT_DIR}/examples/07-order-service/proto/${PROTO_FILE_REL}"
  [graphql-gateway]="${ROOT_DIR}/examples/08-graphql-gateway/proto/${PROTO_FILE_REL}"
)

if [ ! -f "${CANONICAL}" ]; then
  echo "check-proto-drift: canonical proto missing: ${CANONICAL}" >&2
  exit 1
fi

for name in "${!VENDORED[@]}"; do
  if [ ! -f "${VENDORED[$name]}" ]; then
    echo "check-proto-drift: vendored proto missing (${name}): ${VENDORED[$name]}" >&2
    exit 1
  fi
done

CANONICAL_SHA="$(sha256sum "${CANONICAL}" | awk '{print $1}')"
DRIFTED=0

for name in "${!VENDORED[@]}"; do
  path="${VENDORED[$name]}"
  sha="$(sha256sum "${path}" | awk '{print $1}')"
  if [ "${CANONICAL_SHA}" != "${sha}" ]; then
    echo "check-proto-drift: PROTO DRIFT DETECTED (${name})" >&2
    echo "  canonical (${CANONICAL}): ${CANONICAL_SHA}" >&2
    echo "  vendored  (${path}):  ${sha}" >&2
    echo "Fix: cp '${CANONICAL}' '${path}' && scripts/gen-proto.sh" >&2
    DRIFTED=1
  fi
done

if [ "${DRIFTED}" -ne 0 ]; then
  exit 1
fi

echo "check-proto-drift: OK -- canonical + all ${#VENDORED[@]} vendored copies are byte-identical (${CANONICAL_SHA})"
