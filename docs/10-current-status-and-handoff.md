# Current Status And Handoff

## Purpose

This document tells future agents and teammates where the project stands, what to do next, what can be delegated safely, and which parts need architecture-level review.

Read this after `AGENTS.md`, `CLAUDE.md`, `docs/00-project-brief.md`, `docs/01-architecture.md`, and `docs/02-agent-contracts.md`.
For Cursor, Windsurf, Gemini, Codex, Claude Code, or other tools, also read `docs/11-tooling-handoff.md`.

## Current Implemented State

### Collaboration Foundation

- Root `AGENTS.md` exists.
- `CLAUDE.md` is adapted for Claude Code.
- `.claude/memory/` contains project memories.
- Architecture, Agent contracts, state/storage, provider interfaces, API contract, export spec, testing strategy, workflow, and roadmap docs exist.
- 交接与记忆文件已同步到当前的多 Agent 协作状态。

### Backend Foundation

- Pydantic schemas exist for projects, evidence, artifacts, and research state.
- Project creation now includes `source_policy`.
- Supervisor planning schemas exist: `SupervisorPlan`, `AgentTask`, `VerificationPlan`, `QAReport`, `AgentSelectionDecision`, `AgentSelectionSignal`, and workflow definition nodes/edges.
- Provider interfaces exist for LLM, search, retrieval, and fake test providers.
- OpenAI-compatible LLM provider exists and is created from environment variables when configured.
- Provider factory returns `None` by default when no real credentials are configured, so tests and local demos stay deterministic.
- Tavily provider exists and is tested with fake HTTP.
- Serper, Brave Search, Exa, and `MultiSearchProvider` now exist; provider factory can return Tavily-only, Serper-only, Brave-only, Exa-only, or aggregated multi-search depending on configured keys.
- Minimal document ingestion foundation now exists: backend stores uploaded text documents with filename, mime type, word count, char count, and simple citation counting through `/api/projects/{project_id}/documents`.
- Multipart `.md` / `.txt` upload is now supported through `/api/projects/{project_id}/documents/upload`.
- Backend now exposes search provider configuration status, and the frontend explicitly warns when web search is not configured.
- Search/report ingestion architecture design now lives in `docs/14-search-and-report-ingestion-design.md` as the implementation entry point for multi-provider search, uploaded reports, source verification, and counterevidence expansion.
- SQLite migrations exist for projects, evidence, FTS, and artifacts.
- Evidence Ledger fields now store source channel, source policy, claims, source quality, claim strength, bias risk, counterevidence flags, and artifact usage.
- A first reliable-source pack layer now exists and is shared across source verification, policy-constrained search, and counterevidence planning.
- Repository supports project creation, evidence storage, artifact storage, FTS search.
- Repository supports project listing and detail lookup.
- Document citation evidence writes are now idempotent at the repository layer, so repeated ingestion or workflow persistence does not fail on duplicate evidence IDs.

### Workflow And Export

