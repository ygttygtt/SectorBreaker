CREATE INDEX IF NOT EXISTS idx_runs_project_status_lease
ON runs(project_id, status, lease_expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_single_recovery_child
ON runs(resumed_from_run_id)
WHERE resumed_from_run_id IS NOT NULL;
