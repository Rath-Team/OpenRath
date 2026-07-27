# OpenRath v2 operations

## Release and upgrade

- Build immutable images by Git commit digest; never deploy a mutable `latest`.
- Run `openrath-migrate --check` before traffic and `openrath-migrate` as a
  single pre-deploy Job.
- Database changes are additive in v2.0.0. Roll application pods back first;
  retain added columns/tables until the rollback window closes.
- Take and restore-test PostgreSQL and artifact backups before an upgrade.

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
