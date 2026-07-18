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
11. subsystem docs and tests for the files being changed.

## Current Reality

- Product: local-first autonomous knowledge-base management, not talent intelligence or a one-shot report writer.
- Production owner: `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`.
- Source Vault: read-only input; managed revisions live in SQLite/export.
- Write boundary: existing-note updates require ChangeSet approval/apply.
- Retrieval: shared local lexical retrieval, no embedding model yet.
- UI: V3 knowledge-management panel is implemented.
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

cd frontend
npm test -- --run
npm run build
```

Knowledge-management changes also require a Vault lifecycle acceptance test.

## Current Baseline

- Backend: 182 passed.
- Frontend: 25 passed and production build passed.
- Version isolation passed.
- Temporary real Vault apply/export/rollback/re-export acceptance passed.
