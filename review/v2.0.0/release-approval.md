# OpenRath v2 release approval

Current decision: **v2.0.0rc1 PUBLICATION AUTHORIZED; v2.0.0 GA HOLD**

The repository owner explicitly requested publication of an RC on 2026-07-29.
That authorizes the following RC-only actions:

- changing package metadata to `2.0.0rc1`;
- pushing the `codex/v2-review-remediation` branch;
- creating and pushing the `v2.0.0rc1` tag;
- publishing wheel/sdist as GitHub prerelease assets;
- publishing the RC image to GHCR by immutable digest;
- creating a GitHub prerelease.

The following remain prohibited until separately approved:

- changing package metadata to final `2.0.0`;
- creating or pushing the final `v2.0.0` tag;
- publishing the final PyPI/GHCR/GitHub release;
- deploying to any shared, staging, or production environment.

## Owner review checklist

- [ ] Review public SDK/API compatibility and the stable error model.
- [ ] Review SecurityContext, tenant, policy, trust, secret, Tool, Memory, and
  Sandbox boundaries.
- [ ] Review durable Run/checkpoint/interrupt/effect recovery semantics.
- [ ] Review PostgreSQL migrations, v1 import, backup/restore, and rollback.
- [ ] Review Agent Server authentication, resource isolation, SSE, limits, and
  split API/worker deployment.
- [ ] Review SBOM, zero-HIGH/CRITICAL scan, benchmark, soak, and chaos evidence.
- [ ] Approve the v1 maintenance window and v2 support/security policy.
- [ ] Attach target-environment extended soak, optional live-adapter, and
  rollout/rollback evidence when applicable.
- [ ] Explicitly authorize version bump, tag, push, image publication, and
  release.

Approval must be explicit. Silence, code review completion, or a passing CI
run does not authorize publication.

RC publication is not evidence that the unchecked GA items passed. The
prerelease must link the unresolved Gate C items and remain marked prerelease.
