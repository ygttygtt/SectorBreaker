---
name: tooling-handoff
description: Cross-tool bootstrap for SectorBreaker V3
metadata:
  type: project
---

Read `AGENTS.md`, `CLAUDE.md`, `docs/10-current-status-and-handoff.md`, `docs/20-version-isolation-and-cutover-rules.md`, and `docs/23-autonomous-knowledge-management-v3.md` before changes.

Current production architecture:

- one Agent Kernel knowledge-management path;
- read-only source Vault and managed immutable revisions;
- ChangeSet approval boundary for existing-note updates;
- typed Specialist delegation with role tool allowlists;
- active-only lexical retrieval and V3 Obsidian export;
- no enterprise talent or old workflow production code.

Verification baseline: backend 182 passed, frontend 25 passed/build passed, version isolation passed.

Do not claim an architecture change ready from unit tests alone. Run the real user path and inspect the exported Vault.
