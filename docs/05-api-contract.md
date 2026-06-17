# API Contract

## API Style

FastAPI owns backend contracts. Pydantic schemas are the source of truth. The frontend must call documented API routes rather than infer backend state.

## Core Routes

### Projects

- `POST /api/projects`: create project.
- `GET /api/projects`: list projects.
- `GET /api/projects/{project_id}`: get project.
- `PATCH /api/projects/{project_id}`: update project configuration before a run starts.

Create accepts `source_policy` (`open_web`, `reliable_first`, `reliable_only`, `user_materials_only`). Current v1 implementation supports create/list/detail and workflow definition. Patch/update remains a contract target.

- `GET /api/projects/{project_id}/workflow-definition`: returns the baseline workflow graph definition.

### Runs

- `POST /api/projects/{project_id}/runs`: start a research run.
- `GET /api/runs/{run_id}`: get run status.
- `POST /api/runs/{run_id}/resume`: resume after human review.
- `GET /api/runs/{run_id}/events`: stream run events with SSE.
- `GET /api/runs/{run_id}/workflow-definition`: returns the run graph expanded with Supervisor-selected/skipped agents when available.

Current v1 implementation creates a background run, pauses for Supervisor plan confirmation unless `auto_run=true`, supports resume, and streams SSE node events.

### Evidence And Artifacts

- `GET /api/projects/{project_id}/evidence`
- `GET /api/projects/{project_id}/artifacts`
- `GET /api/artifacts/{artifact_id}`

Current v1 implementation supports project-scoped evidence and artifact lists. Artifact detail remains an upgrade target.

### Q&A

- `POST /api/projects/{project_id}/chat`: ask a question using project-local retrieval.

### Export

- `POST /api/projects/{project_id}/exports`: create export package.
- `GET /api/exports/{export_id}/download`: download export package.

Current v1 implementation returns the export manifest. Download packaging remains an upgrade target.

## Error Shape

Errors should include:

- `code`
- `message`
- `details`
- `request_id`

## Human Review

When the graph interrupts for review, the run status becomes `waiting_for_human`. The frontend must show the gate output and send the user's decision through the resume endpoint.

`POST /api/runs/{run_id}/resume` accepts:

- `guidance`: optional research direction.
- `evidence_data`: optional user material.
- `assistant_brief`: optional Markdown/text external AI report. It is treated as low-trust lead material.
- `plan_confirmed`: confirms the Supervisor plan.

## SSE Events

Node events include:

- `node_started`
- `node_progress`
- `node_completed`
- `node_skipped`
- `node_degraded`
- `node_blocked`
- `node_failed`
- `evidence_collected`
- `claim_extracted`
- `qa_issue_found`
- `human_input_required`

Events may include `progress_current`, `progress_total`, `severity`, and structured `data`.
