#!/usr/bin/env bash
# ch.31 -- Supply-chain gate: SBOM + CVE scan + policy-as-code, scanning
# built container images (the real deployable artifact for every service in
# this project -- see deploy/k8s). A `uv.lock`-only scan would miss UBI
# base-layer CVEs; scanning the image catches both layers.
#
# For the GATING target (order-service, the "after") this script:
#   1. builds the image from its Containerfile,
#   2. generates a CycloneDX SBOM with syft,
#   3. scans that SBOM with grype against the current vulnerability DB, and
#   4. applies the policy-as-code threshold (fail-on) from policy.yaml --
#      a breach here fails this script (exit 1), exactly like CI.
#
# The frozen examples/00-monolith "before" image is built and scanned the
# same three steps, but NON-GATING (policy.yaml: gate: reported): its
# findings are tallied and written to evidence/ alongside order-service's,
# but a breach there can never fail this script or the supply-chain.yml CI
# job. It produces comparative "before" evidence; it is not meant to be
# remediated -- the monolith is frozen. Its build+scan also runs inside a
# subshell so an unexpected non-zero exit there (a flaky build, a grype
# hiccup) can't abort the run that still needs to report the gating target.
# See policy.yaml for the required/reported split (A/B-4 = B, DRQ-088).
#
# These are deliberately the *same* steps the CI workflow
# (.github/workflows/supply-chain.yml) runs, so "it passed locally" and "it
# passed in CI" mean the same thing.
#
# Prereqs: syft, grype, jq, and a container builder (podman or docker) on
# PATH. See README.md.
set -uo pipefail

cd "$(dirname "$0")" || exit 2
REPO_ROOT="$(cd ../.. && pwd)"
EVIDENCE="evidence"
mkdir -p "$EVIDENCE"

for tool in syft grype jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "FATAL: '$tool' not on PATH -- see README.md (Prerequisites)"; exit 2; }
done

# Prefer docker: that's what supply-chain.yml builds with on a standard
# GitHub Actions runner, so local == CI for the builder too. Rootless podman
# works here as a fallback, but its user-namespace UID remap can leave a
# non-root USER's WORKDIR looking root-owned once a layer is committed and
# re-run (a rootless-podman/idmapped-mounts environment quirk, not a defect
# in the Containerfile/Dockerfile) -- if that happens, use docker instead.
BUILDER=""
if command -v docker >/dev/null 2>&1; then
  BUILDER="docker"
elif command -v podman >/dev/null 2>&1; then
  BUILDER="podman"
else
  echo "FATAL: neither 'docker' nor 'podman' on PATH -- see README.md (Prerequisites)"
  exit 2
fi
echo "Builder: $BUILDER"

# --- read policy.yaml without a YAML dependency (small, fixed shape) --------
FAIL_ON="$(grep -E '^fail-on:' policy.yaml | awk '{print $2}')"
echo "Policy: fail the GATING target(s) on >= ${FAIL_ON}   (source: policy.yaml)"
echo "grype DB: $(grype db status 2>/dev/null | awk -F': +' '/^Built/{print $2}')"
echo

summary="$EVIDENCE/summary.txt"
: > "$summary"
gate_failed=0

