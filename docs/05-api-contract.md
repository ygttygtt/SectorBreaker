# API Contract

## API Style

FastAPI owns backend contracts. Pydantic schemas are the source of truth. The frontend must call documented API routes rather than infer backend state.

## Core Routes

### Projects

- `POST /api/projects`: create project.
- `GET /api/projects`: list projects.
- `GET /api/projects/{project_id}`: get project.
- `PATCH /api/projects/{project_id}`: update project configuration before a run starts.

Current v1 implementation supports create/list/detail. Patch/update remains a contract target.

### Runs

- `POST /api/projects/{project_id}/runs`: start a research run.
- `GET /api/runs/{run_id}`: get run status.
- `POST /api/runs/{run_id}/resume`: resume after human review.
- `GET /api/runs/{run_id}/events`: stream run events with SSE.

Current v1 implementation runs synchronously from the project endpoint. Run status, resume, and SSE remain upgrade targets.

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
