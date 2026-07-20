# V3 Autonomous Knowledge Management

## Positioning

SectorBreaker V3 is a local-first, multi-Agent autonomous knowledge-base
management system. Its primary responsibility is no longer producing a one-shot
domain report. It adopts or creates an Obsidian-compatible knowledge base,
diagnoses its health, plans maintenance work, researches and verifies missing
knowledge, proposes controlled changes, and preserves an auditable history.

The user-facing promise is:

> Give SectorBreaker a knowledge goal and an autonomy policy. It will discover
> gaps, verify facts, maintain the vault, and explain every change.

The original domain-breaking capability remains as the bootstrap path for an
empty knowledge base. The long-lived product loop is knowledge maintenance.

## Product Boundary

V3 owns one vertical responsibility across many subject domains: the knowledge
lifecycle.

It may:

- import an existing Markdown/Obsidian vault into a managed project mirror;
- inspect notes, front matter, headings, wikilinks, evidence ids, and versions;
- create deterministic health findings and a persistent maintenance backlog;
- let the Master Agent choose research, verification, editing, or user-review
  actions;
- delegate scoped tasks to registered specialist Agents;
- propose and apply reversible note changes within an explicit autonomy policy;
- export only active knowledge revisions with evidence and state metadata.

It must not:

- silently edit files outside the managed vault root;
- delete or move user notes by default;
- treat generated prose as verified evidence;
- hide unsupported, conflicting, or stale claims;
- use a fixed role parade and call it multi-Agent autonomy;
- make vector retrieval a prerequisite for the first usable maintenance loop.

## V3 First Usable Slice

The first V3 release is accepted only when this loop works end to end:

```text
import existing vault
  -> deterministic health audit
  -> persistent maintenance backlog
  -> Master Agent selects a task
  -> scoped specialist research / verification
  -> proposed ChangeSet with evidence and diff
  -> policy or human approval
  -> apply to managed vault revision
  -> export active revision
  -> rollback to the previous revision
```

The initial implementation may manage a safe mirror rather than directly
mutating the user's source vault. The exported managed vault is the writable
product surface until direct-vault synchronization has its own conflict and
permission design.

## Architecture

### Master Agent

The Master Agent owns project State, autonomy policy, maintenance backlog,
budgets, specialist delegation, conflict resolution, and the final apply/stop
decision.

### Specialist Agents

Specialists are dynamic and task-scoped. They do not own the project and cannot
directly apply filesystem changes.

Initial registered roles:

- `vault_auditor`: interprets deterministic findings and identifies semantic
  follow-up checks;
- `researcher`: searches or reads project material to fill a knowledge gap;
- `verifier`: checks claims, counterevidence, source quality, and conflicts;
- `knowledge_editor`: returns a structured ChangeSet proposal for selected
  notes.

The Master Agent may dispatch one or more independent specialists. Each receives
a bounded ContextPack, allowed tools, target paths, and budget. Each returns a
typed result or fails closed.

### Retrieval

V3 uses a unified local hybrid retrieval service:

- SQLite FTS/BM25-compatible lexical retrieval plus local embeddings;
- documents, segments, evidence, active artifacts, and imported vault notes;
- one implementation shared by project chat and Agent tools;
- reciprocal-rank fusion and active-revision/source-quality/verification filters;
- segment-level citations and hit-local snippets.

SQLite metadata remains the source of truth and the content-hash incremental
vector index is rebuildable. Unavailable models produce explicit
`lexical_degraded` mode. See `docs/24-local-hybrid-rag.md`.

## State And Storage Contracts

### ArtifactMemory

Every active or historical knowledge file must have:

- artifact id;
- relative content path;
- revision number;
- content hash;
- active/superseded status;
- predecessor and successor ids;
- review status and known gaps;
- last modified run id.

Artifact version state must be persisted in SQLite and restored into Agent
State before a continuation run.

### VaultImport

- `id`
- `project_id`
- `source_path`
- `note_count`
- `snapshot_hash`
- `created_at`

Imported Markdown notes are stored as managed `vault_note` artifacts and as
retrievable project documents. Relative paths are preserved. Hidden/cache
directories, symlinks escaping the root, unsupported files, and over-budget
inputs are rejected or skipped with diagnostics.

### KnowledgeHealthReport

