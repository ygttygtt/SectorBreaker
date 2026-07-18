# SectorBreaker Project Brief

## Product Goal

SectorBreaker is a local-first, multi-Agent autonomous knowledge-base
management system. It helps a user create, adopt, inspect, verify, maintain, and
grow an Obsidian-compatible knowledge base while keeping changes evidence-linked,
auditable, and reversible.

The original domain-breaking workflow is retained as the bootstrap experience
for an empty knowledge base. The product is no longer positioned as a one-shot
Deep Search report writer or a generic AI learning assistant.

## Core Promise

Give SectorBreaker a knowledge goal and an autonomy policy. The system should:

- understand the existing vault and project material;
- discover structural and factual gaps;
- create a prioritized maintenance backlog;
- research and verify missing knowledge through approved providers;
- delegate scoped work to specialist Agents when useful;
- propose or apply controlled note revisions;
- preserve evidence, versions, diffs, and rollback points;
- continue growing the knowledge base across runs.

## First V3 Scope

- Single-user, local-first workbench.
- One production knowledge-management mode owned by the Agent Kernel.
- Import an existing Markdown/Obsidian vault into a managed mirror.
- Deterministic knowledge-health audit for structure and metadata.
- Persistent maintenance tasks.
- Master Agent plus dynamically dispatched specialist Agents.
- Evidence-linked note creation and revision.
- Active artifact revisions, ChangeSets, approval, apply, and rollback.
- Unified project retrieval over evidence, documents, segments, and active
  knowledge artifacts.
- Obsidian export with `.sectorbreaker/` state and audit metadata.

## Explicit Non-Goals For The First V3 Release

- No enterprise talent-demand or recruitment product mode.
- No Boss/job-board connector or login-gated scraping.
- No multi-user account system.
- No automatic cloud scheduler or background monitoring daemon.
- No direct destructive synchronization with the user's source vault.
- No move/delete note operations by default.
- No requirement for vector retrieval before the maintenance loop is usable.
- No production cloud deployment automation.

Local embeddings, hybrid vector retrieval, scheduled monitoring, and direct
bidirectional vault synchronization are later additive upgrades.

## Core User Journeys

### Bootstrap A New Knowledge Base

1. User creates a project with a domain, goal, source policy, and depth.
2. Agent Kernel creates an adaptive knowledge schema.
3. Master Agent researches, verifies, writes, and exports the first vault.
4. The run preserves State, evidence, artifacts, and open maintenance tasks.

### Adopt And Maintain An Existing Vault

1. User imports an existing Obsidian/Markdown vault into a managed mirror.
2. System scans paths, front matter, links, metadata, and content hashes.
3. Deterministic audit produces a knowledge-health report and backlog.
4. Master Agent selects a task and may delegate research, verification, or
   editing to specialist Agents.
5. System produces an evidence-linked ChangeSet and diff.
6. Policy or user approval allows the active revision to change.
7. Export contains only active revisions and supports rollback.

### Continue Growing A Vault

1. User asks a follow-up question or selects an open maintenance task.
2. System restores State and active ArtifactMemory.
3. Agent retrieves existing knowledge before searching externally.
4. It updates or creates the smallest useful set of notes.
5. The new state, evidence, task status, and revision history are persisted.

## Technical Foundation

- Python + FastAPI
- Agent Kernel using structured State, Tools, Decisions, Observations, and
  StateDelta
- SQLite for projects, evidence, documents, checkpoints, artifact revisions,
  audits, maintenance tasks, and ChangeSets
- React + TypeScript local workbench
- Markdown/Obsidian as the human-readable knowledge surface
- Replaceable LLM, search, extraction, and retrieval provider interfaces

## Authoritative V3 Design

Read `docs/23-autonomous-knowledge-management-v3.md` before changing V3 vault
management, autonomy policy, specialist delegation, artifact versioning,
ChangeSets, retrieval, or enterprise cutover behavior.
