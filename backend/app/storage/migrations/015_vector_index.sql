CREATE TABLE IF NOT EXISTS vector_index (
    chunk_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    parent_id TEXT,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    relative_path TEXT,
    source_url TEXT,
    verification_status TEXT,
    text_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector BLOB NOT NULL,
    indexed_at TEXT NOT NULL,
    PRIMARY KEY (project_id, chunk_id, embedding_provider, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_vector_index_project_model
ON vector_index(project_id, embedding_provider, embedding_model);

CREATE INDEX IF NOT EXISTS idx_vector_index_source
ON vector_index(project_id, source_id);