- Runnable V1 rearchitecture has started. A simplified product path now exists for `auto_run=true`: backend-owned `RunSnapshot`, latest-run restore endpoint, V1 knowledge pipeline, seven stable knowledge artifacts, and V1 Obsidian export layout. The frontend primary landing action now starts this V1 knowledge-base construction path directly instead of entering the old Supervisor Plan confirmation path. The automated fake-provider regression path passes, and the real-provider acceptance path has passed locally with the configured OpenAI-compatible LLM plus Tavily.
- V1 usability closeout now covers the first complete local product loop: Tavily-only onboarding, Mimo/OpenAI-compatible LLM runtime config, Vite proxy to the active FastAPI port, real-time event display, completed-run trace display, cleaned evidence snippets, and result-page overflow protection. A real UI run for `Agent开发` completed with 5 evidence items, 7 V1 artifacts, visible run trace, no white screen, no horizontal overflow, and no GitHub navigation/XLS/Instagram noise in the rendered result.
- V1.1 now narrows the product promise to "build a learning-oriented domain knowledge base." The main auto-run path intentionally excludes competitor revenue analysis and content ecosystem scraping. It now builds a structured `DomainKnowledgeBase` first (overview, concepts, architectures, tools, trends, learning path, open questions) and renders the seven Obsidian artifacts from that database instead of relying on one-line fallback Markdown templates.
- Important local debugging note: stale `uvicorn` processes and the old Vite proxy default to `127.0.0.1:8030` can make the frontend appear unconfigured even when the current backend on `127.0.0.1:8000` is correct. Before UI acceptance, ensure only one `uvicorn backend.app.api.app:app --port 8000` process is running and restart Vite after config changes.
- LangGraph workflow now includes Scope, Supervisor Plan, Source Strategy, Source Intake, Claim Extractor, Counterevidence, Evidence Ledger, Market, Player, Transaction, Synthesis, Knowledge Map, QA Critic, Export, and RAG Indexer gates.
- Runs pause at `supervisor_plan` for user confirmation unless `auto_run=true`.
- Assistant briefs are optional manual Markdown/text inputs and are treated as low-trust lead material.
- Project documents now feed the workflow automatically at run start/resume:
  - ingested citation evidence enters the workflow as seed evidence;
  - uploaded `assistant_brief` documents are automatically merged into the low-trust report input path;
  - uploaded non-brief user documents are injected as supplemental user evidence context.
- Counterevidence is no longer only a tag: weak or marketing-like claims now generate verification tasks and reuse the configured search provider to collect corroborating or conflicting follow-up evidence.
- Content extraction now has a real provider boundary and default implementation: verification search results can be fetched, cleaned into page text, reassessed for source quality, and then written back as richer evidence.
- Content extraction provider selection is now environment-driven: local HTTP fallback is available by default, and Firecrawl / Jina Reader-style providers can be swapped in without changing workflow code.
- Search/config verification now has a dedicated test path: `/api/config/search/test` can exercise the current search provider and optional extraction provider before a full project run.
- The frontend config panel can now trigger the same search/extraction connectivity check, so API onboarding no longer requires manual curl requests.
- The frontend runtime search settings intentionally expose Tavily only for V1 onboarding. Serper / Brave / Exa remain backend capabilities but are hidden from the first-version settings UI until product support is ready.
- Saving Tavily runtime configuration now refreshes the landing-page search status immediately, so users no longer need a manual browser refresh to clear the missing-key warning.
- Search and extraction provider selection is now visible on the landing page as well, so enabled real providers are visible before a run starts.
- Search smoke testing now has three paths: API (`/api/config/search/test`), frontend config panel, and CLI (`python run_search_smoke_test.py`). The API/CLI path now auto-extracts the first result and returns source assessment hints.
- A dedicated end-to-end acceptance script now exists at `python run_real_search_acceptance.py`; it checks search config, live search, project run completion, and open-web evidence writeback in one flow.
- A minimal env-template generator now exists at `python generate_search_env_template.py`; it prints provider-specific `.env` snippets for faster real-key onboarding.
- Local `.env` loading is now centralized: the FastAPI app and smoke-test script both read repository-root `.env`, so `.env.example -> .env` works as the expected local setup path.
- Real-provider onboarding now also has a dedicated acceptance checklist in `docs/15-real-search-provider-onboarding.md`, covering UI save, API diagnostics, CLI smoke test, and workflow evidence writeback.
- Frontend report upload is now wired into the real flow: landing/review screens can upload `.md` / `.txt` assistant briefs and user materials into project documents before research continues.
- Search and extraction configuration can now also be updated at runtime through `POST /api/config/search`, so real provider onboarding can happen from the UI without editing `.env`.
- Workflow can use injected search and LLM providers.
- Initial search evidence now goes through local source verification before entering the evidence ledger, so official / disclosure / database sources are no longer flattened into generic web evidence.
- Counterevidence task planning now reuses market-specific reliable-domain packs instead of generic `gov/edu/org` hints only.
- MVP reliability closeout now keeps the research-frame gate in both auto-run and human-confirm resume paths, so business agents are not skipped after Supervisor Plan confirmation.
- Counterevidence evidence now links back to the original weak evidence through corroborating/conflicting evidence IDs; challenge results require an explicit conflict signal before they are treated as conflicting evidence.
- `reliable_only` QA now blocks weak sources only when they are being treated as fact support, while still allowing weak leads and broad-web conflict evidence to remain in the evidence ledger for review.
- Workflow produces evidence-linked research frame, industry map, market overview, player map, content/channel map, and opportunity map.
- Supervisor Plan now includes structured selection traces for explainability.
- QA Critic now emits structured `QAReport` and blocks missing coverage, missing evidence references, weak-source misuse, unverified counterevidence needs, and strong factual artifact claims that are not backed by acceptable evidence.
- Markdown exporter writes an Obsidian-friendly package and `manifest.json`.

