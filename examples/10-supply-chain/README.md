# Example 10 — The supply-chain gate (SBOM + CVE scan + policy-as-code)

This is the runnable companion to **Chapter 31**. It does not change any
service; it is an isolated, additive demonstrator that scans the two
container images this project already builds:

- **order-service** (the "after") — the extracted, modernized service built
  from [`examples/07-order-service/Containerfile`](../07-order-service/Containerfile).
  This is the artifact the gate protects: `policy.yaml` marks it
  `gate: required`, so a **fixable** High/Critical finding here fails
  `demo.sh` and the `supply-chain.yml` CI job (`gate-on: fixable` — see
  [`policy.yaml`](policy.yaml) and [`.grype.yaml`](.grype.yaml)).
- **monolith** (the "before") — the frozen
  [`examples/00-monolith`](../00-monolith) Django/gunicorn application, built
  from its [`Dockerfile`](../00-monolith/Dockerfile). `policy.yaml` marks it
  `gate: reported`: it is built, scanned, and its findings — the full raw
  count, every severity, not filtered to fixable-only — are written to
  `evidence/` alongside order-service's, but a breach there can never block
  the pipeline. The monolith is frozen — it exists as comparative evidence,
  not as something to patch and re-scan clean.

Both targets scan the **built container image**, not the source tree or a
`uv.lock` file alone — that catches UBI base-layer CVEs as well as Python
dependency CVEs, which is the whole point of a supply-chain gate.

## What it does

For each target in [`policy.yaml`](policy.yaml), `demo.sh` runs three steps —
the same three steps `.github/workflows/supply-chain.yml` runs in CI, so
"it passed locally" and "it passed in CI" mean the same thing:

1. **Build** — the image, from the target's `Containerfile`/`Dockerfile`.
2. **SBOM** — `syft` produces a CycloneDX JSON bill of materials (the
   complete list of packages, versions, and the base OS layer actually
   inside the built image).
3. **Scan** — `grype` scans that SBOM against its vulnerability database,
   applying the ignore rule in [`.grype.yaml`](.grype.yaml)
   (`fix-state: not-fixed` — see "Fixable-only gating" below), and reports
   every match by severity; `policy.yaml`'s `fail-on` threshold decides
   pass/fail for `gate: required` targets against the **fixable** findings
   only. Ignored (not-fixed) findings are never dropped from the scan — grype
   files them in a separate `ignoredMatches` array in the same JSON output,
   so they are still visible in `evidence/*.grype.json` and in the total
   count `demo.sh` prints for every target.

## Fixable-only gating

The gate blocks on High/Critical findings that have a published fix
(`fix-state` of `fixed`, `wont-fix`, or `unknown`) and reports, but does not
block on, findings with no fix available yet (`fix-state: not-fixed`). A
gate should block on what a maintainer can act on today; a finding with no
upstream patch can't be resolved by any change available inside this
repository, so leaving it in the gate just leaves the pipeline red
indefinitely, with no action to clear it.

This is implemented with one grype ignore rule in
[`.grype.yaml`](.grype.yaml):

```yaml
ignore:
  - fix-state: not-fixed
```

