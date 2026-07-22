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
- Specialist prompts receive bounded active-artifact and local Hybrid RAG context; structured result summaries persist in the delegation log.

### Web Sources

- Search adapters: Tavily, Serper, Brave, Exa, and Firecrawl.
- `multi` executes providers concurrently, isolates failures, deduplicates URLs, and fairly merges source sets.
- Agent search supports explicit preferred domains; source-pack connectors report executable, missing-config, manual, or planned status honestly.
- The configuration workbench can load a dedicated source pack into the real search/extraction self-test.
- Agent decision heartbeat no longer adds a mandatory 10-second delay to fast LLM decisions.
- Production Agent search now extracts readable bodies from up to three
  accepted URLs, persists extraction provenance on Evidence, and isolates page
  failures instead of silently falling back for the whole query.
- Domain policies are rechecked locally after Provider results; out-of-policy
  URLs are rejected even if a search vendor ignores its domain parameters.
- Heuristic source assessment can no longer mark evidence `verified`; source
  quality alone is capped at `partially_verified`.
- Blank secret fields preserve stored search keys, while the status API exposes
  non-secret configured-provider names.
- Domain-pack entries are explicitly labeled discovery-only and are not counted
  as configured direct connectors; inactive extraction adapters report
  `available_not_selected`.
- Search self-test fails closed for `user_materials_only`, zero accepted
  results, and empty/short/binary extraction output.

### Human Resume

- `POST /api/runs/{run_id}/resume` now restores a waiting run from its durable
  checkpoint, persists typed feedback, injects it into State/ContextPack, and
  internalizes an optional assistant brief as low-trust project material.

### Retrieval And Export

- Chat and Agent tools share `ProjectRetriever`.
- FastEmbed uses the local `BAAI/bge-small-zh-v1.5` model with asymmetric query/document encoding.
- A rebuildable SQLite vector index incrementally embeds evidence, document segments, and active-artifact chunks by content hash.
- Lexical and vector rankings are fused with RRF; citations retain both ranks/scores and embedding provenance.
- Retrieval excludes superseded artifacts, deletes stale chunks, and returns hit-local snippets plus path/hash/verification metadata.
- Model/runtime failures are explicitly reported as `lexical_degraded`; disabled embeddings report `lexical`.
- Exporter has one V3 path, writes active revisions only, cleans stale files, emits V3 front matter, and exports full `.sectorbreaker/` State/health/backlog/ChangeSet metadata.

### Frontend

- Vault path import and automatic audit.
- Health metrics/findings and maintenance Backlog selection.
- Maintenance run launch.
- ChangeSet diff, manual proposal, approve, apply, and rollback.
- Hybrid RAG status/model/index diagnostics, reindex action, and citation provenance badges.
- Enterprise talent/Boss UI is removed.

## Verification Baseline

- Backend: `214 passed`, one existing Starlette/httpx deprecation warning.
- Frontend: `30 passed`.
- Frontend production build: passed; existing >500 kB chunk warning remains.
- Version isolation: passed.
- Real temporary Vault acceptance: import -> audit -> ChangeSet -> approve -> apply -> export -> process restart -> rollback -> re-export passed.

## Current Retrieval Answer

The current implementation is real local Hybrid RAG, not keyword matching behind a RAG label. FastEmbed produces 512-dimensional local embeddings, SQLite persists a content-hash incremental vector index, and `ProjectRetriever` fuses lexical/vector rankings with RRF. `python tools/smoke_local_hybrid_rag.py` validates a no-shared-keyword vector-only recall against the real model.

## Remaining Work

- Better claim-level semantic verification and counterevidence linking.
- Per-Specialist bounded tool execution and validated promotion of findings into StateDelta/ChangeSets.
- Optional Firecrawl map/crawl contract after crawl budgets, robots/policy handling, and persistence are designed.
- Scheduled/incremental monitoring.
- Direct bidirectional source-Vault synchronization.
- Move/delete operations with stronger recovery semantics.
- Frontend bundle splitting.

## Required Handoff Rule

When status changes, update this file, `docs/11-tooling-handoff.md`, `.claude/memory/current-progress-and-handoff.md`, and `.claude/memory/tooling-handoff.md` in the same commit.
