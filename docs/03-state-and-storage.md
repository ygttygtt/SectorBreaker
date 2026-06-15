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
- `snippet`
- `summary`
- `confidence`
- `verification_status`
- `collected_at`

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
- evidence index;
- draft artifacts;
- QA issues;
- human review decisions;
- export manifest.

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
