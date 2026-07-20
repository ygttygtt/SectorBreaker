# Testing Strategy

## Principles

Tests protect architecture boundaries, data integrity, reversible writes, and
real user output. Fake providers are regression tools, not proof of product
quality.

## Unit Tests

- V3 State and ArtifactMemory serialization/migration.
- Artifact revision persistence and active/superseded filtering.
- Hybrid lexical/vector retrieval across evidence, segments, and active
  artifacts, including semantic no-keyword recall and RRF provenance.
- Content-hash incremental vector synchronization, stale-row deletion,
  rebuild equivalence, and explicit degraded-mode status.
- Vault import path safety, relative paths, limits, and idempotency.
- Deterministic health findings and backlog deduplication.
- AutonomyPolicy enforcement and hard budgets.
- ChangeSet diff, base-hash conflict, apply, and rollback.
- Specialist role/tool allowlists and typed output validation.
- Export active-revision rules and `.sectorbreaker/` metadata.

## API Tests

- project create/list/detail with retired product fields rejected;
- start/continue run and active artifact restore;
- vault import/status;
- audit/health/backlog;
- maintenance run request contracts;
- ChangeSet approve/apply/conflict/rollback;
- chat/follow-up use unified retrieval;
- retrieval status/reindex APIs and honest mode reporting;
- job-source routes do not exist.

## Frontend Tests

- one knowledge-management landing experience, no TalentScope/Boss controls;
- vault import and health summary;
- maintenance backlog selection;
- ChangeSet diff, approval, apply, conflict, and rollback states;
- Agent brief and specialist activity;
- export/open-folder flow.

## Architecture Tests

- production imports have one Agent Kernel owner;
- retired enterprise modules/providers cannot be imported;
- forbidden legacy and enterprise markers fail version isolation;
- frontend workflow definition comes from backend truth;
- specialists cannot apply ChangeSets directly.

## Golden Tests

Stable fixtures cover imported vault structure, health report, active export,
evidence ledger, and `.sectorbreaker` state. Intentional schema changes require
fixture and changelog updates.

## Real Acceptance

Before V3 readiness is claimed, use configured real providers and a real
Obsidian vault to execute import, audit, research, verification, ChangeSet,
approval, apply, export, open-in-Obsidian inspection, and rollback. Inspect
content quality, evidence links, version markers, and absence of retired paths.
Hybrid RAG additionally requires one real local FastEmbed model smoke test; a
fake embedding provider alone cannot prove semantic retrieval quality.
