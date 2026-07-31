# OpenRath v2 threat model

Status: v2.0.0 baseline.

## Assets and security objectives

| Asset | Required property |
| --- | --- |
| Provider, Tool, Sandbox, Memory, database, object-store credentials | Confidential; referenced rather than persisted in Run state |
| Tenant and project data | Isolated at every API, store, adapter, and artifact boundary |
| Run, Event, Checkpoint, Interrupt, and Effect records | Durable, ordered, attributable, and protected from stale writers |
| Artifact content | Tenant scoped, size bounded, integrity checked |
| Revision and ExecutionPlan | Immutable identity bound to deployed content |
| Security audit records | Redacted, correlated, append-only at the configured collector |

## Trust boundaries

1. HTTP ingress is untrusted until the authentication provider produces a
   `SecurityContext`. Request tenant/project fields never override that context.
2. Provider, Tool, MCP, Sandbox, Memory, and recalled content are external and
   untrusted. Each adapter call receives a reduced context and policy decision.
3. PostgreSQL is the durable source of truth. Redis is only a wake/cancel/fanout
   accelerator and cannot reconstruct Run state.
4. S3-compatible storage is outside the process boundary. Artifact size,
   tenant scope, and SHA-256 are checked independently of object metadata.
5. Workers are replaceable and may be stale. Lease expiry and fencing tokens
   prevent an old worker from committing after ownership changes.
6. Operators, registry publishers, migration identities, and runtime identities
   are separate roles. Runtime identities do not need DDL or release rights.

## Principal abuse cases and controls

| Abuse case | Control | Required evidence |
| --- | --- | --- |
| Tenant/project/object bypass | `SecurityContext` authority, action grants, scoped store queries, not-found masking | Cross-scope API/store negative tests |
| Bearer or provider secret leakage | `SecretRef`, redacted repr/log/trace/audit/error paths | Secret canary tests and repository scan |
| SSRF through URL ingestion | Explicit allowed HTTP hosts, redirect rejection, bounded response | Loopback/link-local/private-range and redirect tests |
| Path or symlink escape | Canonical root checks, symlink rejection, bounded file operations | Traversal/symlink tests on supported platforms |
| Prompt or recalled-content privilege escalation | Trust/provenance labels; external text never becomes SYSTEM authority | Trust-preservation tests |
| Duplicate delivery or stale worker commit | CAS, idempotency key, lease and fencing token | Duplicate/stale-token chaos tests |
| Ambiguous non-idempotent effect replay | Durable effect ledger and `NEEDS_REVIEW` | Kill-after-dispatch test |
| Queue, body, page, or SSE exhaustion | Body/page/queue bounds, deadlines, bounded SSE batches and backoff | Resource-exhaustion tests and load report |
| Revision substitution | Canonical plan/revision digest and resume compatibility check | Revision mismatch tests |
| Audit suppression | Production reference app wires a structured audit sink; sink failures propagate | Audit delivery and redaction tests |

## Residual risks for v2.0.0

- The Agent Server HTTP surface remains **Beta** in `2.0.0`.
- Live provider and OpenViking lifecycle evidence requires approved external
  credentials and is not replaced by offline contracts.
- The reference static-token authenticator is suitable for a bounded
  self-hosted example, not a complete enterprise identity provider.
- Container stdout audit durability depends on an operator-configured collector
  and retention policy.
- A local SQLite soak or single-host benchmark is not production capacity
  evidence.
- Arbitrary third-party non-idempotent side effects cannot be guaranteed
  exactly once.

## Operational evidence

Operational validation should remain source-SHA-bound and record the tested
environment, workload, dependencies, security checks, recovery procedures,
and resulting immutable artifacts.