The rule matches on the `fix-state` property rather than a list of CVE IDs,
so it keeps working as the grype database updates — a new CVE's not-fixed
status is whatever the database currently reports, not something this file
has to be edited to track. `demo.sh` applies the same file locally
(`grype ... -c .grype.yaml`) that `supply-chain.yml` loads in CI
(`anchore/scan-action`'s `config:` input), so a local pass and a CI pass mean
the same thing.

## Prerequisites

- [`syft`](https://github.com/anchore/syft) `v1.54.1` and
  [`grype`](https://github.com/anchore/grype) `v0.120.1` on your `PATH`
  (`syft version`, `grype version`).
- `jq`.
- A container builder. `demo.sh` prefers **docker** (what
  `supply-chain.yml` builds with on a standard GitHub Actions runner) and
  falls back to **podman** if docker isn't on `PATH`. If you only have
  rootless podman and a build fails with a `.venv`/`uv sync` permission
  error, that's a user-namespace UID-remap interaction between rootless
  podman and this project's non-root (`USER 1001:0`) Containerfiles, not a
  defect in the Containerfile — install docker or use a podman setup with
  idmapped-mounts support.

grype downloads/refreshes its vulnerability DB on first use (one network
call); run `grype db update` before `demo.sh` if `grype db status` reports
the DB as stale.

## Run it

```bash
cd examples/10-supply-chain
./demo.sh
```

`demo.sh` exits non-zero only when a `gate: required` target breaches
`fail-on` on its **fixable** findings. That non-zero exit is exactly what
fails a CI job for order-service. A breach on the `gate: reported` monolith
— measured against its full raw count — is tallied and printed but never
changes the exit code; see `policy.yaml` for the required/reported split
(A/B-4 = B, DRQ-088). Evidence is written to `evidence/`: a CycloneDX SBOM
and the grype findings JSON per target, plus a `summary.txt`.

## The captured result (2026-10-17)

```
order-service  [after /required] components=5720 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) PASS
monolith       [before/reported] components=5690 total(Critical=0  High=35 Medium=153) fixable(Critical=0  High=0  Medium=7 ) FAIL
```

Both images carry the same 265 matches: 0 Critical / 35 High / 153 Medium /
77 Low, against the exact same 35 affected packages. Every one of those 35
High findings traces to the shared
`ubi10/python-314-minimal:10.2-1791928506` base layer the two
`Containerfile`/`Dockerfile`s both pin — `curl`/`libcurl-minimal`, `expat`,
`gnutls`, the `libblkid`/`libmount`/`libsmartcols`/`libuuid` util-linux
family, and `python3.14`/`python3.14-libs` itself. None of them come from an
application-level Python dependency: order-service's 140 packages and the
monolith's 131 packages differ (FastAPI/grpc/aiokafka vs. Django/gunicorn),
but neither package set carries a High or Critical finding of its own in
the grype database dated 2026-10-16.

Checking `fix-state` on those 35 High findings puts all 35, on both images,
at `not-fixed` — there is no newer `ubi10/python-314-minimal` build to
re-pin to yet (confirmed against the registry's tag list: the currently
pinned tag is the newest `10.2-` build available). A gate with no
fixable-only carve-out would stay red on order-service until an upstream
maintainer ships a patch, regardless of anything this project changes. The
`gate-on: fixable` rule in `policy.yaml` (enforced via
[`.grype.yaml`](.grype.yaml)) excludes not-fixed findings from the pass/fail
decision: order-service's fixable count is 0 High / 0 Critical, so it
**passes**. The 35 not-fixed High findings remain counted in the `total`
column above and remain in `evidence/order-service.grype.json`'s
`ignoredMatches` array, surfaced in the report and excluded only from the
gate decision.

The monolith's `gate: reported` verdict is measured against its full raw
count (not fixable-only), which is why it still shows `FAIL` above: that is
the expected "before" result and, being non-gating, never blocks the
pipeline. Reporting the monolith on the raw count rather than the
fixable-filtered one keeps its number legible as "total exposure on the
frozen image" rather than mixing it with a gating rule that only applies to
the artifact the gate protects.

This result is a point-in-time measurement against a moving database and a
moving base-image tag: `fix-state` for any of these 35 CVEs can flip from
`not-fixed` to `fixed` the moment the upstream maintainer ships a patch and
a newer `ubi10/python-314-minimal` tag is published, at which point re-
pinning `UBI_PYTHON_IMAGE` and rebuilding would clear them from the fixable
count entirely. Re-run `demo.sh` to refresh this snapshot against the
current DB and tag.

## Verification status

**Verified live** on 2026-10-17 with `syft 1.54.1` and `grype 0.120.1`
(vulnerability DB built 2026-10-16T06:29:51Z), builder `docker 29.9.1`.
`./demo.sh` built both images, generated both SBOMs, scanned both with
[`.grype.yaml`](.grype.yaml) applied, and exited `0`: order-service
(`gate: required`) has 0 fixable High/Critical findings and **passes**
`fail-on: High` on this live scan of the built image, with the 35 not-fixed
High findings still present in `ignoredMatches` (see "The captured result"
above for the full total-vs-fixable breakdown); the
monolith (`gate: reported`) breaches `fail-on: High` on its raw count, as
expected, but, by design, never changes the exit code. The committed
`evidence/*.grype.json`, `evidence/*.sbom.cdx.json`, and `evidence/summary.txt`
are that run's findings snapshot, with `ignoredMatches` present in both
`*.grype.json` files showing the 35 not-fixed High findings excluded from
the gate. Total/fixable counts and the pass/fail split will drift as the
grype DB and the pinned base image update — re-run `demo.sh` to refresh the
evidence.