# Builds one target's image, generates its SBOM, scans it, tallies findings
# by severity, and prints/records the verdict. Sets the global $gate_failed
# to 1 only when a "required" (gating) target breaches fail-on; a "reported"
# (non-gating) breach is tallied and labeled but never trips $gate_failed.
scan_target() {
  local name="$1" kind="$2" gate="$3" buildfile="$4" context="$5" image="$6"
  echo "=== [$kind/$gate] $name -> $image ==="

  local buildlog
  buildlog="$(mktemp)"
  if ! "$BUILDER" build -q -f "$REPO_ROOT/$buildfile" -t "$image" "$REPO_ROOT/$context" >"$buildlog" 2>&1; then
    echo "  BUILD FAILED ($buildfile) -- see $buildlog"
    printf '%-14s [%-6s/%-8s] BUILD FAILED\n' "$name" "$kind" "$gate" >> "$summary"
    if [ "$gate" = "required" ]; then
      gate_failed=1
    else
      echo "  (non-gating target -- build failure reported, does not block the gate)"
    fi
    echo
    return 0
  fi
  rm -f "$buildlog"

  local sbom="$EVIDENCE/${name}.sbom.cdx.json"
  local scan="$EVIDENCE/${name}.grype.json"

  # 1. SBOM -- CycloneDX JSON, the portable bill of materials, read straight
  #    from the image in the same engine's local storage used to build it
  #    (no registry push/pull needed for this local demo loop).
  syft "${BUILDER}:${image}" -o "cyclonedx-json=$sbom" -q

  # 2. scan the SBOM (not the image again) -- the SBOM is the contract.
  grype "sbom:$sbom" -o json -q > "$scan"

  # 3. tally by severity and apply the policy.
  local crit high med components
  crit="$(jq '[.matches[]|select(.vulnerability.severity=="Critical")]|length' "$scan")"
  high="$(jq '[.matches[]|select(.vulnerability.severity=="High")]|length' "$scan")"
  med="$(jq '[.matches[]|select(.vulnerability.severity=="Medium")]|length' "$scan")"
  components="$(jq '.components | length' "$sbom")"

  local breach=0
  if { [ "$FAIL_ON" = "High" ] && { [ "$crit" -gt 0 ] || [ "$high" -gt 0 ]; }; } \
     || { [ "$FAIL_ON" = "Critical" ] && [ "$crit" -gt 0 ]; }; then
    breach=1
  fi

  local verdict="PASS"
  if [ "$breach" -eq 1 ]; then
    verdict="FAIL"
    if [ "$gate" = "required" ]; then
      gate_failed=1
    fi
  fi

  printf '  components=%s  Critical=%s  High=%s  Medium=%s  -> %s\n' \
    "$components" "$crit" "$high" "$med" "$verdict"
  if [ "$breach" -eq 1 ] && [ "$gate" = "reported" ]; then
    echo "  (this is the expected 'before' result demonstrating the gate firing -- non-gating, does not block the pipeline)"
  fi
  printf '%-14s [%-6s/%-8s] components=%-4s Critical=%-2s High=%-2s Medium=%-2s %s\n' \
    "$name" "$kind" "$gate" "$components" "$crit" "$high" "$med" "$verdict" >> "$summary"
  echo
}

# Runs scan_target for one target, isolating "reported" (non-gating) targets
# in a subshell: any unexpected non-zero exit there (not just a policy
# breach -- a tool hiccup) is swallowed so it can never abort the run before
# the gating target has been scanned and reported.
run_target() {
  local gate="$3"
  if [ "$gate" = "reported" ]; then
    ( scan_target "$@" ) || echo "  (non-gating target hit an unexpected error -- reported, does not block the gate)"
  else
    scan_target "$@"
  fi
}

# --- parse policy.yaml's targets: list (small, fixed shape; no YAML dep) ----
name="" kind="" gate="" buildfile="" context="" image=""

flush() {
  [ -n "$name" ] && run_target "$name" "$kind" "$gate" "$buildfile" "$context" "$image"
}

while IFS= read -r line; do
  case "$line" in
    *"- name:"*)    flush; name="$(echo "$line" | awk '{print $3}')"; kind=""; gate=""; buildfile=""; context=""; image="" ;;
    *"kind:"*)      kind="$(echo "$line" | awk '{print $2}')" ;;
    *"gate:"*)      gate="$(echo "$line" | awk '{print $2}')" ;;
    *"buildfile:"*) buildfile="$(echo "$line" | awk '{print $2}')" ;;
    *"context:"*)   context="$(echo "$line" | awk '{print $2}')" ;;
    *"image:"*)     image="$(echo "$line" | awk '{print $2}')" ;;
  esac
done < <(sed -n '/^targets:/,$p' policy.yaml)
flush

echo "===================== gate summary ====================="
cat "$summary"
echo "==========================================================="
if [ "$gate_failed" -ne 0 ]; then
  echo "GATE: FAIL -- a GATING target breached policy (fail-on: ${FAIL_ON})."
  exit 1
fi
echo "GATE: PASS -- every GATING target is within policy."
echo "(Non-gating 'before' evidence, if any, is reported above and in evidence/ -- it never blocks this gate.)"
