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
