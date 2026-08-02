CREATE TABLE IF NOT EXISTS agent_missions (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    mission_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_missions_project
ON agent_missions(project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_performance (
    project_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    performance_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, agent_id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
