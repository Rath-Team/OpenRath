# OpenRath v2.0.0 release approval

Current decision: **HOLD — owner review required**

The implementation may be reviewed, amended, and committed locally. The
following actions remain prohibited until the repository owner gives explicit
approval in a later message:

- changing package metadata to `2.0.0`;
- creating or pushing a `v2.0.0` tag;
- pushing the review branch or image;
- creating a GitHub release;
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
