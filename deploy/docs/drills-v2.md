# OpenRath v2 target validation and recovery drills

These procedures produce Gate C evidence for one immutable source commit. Run
them only in an approved, isolated target-like environment with an operations
owner, a rollback decision maker, tested backups, and a documented maintenance
window. A Docker Desktop rehearsal does not satisfy this gate.

## Evidence directory

Create one runner-local directory below the configured
`OPENRATH_GA_EVIDENCE_ROOT`. Its leaf name is the bundle ID used when
dispatching `Collect v2.0.0 Gate C evidence`.

```text
<root>/<bundle-id>/
  tests.json
  live-adapters.json
  performance.json
  soak.json
  drills.json
  compatibility.json
  evidence/
    ...
```

Every command and target observation must be written below `evidence/`.
Never place credentials, bearer headers, kubeconfig content, database
passwords, or provider responses containing user data in these files. The
collector accepts only UTF-8 JSON/log/text/XML/CSV files and rejects common
credential patterns before upload.

## Live adapters

Capture logs for the required live Provider, OpenSandbox, and OpenViking
lifecycle tests. Skips, `continue-on-error`, or a successful offline-only run
are failures. Record the gate with `record_gate.py`; the details object must
set `provider`, `opensandbox`, and `openviking` to `passed`.

## Capacity and scaling

Deploy the same image digest and source commit for all samples. Run
`load_v2.py` for a minimum of five minutes for:

1. single-host, one embedded worker;
2. split profile, one worker replica;
3. split profile, two worker replicas;
4. split profile, four worker replicas.

The authentication token is read from `OPENRATH_TOKEN`; it is never a command
argument or report field. Combine the four raw samples with
`build_performance_report.py`. Four-worker throughput must be at least 70% of
linear scaling from the one-worker split baseline.

## Eight-hour soak

Run `load_v2.py` against the split target for at least 28,800 seconds without
`--max-runs`. Capture resource snapshots before warm-up and after completion.
Each snapshot uses:

```json
{
  "schema": "openrath.v2.resource-snapshot/1",
  "source_commit": "<40 hex>",
  "phase": "before",
  "captured_at": "<ISO 8601>",
  "components": {
    "api": {"memory_bytes": 0, "restarts": 0},
    "worker": {"memory_bytes": 0, "restarts": 0},
    "postgres": {"connections": 0, "storage_bytes": 0}
  }
}
```

An operations owner compares time-series telemetry, queue age, database
connections/storage, pod restarts, memory, and error logs. The signed-off
assessment must use `openrath.v2.resource-assessment/1`, identify the same
commit and assessor, explain the observed delta, and set
`unexplained_resource_growth` to `false`. Build `soak.json` with
`build_soak_report.py`.

## Fault and recovery matrix

Stop immediately if data integrity is uncertain, the backup cannot be read, a
non-idempotent effect is replayed automatically, or rollback cannot complete.
Record start/end timestamps, operator, recovery time, observed state, and data
loss for every drill:

1. terminate an active worker and verify lease expiry, fencing, and requeue;
2. terminate an API replica and verify readiness, reconnect, and SSE resume;
3. interrupt PostgreSQL and verify readiness becomes 503 with no false success;
4. interrupt Redis and verify durable state remains in PostgreSQL;
5. restart S3/object storage and verify hashes and bounded retry semantics;
6. restore PostgreSQL and artifacts into an isolated namespace, run
   `openrath-migrate --check`, and verify RPO 0 / RTO at most 60 minutes;
7. roll from the previous supported release to the candidate, roll the
   application back while retaining additive schema, then roll forward again.

Record structured results, raw operator logs, source commit, environment,
timestamps, and recovery outcomes in the operator's evidence system.
