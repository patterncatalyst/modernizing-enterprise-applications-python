---
title: "CI/CD, GitOps, Progressive Delivery & Supply Chain"
order: 31
part: "Delivering & Reflection"
description: "The GitHub Actions workflows the repo ships, flag-gated progressive delivery in the strangler proxy, and a supply-chain gate: SBOM, CVE scan and a fixable-only policy."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- List the seven workflows in `.github/workflows/` and explain why `code-ci.yml` has a single `contract-gate` instead of six `*-equivalence-gate` jobs.
- Structure a workflow as `changes`, gate and `*-ok` summary jobs so a required check always reports.
- Explain why an all-or-nothing reversible flag is progressive delivery, and how it differs from a weighted canary.
- Build a CycloneDX SBOM with `syft` and scan the SBOM with `grype` instead of scanning the image twice.
- Write a policy-as-code gate (`fail-on`, `gate-on: fixable`) and read the severity tally for `order-service` (`gate: required`) and the monolith (`gate: reported`).
- Say why GitOps (an Argo CD or Flux reconciliation loop), a registry push and an Istio weighted canary are named next steps and not half-wired demos.

## Why this matters

Getting a change from a laptop to a cluster has two questions: what stands between a green check and a merge, and what ships inside the image. The repo already answers most of the first. `.github/workflows/` has carried a real CI pipeline since the first extraction, and the strangler proxy's cutover flags have been a working form of progressive delivery since the Review extraction. The new concern is whether the images are safe to run, not just correct.

`examples/10-supply-chain/` holds the supply-chain gate. `policy.yaml` and `.grype.yaml` encode the policy as committed files, `demo.sh` builds, inventories and scans the modernized order-service image and the frozen monolith image the way `supply-chain.yml` does in CI, and `evidence/` holds the scan output cited below. Both images carry the identical 35 High-severity findings, so the real decision is what a gate should do about a finding nothing in the repository can fix.

{% include excalidraw.html file="supply-chain-gate-pipeline" alt="Top band: the syft, grype and policy pipeline run for order-service (gate required) and the monolith (gate reported). Both produce 265 matches and 35 High findings from the shared UBI base layer; the fixable-only ignore rule routes order-service's 35 not-fixed High findings out of the pass/fail decision, so the service passes. Bottom band: six additive gate workflows plus the Pages build, each gate workflow with its own summary job and no paths filter, feeding one repository ruleset that requires summary jobs; monolith-scan hangs off supply-chain.yml but is excluded from the required check." caption="Figure 31.1: The supply-chain gate pipeline and the additive CI checks it joins" %}

## The pipelines the repo ships

| Workflow | Required check | What it covers |
|---|---|---|
| `code-ci.yml` | `code-ci-ok` | `contract-gate`: the full Newman collection (smoke, the four checkout scenarios, the six per-context contract folders, the order-service contract and the GraphQL gateway contract) through the flagless strangler proxy against the monolith-free mesh, plus one inverted negative: order-service killed mid-suite, and the next checkout must return 502. |
| `schema-registry.yml` | `schema-registry-ok` | `schema-registry-gate`: `examples/09-schema-registry-demo`'s pytest suite against Testcontainers-managed Kafka and Apicurio, covering the Avro round trip and the live BACKWARD-compatibility boundary. |
| `deploy-manifests.yml` | `deploy-manifests-ok` | `render`: `kubectl kustomize` on `deploy/k8s/base` and `overlays/minikube`, piped through `kubeconform -strict` and `kubectl apply --dry-run=client`. |
| `supply-chain.yml` | `supply-chain-ok` | `sbom-scan`: syft SBOM, grype scan and the fixable-only policy on the order-service image. |
| `mesh-manifests.yml` | `mesh-manifests-ok` | `render`: the `deploy/k8s/istio`, `deploy/k8s/observability` and activated `overlays/minikube` trees through `kubectl kustomize` and `kubeconform -strict`; the three Istio custom resources have no published schema, so they run with `-ignore-missing-schemas` and report Skipped, not valid. |
| `openshift-chart.yml` | `openshift-chart-ok` | `render`: `helm lint` and `helm template` on `openshift/helm/mea` with the mesh and observability flags off and on, then `kubeconform -strict` on the plain Kubernetes objects; the Route and PeerAuthentication resources report Skipped. |
| `pages.yml` | none | Builds the Jekyll site on every push and deploys it on `main`. Not a code gate. |

