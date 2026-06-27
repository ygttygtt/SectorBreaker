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

- Runnable V1 rearchitecture is in progress: `auto_run=true` now follows a simplified V1 path with backend `RunSnapshot`, latest-run restore, seven stable knowledge artifacts, and `_sources/evidence-ledger.md` export layout. The frontend primary landing action starts this V1 path by default; do not reintroduce the old Supervisor Plan confirmation as the main CTA unless the product direction changes. Real acceptance has passed locally with the configured OpenAI-compatible LLM plus Tavily.
- V1 first local product loop is now verified end to end: Tavily-only onboarding, Mimo/OpenAI-compatible runtime LLM config, Vite proxy to the active FastAPI port, real-time progress display, completed-run trace display, cleaned evidence snippets, and result-page overflow protection. A real UI run for `Agent开发` completed with 5 / 5 evidence items, 7 V1 artifacts, visible run trace, no white screen, no horizontal overflow, and no GitHub navigation/XLS/Instagram noise.
- V1.1 scope is intentionally learning-oriented domain knowledge base construction. The main path now skips competitor/revenue and content-ecosystem work, builds a structured `DomainKnowledgeBase`, and renders the Obsidian artifacts from concepts, architectures, tools, trends, learning path, and open questions.
- Backend: FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger + explainable agent selection traces.
- Frontend: Vite + React + TypeScript explainable research workbench with real workflow graph, vertical layout, and active-node centering.
- Local debugging note: the default Vite proxy targets `http://127.0.0.1:8030`. If the landing page reports LLM/search as unconfigured, check for stale `uvicorn` processes on other ports and restart Vite after changing backend ports.
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
uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8030 --reload
```

Default frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
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
- Tavily, Serper, Brave, and Exa search providers.
- Search configuration status endpoint and frontend warning when search is unavailable.
- `docs/14-search-and-report-ingestion-design.md` is now the implementation entry point for multi-provider search and report ingestion.
- Environment-backed provider factory.
- SQLite project/evidence/artifact persistence and FTS evidence search.
- Uploaded documents now affect real runs automatically: ingested document citations seed workflow evidence, assistant-brief documents auto-enter the low-trust report path, and repository evidence writes are idempotent for repeated ingestion/resume flows.
- Weak-source counterevidence now has a real first-pass execution loop: the workflow creates verification tasks and reuses the configured search provider to collect follow-up corroborating/conflicting evidence.
- Research-frame generation now runs in both auto-run and human-confirm resume paths, preventing Supervisor Plan confirmation from skipping market/player/transaction agents.
- Counterevidence writeback now records corroborating/conflicting evidence IDs on the original weak evidence; challenge results require explicit conflict language before they are treated as conflicting evidence.
- `reliable_only` QA now blocks weak evidence only when it is being used as fact support, while preserving weak leads and conflict evidence for review.
- Content extraction is now a real provider boundary too: verification search can fetch page content, clean it locally, reassess the source, and write richer evidence back into the workflow.
- Content extraction provider choice is now configurable: `http` fallback plus Firecrawl and Jina Reader-style extractors are available through environment-based factory selection.
- `/api/config/search/test` is now the recommended connectivity check after filling `.env`, because it can verify both search and optional extraction without starting a full run.
- The frontend `LLM 设置` panel now exposes a `测试搜索链路` action backed by the same API, so manual curl is optional.
- The frontend runtime search settings intentionally expose Tavily only for V1 onboarding. Other backend search providers should stay hidden from the first-version UI until productized.
- Saving Tavily runtime configuration in the frontend refreshes the landing-page configured state immediately.
- The landing page also surfaces the active search provider and extraction provider, making real API activation visible at a glance.
- A CLI smoke test now exists at `python run_search_smoke_test.py`, and the API/UI smoke test path now auto-extracts the first search result and returns source-assessment hints.
- A second CLI acceptance path now exists at `python run_real_search_acceptance.py`, intended for real-key onboarding proof after smoke tests pass.
- A small setup helper now exists at `python generate_search_env_template.py`, useful when the next agent wants the shortest `.env` path for one provider.
- `docs/15-real-search-provider-onboarding.md` now provides the recommended real-key acceptance order, so future agents can move from setup to proof without rediscovering the sequence.
- Repository-root `.env` is now automatically loaded by the backend app and smoke-test script during local development.
- Landing/review UI now uploads `.md` / `.txt` assistant briefs and user materials through the real documents API instead of relying on textarea-only input.
- LangGraph workflow with Scope, Supervisor Plan, Source Strategy, Source Intake, Claim Extractor, Counterevidence, Evidence Ledger, Market, Player, Transaction, Synthesis, Knowledge Map, QA gate, Export, and RAG Indexer.
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
- Multi-provider search routing and crawler expansion, because search quality directly affects evidence integrity.
- Better counterevidence query planning, extractor failure/domain controls, and stronger uploaded report citation verification beyond first-pass heuristics.
- Full API test runtime profiling: `tests/api/test_app.py` may exceed 3 minutes locally even though focused API workflow tests pass.

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
