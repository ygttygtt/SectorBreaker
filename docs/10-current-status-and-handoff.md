# Current Status And Handoff

## Current Product

SectorBreaker V3 is a local-first, multi-Agent autonomous knowledge-base management system. The first usable knowledge-maintenance loop is implemented.

## Implemented

### Product Cutover

- One production knowledge-management path owned by the Agent Kernel.
- Enterprise talent-demand, TalentScope, Boss/job-source, and old graph workflow code are deleted from production.
- Migration `011_retire_enterprise_talent.sql` archives/normalizes historical enterprise projects and removes enterprise artifacts/evidence.
- `tools/check_version_isolation.py` checks both legacy workflow and enterprise retirement markers.

### Vault And Control Plane

- Safe Markdown Vault import with relative paths, ignored cache folders, limits, snapshot hash, and idempotency.
- Deterministic health audit for broken links, orphan notes, duplicate titles, missing front matter/evidence metadata, and unresolved markers.
- Persistent, deduplicated maintenance backlog.
- Immutable artifact revisions with content hash, active status, supersession links, run id, and ChangeSet id.
- ChangeSet propose/approve/apply/conflict/rollback, factual evidence gate, file/byte limits, and whole-journal prevalidation.
- Existing-note Agent revision now produces a ChangeSet and waits for review instead of mutating the active artifact.

### Agent And Permissions

- V3 State contains ArtifactMemory, AutonomyPolicy, Vault/health/task references, maintenance objective, and delegation log.
- Continuation restores active artifacts before Agent decisions.
- Search/writer/file/byte budgets are runtime-enforced.
- `user_materials_only` and disabled network policy block SearchProvider dispatch.
- Dynamic Specialist roles have typed results and role-level tool allowlists; no Specialist can apply changes.
- Agent decision heartbeat no longer adds a mandatory 10-second delay to fast LLM decisions.

### Retrieval And Export

- Chat and Agent tools share `ProjectRetriever`.
- Current retrieval is lexical: evidence FTS plus document/segment/active-artifact scoring.
- Retrieval excludes superseded artifacts and returns hit-local snippets plus path/hash/verification metadata.
- Exporter has one V3 path, writes active revisions only, cleans stale files, emits V3 front matter, and exports full `.sectorbreaker/` State/health/backlog/ChangeSet metadata.

### Frontend

- Vault path import and automatic audit.
- Health metrics/findings and maintenance Backlog selection.
- Maintenance run launch.
- ChangeSet diff, manual proposal, approve, apply, and rollback.
- Enterprise talent/Boss UI is removed.

## Verification Baseline

- Backend: `182 passed`, one existing Starlette/httpx deprecation warning.
- Frontend: `25 passed`.
- Frontend production build: passed; existing >500 kB chunk warning remains.
- Version isolation: passed.
- Real temporary Vault acceptance: import -> audit -> ChangeSet -> approve -> apply -> export -> process restart -> rollback -> re-export passed.

## Current Retrieval Answer

There is no local embedding model in the current implementation. Evidence uses SQLite FTS; documents, segments, and active artifacts use local lexical scoring. Local embeddings and hybrid retrieval remain later additive work.

## Remaining Work

- Optional local `EmbeddingProvider` and rebuildable vector index.
- Better claim-level semantic verification and counterevidence linking.
- Scheduled/incremental monitoring.
- Direct bidirectional source-Vault synchronization.
- Move/delete operations with stronger recovery semantics.
- Frontend bundle splitting.

## Required Handoff Rule

When status changes, update this file, `docs/11-tooling-handoff.md`, `.claude/memory/current-progress-and-handoff.md`, and `.claude/memory/tooling-handoff.md` in the same commit.
