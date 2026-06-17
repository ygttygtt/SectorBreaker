ALTER TABLE projects ADD COLUMN source_policy TEXT DEFAULT 'reliable_first';

ALTER TABLE evidence ADD COLUMN source_channel TEXT DEFAULT 'search';
ALTER TABLE evidence ADD COLUMN source_policy TEXT;
ALTER TABLE evidence ADD COLUMN raw_excerpt TEXT;
ALTER TABLE evidence ADD COLUMN claims TEXT DEFAULT '[]';
ALTER TABLE evidence ADD COLUMN source_quality TEXT DEFAULT 'unknown';
ALTER TABLE evidence ADD COLUMN claim_strength TEXT DEFAULT 'opinion';
ALTER TABLE evidence ADD COLUMN bias_risk TEXT;
ALTER TABLE evidence ADD COLUMN recency TEXT;
ALTER TABLE evidence ADD COLUMN corroborating_evidence_ids TEXT DEFAULT '[]';
ALTER TABLE evidence ADD COLUMN conflicting_evidence_ids TEXT DEFAULT '[]';
ALTER TABLE evidence ADD COLUMN needs_counterevidence INTEGER DEFAULT 0;
ALTER TABLE evidence ADD COLUMN collected_by TEXT;
ALTER TABLE evidence ADD COLUMN used_by_artifact_ids TEXT DEFAULT '[]';
