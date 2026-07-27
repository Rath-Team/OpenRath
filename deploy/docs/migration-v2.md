# OpenRath v1 → v2 migration

OpenRath v2 uses durable Runs, checkpoints, effect ledgers, immutable
revisions, and tenant-scoped resources. A v1 JSONL Session contains a
transcript but no reliable program counter or external-side-effect outcome.
It is therefore imported as historical evidence and is never resumed as an
active v2 Run.

## Safe procedure

1. Stop v1 writers or take a filesystem snapshot. Keep the original data
   read-only throughout the migration.
2. Back up PostgreSQL and the artifact root.
3. Run an inventory (no writes):

   ```bash
   python scripts/migrate_v1_to_v2.py \
     --source /data/v1/sessions \
     --report migration-inventory.json \
     --tenant TENANT_ID
   ```

4. Review every `invalid` or partial Session. Partial Sessions import as
   `NEEDS_REVIEW`; closed Sessions import as historical `SUCCEEDED` Runs.
5. Apply with explicit storage targets:

   ```bash
   python scripts/migrate_v1_to_v2.py \
     --source /data/v1/sessions \
     --report migration-result.json \
     --tenant TENANT_ID \
     --apply \
     --postgres-dsn "$OPENRATH_POSTGRES_DSN" \
     --artifact-root /data/openrath-artifacts
   ```

The import is idempotent per legacy Session ID. Imported content carries
`provenance=legacy-import`, `trust=untrusted`, and `resumable=false`.
Remote sandbox identities are not reattached. Credentials are not copied.

## Rollback

The migration does not mutate v1 files. Roll back application traffic to v1
and retain the v2 database and artifacts for investigation. Do not down-migrate
v2 Runs into v1 JSONL because checkpoint and effect semantics would be lost.
