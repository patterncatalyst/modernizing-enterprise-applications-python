#!/usr/bin/env bash
set -euo pipefail

# Drift guard for the inventory ACL proto (r04/ch.19): asserts the canonical
# proto and its vendored copy on the monolith side are byte-identical.
# Intended to be called from CI / pre-commit. Exits non-zero on drift or if
# either file is missing.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

PROTO_FILE_REL="dev/patterncatalyst/inventory/v1/inventory.proto"
CANONICAL="${ROOT_DIR}/examples/04-inventory-service/proto/${PROTO_FILE_REL}"
VENDORED="${ROOT_DIR}/examples/00-monolith/order/proto/${PROTO_FILE_REL}"

if [ ! -f "${CANONICAL}" ]; then
  echo "check-proto-drift: canonical proto missing: ${CANONICAL}" >&2
  exit 1
fi
if [ ! -f "${VENDORED}" ]; then
  echo "check-proto-drift: vendored proto missing: ${VENDORED}" >&2
  exit 1
fi

CANONICAL_SHA="$(sha256sum "${CANONICAL}" | awk '{print $1}')"
VENDORED_SHA="$(sha256sum "${VENDORED}" | awk '{print $1}')"

if [ "${CANONICAL_SHA}" != "${VENDORED_SHA}" ]; then
  echo "check-proto-drift: PROTO DRIFT DETECTED" >&2
  echo "  canonical (${CANONICAL}): ${CANONICAL_SHA}" >&2
  echo "  vendored  (${VENDORED}):  ${VENDORED_SHA}" >&2
  echo "Fix: cp '${CANONICAL}' '${VENDORED}' && scripts/gen-proto.sh" >&2
  exit 1
fi

echo "check-proto-drift: OK -- proto files are byte-identical (${CANONICAL_SHA})"