`code-ci.yml` changes shape with the system it tests. While extractions were in flight it carried six `*-equivalence-gate` jobs, each standing up the live monolith next to one freshly extracted service to prove the cutover was transparent through the proxy. The final extraction retired the monolith from the running system (frozen in the repo, rebootable only as a break-glass referent) and removed every `STRANGLER_*_ENABLED` flag from the proxy's `Settings`. The six gates no longer matched reality, so they collapsed into one `contract-gate`. A pipeline that keeps testing a topology that no longer exists is a liability.

## The `changes` / gate / `*-ok` shape

Every workflow except `pages.yml` uses the same three jobs, and `supply-chain.yml` is the newest:

1. A cheap `changes` job diffs the push or PR against its base and sets one boolean output.
2. The real work (`sbom-scan`, `contract-gate`, `schema-registry-gate`, `render`) runs only `if: needs.changes.outputs.run == 'true'`.
3. A summary job (`supply-chain-ok`, `code-ci-ok` and so on) runs `if: always()` and checks that every job in its `needs:` resolved to `success` or `skipped`. The ruleset requires the summary job, never the heavy job.

The workflow's `on:` block carries no `paths:` filter:

```yaml
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
```

A required check blocks a merge only if the workflow that produces it runs on that PR, and a required check that never reports blocks indefinitely. Filter the workflow to `paths: [examples/10-supply-chain/**, ...]` and a PR that touches only `_docs/32-pattern-language-revisited.md` never triggers it, so the ruleset waits forever on `supply-chain-ok`. One path-filtered workflow with a required summary job wedges every unrelated PR. Letting the workflow always run and moving the path decision into `changes` keeps the check reporting (`success` after real work, or `success` because the job was cleanly `skipped`) while the expensive job, two image builds and two SBOM scans, runs only when something relevant changed. A `paths:` filter with no `*-ok` job is the broken combination; `schema-registry.yml` got the shape right first and every later workflow copies it.

## Progressive delivery, already practiced

Progressive delivery does not need a flag service, a canary controller or a mesh traffic rule. The strangler proxy has done it with an environment variable read at process start. `STRANGLER_REVIEW_ENABLED` was the first: off by default, every review request goes to the monolith; set to `true`, the identical path goes to `review-service`, and the only code difference is one `if`. Each later extraction added its own flag: `STRANGLER_NOTIFICATION_ENABLED`, `STRANGLER_INVENTORY_ENABLED` with an independent `INVENTORY_MODE` axis, `STRANGLER_PAYMENT_ENABLED` with `PAYMENT_MODE=choreographed`, and `SHIPPING_MODE=orchestrated`. Each has the same shape: a dark-launched backend behind the same client contract, one switch that decides which backend answers, and a negative check that kills the enabled backend and confirms the caller gets a real failure and not a silently masked one.

That is the definition: ship the new path dormant, prove it equivalent to the old one, flip the switch, and keep the switch reachable until the old path is provably unneeded. `Settings.from_env()` and an `if`/`elif` chain are enough for one team, one repo and one deploy unit per service. The flag is all-or-nothing and reversible; a weighted canary splits traffic by percentage and needs a mesh, which is a named next step.

The final extraction removed every flag, because no monolith path was left to switch back to. A flag that can never be flipped back is a decommission that hasn't been finished. The `FROZEN STATUS` note in `examples/00-monolith`'s README is what remains of that irreversibility, so `contract-gate` tests the permanent flagless shape and the supply-chain gate scans the image that ships, not a rollback path that no longer exists.

## Pattern: SBOM, scan, policy-as-code

The supply-chain gate scans the built container image, not the source tree and not `uv.lock` alone. A dependency-file scan catches a vulnerable `aiokafka` pin but cannot see the UBI base layer the image ships: `curl`, `expat`, `gnutls`, the `util-linux` family and `python3.14` itself.

{% include codetabs.html langs="examples/10-supply-chain/policy.yaml (trimmed)|examples/10-supply-chain/.grype.yaml" %}

