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

### Configuration

- `GET /api/config/llm`
- `POST /api/config/llm`
- `POST /api/config/llm/test`
- `GET /api/config/search`
- `POST /api/config/search`
- `POST /api/config/search/test`

Current baseline exposes LLM configuration status and search configuration
status. Search config should expose which providers are currently enabled. The
frontend must surface explicit warnings when search is unavailable.

`GET /api/config/search` now also serves as the primary runtime diagnostic
endpoint for search onboarding. In addition to enabled provider names, it should
return:

- `requested_extraction_provider`: the extractor the user asked for;
- `missing_configuration`: missing key names such as `tavily_api_key`,
  `serper_api_key`, `brave_api_key`, `exa_api_key`, or `firecrawl_api_key`;
- `diagnostics`: human-readable fallback / misconfiguration notes;
- `status_message`: a one-line summary suitable for direct frontend display.

`missing_configuration` should reflect the currently requested mode rather than
always listing every unfilled provider key. For example:

- `auto`: report all provider keys only when none are configured;
- `exa`: report only `exa_api_key` if Exa is forced but still missing;
- `multi`: report whichever provider keys are absent from the requested
  aggregate set.

`POST /api/config/search/test` is the recommended connectivity check for the
real search stack. It should:

- run a live test query through the currently configured `SearchProvider`;
- support optional `allowed_domains` / `blocked_domains` constraints for domain-scoped checks;
- optionally run `url -> ContentExtractionProvider` when `url_to_extract` is
  provided;
- return provider names, result count, sample results, and extracted-page
  preview or a structured failure message.

`POST /api/config/search` now supports runtime search-stack updates for local
development. The backend should:

- accept `search_provider_mode` (`auto`, `multi`, `tavily`, `serper`, `brave`, `exa`);
- persist the submitted runtime config locally so restart does not clear it;
- rebuild the in-memory `SearchProvider` from submitted Tavily / Serper / Brave / Exa config;
- rebuild the in-memory `ContentExtractionProvider` from submitted extraction
  config (`http`, `firecrawl`, `jina`);
- make the updated providers immediately visible through `GET /api/config/search`
  and immediately usable by `POST /api/config/search/test`.

### Documents

Contract target for the next search phase:

- `POST /api/projects/{project_id}/documents`
- `POST /api/projects/{project_id}/documents/upload`
- `GET /api/projects/{project_id}/documents`
- `GET /api/documents/{document_id}`
- `GET /api/documents/{document_id}/segments`
- `GET /api/documents/{document_id}/citations`
- `GET /api/documents/{document_id}/evidence-preview`
- `POST /api/documents/{document_id}/ingest-evidence`

Recommended purpose:

- upload or register external AI reports and user materials;
- support `.md` and `.txt` first;
- expand to `.pdf` and `.docx` later;
- return parsing stats such as word count, char count, segment count, and
  extracted citation count.

Current implementation target:

- text payload upload for assistant briefs and user materials;
- multipart file upload for `.md` / `.txt` documents;
- document persistence with file name, mime type, word count, char count, and
  segment/citation counts;
- basic paragraph segmentation and URL citation extraction;
- citation query responses now include first-pass `source_assessment`;
- evidence preview can now convert citations into `EvidenceItem`-shaped payloads
  with `needs_counterevidence` and verification hints;
- document citations can now be explicitly ingested into the project evidence
  ledger through a dedicated API;
- richer source-title extraction and stronger source verification comes next.

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

Upgrade direction:

- keep `assistant_brief` text input for compatibility;
- add uploaded document IDs as a parallel path instead of replacing text input
  immediately.

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

Recommended additive event types for the next search phase:

- `document_uploaded`
- `document_parsed`
- `citation_extracted`
- `source_assessed`
- `verification_task_created`
- `counterevidence_found`
