# OpenRath v2 API and maintenance policy

This policy is part of the v2.0.0 review candidate and becomes effective only
when the repository owner approves the release.

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
- Unlabelled public APIs are treated as Stable. Internal modules and names
  beginning with `_` are not public contracts.

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