```yaml
# Severities, most-to-least severe: Critical, High, Medium, Low, Negligible.
fail-on: High          # fail the GATING target(s) on any High or Critical finding

# gate-on: fixable -- a High/Critical finding only counts toward the
# fail-on threshold above when it has a fix state other than `not-fixed`.
gate-on: fixable

targets:
  - name: order-service
    kind: after
    gate: required        # hard-gated: a fixable breach fails demo.sh and CI
    buildfile: examples/07-order-service/Containerfile
    context: examples/07-order-service
    image: localhost/mea/order-service:supply-chain-demo

  - name: monolith
    kind: before
    gate: reported         # built, scanned, reported -- never blocks the pipeline
    buildfile: examples/00-monolith/Dockerfile
    context: examples/00-monolith
    image: localhost/mea/monolith:supply-chain-demo
```

```yaml
# grype's own ignore rule, matching the gate-on: fixable decision above.
# Matches on the fix-state PROPERTY, not a list of CVE IDs, so the rule
# keeps working as the grype DB updates -- a newly disclosed CVE's
# not-fixed status is whatever the database currently reports, nothing
# here has to be edited to keep tracking it.
ignore:
  - fix-state: not-fixed
```

For each target, `demo.sh` runs the three steps `supply-chain.yml` runs in CI, so a local `PASS` is the verdict the pull request will get:

1. **Build** the image from the target's `Containerfile` or `Dockerfile`.
2. **SBOM**: `syft <image> -o cyclonedx-json` produces a versioned component inventory, 5,720 components for order-service and 5,690 for the monolith. The difference is FastAPI, grpc and aiokafka on one side and Django and gunicorn on the other.
3. **Scan**: `grype sbom:<file> -c .grype.yaml` scans the SBOM, not the image a second time, against the current vulnerability database, applies the ignore rule and writes `evidence/<name>.grype.json`.

`demo.sh` reads `fail-on` and `gate-on` back out of `policy.yaml` with `grep` and `awk` against its small fixed shape, so the policy a reviewer sees in the diff is the policy the script enforces.

## The fixable-only decision

Both images pin the same `ubi10/python-314-minimal` base layer. `demo.sh` on 2026-10-17 printed:

```text
order-service  [after /required] components=5720 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) PASS
monolith       [before/reported] components=5690 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) FAIL
```

Each image has 265 matches (0 Critical, 35 High, 153 Medium, 77 Low), and the 35 High findings are identical: `curl`/`libcurl-minimal`, `expat`, `gnutls`, the `libblkid`/`libmount`/`libsmartcols`/`libuuid` family, and `python3.14`/`python3.14-libs`. None traces to an application dependency. Order-service's 140 packages and the monolith's 131 differ completely, and neither set carries a High or Critical finding. So the evidence does not say the monolith fails and the service passes on merit. It says both inherit the same base-layer exposure however much application modernization happened, and a scan is what makes that exposure visible and gate-able.

All 35 report `fix-state: not-fixed`. The pinned `10.2-1791928506` build is already the newest `ubi10/python-314-minimal` tag in the registry, so there is no tag to re-pin to and no patched `curl` or `expat` inside it. A gate without a fixable-only carve-out would block order-service until an upstream maintainer ships a patch. `gate-on: fixable` scopes the block to what the team can act on: order-service has 0 fixable High and 0 fixable Critical, so it passes `fail-on: High`. The 35 stay visible, because grype moves them to an `ignoredMatches` array instead of dropping them. They remain in `evidence/order-service.grype.json`, in the `total` column and in `grype --show-suppressed`. The rule changes which findings can block a merge, not which appear in the report.

The monolith's `FAIL` is expected. A `gate: reported` target is measured against the raw count (35 High, unfiltered), so the number reads as total exposure on a frozen image and not as the actionable subset. `continue-on-error: true` on the `monolith-scan` job, and its absence from `supply-chain-ok`'s `needs:`, keep that failure away from the required check:

{% include codetabs.html langs=".github/workflows/supply-chain.yml: sbom-scan + supply-chain-ok (trimmed)" %}

```yaml
  sbom-scan:
    name: sbom-scan (order-service)
    needs: changes
    if: needs.changes.outputs.run == 'true'
    runs-on: ubuntu-latest
    steps:
      # ... build order-service image ...
      - uses: anchore/sbom-action@v0
        with:
          image: mea/order-service:scan
          format: cyclonedx-json
      - uses: anchore/scan-action@v7
        with:
          sbom: order-service.cdx.json
          fail-build: true
          severity-cutoff: high
          config: examples/10-supply-chain/.grype.yaml   # fixable-only rule

  monolith-scan:                 # non-gating: NOT in supply-chain-ok's needs:
    needs: changes
    if: needs.changes.outputs.run == 'true'
    continue-on-error: true
    steps:
      # ... build + scan the frozen monolith image, reported only ...

  supply-chain-ok:
    if: always()
    needs: [changes, sbom-scan]  # monolith-scan deliberately absent
    steps:
      - run: jq -e 'to_entries | all(.value.result == "success" or .value.result == "skipped")' <<<"$NEEDS"
```

