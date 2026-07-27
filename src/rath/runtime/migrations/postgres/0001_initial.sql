CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    session_id UUID NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL,
    state_json JSONB NOT NULL,
    next_nodes_json JSONB NOT NULL,
    idempotency_key TEXT,
    request_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL,
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS runs_tenant_status_idx
    ON runs (tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS run_events (
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL,
    type TEXT NOT NULL,
    data_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL,
    plan_hash TEXT NOT NULL,
    state_json JSONB NOT NULL,
    next_nodes_json JSONB NOT NULL,
    pending_interrupts_json JSONB NOT NULL,
    effect_watermark BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS interrupts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    request_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    decision_kind TEXT,
    decision_actor_id TEXT,
    decision_reason TEXT,
    decision_payload_json JSONB,
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS interrupts_run_pending_idx
    ON interrupts (run_id, decided_at);

CREATE TABLE IF NOT EXISTS run_leases (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    holder_worker_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    fencing_token BIGINT NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS run_leases_expiry_idx
    ON run_leases (active, expires_at);

CREATE TABLE IF NOT EXISTS tool_invocations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    effect_class TEXT NOT NULL,
    idempotency_key TEXT,
    arguments_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (run_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS tool_invocations_reconcile_idx
    ON tool_invocations (status, effect_class, updated_at);
