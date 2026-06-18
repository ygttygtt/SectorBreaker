# Cross-Tool Handoff

## Purpose

This file is the entry point for any development tool or coding Agent that does
not have access to the original chat history. Treat repository files as the
source of truth.

## Required Reading Order

1. `AGENTS.md`
2. `README.md`
3. `docs/10-current-status-and-handoff.md`
4. This file
5. The subsystem document for the task:
   - Backend API: `docs/05-api-contract.md`
   - Graph or Agent logic: `docs/01-architecture.md` and `docs/02-agent-contracts.md`
   - State or database: `docs/03-state-and-storage.md`
   - Providers: `docs/04-provider-interfaces.md`
   - Export: `docs/06-export-spec.md`
   - Tests: `docs/07-testing-strategy.md`
   - Workflow/setup: `docs/08-development-workflow.md`

Claude Code should also read `CLAUDE.md` and `.claude/memory/MEMORY.md`.

## Current Working Baseline

The latest completed implementation milestone is:

- Backend: FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger.
- Frontend: Vite + React + TypeScript explainable research workbench with real workflow graph, vertical layout, and active-node centering.
- Environment: conda environment `sectorbreaker`.

Verified commands at this baseline:

```bash
conda run -n sectorbreaker python -m pytest -q
cd frontend && npm test -- --run
cd frontend && npm run build
cd frontend && npm audit --audit-level=high
```

Expected result after the explainable multi-Agent upgrade:

- Python: 23 tests pass, with one FastAPI/TestClient deprecation warning.
- Frontend: 3 tests pass.
- Build passes.
- npm audit reports 0 high vulnerabilities.

## Local Run

Default backend:

```bash
conda activate sectorbreaker
uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Default frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

If ports are occupied:

```bash
uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8010
cd frontend
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8010"
npm run dev -- --host 127.0.0.1 --port 3010
```

## What Has Been Implemented

- Structured schemas for projects, evidence, artifacts, and graph state.
- Source policy, SupervisorPlan, AgentTask, EvidenceClaim, QAReport, and workflow definition schemas.
- Provider interfaces and fake providers.
- OpenAI-compatible LLM provider.
- Tavily search provider.
- Environment-backed provider factory.
- SQLite project/evidence/artifact persistence and FTS evidence search.
- LangGraph workflow with Scope, Supervisor Plan, Source Strategy, Source Intake, Claim Extractor, Counterevidence, Evidence Ledger, Business Analysis fan-out, QA gate, Export, and RAG Indexer.
- FastAPI project create/list/detail, run, workflow-definition, evidence, artifacts, export, and chat endpoints.
- Markdown/Obsidian export manifest and files.
- React workbench wired to backend API for source policy selection, optional assistant brief, plan review, live graph, event stream, evidence/artifact display, chat, and export.

## Highest-Risk Remaining Work

Architecture review is required before implementing:

- Research Planner dedicated Pydantic output schema and prompts.
- Real reliable-source packs and source-quality rules.
- Real Counterevidence search.
- QA Critic unsupported-claim detection inside artifact prose and retry strategy.
- LangGraph interrupt/resume/checkpoint design.
- Any public schema, graph state, export format, or provider interface change.

## Safe Delegation Candidates

These can be given to lower-context Agents after they read the required docs:

- Editable frontend project form.
- Extract `frontend/src/App.tsx` API calls into a typed API client.
- Artifact detail viewer.
- Evidence filters.
- More export formatting polish.
- More deterministic fixtures and golden export tests.

## Memory Sync Rule

When meaningful progress happens, update these in the same commit:

- `docs/10-current-status-and-handoff.md`
- `docs/11-tooling-handoff.md`
- `.claude/memory/current-progress-and-handoff.md`
- `.claude/memory/tooling-handoff.md`
- `README.md` if user-facing setup or project status changed
- `AGENTS.md` or `CLAUDE.md` if onboarding rules changed

Commit messages must be Chinese. Push both remotes:

```bash
git push origin main && git push gitee main
```
