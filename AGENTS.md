# SectorBreaker Agent Collaboration Guide

This repository is designed for multi-agent and multi-developer collaboration. Read this file before changing anything.

## Required Reading Order

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/00-project-brief.md`
4. `docs/01-architecture.md`
5. `docs/02-agent-contracts.md`
6. `docs/10-current-status-and-handoff.md`
7. `docs/11-tooling-handoff.md`
8. `docs/19-agent-kernel-debugging-retrospective.md`
9. `docs/20-version-isolation-and-cutover-rules.md`
10. `docs/21-living-knowledge-base-roadmap.md` for knowledge-base persistence, follow-up Q&A, or Obsidian growth work.
11. The subsystem document for the files you will touch.

If instructions conflict, follow the most specific project document first, then this file, then general tool instructions.

## Non-Negotiable Rules

- Do not implement business features before the relevant contract, schema, and test expectation are documented.
- Do not pass free-form natural language between internal modules when a Pydantic model or JSON schema is available.
- Do not call external services directly from graph nodes or API handlers. Use provider interfaces.
- Do not write final research claims without linked evidence metadata.
- Do not change public schemas, graph state, export format, or API contracts without updating docs and tests in the same change.
- Do not mix frontend state orchestration with research logic. The backend owns research workflow decisions.
- Do not commit generated runtime data, local exports, caches, or API secrets.
- Do not implement a new architecture by patching the old executable spine.
- Do not keep old workflow code reachable from production imports after a cutover. Delete it, or move it to a clearly archived non-production area and prove production code cannot import it.
- Do not rely on runtime guards as the primary fix for version leakage. Guards are smoke alarms; version isolation is the fix.
- For personal `domain_knowledge` auto-run, the production owner is the V2 Agent Kernel. If legacy markers such as `Knowledge Builder`, `Document Writer`, `specialist_react_loop`, `EV-V1-`, `ART-V1-`, or `已使用保底` appear in a current personal run, treat it as an architecture regression.

## Development Shape

Keep files small and ownership obvious. Prefer a focused module with a README, tests, and examples over a large file that requires global context. A lower-capability agent should be able to complete a task by reading one subsystem document and nearby tests.

## Safety Gates

Before marking work complete:

- Run the smallest relevant tests.
- Re-read the plan or issue and verify each requested item.
- Check `git diff --stat` and `git diff` for unrelated changes.
- Update documentation when behavior, contracts, or setup changed.
- For Agent/workflow cutovers, run `python tools/check_version_isolation.py` before claiming readiness.
- Commit with a clear message after verification.

## Handoff And Memory Sync

Before handing work to another agent or teammate, read `docs/10-current-status-and-handoff.md`.

When project status changes, update all relevant memory surfaces in the same commit:

- `docs/10-current-status-and-handoff.md`
- `docs/11-tooling-handoff.md` when cross-tool handoff status changes
- `AGENTS.md` when collaboration rules change
- `CLAUDE.md` when Claude Code onboarding changes
- `.claude/memory/MEMORY.md` and the linked memory file when Claude project memory changes

## Commit And Push

Commit messages should be written in Chinese.

This project uses two remotes. After committing to `main`, push both remotes when network/auth allows:

```bash
git push origin main && git push gitee main
```

If push fails because credentials or network are unavailable, report the exact failure and leave the commit local.
