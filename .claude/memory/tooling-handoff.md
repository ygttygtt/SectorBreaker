---
name: tooling-handoff
description: Cross-tool bootstrap for SectorBreaker V3
metadata:
  type: project
---

Read `AGENTS.md`, `CLAUDE.md`, `docs/10-current-status-and-handoff.md`, `docs/20-version-isolation-and-cutover-rules.md`, `docs/23-autonomous-knowledge-management-v3.md`, and `docs/24-local-hybrid-rag.md` before changes.

Current production architecture:

- one Agent Kernel knowledge-management path;
- read-only source Vault and managed immutable revisions;
- ChangeSet approval boundary for existing-note updates;
- typed Specialist delegation with role tool allowlists;
- bounded Specialist artifact/local-retrieval context, with external recommendations routed back through the Master;
- concurrent Tavily/Serper/Brave/Exa/Firecrawl search and honest source-pack execution status;
- persisted project source policy plus actual Provider/extraction budgets and typed diagnostics;
- production body extraction with persisted provenance and post-filtered domain policy;
- public-target/redirect SSRF checks and atomic backed-up runtime configuration;
- typed waiting-run resume that feeds persisted user input into State;
- owner-checked leases plus explicit interrupted recovery with child-run lineage;
- blank search secrets preserve stored keys; source packs no longer masquerade as configured direct connectors;
- historical artifacts cannot satisfy a new run's finish gate; checkpoint writes fail loudly;
- ChangeSet/artifact review evidence ids must exist in the owning project;
  unknown evidence downgrades verified claims;
- follow-up pages are idempotent and persist only resolved project evidence ids;
- active-only local Hybrid RAG and V3 Obsidian export;
- no enterprise talent or old workflow production code.
- UI now reports start-up readiness and truthful provider consequences, exposes
  typed run budget/timeline diagnostics, gives result next actions, remembers
  Vault paths, and lazy-loads heavy control-plane/ReactFlow chunks.

Verification baseline: backend 265 passed, frontend 33 passed/build passed, real local semantic smoke passed, version isolation passed. Real V3 web/Agent/ChangeSet/export acceptance passed on project `project-63a8ed6dcd05454ab28cc0443a4e765b`.

Demo-First real acceptance: `联邦学习` completed in 249.5 seconds with local + A2A research, 7 Evidence records, 6 ClaimChecks, and approve/apply. This is one live acceptance, not the mandatory ten-domain gate; Backup LLM and a second SearchProvider are still missing locally.

Do not claim an architecture change ready from unit tests alone. Run the real user path and inspect the exported Vault.
# Demo-First 入口（2026-08-02）

- 合同：`docs/27-demo-first-agent-contract-network.md`
- 预检：`python tools/demo_preflight.py`
- A2A Worker：`python tools/demo_a2a_researcher.py`
- 环境：Backup LLM、第二搜索通道、Backup Extraction、`SECTORBREAKER_A2A_RESEARCHER_URL` 必须真实配置。
- 现场挑战必须先得到 `DEMO READY`；不得用 Fake Provider、预生成正文或回放替代。
