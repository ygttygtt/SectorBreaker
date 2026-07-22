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
- production body extraction with persisted provenance and post-filtered domain policy;
- typed waiting-run resume that feeds persisted user input into State;
- blank search secrets preserve stored keys; source packs no longer masquerade as configured direct connectors;
- historical artifacts cannot satisfy a new run's finish gate; checkpoint writes fail loudly;
- active-only local Hybrid RAG and V3 Obsidian export;
- no enterprise talent or old workflow production code.

Verification baseline: backend 217 passed, frontend 30 passed/build passed, real local semantic smoke passed, version isolation passed. Real V3 web/Agent/ChangeSet/export acceptance passed on project `project-63a8ed6dcd05454ab28cc0443a4e765b`.

Do not claim an architecture change ready from unit tests alone. Run the real user path and inspect the exported Vault.
