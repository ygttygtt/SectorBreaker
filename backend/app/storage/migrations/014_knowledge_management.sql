CREATE TABLE IF NOT EXISTS vault_imports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    note_count INTEGER NOT NULL,
    total_bytes INTEGER NOT NULL,
    snapshot_hash TEXT NOT NULL,
    imported_paths TEXT NOT NULL,
    skipped_paths TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vault_imports_project
ON vault_imports(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_health_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    vault_import_id TEXT,
    snapshot_hash TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_reports_project
ON knowledge_health_reports(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS maintenance_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    task_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_maintenance_task_fingerprint
ON maintenance_tasks(project_id, fingerprint);

CREATE TABLE IF NOT EXISTS change_sets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    status TEXT NOT NULL,
    change_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_change_sets_project
ON change_sets(project_id, created_at DESC);
