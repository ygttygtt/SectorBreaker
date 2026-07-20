# API Contract

## API Style

FastAPI owns backend contracts. Pydantic models are the source of truth. Public
requests reject unknown product-mode fields instead of silently accepting a
retired enterprise payload.

## Projects

- `POST /api/projects`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}` (target)
- `GET /api/projects/{project_id}/workflow-definition`

Project creation accepts title, domain/knowledge goal, market scope, depth, and
source policy. V3 exposes one knowledge-management product path; there is no
talent-demand selector.

Archived projects cannot start or continue runs.

## Runs

- `POST /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/continue`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/snapshot`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/trace`
- `POST /api/runs/{run_id}/resume`

The production auto-run owner is the Agent Kernel. Continuation restores the
latest completed/resumable project checkpoint and active artifact revisions.

V3 continuation target body:

```json
{
  "objective": "验证并更新 RAG 页面里的过期描述",
  "task_ids": ["MT-..."],
  "execution_mode": "plan_only",
  "autonomy_policy": {}
}
```

`execution_mode` values:

- `plan_only`: research and create ChangeSets without applying them;
- `apply_safe`: apply only operations allowed by AutonomyPolicy;
- `require_review`: pause on any existing-note update.

## Vault Management

### Import

- `POST /api/projects/{project_id}/vault/import`

Request:

```json
{
  "source_path": "D:/Knowledge/MyVault",
  "max_files": 1000,
  "max_total_bytes": 52428800
}
```

The backend reads Markdown only, preserves safe relative paths, rejects root
escape/symlink escape, and imports into a managed project mirror. It does not
mutate the source vault.

- `GET /api/projects/{project_id}/vault`

Returns latest import metadata, active note count, snapshot hash, and path-safe
note summaries.

## Knowledge Health And Backlog

- `POST /api/projects/{project_id}/audits`
- `GET /api/projects/{project_id}/health`
- `GET /api/projects/{project_id}/maintenance-backlog`

Audit returns deterministic metrics/findings and creates idempotent open
maintenance tasks. Re-running the same snapshot must not duplicate equivalent
open tasks.

## Maintenance Runs And Specialists

- `POST /api/projects/{project_id}/maintenance-runs`

Request selects task ids, objective, execution mode, and optional policy
overrides. The Master Agent decides whether to retrieve, search, delegate a
registered specialist, draft a ChangeSet, ask the user, or block.

Specialist output is never applied directly.

## ChangeSets

- `GET /api/projects/{project_id}/change-sets`
- `POST /api/projects/{project_id}/change-sets/{change_set_id}/approve`
- `POST /api/projects/{project_id}/change-sets/{change_set_id}/apply`
- `POST /api/projects/{project_id}/change-sets/{change_set_id}/rollback`

Apply validates project ownership, allowed operation/path, approval/policy,
base content hash, evidence requirement, active revision, and byte/file budget.
A mismatch returns conflict and writes nothing.

Rollback restores the exact prior active content as a recorded revision/event.

## Evidence, Documents, And Artifacts

- `GET /api/projects/{project_id}/evidence`
- `GET /api/projects/{project_id}/artifacts`
- `GET /api/artifacts/{artifact_id}` (target)
- `POST /api/projects/{project_id}/documents`
- `POST /api/projects/{project_id}/documents/upload`
- document/segment/citation routes retained from V2.

Artifact lists return active revisions by default. An explicit history query may
include superseded revisions.

## Project Retrieval And Q&A

- `POST /api/projects/{project_id}/chat`
- `POST /api/projects/{project_id}/follow-up`

Both use the same RetrievalProvider as the Agent Kernel. Responses include
answer, citation ids, citation details, effective retrieval mode, vector model,
and lexical/vector rank provenance. Follow-up pages are versioned
artifacts and must link back to original evidence where available.

## Retrieval Index

- `GET /api/config/retrieval`
- `POST /api/projects/{project_id}/retrieval/reindex`

Status exposes configured/available provider, model, dimension, index counts,
last error, and effective mode. Reindex generates a replacement snapshot and
atomically swaps only the selected project's current provider/model rows; a
failed rebuild preserves the prior index.

## Export

- `POST /api/projects/{project_id}/exports`
- `POST /api/exports/open-folder`

Exports contain active notes, evidence, manifest, `.obsidian/`, and V3
`.sectorbreaker/` control-plane metadata. Opening a folder remains restricted
to the configured export root.

## Configuration

LLM, search, extraction, presets, and source-registry routes remain local
runtime configuration. Job-source/Boss configuration routes are removed.

## Error And Event Shape

Errors include code/message/details/request id where possible. Run events keep
Thought Summary, Action, Observation, State Update, Decision, writing/review,
human review, and export semantics. V3 adds audit, maintenance task, specialist,
ChangeSet proposed/applied/conflicted/rolled-back events.
