#!/usr/bin/env bash
# ch.31 -- Supply-chain gate: SBOM + CVE scan + policy-as-code, scanning
# built container images (the real deployable artifact for every service in
# this project -- see deploy/k8s). A `uv.lock`-only scan would miss UBI
# base-layer CVEs; scanning the image catches both layers.
#
# For the GATING target (order-service, the "after") this script:
#   1. builds the image from its Containerfile,
#   2. generates a CycloneDX SBOM with syft,
#   3. scans that SBOM with grype against the current vulnerability DB,
#      applying the fixable-only ignore rule in .grype.yaml (gate-on:
#      fixable in policy.yaml), and
#   4. applies the policy-as-code threshold (fail-on) from policy.yaml to
#      the FIXABLE findings only -- a breach here fails this script (exit
#      1), exactly like CI. Findings with no published fix (`fix-state:
#      not-fixed`) are never dropped: grype moves them to a separate
#      `ignoredMatches` array instead of `matches`, so they are still
#      counted and printed (see the per-target "total" vs "fixable" tally
#      below and evidence/*.grype.json) -- they just can't block the
#      pipeline on a fix that doesn't exist yet. See .grype.yaml for the
#      full rationale.
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
GATE_ON="$(grep -E '^gate-on:' policy.yaml | awk '{print $2}')"
GRYPE_CFG=".grype.yaml"
echo "Policy: fail the GATING target(s) on >= ${FAIL_ON}, gated on '${GATE_ON}' findings only   (source: policy.yaml, ${GRYPE_CFG})"
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
  #    -c .grype.yaml applies the fixable-only ignore rule (gate-on:
  #    fixable in policy.yaml): grype moves any match with
  #    `fix-state: not-fixed` out of `matches` and into a separate
  #    `ignoredMatches` array rather than dropping it, so not-fixed
  #    findings are still present in $scan and still counted below -- just
  #    not counted toward the gate.
  grype "sbom:$sbom" -c "$GRYPE_CFG" -o json -q > "$scan"

  # 3. tally by severity -- FIXABLE (from `matches`, what the gate acts on)
  #    and TOTAL (`matches` + `ignoredMatches`, every finding regardless of
  #    fix state) -- then apply the policy to the basis each gate type
  #    reports on: `required` targets gate on fixable findings only;
  #    `reported` targets show the full raw count (all severities,
  #    including not-fixed) so readers see total exposure.
  local fx_crit fx_high fx_med ig_crit ig_high ig_med components
  fx_crit="$(jq '[.matches[]|select(.vulnerability.severity=="Critical")]|length' "$scan")"
  fx_high="$(jq '[.matches[]|select(.vulnerability.severity=="High")]|length' "$scan")"
  fx_med="$(jq '[.matches[]|select(.vulnerability.severity=="Medium")]|length' "$scan")"
  ig_crit="$(jq '[.ignoredMatches[]?|select(.vulnerability.severity=="Critical")]|length' "$scan")"
  ig_high="$(jq '[.ignoredMatches[]?|select(.vulnerability.severity=="High")]|length' "$scan")"
  ig_med="$(jq '[.ignoredMatches[]?|select(.vulnerability.severity=="Medium")]|length' "$scan")"
  components="$(jq '.components | length' "$sbom")"

  local tot_crit=$((fx_crit + ig_crit))
  local tot_high=$((fx_high + ig_high))
  local tot_med=$((fx_med + ig_med))

  # The basis a verdict is computed on: `required` targets gate on fixable
  # findings only (gate-on: fixable); `reported` targets verdict against
  # the full raw total, to demonstrate total exposure on the frozen image.
  local basis_crit basis_high
  if [ "$gate" = "required" ] && [ "$GATE_ON" = "fixable" ]; then
    basis_crit="$fx_crit"; basis_high="$fx_high"
  else
    basis_crit="$tot_crit"; basis_high="$tot_high"
  fi

  local breach=0
  if { [ "$FAIL_ON" = "High" ] && { [ "$basis_crit" -gt 0 ] || [ "$basis_high" -gt 0 ]; }; } \
     || { [ "$FAIL_ON" = "Critical" ] && [ "$basis_crit" -gt 0 ]; }; then
    breach=1
  fi

  local verdict="PASS"
  if [ "$breach" -eq 1 ]; then
    verdict="FAIL"
    if [ "$gate" = "required" ]; then
      gate_failed=1
    fi
  fi

  printf '  components=%s\n' "$components"
  printf '  total:    Critical=%s  High=%s  Medium=%s  (all severities, incl. not-fixed)\n' \
    "$tot_crit" "$tot_high" "$tot_med"
  printf '  fixable:  Critical=%s  High=%s  Medium=%s  (gating basis for required targets; not-fixed findings excluded, still reported in evidence/)\n' \
    "$fx_crit" "$fx_high" "$fx_med"
  printf '  -> %s\n' "$verdict"
  if [ "$breach" -eq 1 ] && [ "$gate" = "reported" ]; then
    echo "  (this is the expected 'before' result demonstrating the gate firing on the full raw count -- non-gating, does not block the pipeline)"
  fi
  printf '%-14s [%-6s/%-8s] components=%-4s total(Critical=%-2s High=%-2s Medium=%-2s) fixable(Critical=%-2s High=%-2s Medium=%-2s) %s\n' \
    "$name" "$kind" "$gate" "$components" "$tot_crit" "$tot_high" "$tot_med" "$fx_crit" "$fx_high" "$fx_med" "$verdict" >> "$summary"
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
