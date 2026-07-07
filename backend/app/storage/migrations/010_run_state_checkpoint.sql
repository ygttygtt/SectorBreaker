CREATE TABLE IF NOT EXISTS run_state_checkpoints (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    checkpoint_type TEXT NOT NULL DEFAULT 'artifact_write',
    artifact_id TEXT,
    iteration   INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rsc_run_id ON run_state_checkpoints (run_id, created_at DESC);
