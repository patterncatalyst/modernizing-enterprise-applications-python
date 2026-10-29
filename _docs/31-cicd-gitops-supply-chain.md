---
title: "CI/CD, GitOps, Progressive Delivery & Supply Chain"
order: 31
part: "Delivering & Reflection"
description: "The GitHub Actions workflows this repo actually ships (the equivalence/contract gates and the site build), the flag-gated progressive delivery the strangler already used, and a new, verified-live supply-chain gate: SBOM + CVE scan + policy-as-code."
duration: 35 minutes
---

## Learning objectives

By the end of this chapter you can:

- Enumerate the four GitHub Actions workflows this repo ships (`code-ci.yml`, `schema-registry.yml`, `supply-chain.yml`, `pages.yml`) and explain why `code-ci.yml`'s single `contract-gate` replaced six separate `*-equivalence-gate` jobs once ch.26 retired every `STRANGLER_*_ENABLED` flag.
- Explain why this project's flag-gated strangler cutovers constitute progressive delivery, and how an all-or-nothing reversible flag differs from a weighted-canary traffic split.
- Build a CycloneDX software bill of materials with `syft`, and explain why a scanner should run against the SBOM rather than the image a second time.
- Configure a policy-as-code gate (`policy.yaml`'s `fail-on`/`gate-on` keys) that turns a fixable High-or-Critical finding into a non-zero exit, and read a `grype` scan's severity tally for two differently-gated images, `order-service` (`gate: required`) and the monolith (`gate: reported`).
- Explain why `gate-on: fixable` turns an otherwise-unfixable permanent red into a workable gate, and why a CVE scan is a point-in-time claim against a moving vulnerability database that argues for running the supply-chain gate on every push rather than once at release.
- Name the GitOps components this project does not run (an image-registry push, an Argo CD/Flux reconciliation loop, and Istio weighted canary) and the scope-discipline reason each is a named next step rather than a half-wired demo.

## Why this matters

Chapter 29 put this system on a cluster; Chapter 30, still ahead, puts a
mesh and an observability stack around it. This chapter steps back from
both to ask a question neither one answers: how does a change get from a
developer's laptop to any of those environments at all, and what stands
between a green checkmark and something shipping with a known, unpatched
vulnerability baked into it? The accurate starting point is that this
project already answers most of that question: `.github/workflows/`
has carried a real CI pipeline since the very first extraction, and the
strangler proxy's cutover flags have been a working, if informal, form of
progressive delivery since Chapter 14. What this chapter adds on top of
that existing machinery is one new concern this book hasn't touched yet:
whether the container images this project builds are safe to run, not
just correct to run.

`examples/10-supply-chain/` is the runnable companion: `policy.yaml` and
`.grype.yaml` encode a supply-chain policy as committed, reviewable files;
`demo.sh` builds, SBOMs, and scans both the modernized order-service image
and the frozen monolith image the same way `.github/workflows/
supply-chain.yml` does in CI; `evidence/` holds the exact scan output this
chapter cites. The result is more interesting than a clean pass on the new
service and a clean fail on the old one: both images carry the identical
set of 35 High-severity findings, and the real engineering decision this
chapter walks through is what a gate should do about a finding nothing in
this repository can fix.

{% include excalidraw.html file="supply-chain-gate-pipeline" alt="Top band: the syft-to-grype-to-policy pipeline run for both order-service (gate required) and the monolith (gate reported), both producing the identical 265-match, 35-High result from their shared UBI base layer, with the fixable-only ignore rule routing order-service's 35 not-fixed High findings out of the pass/fail decision so the service passes with zero fixable High findings. Bottom band: the four separate, additive GitHub Actions workflows this repo ships, each with its own changes/gate/star-ok summary job and no paths filter, converging on one repository ruleset with four required checks; monolith-scan hangs off supply-chain.yml's sbom-scan job but is explicitly excluded from the required check." caption="Figure 31.1: The supply-chain gate pipeline, and the four additive CI checks it joins" %}

## The pipelines this repo actually ships

By the time this chapter opens, `.github/workflows/` holds five files. Here
is what each one actually does before adding a sixth
concept (the supply-chain gate) on top:

| Workflow | Required check | What it proves |
|---|---|---|
| `code-ci.yml` | `code-ci-ok` | `contract-gate`: the full, unedited Newman collection (Smoke, all four checkout scenarios, all six per-context contract folders, the order-service contract, and the GraphQL gateway contract) run through the now-flagless strangler proxy against the fully-extracted, **monolith-free** mesh, plus one inverted negative (order-service killed mid-suite, the next checkout must 502). |
| `schema-registry.yml` | `schema-registry-ok` | `schema-registry-gate`: `examples/09-schema-registry-demo`'s own pytest suite, Testcontainers-managed Kafka and Apicurio, proving the Avro round trip and the live BACKWARD-compatibility boundary from Chapter 28. |
| `deploy-manifests.yml` | `deploy-manifests-ok` | `render`: `kubectl kustomize` against `deploy/k8s/base` and `overlays/minikube`, piped through `kubeconform -strict` and `kubectl apply --dry-run=client`, the offline half of Chapter 29's "verifying without a cluster" story. |
| `supply-chain.yml` | `supply-chain-ok` | `sbom-scan`: this chapter's gate: syft SBOM, grype scan, fixable-only policy on the order-service image. |
| `pages.yml` | none | Builds (and, on `main`, deploys) this Jekyll site on every push; not a code gate, included here only because it is the fifth file in the same directory. |

`code-ci.yml` has its own history worth a sentence, because it's the
clearest evidence that this project's CI shape evolves with the system it
tests rather than accumulating dead jobs. Through Chapter 26 it carried
six separate `*-equivalence-gate` jobs, one per extraction, each standing
up a live monolith alongside the one freshly extracted service and
proving the cutover was behaviorally transparent through the proxy.
Chapter 26's final extraction retired the monolith from the running
system for good (frozen in-repo, rebootable only as a break-glass
referent) and retired every `STRANGLER_*_ENABLED` flag from the proxy's
`Settings` along with it. The six equivalence gates stopped matching
reality the moment that happened, so `code-ci.yml` was restructured to a
single `contract-gate` rather than left to test a monolith that no longer
takes traffic. A CI pipeline that doesn't get edited as the system it
tests changes shape isn't a safety net, it's a fossil.

## The `changes` / gate / `*-ok` shape, and why `paths:` would wedge it

Every workflow in the table above (`pages.yml` excepted) follows the same
three-job skeleton, and `supply-chain.yml` is the clearest place to read
it because it's the newest:

1. A cheap `changes` job diffs the push or PR against its base and sets a
   single boolean output.
2. The real work (`sbom-scan`, `contract-gate`, `schema-registry-gate`,
   `render`) runs only `if: needs.changes.outputs.run == 'true'`.
3. A summary job (`supply-chain-ok`, `code-ci-ok`, and so on) runs
   `if: always()` and checks that every job it `needs:` resolved to
   `success` or `skipped`. **That summary job, never the heavy job
   itself, is what a branch-protection ruleset requires.**

The reason that third job exists at all, rather than requiring
`sbom-scan` directly, is the same reason the workflow's `on:` block
carries no `paths:` filter:

```yaml
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
```

A GitHub required check only blocks a merge if the workflow that produces
it actually *runs* on that PR. Filter the whole workflow to
`paths: [examples/10-supply-chain/**, ...]` and a PR that only touches,
say, `_docs/32-pattern-language-revisited.md` never triggers
`supply-chain.yml` at all: no job runs, no check reports, and a ruleset
that requires `supply-chain-ok` has nothing to evaluate. GitHub's own
behavior here is unforgiving: a required check with no reported status
blocks the merge indefinitely, not permissively. One path-filtered
workflow with a required summary job is enough to wedge every PR in the
repository, including ones that have nothing to do with the gate. Letting
the *workflow* always run, and pushing the path decision down into the
cheap `changes` job instead, keeps the required check always reporting
(`success` either because the real work ran and passed, or because it was
cleanly `skipped`) while the actually expensive job (building two
container images, downloading two SBOMs' worth of grype matches) still
only runs when something relevant changed.

This is a corrected pattern, not a freely chosen one. A naive
`supply-chain.yml` carries a `paths:` filter *and* no `*-ok` summary job:
the exact combination this section just described as broken.
`schema-registry.yml` (Chapter 28)
got the shape right first; `deploy-manifests.yml` and `supply-chain.yml`
both copy it, specifically so a
future reader grepping this repository's `.github/workflows/` for "how
do I add a required check safely" finds the corrected answer here.

## Progressive delivery, already practiced

"Progressive delivery" sounds like it names a tool this project would
need to add: a feature-flag SaaS, a canary controller, a service mesh's
traffic-splitting rule. This project has been doing a version of it since
Chapter 14, with nothing more exotic than an environment variable the
strangler proxy reads at process start.

`STRANGLER_REVIEW_ENABLED` was the first of these: off by default,
routing every review request to the monolith exactly as before; set to
`true`, routing the identical path to `review-service` instead; proxy
code and routing behavior unchanged either way except for one `if`. Every
extraction after it added its own flag to the same family:
`STRANGLER_NOTIFICATION_ENABLED` in Chapter 17, `STRANGLER_INVENTORY_ENABLED`
paired with a second, independent `INVENTORY_MODE` axis in Chapter 19,
`STRANGLER_PAYMENT_ENABLED` alongside `PAYMENT_MODE=choreographed` in
Chapter 23, `SHIPPING_MODE=orchestrated` in Chapter 24. Each one is the
same shape: a dark-launched new backend reachable by the same client
contract, a single switch that decides which backend answers, and,
proven, not asserted, a negative test that kills the enabled backend and
confirms the caller gets a real failure rather than a silently masked
one. That is progressive delivery's actual definition: ship the new code
path dormant, prove it behaviorally equivalent to the old one, flip the
switch, keep the switch reachable until the old path is provably no
longer needed. This project just implemented it with `Settings.from_env()`
and an `if`/`elif` chain instead of a dedicated flag service, because a
single proxy process reading its own environment at startup was already
sufficient for a project with one team, one repo, and one deploy unit per
service.

It's also why `code-ci.yml`'s current single `contract-gate` is correct
to run with no flags set to anything but their final value. Chapter 26's
last extraction didn't just add a seventh dark-launched path. It retired
every `STRANGLER_*_ENABLED` flag from the proxy's `Settings` entirely,
because there was no longer a monolith path left to switch back to. A
progressive-delivery flag that can never be flipped back is a decommission
that hasn't been finished yet, not a flag; the proxy's own
`FROZEN STATUS` note on `examples/00-monolith`'s README is the one
remaining artifact of that irreversibility, not a runtime switch. This
chapter's gates inherit that: `contract-gate` tests the permanent,
flagless shape of the system, and the supply-chain gate below is scoped
the same way: to the image that actually ships, not to a hypothetical
rollback path that no longer exists.

## SBOM, scan, policy-as-code

`examples/10-supply-chain/`'s three-step pipeline scans the **built
container image**, not the source tree and not `uv.lock` alone. That
choice is deliberate and stated in `policy.yaml`'s own header: a
dependency-file scan would catch a vulnerable `aiokafka` pin, but it has
no visibility into the UBI base layer the image actually ships:
`curl`, `expat`, `gnutls`, the `util-linux` family, `python3.14` itself,
and a supply-chain gate that can't see the base layer isn't scanning the
real deployable artifact `deploy/k8s` actually runs.

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

For each target, `examples/10-supply-chain/demo.sh` runs the same three
steps `supply-chain.yml` runs in CI, which is the point: a developer who
runs `./demo.sh` locally and sees `PASS` is looking at the same verdict
the pull request will get.

1. **Build**: the image, from that target's `Containerfile` or
   `Dockerfile`.
2. **SBOM**: `syft <image> -o cyclonedx-json` reads the built image's
   local layers and produces a complete, versioned component inventory,
   5,720 components for order-service, 5,690 for the monolith, the
   difference accounted for by FastAPI/grpc/aiokafka on one side and
   Django/gunicorn on the other.
3. **Scan**: `grype sbom:<file> -c .grype.yaml` scans that SBOM (not the
   image a second time; the SBOM is the artifact of record) against the
   current vulnerability database, applying the ignore rule above, and
   writes the full JSON result to `evidence/<name>.grype.json`.

`demo.sh` then reads `policy.yaml`'s own `fail-on` and `gate-on` keys back
out of the file. It has no YAML library dependency, just `grep`/`awk`
against a small, fixed shape, so the policy a human reviews
in a pull request diff is the literal policy the script enforces, not a
paraphrase of it hardcoded somewhere else.

## The fixable-only decision, and the real result

Here is where this chapter's evidence gets more interesting than a tidy
"legacy app fails, modernized service passes" story would be. Both
images pin the exact same `ubi10/python-314-minimal` base layer. Running
`demo.sh` on 2026-10-17 produced:

```text
order-service  [after /required] components=5720 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) PASS
monolith       [before/reported] components=5690 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) FAIL
```

265 matches on each image (0 Critical, 35 High, 153 Medium, 77 Low), and
the 35 High findings are identical on both: `curl`/`libcurl-minimal`,
`expat`, `gnutls`, the `libblkid`/`libmount`/`libsmartcols`/`libuuid`
util-linux family, and `python3.14`/`python3.14-libs`. None of them trace
to an application-level Python dependency; order-service's 140 packages
and the monolith's 131 differ completely from each other, and neither
package set carries a High or Critical finding of its own. The
before/after lesson this evidence actually supports is **not** "the
monolith fails on its own merits and the microservice passes on its
own": it is that both services inherit the identical base-layer exposure
regardless of how much application-level modernization happened around
it, and a supply-chain scan is what makes that exposure visible and
gate-able at all, independent of how much application-level refactoring
happened around it.

Checking `fix-state` on those 35 High findings is what turns this from an
unfixable permanent red into a workable gate. Every one of the 35, on
both images, reports `fix-state: not-fixed`. Confirmed against the
registry's own tag list, the pinned `10.2-1791928506` build is already
the newest `ubi10/python-314-minimal` available; there is no newer tag to
re-pin to yet, and no patched `curl` or `expat` package published inside
that tag. A gate with no fixable-only carve-out would block order-service
indefinitely on a finding this repository has no change available to make,
not a dependency bump, not a re-pin, nothing short of waiting for an
upstream maintainer. `gate-on: fixable` scopes the block to what the team
can actually act on: order-service's **fixable** count is 0 High, 0
Critical, so it passes `fail-on: High` cleanly, while the 35 not-fixed
findings stay fully visible: grype moves them to a separate
`ignoredMatches` array rather than dropping them, so they're still in
`evidence/order-service.grype.json`, still in the `total` column `demo.sh`
prints, and still readable with `grype --show-suppressed`. Nothing here
is a workaround that makes a real exposure disappear from the report; it
is a decision about which findings a merge decision should be allowed to
block on.

The monolith's `FAIL` above is the expected result and is read on a
different basis by design: `gate: reported` targets are measured against
the **raw** count (35 High, unfiltered), not the fixable-filtered one, so
the number stays legible as "total exposure on a frozen image" rather
than getting mixed with the fixable rule that exists specifically to keep
the gate actionable for a service someone still maintains. `continue-on-error: true`
on `supply-chain.yml`'s `monolith-scan` job, and that job's by-design
absence from `supply-chain-ok`'s `needs:` list, is what keeps that
expected, by-design failure from ever touching the one required check:

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

One more number worth sitting with: `fixable(... Medium=7)` is identical
on both images too. `fail-on: High` doesn't gate on it today, but it's
visible in `evidence/summary.txt` the moment anyone tightens the
threshold, which is the entire point of policy-as-code living in a
committed, diffable file instead of a buried shell flag. Reviewing a
one-line change to `fail-on` is a pull request like any other; reviewing
a change buried in a CI step's inline arguments usually isn't.

## GitOps: named, and scoped out of this chapter

GitOps is a specific operational pattern, not a synonym for "CI/CD with
Git." This section is precise about what it names before explaining why
this project doesn't have it. In a GitOps setup, a Git repository is the
single declared source of truth for a cluster's desired state, and an
in-cluster controller (Argo CD and Flux are the two names anyone will
encounter) continuously and automatically reconciles the live cluster
toward whatever that repository currently says, pulling changes rather
than waiting for a pipeline to push them. The controller, not a CI
runner, is the thing that ultimately runs `kubectl apply`, and it keeps
doing so forever, correcting drift any time the live state and the
repository disagree.

What this project actually has, from Chapter 29, is the opposite
direction of that arrow: `deploy/k8s/scripts/deploy.sh` is a human- or
CI-triggered push, run once, against whichever cluster the operator
points it at. Nothing watches `deploy/k8s/` continuously; nothing
notices or corrects drift between a commit and the cluster's current
state unless someone reruns the script. That's a legitimate, common
shape for a project without a cluster it owns long-term: this book's
Kubernetes target is `minikube`, started and torn down per reader, not a
standing environment with its own lifecycle independent of any one
reader's laptop. Standing up Argo CD against a cluster that doesn't exist
between sessions would be exactly the kind of infrastructure this book
has repeatedly declined to build ahead of a need that doesn't exist yet,
the same discipline Chapter 28 applied to the five other event schemas
this project could have registered but didn't. GitOps is the right next
step the moment this system runs on a cluster someone keeps running
between deploys; it isn't a gap in this book's current chapter so much as
a named, scoped, and explicitly deferred one.

## A point-in-time result, not a permanent one

Every number in this chapter's evidence section is a measurement against
two things that move independently of this repository: the grype
vulnerability database (built 2026-10-16 for the run cited above) and the
pinned `ubi10/python-314-minimal` tag both Containerfiles reference. A
`fix-state` of `not-fixed` today can become `fixed` the moment a UBI
maintainer ships a patched base image and a newer tag. At that point
re-pinning `UBI_PYTHON_IMAGE` and rebuilding clears the finding from the
fixable count without this chapter's gate logic changing at all. The
opposite can also happen: a High CVE disclosed after this evidence was
committed can appear in a future scan and legitimately turn today's green
gate red. `supply-chain.yml` always scans against the *live* database, so
a failure there should be read as a real new finding to triage, not a
regression in this chapter's reasoning, and a transient breach on the
gating target gets resolved by a documented, reviewed `.grype.yaml`
addition with a stated justification, never by quietly loosening
`fail-on`. `README.md` in `examples/10-supply-chain/` and the committed
`evidence/` snapshot both carry this same caveat, and re-running
`demo.sh` is the one-command way to refresh it against whatever the
database currently says.

> **ADLC in Action**: This chapter's central claim, that order-service
> and the monolith carry the *identical* 35 High findings, is the kind
> of result that's easy to round off to something tidier while drafting
> ("the modernized service has fewer vulnerabilities"), and that rounding
> would have been wrong. Confirming it meant running `demo.sh` against
> both images rather than citing a remembered or expected shape of the
> result, diffing `evidence/order-service.grype.json` and
> `evidence/monolith.grype.json` package by package, and checking that
> the overlap was the UBI base layer specifically rather than a
> coincidence of two large dependency trees. The same discipline applied
> to the `fix-state` claim underlying the gate design: rather than
> asserting a CI gate "should" ignore unfixable findings as a design
> opinion, this chapter's author checked `fix-state` on all 35 live
> matches and confirmed, against the actual registry tag list, not an
> assumption, that the pinned base image was already the newest build
> available, which is what makes `gate-on: fixable` a correct
> engineering decision here rather than a convenient excuse to turn a red
> gate green. An agent drafting this chapter from the plan's working
> assumption of a clean before/after contrast, without re-running
> `demo.sh` against the live images and the live grype database, would
> have shipped a result that was more satisfying to write and
> substantially less true.

## What you learned

- **This repo's CI already evolves with the system it tests**:
  `code-ci.yml`'s six retired `*-equivalence-gate` jobs collapsed into one
  `contract-gate` the moment the monolith was permanently decommissioned;
  a pipeline that keeps testing a topology that no longer exists is a
  liability, not a safety net.
- **The `changes` / gate / `*-ok` shape, with no `paths:` filter on the
  workflow itself, is what keeps a required check always reporting**: a
  path-filtered required summary job reports nothing on an unrelated PR
  and wedges every merge behind a check that never runs; pushing the path
  decision into a cheap `changes` job instead keeps the heavy work
  conditional without ever leaving the required check silent.
- **Progressive delivery here is a Python `if` on an environment
  variable, proven, not a platform feature**: `STRANGLER_REVIEW_ENABLED`
  through `SHIPPING_MODE`, each dark-launched, each cut over, each
  negative-tested by killing the enabled backend and asserting the
  caller's failure is real, and each one retired for good the moment the
  path it protected stopped being reversible.
- **A supply-chain gate that scans the built image catches what a
  dependency-file scan can't**: all 35 High findings in this chapter's
  evidence live in the shared UBI base layer, in packages neither
  service's own `pyproject.toml` lists.
- **`gate-on: fixable` is a decision about what a gate should block on,
  not a way to hide a finding**: order-service and the frozen monolith
  carry the identical 35 not-fixed High findings; the fixable-only rule
  changes which of those findings can fail a merge, not which ones appear
  in the report.
- **GitOps names a specific pull-based reconciliation pattern this
  project doesn't need yet**: `deploy/k8s/scripts/deploy.sh` pushes once,
  on request, to a `minikube` instance that doesn't persist between
  sessions; an Argo CD or Flux controller reconciling a cluster this book
  doesn't keep running would be infrastructure built ahead of a need.
- **Every scan result here is a point-in-time measurement**: against a
  grype database built 2026-10-16 and a specific pinned base-image tag,
  both of which move independently of this repository and of this
  chapter's prose.

Chapter 32 closes this book out by walking the microservices pattern
catalog back against everything built across thirty-one chapters: which
patterns this project actually needed, which were named and scoped out
as not-yet-needed (a shared chassis library, GitOps among them), and what the
ADLC discipline this chapter's own callout practiced one more time looked
like end to end.
