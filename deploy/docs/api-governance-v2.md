# OpenRath v2 API and maintenance policy

This policy is part of the v2.0.0 release candidate. The RC publishes it for
compatibility feedback; final Stable promotions and the v1 maintenance window
still require repository-owner approval before GA.

## Stability levels

- **Stable**: documented public Python symbols, the `/v1` HTTP resource model,
  persisted v2 schemas, stable error codes, and migration CLI. Breaking changes
  require a new major version.
- **Beta**: explicitly labelled evaluation, deployment-helper, or adapter SDK
  surfaces. A breaking change requires release notes, a migration path, and at
  least one minor release of notice.
- **Experimental**: explicitly labelled research integrations and extension
  hooks. They may change in a minor release and must not be required for the
  durable Run, security, or storage contracts.
- Unlabelled v2 additions are not Stable. They remain Experimental until a
  release note and this policy explicitly classify them. Internal modules and
  names beginning with `_` are not public contracts.

The Agent Server OpenAPI document currently labels `/v1` operations **Beta**.
Stable error codes and persisted fields may be promoted independently only
after the RC evidence gate passes.

For `2.0.0rc1`, the Python v1 façade remains supported and the Agent Server
remains Beta. The RC does not begin or end a maintenance window.

## Action and object authorization

Authentication alone grants no access. Tokens carry explicit action grants;
`*` is an intentionally privileged reference-only grant. The service enforces
the following minimum actions:

| Resource | Read | Mutate/control |
| --- | --- | --- |
| Assistant | `assistant.read` | `assistant.create` |
| Session | `session.read` | `session.create` |
| Run | `run.read` | `run.create`, `run.cancel`, `run.resume` |
| Interrupt | `interrupt.read` | `interrupt.decide` |
| Feedback | — | `feedback.create` |
| Memory | `memory.search` | `memory.put`, `memory.delete` |
| Metrics | `metrics.read` | — |

Run, Session, Interrupt, Feedback, and Memory operations also verify tenant and
project scope. A user-scoped memory namespace cannot name another principal
unless the token has `memory.admin`. Cross-scope objects are returned as not
found to avoid disclosing their existence. Control-plane mutations emit
redacted security audit events when an `AuditSink` is configured.

## SemVer and deprecation

- Patch releases contain compatible fixes, security updates, and documentation.
- Minor releases may add compatible functionality.
- Breaking Stable API or persisted-schema changes require a new major release.
- Stable APIs are deprecated before removal. The default notice is two minor
  releases and at least six months, unless retaining the API would preserve an
  actively exploitable vulnerability.
- Database migrations are forward-only and additive during the rollback
  window. Application rollback precedes removal of old columns or tables.

## v1 compatibility

The v1 Python facade remains available through the owner-approved maintenance
window. v1 JSONL Sessions import as non-resumable historical evidence because
they do not contain a durable program counter or effect outcome. The exact end
date for v1 security and critical-fix support must be approved in
`review/v2.0.0/release-approval.md`; the implementation does not invent that
organizational commitment.

## Security reporting

Report suspected vulnerabilities privately through the repository's GitHub
Security Advisory flow. Do not open a public issue with exploit details,
credentials, tenant data, or unredacted traces. Maintainers should acknowledge,
triage severity, coordinate a fix and advisory, and publish remediation and
affected-version information. Secrets found in reports must be rotated rather
than copied into tests or logs.

## Release evidence

Every release candidate must link:

- compatibility, migration, and rollback evidence;
- unit, conformance, real-backend, chaos, and tenant/security tests;
- a reproducible image digest and dependency lock;
- a CycloneDX SBOM and zero-unaccepted HIGH/CRITICAL scan;
- hardware-bound benchmark and soak profiles;
- explicit owner approval for tag, push, image publication, and deployment.