- project and import ids;
- deterministic metrics;
- findings;
- generated timestamp;
- snapshot hash.

Initial deterministic finding types:

- `broken_link`;
- `orphan_note`;
- `duplicate_title`;
- `missing_frontmatter`;
- `missing_evidence_metadata`;
- `unresolved_marker`.

Semantic findings such as stale or conflicting claims require evidence or a
Verifier Agent and must name the detector that produced them.

### MaintenanceTask

- `id`
- `project_id`
- source finding ids;
- task type and objective;
- target paths;
- priority;
- status (`open`, `planned`, `running`, `blocked`, `done`, `dismissed`);
- assigned specialist;
- required evidence types;
- approval requirement;
- related ChangeSet id.

### ChangeSet

Every proposed knowledge change carries:

- change-set id and maintenance task id;
- status (`proposed`, `approved`, `applied`, `conflicted`, `rolled_back`);
- summary and evidence ids;
- one or more create/update operations;
- path, base content hash, before/after content, and unified diff;
- author Agent and timestamps.

Applying a ChangeSet validates the active base hash. A mismatch produces a
conflict instead of overwriting newer content. Delete and move operations are
outside the first usable slice.

### AutonomyPolicy

The default local policy is safe autonomy:

- audit and retrieval: automatic;
- research within source policy: automatic and budgeted;
- create new notes/cards: automatic within allowed paths;
- update existing notes: propose first, apply only when policy permits;
- move/delete: denied;
- factual changes require evidence ids;
- path, file-count, changed-byte, search-call, and writer-call limits are hard
  runtime constraints, not prompt suggestions.

## API Contract

V3 adds:

```text
POST /api/projects/{project_id}/vault/import
GET  /api/projects/{project_id}/vault
POST /api/projects/{project_id}/audits
GET  /api/projects/{project_id}/health
GET  /api/projects/{project_id}/maintenance-backlog
POST /api/projects/{project_id}/maintenance-runs
GET  /api/projects/{project_id}/change-sets
POST /api/projects/{project_id}/change-sets/{change_set_id}/approve
POST /api/projects/{project_id}/change-sets/{change_set_id}/apply
POST /api/projects/{project_id}/change-sets/{change_set_id}/rollback
```

The existing `/continue` endpoint remains a compatibility entrypoint but must
restore active artifacts and ArtifactMemory, not only SectorBreakerState.

## Version Isolation And Enterprise Cutover

The retired `talent_demand` product mode, Boss/job-source providers, frontend
mode, API routes, schemas, and executable tests must be removed from production
code. Historical documentation may record that the experiment existed, but no
production Python or frontend source may import or route to it.

Existing database rows with `project_mode="talent_demand"` are migrated to an
archived status and normalized to the surviving knowledge-management mode. They
must not become runnable through an accidental fallback.

`tools/check_version_isolation.py` must fail if production source contains the
retired mode, enterprise pipeline import, TalentScope UI, Boss job-source code,
or old fixed-workflow markers.

## Acceptance Gates

### Deterministic tests

- nested vault import preserves relative Markdown paths and is idempotent;
- path traversal and escaping symlinks are rejected;
- health audit finds broken links, orphans, duplicate titles, and missing
  metadata consistently;
- repeated audit does not duplicate open maintenance tasks;
- artifact supersession survives process restart;
- retrieval and export exclude superseded artifacts;
- continuation loads active artifacts and can revise a previous-run document;
- ChangeSet apply detects base-hash conflicts;
- rollback restores the exact previous content;
- specialists cannot use unregistered roles or apply changes directly;
- hard autonomy budgets actually block execution.

### Real acceptance

Use one real Obsidian vault and complete:

1. import;
2. health audit;
3. select one meaningful backlog item;
4. research and verify it with configured providers;
5. generate a cited note revision;
6. inspect and approve the diff;
7. apply and export;
8. open the vault in Obsidian;
9. rollback and confirm byte-for-byte restoration;
10. confirm no enterprise or legacy markers appear in events, imports, or
    exported files.

## Explicit Later Work

- incremental background monitoring and scheduled refresh;
- direct bidirectional synchronization with a user's source vault;
- move/delete operations with stronger approval and recovery semantics;
- multi-user collaboration, cloud deployment, and organization permissions.
