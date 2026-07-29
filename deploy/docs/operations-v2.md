# OpenRath v2 operations

## Release and upgrade

- Build immutable images by Git commit digest; never deploy a mutable `latest`.
- Replace every review tag in `deploy/kubernetes/openrath.yaml` with the exact
  `image@sha256:...` produced for the candidate. A manifest containing a tag is
  a template, not release evidence.
- Run `openrath-migrate --check` before traffic and `openrath-migrate` as a
  single pre-deploy Job.
- Database changes are additive in v2.0.0. Roll application pods back first;
  retain added columns/tables until the rollback window closes.
- Take and restore-test PostgreSQL and artifact backups before an upgrade.

The server durable profile rejects synchronous steps that declare a timeout:
an in-process Python thread cannot be preempted safely. Use an async handler or
an isolated executor. Embedded compatibility mode waits for a synchronous
handler to return before recording timeout and must never be presented as a
preemptive cancellation guarantee.

`LocalTrustedPolicy` is limited to an explicit local `trusted_host` grant. It
allows same-process filesystem/network behavior and is unsuitable for
untrusted tenants. Service deployments should supply a fail-closed policy,
governed adapter executors, durable effect ledger, and audit sink.

The reference server requires `OPENRATH_GRANTS` with explicit actions and
rejects the wildcard grant. It emits redacted newline-delimited JSON audit
records to stdout. Production operators must configure a collector, retention,
access control, and delivery alert for that stream; an in-memory sink is never
production evidence.

The Kubernetes template is fail closed for egress. PostgreSQL, Redis, S3, and
an HTTPS egress gateway must run in a namespace labelled
`openrath.io/data-plane=allowed`; DNS is limited to `kube-system`. If the CNI
supports FQDN policies, restrict provider and object-store hostnames there.
Do not replace this with unrestricted `to: []` egress.

## Incident runbooks

### PostgreSQL unavailable

Stop accepting new Runs (`/health/ready` returns 503), keep existing pods from
restart loops, restore database connectivity, verify schema and lease expiry,
then let workers requeue expired leases. Never substitute Redis as state.

### Redis unavailable

Runs remain durable. Alert on signal failures and increased queue latency,
restore Redis, and allow polling to continue. Do not reconstruct Run state
from Redis.

### Worker terminated or stuck

Confirm the worker lease has expired, call the orphan reconciliation loop, and
verify the fencing token increased. A stale worker must fail its next commit.
Inspect dispatched non-idempotent ToolInvocations; they must enter
`NEEDS_REVIEW`, not automatic retry.

### Queue backlog

Measure queued age, database lock time, provider saturation, and artifact
latency. Scale replicas only after confirming PostgreSQL connection capacity.
Rate-limit tenants producing disproportionate load.

### Artifact store unavailable

Keep the Run/checkpoint durable, fail or pause the affected step, and do not
inline payloads beyond the configured limit. Restore object storage and verify
SHA-256 before resuming.

## Backup/restore exercise

Quarterly, restore PostgreSQL and artifacts into an isolated environment,
run `openrath-migrate --check`, fetch historical Runs and artifacts, requeue
an expired lease, and verify a non-idempotent ambiguous invocation remains
blocked for review.

## RC evidence boundary

Offline tests, a locally built wheel, a mutable image tag, or a Fake provider
do not approve a release. RC evidence must be generated from one immutable
commit and include real provider/sandbox/memory lifecycles, PostgreSQL/Redis/S3
restart drills, backup/restore, rollback, scale, soak, SBOM, vulnerability scan,
and the published image digest. Missing infrastructure is recorded as a
release blocker rather than silently skipped.
