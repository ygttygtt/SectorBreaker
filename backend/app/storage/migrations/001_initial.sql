CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    market_scope TEXT NOT NULL,
    depth TEXT NOT NULL,
    status TEXT NOT NULL,
    custom_market_scope TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT,
    snippet TEXT NOT NULL,
    summary TEXT,
    confidence REAL NOT NULL,
    verification_status TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    id UNINDEXED,
    project_id UNINDEXED,
    content
);
