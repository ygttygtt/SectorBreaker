CREATE TABLE IF NOT EXISTS document_segments (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    citation_refs TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS document_citations (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    raw_reference TEXT NOT NULL,
    source_title TEXT,
    source_url TEXT,
    referenced_segment_ids TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