The fixable Medium count is 7 on both images. `fail-on: High` ignores it today, but it surfaces in `evidence/summary.txt` the moment someone tightens the threshold. That is the point of keeping policy in a committed, diffable file: a one-line change to `fail-on` is a pull request like any other, and a change buried in a CI step's inline arguments usually isn't reviewed.

A scan is a point-in-time claim against two things that move independently of the repo: the grype database (built 2026-10-16 for this run) and the pinned base-image tag. A `not-fixed` finding becomes `fixed` when a maintainer ships a patched image; re-pinning `UBI_PYTHON_IMAGE` and rebuilding then clears it from the fixable count with no change to the policy. A High disclosed later can turn a green gate red. `supply-chain.yml` scans the live database on every push for that reason, and a failure is a new finding to triage. Resolve a transient breach with a reviewed `.grype.yaml` addition and a stated justification, never by loosening `fail-on`.

## GitOps: named, and scoped out

In GitOps a Git repository is the declared source of truth for cluster state, and an in-cluster controller (Argo CD or Flux) pulls and continuously reconciles the live cluster toward it, correcting drift. The controller, not a CI runner, runs `kubectl apply`, and keeps running it.

The project points the other way. `deploy/k8s/scripts/deploy.sh` is a push, run once by a person or CI against whichever cluster the operator names. Nothing watches `deploy/k8s/` or corrects drift until someone reruns the script. That is a sound shape for a project whose Kubernetes target is `minikube`, started and torn down per reader. Argo CD against a cluster that doesn't exist between sessions would be infrastructure ahead of a need. GitOps becomes the right step once the system runs on a cluster someone keeps up between deploys.

> **ADLC in Action**: The claim that order-service and the monolith carry the identical 35 High findings is easy to round off to "the modernized service has fewer vulnerabilities", and that would be wrong. Confirming it meant running `demo.sh` against both images, diffing the two `evidence/*.grype.json` files package by package, and checking that the overlap was the UBI base layer and not a coincidence of two large dependency trees. The same applied to the policy design: the agent checked `fix-state` on all 35 live matches and checked the registry tag list to confirm the pinned base was already the newest, which makes `gate-on: fixable` an engineering decision and not an excuse to turn a red gate green. A draft written from the working assumption of a clean before/after contrast, without re-running `demo.sh` against the live images and database, would have been more satisfying and less true.

> **Decision**
>
> Gate a merge on what the team can fix: scan the built image's SBOM, fail on fixable High or Critical findings, keep not-fixed findings in the report, and put the policy in a committed file. Make the always-running workflow's summary job the required check.

> **🤖 Explore with your agent**
>
> "In examples/10-supply-chain, remove the fix-state: not-fixed ignore rule from .grype.yaml, run ./demo.sh, and show which of the 35 High findings now block order-service and which packages they come from. Then restore the rule, and review whether any finding in evidence/order-service.grype.json traces to a package in examples/07-order-service/pyproject.toml rather than the UBI base layer."
>
> Check: without the rule, the order-service line shows `fixable(Critical=0  High=35 ...)` and FAIL; after the restore, `./demo.sh` prints PASS for order-service.

## Build, run, observe

```bash
cd examples/10-supply-chain
./demo.sh
```

`demo.sh` needs `syft`, `grype` and a container engine to build both images; it prints one line per target as shown above and writes `evidence/<name>.grype.json` and `evidence/summary.txt`. Order-service passes and the monolith, reported only, shows FAIL.

- Delete the `fix-state: not-fixed` rule from `.grype.yaml`: the 35 not-fixed High findings block order-service.
- Run `grype --show-suppressed` on the SBOM: the 35 ignored findings are listed.
- Re-pin `UBI_PYTHON_IMAGE` once a newer base tag ships and rebuild: a finding that gains a fix moves into the fixable count and a patched one clears.
