# OpenRath v2.0.0 Gate C Design

## Objective and trust boundary

Gate C must turn target-environment observations into a reproducible,
same-commit artifact without treating local tests, handwritten status, or a
short rehearsal as production evidence. The release preparation workflow may
consume only an artifact produced by the dedicated `Collect v2.0.0 Gate C
evidence` workflow. That workflow must run from `main`, on the exact candidate
commit, in a protected `ga-evidence` environment, and on a runner labelled
`openrath-ga`.

The target runner owns infrastructure access. GitHub-hosted release jobs do not
receive Kubernetes, provider, database, or object-store credentials. Operators
place a bundle below a configured runner-local evidence root. The bundle name
is a restricted identifier, not an arbitrary path. The collector copies the
bundle to an isolated temporary directory, validates every report and referenced
file, and uploads it as `openrath-v2.0.0-ga-input`.

The GA preparation workflow independently verifies the source SHA, workflow
name, event type, branch, report semantics, and referenced hashes before it
builds any public candidate.

## Reports and target tooling

Six reports use `openrath.ga-gate-report/1`: tests, live adapters, performance,
soak, drills, and compatibility. Every report identifies the exact source
commit, a timezone-aware generation time, a target-like environment profile,
structured details, open risks, and at least one evidence file. Evidence
entries are relative paths with byte size and SHA-256; absolute paths,
traversal, symlinks, missing files, and hash mismatches fail closed.

`record_gate.py` records tests, live-adapter, drill, and compatibility outcomes
from immutable logs produced by the approved operator commands.
`load_v2.py` executes bounded authenticated HTTP lifecycle load against a
deployed OpenRath API without printing credentials. Separate single-host and
one/two/four-worker samples are combined by `build_performance_report.py`,
which calculates four-worker scaling efficiency.

The existing local SQLite soak remains a review tool. Target soak evidence is
recorded from an eight-hour run plus resource snapshots and must explicitly
state zero errors and no unexplained growth. Drill recording never injects a
fault itself: destructive PostgreSQL, Redis, S3, API, worker, backup/restore,
and rollout/rollback operations remain operator-controlled and require
target-specific runbooks.

## Recovery and verification

Collector reruns are immutable at the report level: all files are copied and
hashed before upload, and a changed bundle produces a different artifact. A
failed or cancelled run cannot authorize preparation. Release preparation
checks the collector workflow identity instead of accepting an artifact from
any successful workflow.

Unit tests cover path containment, symlink rejection, evidence hashing, gate
semantics, performance calculations, target/rehearsal separation, and workflow
identity checks. Actionlint and zizmor validate the workflows. Short local
HTTP tests validate the load client, while real Gate C execution remains
blocked until the approved secrets, target cluster, and protected runner are
available.
