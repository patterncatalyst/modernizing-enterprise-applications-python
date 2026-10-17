# Example 10 — The supply-chain gate (SBOM + CVE scan + policy-as-code)

This is the runnable companion to **Chapter 31**. It does not change any
service; it is an isolated, additive demonstrator that scans the two
container images this project already builds:

- **order-service** (the "after") — the extracted, modernized service built
  from [`examples/07-order-service/Containerfile`](../07-order-service/Containerfile).
  This is the artifact the gate protects: `policy.yaml` marks it
  `gate: required`, so a High/Critical finding here fails `demo.sh` and the
  `supply-chain.yml` CI job.
- **monolith** (the "before") — the frozen
  [`examples/00-monolith`](../00-monolith) Django/gunicorn application, built
  from its [`Dockerfile`](../00-monolith/Dockerfile). `policy.yaml` marks it
  `gate: reported`: it is built, scanned, and its findings are written to
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
3. **Scan** — `grype` scans that SBOM against its vulnerability database and
   reports every match by severity; `policy.yaml`'s `fail-on` threshold
   decides pass/fail for `gate: required` targets.

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
`fail-on`. That non-zero exit is exactly what fails a CI job for
order-service. A breach on the `gate: reported` monolith is tallied and
printed but never changes the exit code — see `policy.yaml` for the
required/reported split (A/B-4 = B, DRQ-088). Evidence is written to
`evidence/`: a CycloneDX SBOM and the grype findings JSON per target, plus a
`summary.txt`.

## The captured result (2026-10-17)

```
order-service  [after /required] components=5720 Critical=0  High=35 Medium=153 FAIL
monolith       [before/reported] components=5690 Critical=0  High=35 Medium=153 FAIL
```

On the day this evidence was captured, **both** targets breach `fail-on:
High` — and they breach it identically: 265 matches each, 0 Critical / 35
High / 153 Medium / 77 Low, against the exact same 35 affected packages.
Every one of those 35 High findings traces to the shared
`ubi10/python-314-minimal:10.2-1791928506` base layer the two
`Containerfile`/`Dockerfile`s both pin — `curl`/`libcurl-minimal`,
`expat`, `gnutls`, the `libblkid`/`libmount`/`libsmartcols`/`libuuid`
util-linux family, and `python3.14`/`python3.14-libs` itself. None of them
come from an application-level Python dependency: order-service's 140
packages and the monolith's 131 packages differ (FastAPI/grpc/aiokafka vs.
Django/gunicorn), but neither package set currently carries a High or
Critical finding of its own in the grype database dated 2026-10-16.

This is the grype-DB-drift risk made concrete rather than hypothetical: a
CVE batch disclosed against the pinned base image after the tag was chosen
can turn the gate red on the modernized "after" target through no change to
the service's own code. It is evidence the gate is watching the whole image,
not just the application layer — but it also means this particular snapshot
doesn't show the clean "before fails / after passes" split the chapter's
thesis describes, because both images currently share one unpatched base
tag. The structural advantage the chapter argues for is independent
patch/redeploy per service — order-service can be rebuilt against a newer
`UBI_PYTHON_IMAGE` tag and redeployed on its own the moment one ships,
without touching the other seven services or the frozen monolith. That
property is real regardless of what any single snapshot shows.

The remediation a maintainer would take next — re-pinning
`UBI_PYTHON_IMAGE` to a tag built after these CVEs were patched upstream, or
adding a justified, committed grype ignore for the specific CVE IDs while
that tag is pending — is intentionally **not** applied in this example. The
gate's job is to surface the finding, not to have an opinion baked in about
which outstanding CVE is acceptable to carry; that is a triage call for
whoever owns the pin.

A scan is a point-in-time claim against a moving database: a clean artifact
today can fail tomorrow when a CVE is disclosed, and a failing one today can
clear tomorrow when the base image is rebuilt. That is why the gate runs on
every push, not once — re-run `demo.sh` to refresh this snapshot against the
current DB.

## Verification status

**Verified live** on 2026-10-17 with `syft 1.54.1` and `grype 0.120.1`
(vulnerability DB built 2026-10-16T06:29:51Z), builder `docker 29.9.1`.
`./demo.sh` built both images, generated both SBOMs, scanned both, and
exited `1`: order-service (`gate: required`) breached `fail-on: High` (0
Critical / 35 High), which is the gate doing its job on a real, unscripted
base-image CVE batch (see "The captured result" above); the monolith
(`gate: reported`) breached identically but, by design, never changed the
exit code. The committed `evidence/*.grype.json`, `evidence/*.sbom.cdx.json`,
and `evidence/summary.txt` are that run's findings snapshot. CVE counts and
the pass/fail split will drift as the grype DB and the pinned base image
update — re-run `demo.sh` to refresh the evidence.
