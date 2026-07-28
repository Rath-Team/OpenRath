# OpenRath v2.0.0 review-remediation evidence

This bundle records the validation performed for implementation commit
`51a26c4a23850876548c61340da2d2da3bc834ce`. It is review evidence, not a
v2.0.0 release bundle.

## Decision

- `release_approved`: **false**
- `package_version`: `1.3.0`
- `intended_release`: `2.0.0` (unreleased)
- Local implementation gates: passed
- Production/RC Gate D: not satisfied

The package version was deliberately not changed to `2.0.0`. A local image ID
is not a published registry digest, and the unavailable external and
operational gates cannot be replaced by unit tests or a short local soak.

## Completed validation

| Area | Result |
|---|---|
| Lock | `uv lock --check` passed |
| Lint/format | Ruff check and format check passed |
| Types | mypy passed for 166 source files |
| Offline test matrix | 1043 passed, 20 skipped |
| OpenAPI contract | 2 passed; generated document matches the committed golden file |
| OpenSandbox real service | 45 passed, 3 skipped in the full run; the single environment-sensitive timing assertion was corrected and its focused rerun passed |
| PostgreSQL/Redis/S3 integration | 10 passed against real local services |
| Build | wheel and sdist built; `twine check` passed |
| Dependency audit | exact production set and all extras/groups: no known vulnerabilities |
| Container build | current source built as local image `openrath:review` |
| Image scan | 0 fixed HIGH/CRITICAL findings with Trivy 0.67.2 |
| Repository secret scan | 0 findings with Trivy 0.67.2 |
| Reference manifests | Compose validation and strict kubeconform validation passed |
| Review soak | 143 runs in 10.03 seconds, 0 failures; review profile only |

## Outstanding release gates

The following require external credentials, services, a registry, target
cluster, or elapsed operational time and remain blocking:

1. Live LLM/provider lifecycle using the approved production provider.
2. Live OpenViking lifecycle against the approved service.
3. Published OpenRath OCI artifact addressed by an immutable registry digest.
4. Eight-hour soak on target-like hardware.
5. Worker scale test from one to four replicas.
6. Backup/restore, rollout/rollback, database restart, S3 restart, and Redis
   loss drills on the target cluster.
7. Final CI run and release evidence regeneration on the frozen RC commit.

Do not tag, publish, or deploy v2.0.0 from this evidence bundle.

## Included artifacts

- `manifest.json`: machine-readable result and blocker summary.
- `openrath-v2-review.sbom.cdx.json`: CycloneDX SBOM for the local image.
- `image-scan-high-critical.json`: Trivy HIGH/CRITICAL image scan.
- `repository-secret-scan.json`: Trivy repository secret scan.
