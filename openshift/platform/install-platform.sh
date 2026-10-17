#!/usr/bin/env bash
#
# install-platform.sh -- the whole optional platform tier on top of a
# deployed core: the service mesh, then tracing. Each step is its own
# script and can run alone.
#
#   ./openshift/platform/install-platform.sh
set -uo pipefail
# shellcheck source=../lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
P="$OPENSHIFT_DIR/platform"

require_crc
# Measured on the lgtm-crc reference run with mesh + observability both on.
require_crc_size 12 32768
run() { local start; start=$(date +%s); "$@" || fail "$(basename "$1") failed"; ok "$(basename "$1") done in $(( $(date +%s) - start ))s"; }
run "$P/install-mesh.sh"
run "$P/install-observability.sh"
