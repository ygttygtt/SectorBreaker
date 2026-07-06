# State And Storage

## Storage Principles

SQLite stores structured state and metadata. Files store human-readable research artifacts. Generated runtime data is not committed.

## Core Entities

### ResearchProject

- `id`
- `title`
- `domain`
- `market_scope`
- `depth`
- `source_policy`
- `project_mode`
- `status`
- `created_at`
- `updated_at`

### ResearchRun

- `id`
- `project_id`
- `graph_state_version`
- `current_gate`
- `status`
- `checkpoint_id`
- `started_at`
- `completed_at`

### EvidenceItem

- `id`
- `project_id`
- `source_url`
- `source_title`
- `source_type`
- `source_channel`
- `source_policy`
- `raw_excerpt`
- `snippet`
- `summary`
- `claims`
- `source_quality`
- `claim_strength`
- `bias_risk`
- `recency`
- `corroborating_evidence_ids`
- `conflicting_evidence_ids`
- `needs_counterevidence`
- `collected_by`
- `used_by_artifact_ids`
- `confidence`
- `verification_status`
- `collected_at`

V1.4 adds `source_channel="boss_job"` for structured recruitment samples
collected through the enterprise talent-demand job-source provider.

### EvidenceClaim

- `claim_id`
- `text`
- `claim_type`
- `support_level`
- `requires_verification`
- `verification_status`
- `evidence_ids`
- `counterevidence_ids`
- `notes`

### Artifact

- `id`
- `project_id`
- `artifact_type`
- `schema_version`
- `title`
- `content_path`
- `source_evidence_ids`
- `created_at`

## Graph State

`ResearchState` should include:

- project configuration;
- current gate;
- coverage checklist;
- task queue;
- supervisor plan;
- evidence index;
- draft artifacts;
- QA issues;
- QA report;
- human review decisions;
- export manifest.

## V2 Agent State And Memory

V2 introduces a separate Agent cognition state under
`backend/app/agent_state/`. This does not replace the older `ResearchState`
immediately; it provides the durable models needed for the next LangGraph-native
ReAct rebuild.

Core models:

- `SectorBreakerState`: top-level task state with `meta_context`,
  `knowledge_schema`, `shared_knowledge`, `evidence_refs`, `working_memory`,
  `decision_log`, and `human_feedback`.
- `KnowledgeSchema` / `KnowledgeLayer`: dynamic L0-L5 practical cognition
  schema, including optional prerequisite basics, What/Why, Who, How,
  Money/Incentives, and Risks/Boundaries.
- `SharedKnowledge`: curated entities, claims, relationships, open questions,
  and source memories that are safe to reuse across nodes.
- `TaskMemory`: short-lived local ReAct working memory for one task or
  specialist Agent. It stores attempts and reflections, then compresses them
  before crossing node boundaries.
- `ContextPack`: the curated prompt payload created by `ContextPackBuilder`;
  it includes relevant goals, layer criteria, claims, evidence snippets, open
  questions, and compressed working memory while excluding raw dumps and noise.

Design rule: long documents, raw pages, rejected sources, and event logs stay in
storage/audit surfaces. LLM calls receive `ContextPack`, not the whole state.

V2 governance update: Agent Kernel state is no longer append-only. Deltas may
hide/delete noisy source memories, hide/delete/supersede or update claims,
resolve open questions, update layer coverage scores/status, and record phase
reflections. `ContextPackBuilder` must filter hidden, inactive, rejected, and
superseded memories before prompt construction. Adaptive schemas may use string
layer ids in addition to the original L0-L5 enum ids.

## Source Policy

`source_policy` values:

- `open_web`: broad exploration; weak sources are allowed but downgraded.
- `reliable_first`: reliable sources first, open web as fallback.
- `reliable_only`: only reliable public/official/company-disclosure/user-trusted sources may support facts.
- `user_materials_only`: no open search unless the user later changes policy.

## File Layout

Generated project files should use:

```text
exports/<project-slug>/
  manifest.json
  00-研究框架/
  01-行业地图/
  02-市场现状/
  03-玩家与交易单位/
  04-内容与渠道/
  05-机会地图/
  99-待验证问题/
```

## Versioning

State, artifacts, and exports must carry schema versions. Breaking schema changes require migration notes and tests.

## Project Mode

`project_mode` is additive and defaults to `domain_knowledge` for old payloads
and old database rows.

Supported values:

- `domain_knowledge`: the existing learning-oriented V1/V1.2 knowledge-base path.
- `talent_demand`: the V1.3 talent-demand intelligence path.

SQLite migration `009_project_mode.sql` adds the column with default
`domain_knowledge`.

## V1.4 Runtime Job Source Config

Boss/job-source settings are local runtime configuration, not committed state.
They are stored with the existing runtime config file and include:

- `job_source_enabled`
- `job_source_provider`
- `boss_agent_cli_command`
- `boss_agent_cli_args_template`
- `boss_agent_cli_timeout_seconds`
- `boss_keyword`
- `boss_city`
- `boss_limit`

Project RAG currently reuses existing SQLite evidence/documents/artifacts tables
and FTS evidence index. No vector database migration is required for V1.4.
