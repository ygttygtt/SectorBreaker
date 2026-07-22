# Tooling Handoff

This is the shared entry point for Codex, Claude Code, Cursor, Windsurf, Gemini, and future agents.

## Bootstrap

Read, in order:

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/00-project-brief.md`
4. `docs/01-architecture.md`
5. `docs/02-agent-contracts.md`
6. `docs/10-current-status-and-handoff.md`
7. `docs/19-agent-kernel-debugging-retrospective.md`
8. `docs/20-version-isolation-and-cutover-rules.md`
9. `docs/21-living-knowledge-base-roadmap.md`
10. `docs/23-autonomous-knowledge-management-v3.md`
11. `docs/24-local-hybrid-rag.md`
12. subsystem docs and tests for the files being changed.

## Current Reality

- Product: local-first autonomous knowledge-base management, not talent intelligence or a one-shot report writer.
- Production owner: `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`.
- Source Vault: read-only input; managed revisions live in SQLite/export.
- Write boundary: existing-note updates require ChangeSet approval/apply.
- Retrieval: shared local Hybrid RAG with FastEmbed, incremental SQLite vectors, RRF, provenance, and honest degradation.
- Web acquisition: Tavily/Serper/Brave/Exa/Firecrawl SearchProviders, concurrent fair `multi`, targeted source-pack domains, and separate HTTP/Firecrawl/Jina extraction.
- Search execution reports typed per-Provider diagnostics and charges the Agent
  budget for actual Provider fan-out; extraction requests have an independent
  hard budget.
- Production `search_web` now consumes HTTP/Firecrawl/Jina extraction for up to
  three accepted URLs, persists body/provenance, and post-filters domains.
- Project source packs and custom domain policies persist on the project and
  execute as `prefer` with explicit fallback or `require` as a hard allowlist.
- Waiting Agent runs have a real typed `/resume` path; feedback is persisted and
  exposed to the next Master decision.
- Search config preserves blanked stored keys and reports only non-secret key
  presence; domain-pack entries are discovery filters, not direct connectors.
- Search/extraction dispatch rejects private and reserved network targets; local
  HTTP redirects are validated hop by hop. Runtime config uses atomic replace
  with one backup and best-effort owner-only permissions.
- Runtime completion requires a current-run artifact, and checkpoint failures
  are fatal rather than hidden.
- Specialists receive bounded artifact plus local retrieval context; they still recommend external tool calls to the Master rather than owning a nested ReAct loop.
- UI: V3 knowledge-management panel includes semantic-index status and rebuild controls.
- Export: active-only Obsidian vault with full `.sectorbreaker/` control metadata.

## Do Not Reintroduce

- `backend.app.graph.workflow` or fixed L1-L5 execution chains.
- talent-demand/TalentScope/Boss/job-source production modules or routes.
- Specialist direct filesystem writes or ChangeSet apply.
- fake/template artifacts reported as success.
- superseded artifacts in normal retrieval/export.
- network search when the source policy forbids it.

## Standard Verification

```powershell
python -m compileall -q backend/app
python -m pytest -q
python tools/check_version_isolation.py
python tools/smoke_local_hybrid_rag.py

cd frontend
npm test -- --run
npm run build
```

Knowledge-management changes also require a Vault lifecycle acceptance test.

## Current Baseline

- Backend: 244 passed.
- Frontend: 30 passed and production build passed.
- Version isolation passed.
- Temporary real Vault apply/export/rollback/re-export acceptance passed.
- Real V3 web/Agent/ChangeSet/export acceptance passed on project
  `project-63a8ed6dcd05454ab28cc0443a4e765b`; see `docs/26-product-readiness-audit-v3.md`.
