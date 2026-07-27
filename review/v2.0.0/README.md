# OpenRath v2.0.0 review candidate

Status: **implementation complete; release on hold for user review**

This directory is the local evidence package for the v2.0.0 implementation.
It is not a release. The package metadata intentionally remains `1.3.0`; no
v2 tag, registry push, GitHub release, or production deployment is permitted
until the owner approves [release-approval.md](release-approval.md).

## Implemented production surface

- Immutable events, explicit `@step`/`@router` compilation, canonical plans,
  revision identity, and compatibility reporting.
- Durable Run state machine, transactional events/checkpoints, CAS updates,
  retries, deadlines, cancellation, priority, per-session serialization, and
  queue backpressure.
- SQLite local storage and PostgreSQL production storage with pooled
  connections, `SKIP LOCKED` claims, leases, heartbeats, fencing, and orphan
  recovery.
- Durable human-in-the-loop interrupts with inbox, approve/edit/reject/respond,
  actor/reason audit data, timeout expiry, and same-step resume.
- Effect ledger for read-only, idempotent, and non-idempotent operations;
  ambiguous outcomes enter review instead of unsafe replay.
- Tenant-scoped local/S3 artifacts and governed Provider, Tool, Sandbox, and
  Memory boundaries with explicit context, policy, timeout, trust, and
  credential references.
- Agent Server resources for Assistants, Sessions, Runs, Events/SSE,
  Interrupts, Store, and Feedback; sync/async remote clients; authentication,
  tenant isolation, correlation IDs, pagination, body limits, and security
  headers.
- OpenTelemetry trace/metric bridge, redacted structured JSON logs, durable
  feedback, datasets, experiments, and regression gates.
- Immutable deployment revisions, migration CLI, v1 history importer,
  non-root/read-only OCI image, split API/worker Compose and Kubernetes
  references, runbooks, capacity calculator, backup/restore procedure, CI,
  SBOM, and vulnerability gate.

## Evidence summary

| Gate | Result |
|---|---|
| Ruff | passed |
| mypy | passed, 164 source files |
| Test suite | 1024 passed, 14 conditional skips, 1 third-party deprecation warning |
| Real backends | PostgreSQL 17, Redis 8, and MinIO lifecycle tests passed |
| Worker crash recovery | succeeded; 2 claims, 1 lease-expiry recovery event |
| Backup/restore | restored isolated database; 1 Run and 6 RunEvents verified |
| Container lifecycle | ready, Run succeeded, UID 10001, read-only root filesystem |
| Kubernetes | kubeconform strict: 10 valid, 0 invalid |
| Vulnerability scan | Trivy 0.67.2: 0 HIGH/CRITICAL after upgrading MCP to 1.28.1 |
| SBOM | CycloneDX 1.6 generated |
| Benchmark | 500 Runs; see [benchmark.json](benchmark.json) |
| Review soak | 1050 Runs/30 s, 0 failures, 0 thread delta; see [soak.json](soak.json) |
| Wheel smoke | isolated install, package migration resource, and server CLI passed |

The local review image is
`sha256:92fa787d8b2be51b2248c13628765ad630f0820b757f74d46514ab94f332c7f6`.
It is intentionally not pushed.

## Evidence files

- [benchmark.json](benchmark.json): hardware-bound latency/throughput profile.
- [soak.json](soak.json): bounded resource-leak review profile.
- [sbom.cdx.json](sbom.cdx.json): CycloneDX software bill of materials.
- [vulnerability-report.json](vulnerability-report.json): machine-readable
  HIGH/CRITICAL scan result.
- [release-approval.md](release-approval.md): explicit owner review and release
  authorization gate.
- [API governance and maintenance policy](../../deploy/docs/api-governance-v2.md):
  stability labels, SemVer, deprecation, v1 compatibility, and private
  vulnerability reporting.

## Scope boundaries and remaining operator acceptance

The following are not unreported implementation gaps:

- Webhooks and cron triggers remain P2 and are deferred; Runs can be submitted
  through the stable API or an external scheduler.
- Exactly-once execution for arbitrary third-party side effects is not
  promised; the supported contract is ledger + idempotency + `NEEDS_REVIEW`.
- Enterprise UI, SAML/SCIM, billing, and cross-region active-active are outside
  v2.0.0 scope.

Before production rollout, the operator must repeat the supplied soak tool for
the approved 8h/24h duration on target hardware, exercise the chosen live LLM,
OpenSandbox, and OpenViking credentials if those optional adapters are enabled,
and perform a target-cluster rollout/rollback drill. These environment-specific
checks do not authorize a release and must be attached to the approval record.