### API And Frontend

- FastAPI app factory exists with project create/list/detail, run, evidence, artifact, export, and chat endpoints.
- API exposes `/api/projects/{project_id}/workflow-definition` and `/api/runs/{run_id}/workflow-definition`.
- API exposes `/api/config/sources` for source registry status with connector configuration state.
- SSE emits node-level progress, degraded, blocked, completed, evidence, and claim events.
- Module-level ASGI app exists at `backend.app.api.app:app`.
- React/Vite workbench has been rebuilt around a real workflow graph, source policy selection, optional assistant brief input, Supervisor Plan review, live node status, event stream, elapsed time, QA blocking view, evidence/artifact rendering, chat, export, and vertical graph centering.
- QA blocking views now render structured retry/user-action lists instead of raw JSON blobs.
- Result evidence ledger now exposes quality/status chips, outbound source links, and client-side filters for quality, verification status, and attention-only review.
- Frontend config panel now shows reliable source onboarding with connector status, key requirements, and setup links.
- Landing page search warning is now clickable and opens settings for source onboarding.
- Vite now proxies `/api` to `http://127.0.0.1:8000` by default, matching the standard local FastAPI port.
- Vite proxies `/api` to `http://127.0.0.1:8000`.

## Verification Commands

Run these before claiming progress:

```bash
python -m pytest -q
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm audit --audit-level=high
```

Current known baseline:

