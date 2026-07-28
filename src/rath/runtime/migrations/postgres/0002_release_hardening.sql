ALTER TABLE schema_migrations
    ADD COLUMN IF NOT EXISTS filename TEXT;
ALTER TABLE schema_migrations
    ADD COLUMN IF NOT EXISTS checksum TEXT;

ALTER TABLE tool_invocations
    ADD COLUMN IF NOT EXISTS node_id TEXT;
ALTER TABLE tool_invocations
    ADD COLUMN IF NOT EXISTS checkpoint_sequence BIGINT;
ALTER TABLE tool_invocations
    ADD COLUMN IF NOT EXISTS invocation_sequence BIGINT;

CREATE UNIQUE INDEX IF NOT EXISTS tool_invocations_run_sequence_idx
    ON tool_invocations (run_id, invocation_sequence)
    WHERE invocation_sequence IS NOT NULL;

CREATE INDEX IF NOT EXISTS run_events_created_idx
    ON run_events (run_id, created_at, sequence);

ALTER TABLE revisions
    ADD COLUMN IF NOT EXISTS content_digest TEXT;
UPDATE revisions
    SET content_digest = code_digest || ':' || id::text
    WHERE content_digest IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS revisions_content_digest_idx
    ON revisions (content_digest);
