CREATE INDEX IF NOT EXISTS idx_artifacts_project_active
ON artifacts(project_id, active, content_path);

CREATE INDEX IF NOT EXISTS idx_artifacts_supersedes
ON artifacts(supersedes, superseded_by);
