# API Contract

## API Style

FastAPI owns backend contracts. Pydantic schemas are the source of truth. The frontend must call documented API routes rather than infer backend state.

## Core Routes

### Projects

- `POST /api/projects`: create project.
- `GET /api/projects`: list projects.
- `GET /api/projects/{project_id}`: get project.
- `PATCH /api/projects/{project_id}`: update project configuration before a run starts.

Create accepts `source_policy` (`open_web`, `reliable_first`, `reliable_only`, `user_materials_only`) and additive `project_mode`.

`project_mode` values:

- `domain_knowledge` (default): run the V2 Agent Kernel learning-oriented knowledge-base workflow.
- `talent_demand`: run the V1.3 Talent Demand Intelligence workflow.

Old create-project payloads that omit `project_mode` remain valid and are stored
as `domain_knowledge`. Current implementation supports create/list/detail and
workflow definition. Patch/update remains a contract target.

- `GET /api/projects/{project_id}/workflow-definition`: returns the baseline workflow graph definition. For `domain_knowledge`, this is the V2 Agent Kernel graph (`initialize_state`, `external_materials`, `agent_decide`, `tool_execution`, `state_update`, `artifact_writing`, `artifact_review`, `human_feedback`, `export`).

### Runs

- `POST /api/projects/{project_id}/runs`: start a research run.
- `POST /api/projects/{project_id}/continue`: start a follow-up Agent Kernel run from the latest project checkpoint.
- `GET /api/runs/{run_id}`: get run status.
- `POST /api/runs/{run_id}/resume`: resume after human review.
- `GET /api/runs/{run_id}/events`: stream run events with SSE.
- `GET /api/runs/{run_id}/workflow-definition`: returns the run graph. Runs with a stored Supervisor plan return the expanded legacy Supervisor graph; personal Agent Kernel runs without a Supervisor plan return the Agent Kernel graph.

Current implementation creates a background run, pauses for Supervisor plan confirmation unless `auto_run=true`, supports resume, and streams SSE node events. The `auto_run=true` personal path uses the V2 Agent Kernel loop and must not import archived legacy pipelines.

`POST /api/projects/{project_id}/continue` is supported for
`project_mode="domain_knowledge"` only. It loads the latest resumable
`SectorBreakerState` checkpoint by `project_id`, creates a new run, and re-enters
the V2 Agent Kernel with `resume_state`. It must not look up only
`run_id=project_id`, because previous continue runs save checkpoints under their
own run ids. The response shape is:

```json
{
  "run_id": "...",
  "status": "started",
  "resumed_from_checkpoint": true
}
```

If no resumable checkpoint exists, the endpoint returns 404. Failed/diagnostic
checkpoints are not valid default continuation sources.

### Evidence And Artifacts

- `GET /api/projects/{project_id}/evidence`
- `GET /api/projects/{project_id}/artifacts`
- `GET /api/artifacts/{artifact_id}`

Current v1 implementation supports project-scoped evidence and artifact lists. Artifact detail remains an upgrade target.

### Configuration

- `GET /api/config/llm`
- `POST /api/config/llm`
- `POST /api/config/llm/test`
- `GET /api/config/llm/presets`
- `PUT /api/config/llm/presets/{preset_id}`
- `DELETE /api/config/llm/presets/{preset_id}`
- `POST /api/config/llm/presets/{preset_id}/apply`
- `GET /api/config/search`
- `POST /api/config/search`
- `POST /api/config/search/test`
- `GET /api/config/job-source`
- `POST /api/config/job-source`
- `POST /api/config/job-source/test`

Current baseline exposes LLM configuration status, local LLM presets, and search
configuration status. Search config should expose which providers are currently
enabled. The frontend must surface explicit warnings when search is unavailable.

LLM presets are local runtime configuration for test convenience. Presets may
include provider name, OpenAI-compatible base URL, model, max tokens, notes, and
an API key, but list/read responses must never return the API key. They return
`has_api_key` instead. The default runtime config file is ignored by Git, and
`*.runtime-config.json` must remain ignored so user-created presets are not
uploaded to GitHub.

Built-in LLM preset templates:

- `deepseek-official`
- `sensenova-v4-flash`
- `mimo`

`POST /api/config/llm/presets/{preset_id}/apply` loads the local preset,
optionally updates its local key from the request body, rebuilds the active LLM
provider, and writes the active LLM config back to local runtime config. Applying
a preset requires `base_url`, `api_key`, and `model`.

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

`POST /api/config/job-source` is local-only runtime configuration for the
enterprise talent-demand job-source path. It accepts:

- `enabled`
- `provider` (`disabled` or `boss_agent_cli`)
- `boss_agent_cli_command`
- `boss_agent_cli_args_template`
- `boss_agent_cli_timeout_seconds`
- `boss_keyword`
- `boss_city`
- `boss_limit`

`POST /api/config/job-source/test` runs a small configured provider check and
returns sample job postings when the local tool is available.

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
- multipart file upload for `.md` / `.txt` / `.docx` / `.pdf` documents;
- `.docx` is parsed through WordprocessingML text extraction; `.pdf` uses
  `pypdf` when installed and otherwise attempts a basic text fallback, returning
  a clear parse error when no text can be extracted;
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

Response remains backward compatible:

- `answer`
- `citations`
- `citation_details` with `source_id`, `source_type`, `title`, `snippet`,
  `score`, and optional `url`.

### Export

- `POST /api/projects/{project_id}/exports`: create export package.
- `GET /api/exports/{export_id}/download`: download export package.

Current v1 implementation returns the export manifest. Download packaging remains an upgrade target.

The export manifest now includes `export_dir`, the absolute local folder path.
Local workbench clients may call `POST /api/exports/open-folder` with that path.
The backend must validate that the target folder is inside the configured export
root before opening it with the operating system.

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

## Talent Demand Mode

When a project has `project_mode="talent_demand"` and a run is started with
`auto_run=true`, the API routes to the talent-demand pipeline instead of the V1
domain-knowledge pipeline.

Recommended input path:

- `POST /api/projects/{project_id}/documents` or `/documents/upload` with
  `channel="user_upload"` for JD samples, internal role descriptions, or pasted
  hiring requirements.
- `channel="assistant_brief"` for Gemini/Kimi/DeepSeek/Kwen/other external AI
  research reports.
- Search providers are used as supplement when uploaded/source materials are
  thin.

Talent-demand runs emit these additional gates:

- `talent_source_intake`
- `boss_job_intake` when enterprise Boss/job-source collection is enabled
- `jd_signal_extraction`
- `skill_normalization`
- `source_coverage`
- `talent_synthesis`
- `artifact_review`
- `obsidian_export`

`source_coverage` events include a `SourceCoverageMatrix` payload. Result UIs
should render this as warning-level coverage context, not as raw JSON.

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