- Focused MVP reliability suite passes (`python -m pytest tests/unit/test_schemas.py tests/graph/test_research_workflow.py tests/unit/test_workflow_counterevidence.py -q`: 15 passed).
- Source registry suite passes (`python -m pytest tests/unit/test_source_registry.py tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py tests/unit/test_provider_factory.py -q`: 21 passed).
- Focused API workflow suite passes (`python -m pytest tests/api/test_app.py::test_api_pauses_for_supervisor_plan_confirmation tests/api/test_app.py::test_api_run_uses_injected_search_and_llm_providers tests/api/test_app.py::test_api_run_applies_source_policy_domain_constraints tests/api/test_app.py::test_api_exposes_source_registry_status -q`: 4 passed, 1 Starlette deprecation warning).
- Current full `tests/api/test_app.py` run can exceed 3 minutes in this local environment; split API subsets are the reliable verification path until the long-running test behavior is profiled.
- Frontend tests: 14 passing.
- Frontend build: passing.
- Real acceptance: `python run_real_search_acceptance.py` passed locally, including LLM config, Tavily live search, project run completion, 5 search-channel evidence records, 7 V1 artifacts, and Obsidian export manifest.
- Current V1 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` passed; a real default-policy API run for `Agent开发` completed with 4 search evidence items and 7 artifacts; a real frontend run for `Agent开发` completed with visible run trace, 5 / 5 evidence items, no failed status, no horizontal overflow, and no GitHub navigation/XLS/Instagram noise.
- Current V1.1 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 8 passed; `python -m pytest tests/api/test_app.py::test_api_v1_run_creates_knowledge_system_artifacts tests/unit/test_real_search_acceptance_script.py -q` => 6 passed, 1 Starlette warning.
- npm audit high severity: 0 vulnerabilities.

## What Is Easy

These are suitable for regular teammates or lower-capability coding agents if they read the relevant docs first:

- Add editable React project creation form.
- Extract typed API client from `frontend/src/App.tsx`.
- Add artifact detail viewer and richer evidence filters.
- Improve Markdown export formatting.
- Add more fixture examples.
- Add small API endpoints that match `docs/05-api-contract.md`.
- Add frontend component tests.

## What Needs Strong Architecture Review

Do not hand these off without a clear task contract and review:

- Real `LLMProvider` implementation and structured output parsing.
- Research Planner prompts and output schemas.
- Tavily Search Scout query planning.
- Multi-provider web search capability beyond Tavily, plus provider routing and fallback strategy.
- Uploaded report ingestion, citation extraction, and source-verification pipeline.
- Evidence Curator confidence and verification rules.
- QA Critic gate-blocking logic.
- LangGraph interrupt/resume/checkpoint design.
- Any change to `ResearchState`, Agent output schemas, export schema, or provider interfaces.

Why: these parts control hallucination risk, evidence integrity, workflow stability, and future upgrade safety.

## Recommended Next Steps

### Step 1: Planner And Agent Output Hardening

Replace remaining raw `dict` LLM outputs in business agents with dedicated Pydantic output schemas.

### Step 2: Search Scout And Evidence Curator

Continue implementing `docs/14-search-and-report-ingestion-design.md`: strengthen counterevidence query planning, improve extractor failure controls/domain routing, and add richer verification linking. Multi-provider search base, document-to-workflow ingestion, first-pass reliable-source packs, initial verification search/extraction loop, and evidence-level corroborating/conflicting links are now in place.

### Step 3: QA Critic Gate

Current QA now blocks structural issues, weak-source misuse, and unsupported strong factual artifact claims. Next, improve claim-to-evidence pinpointing and automatic retry / degrade routing.

### Step 4: Human Review

Human review exists for Supervisor Plan confirmation. Next, add richer decisions such as "degrade and continue" for unresolved low-trust claims.

### Step 5: Frontend Productization

Add artifact detail viewer, server-backed evidence filters, source policy editing before run, and workflow node detail drill-down backed by real run state.

### Step 6: Acceptance Examples

Run two end-to-end examples:

- China/local-market industry.
- Global or mixed-scope AI trend industry.

Use outputs to tighten prompts, evidence rules, and export structure.

## How To Read Project Progress

1. Check latest commits:

   ```bash
   git log --oneline -8
   ```

2. Check current working state:

   ```bash
   git status --short --branch
   ```

3. Read this file for current status.
4. Read docs for the subsystem you will touch.
5. Run the verification commands before and after changes.

## How To Sync Project Memory

When meaningful progress happens, update memory in the same commit:

1. Update this file with completed work and next steps.
2. Update `docs/11-tooling-handoff.md` when cross-tool onboarding or baseline changes.
3. Update `.claude/memory/current-progress-and-handoff.md` with the concise memory version.
4. Update `.claude/memory/tooling-handoff.md` when cross-tool onboarding or baseline changes.
5. Update `.claude/memory/MEMORY.md` if a new memory file is added.
6. Update `CLAUDE.md` if Claude Code onboarding changes.
7. Update `AGENTS.md` if cross-agent rules change.
8. Commit and push both remotes:

   ```bash
   git push origin main && git push gitee main
   ```

If one remote fails, report the exact failure and leave the commit local or pushed to the successful remote.
