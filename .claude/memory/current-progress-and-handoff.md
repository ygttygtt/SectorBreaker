---
name: current-progress-and-handoff
description: SectorBreaker V3 current implementation and next work
metadata:
  type: project
---

SectorBreaker is now a local-first multi-Agent autonomous knowledge-base management system.

Implemented V3 loop:

- safe Vault import;
- deterministic health audit;
- persistent maintenance backlog;
- Master Agent plus typed, allowlisted Specialists;
- Specialists receive bounded active-artifact and local Hybrid RAG context;
- Tavily/Serper/Brave/Exa/Firecrawl search with concurrent fair multi-provider merging and executable source-pack domain targeting;
- persisted project source-pack/domain policy with explicit `prefer` fallback
  and hard `require` enforcement;
- actual Provider fan-out and extraction budgets with typed per-Provider diagnostics;
- production search body extraction with persisted provenance and local domain-policy enforcement;
- public-URL/redirect SSRF checks and atomic backed-up runtime configuration;
- typed waiting-run resume with feedback injected into Agent State/ContextPack;
- owner-checked run leases, explicit interrupted/orphaned reconciliation, and
  lineage-linked crash recovery in API/UI;
- search-key preservation and honest discovery-only source-pack status;
- current-run output completion gate and fail-loud checkpoint persistence;
- unified active-only Hybrid RAG with local FastEmbed vectors and RRF;
- ChangeSet diff/approval/apply/conflict/rollback;
- project-owned evidence resolution for ChangeSet apply/artifact review, plus
  verified-claim downgrade when evidence ids are unknown;
- idempotent follow-up pages with real-evidence-only artifact metadata;
- immutable Artifact revisions and ArtifactMemory continuation;
- V3 Obsidian export with full `.sectorbreaker/` metadata;
- frontend Vault/health/backlog/ChangeSet workbench.
- frontend readiness matrix, real run timeline with durable budget telemetry,
  result quality next-action verdicts, remembered Vault paths/read-only export
  guidance, and evidence/base-hash ChangeSet review summary;
- lazy-loaded ConfigPanel, KnowledgeManagementPanel and WorkflowEditor chunks.

Retired and deleted from production:

- talent-demand/TalentScope;
- Boss/job-source;
- old graph workflow and fixed pipeline tests.

Current verification baseline:

- backend 265 passed;
- frontend 33 passed;
- frontend build passed;
- version isolation passed;
- import/audit/apply/export/restart/rollback/re-export acceptance passed.
- real V3 web acceptance passed with deepseek-v4-flash, Tavily, HTTP extraction,
  42 search Evidence, 4 active artifacts, approve/apply/resume, and full export
  (`project-63a8ed6dcd05454ab28cc0443a4e765b`).

Current RAG is real local Hybrid RAG: `BAAI/bge-small-zh-v1.5`, content-hash incremental SQLite vectors, lexical/vector RRF, typed provenance, and explicit `lexical_degraded` fallback. The real-model smoke test proves vector-only recall without shared keywords.

Next valuable work: claim-level semantic support/counterevidence gates, per-Specialist bounded tool
execution, one real direct source connector, optional Firecrawl map/crawl
contracts, scheduled monitoring, and direct bidirectional Vault sync.
# 2026-08-02 Demo-First Multi-Agent 增量

- 新增 `docs/27-demo-first-agent-contract-network.md`；唯一生产入口仍是 V3 Agent Kernel。
- 已实现 LiveChallenge、Mission DAG、Manifest、可解释派单、Mini-ReAct、Deliverable 验收/返工/结算、A2A 1.x Worker 与本地 failover、Starter Note ChangeSet。
- 前端 Mission Control 与真实 Demo Preflight 门禁已接通。
- 十个随机领域的真实 Provider 300 秒 Release Gate 尚未执行，禁止对外声称 Demo Ready。
- 已完成一次真实 `联邦学习` 全链路验收：local + A2A Researcher、Verifier、Editor、7 Evidence、6 ClaimChecks、Approve/Apply，249.5 秒完成。
- 当前本机仍缺独立 Backup LLM 和第二 SearchProvider，因此预检应保持 blocked，不能声称 Demo Ready。
