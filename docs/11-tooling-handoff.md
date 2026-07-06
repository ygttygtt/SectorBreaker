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
5. `docs/19-agent-kernel-debugging-retrospective.md`
6. `docs/20-version-isolation-and-cutover-rules.md`
7. `docs/21-living-knowledge-base-roadmap.md` for knowledge-base persistence, follow-up Q&A, or Obsidian growth work.
8. The subsystem document for the task:
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
- V1.1 search filtering now supports Chinese compound learning/career topics such as `大模型开发就业`; large-model career fallback content is topic-specific instead of Agent-framework-only.
- V1.1 now asks the LLM to write every exported Markdown artifact after building the structured knowledge base. The V1 run emits `document_writing` events so the frontend can show progress while longer documents are being generated.
- V1.1 now performs a simple evidence sufficiency check: below 8 usable evidence items, it runs one supplemental open-web query and emits a warning if coverage remains thin. Knowledge Builder and Document Writer long LLM calls emit heartbeat progress events.
- V1.2 rich Obsidian output adds a bounded `Artifact Reviewer` after each primary document. The review goal is to make thin documents more detailed, not shorter; at most one expansion call is allowed per document.
- V1.2 exports additional Obsidian knowledge cards under `concepts/`, `architectures/`, `tools/`, and `questions/`. Main fallback Markdown uses `[[wikilinks]]` that correspond to these generated card titles, and exported YAML front matter is more Obsidian Properties-friendly.
- V1.2 demo-readiness plan is now `docs/superpowers/plans/2026-07-03-v1-2-demo-readiness.md`. Use it as the active guide before the 2026-07-04 recording: finish visible progress mapping, result quality summary, export README home page, and demo-safe failure/restore messaging without expanding into full RAG or multi-search.
- V1.2 demo-readiness UI/export closeout is now implemented. Frontend maps `artifact_review` into the visible workflow, shows a result quality summary, and keeps a failed-run recovery block. The Markdown exporter generates a V1 Obsidian Vault README home page with main docs, card indexes, evidence entry, and continuation guidance.
- V1.3 `Talent Demand Intelligence Agent` is now runnable as an additive project mode. `project_mode="domain_knowledge"` remains the default V1.2 flow; `project_mode="talent_demand"` runs the new talent-demand branch.
- V1.3 talent-demand mode currently supports uploaded JD/user materials, pasted/uploaded external AI reports, supplemental search-provider evidence, conservative JD signal extraction, skill alias normalization, Source Coverage Matrix, talent-specific Obsidian artifacts/cards, and a frontend Source Coverage panel.
- V1.4 enterprise job-source support is implemented. A local Boss-compatible CLI can be connected through `JobSourceProvider` / `BossAgentCliProvider`; collected postings are stored as `boss_job` evidence and counted as `boss_job_count`. This is off by default and only used by `talent_demand`.
- V1.4 project RAG is implemented. Chat retrieves project evidence, documents, document segments, and artifacts, then returns `citations` plus `citation_details`.
- V1.5 fixes the latest personal-mode 0-evidence/template-contamination class: generic Chinese topics use Chinese research search terms, Chinese compound-topic filtering accepts meaningful partial markers, non-Agent fallback is domain-neutral `待补证草稿`, and LLM fallback emits degraded run events instead of silently substituting templates.
- V1.5 also makes zero usable evidence a blocking gate: after initial and supplemental collection, a V1 run with 0 evidence emits `node_blocked` at `source_collection`, fails the run, and does not create artifacts.
- V1.5 upload/export UX is expanded: external reports and JD/user materials accept Markdown, TXT, DOCX, and PDF; export manifests include `export_dir`; `/api/exports/open-folder` can open local export folders after validating they are inside the configured export root.
- V1.5 frontend makes product modes clearer: `SectorBreaker 领域建库` for personal knowledge-base building and `TalentScope 人才需求情报台` for enterprise talent-demand intelligence now have distinct copy, themes, inputs, and branched workflow preview graphs.
- Master Agent architecture requirement is now captured in `docs/16-master-agent-research-core.md`: the next major iteration must move core research decisions into a stateful, tool-capable Master Agent that can judge coverage, call approved tools, use uploaded external reports as first-class sources, and decide continue/search-again/ask-user/degrade/block. Do not treat fixed evidence counts as the primary sufficiency rule.
- V1.6 implements the first bounded Master Agent loop in the personal `domain_knowledge` path. It records run-local memory, ingests uploaded reports/user materials/citations as evidence before search, creates multi-intent search plans, calls the configured `SearchProvider`, records tool diagnostics, evaluates coverage with `CoverageReport`, and decides continue/search-again/degrade/block. Zero evidence blocks before writing; thin evidence is shown as degraded instead of sufficient.
- V1.6 workflow graphs now match actual personal run events: `master_agent`, `external_report_intake`, `source_collection`, `evidence_ledger`, `coverage_evaluation`, `knowledge_structuring`, `document_writing`, `artifact_review`, and `export`.
- State/memory architecture direction is now documented in `docs/17-agent-state-memory-architecture.md`. The next rebuild plan is `docs/superpowers/plans/2026-07-06-agent-state-memory-react-rebuild.md`: explicit `SectorBreakerState`, dynamic practical cognition schema, context-pack filtering, report internalization, specialist ReAct loops, safe iceberg/risk investigation, and human-feedback reopen.
- V2 Agent Kernel is now the production personal `domain_knowledge` auto-run path. `backend/app/agent_kernel/pipeline.py` initializes state, internalizes uploaded reports/materials, lets the LLM policy choose approved tools, applies observations into state, and persists only completed artifacts. Legacy V1/V2 executable workflow files have been deleted, not merely archived. Writer failure is strict: `write_layer_document` writes Markdown through plain text completion, retries three times, then fails the run with `artifact_writing_failed` instead of exporting fake template Markdown.
- Production personal auto-run has a fail-closed legacy event guard. If archived fixed-workflow markers such as `specialist_react_loop`, `Knowledge Builder`, `Document Writer`, `EV-V1-*`, `ART-V1-*`, or fallback markers appear in an event payload, the run fails and the marker is not re-emitted to the user-facing event stream.
- Agent Kernel readiness must be verified with one real Mimo + Tavily end-to-end run and exported Markdown inspection. Passing fake/unit tests alone is not an acceptance signal for the user-facing path.
- Current real Agent Kernel acceptance used project `api中转站-v2-agent-kernel验收5` and export directory `E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2-agent-kernel验收5`. The accepted export has five V2 Markdown documents around 17KB-22KB each, `schema_version: "v2-agent-kernel"`, and `EV-KERNEL-*` evidence IDs. It must not regress to `Knowledge Builder`, `Document Writer`, `specialist_react_loop`, `已使用保底`, `EV-V1-*`, or `ART-V1-*`.
- V2 Agent Kernel failure handling is strict across the whole run: if one document write succeeds and a later write fails, the failed run must not persist that earlier partial artifact. Do not weaken this into "save whatever succeeded" unless the product explicitly adds a partial-results review mode.
- V2 running-page UX now shows Agent activity in a center live brief panel rather than forcing users to read the narrow raw event stream. Existing Kernel events are rendered as concise cards for Agent judgment, action, tool result, state update, writing, and warning. The raw log is still available, but it is a collapsible right panel with wrapping. Frontend evidence metrics count `State Update: sources+N` from V2 traces, not only legacy `evidence_collected`.
- V2 Agent Kernel governance has been upgraded based on `docs/22-agent-kernel-architecture-review.md`: adaptive LLM-planned knowledge schema, dynamic layer ids, coverage score/status updates, ordered `tool_calls`, reflection and coverage tools, memory hide/delete/supersede deltas, drill-down open questions, and ContextPack filtering for hidden/superseded memories are now implemented. This is an architecture maturity step, not a replacement for real provider acceptance; run one real Mimo/DeepSeek + search acceptance before presenting output quality.
- Markdown/Obsidian export copies the repository-root `.obsidian/` folder into each generated project vault. Treat `.obsidian/` as the default vault configuration template for preferred Obsidian plugins/settings/workspace, not as generated research output.
- V2 debugging retrospective is now `docs/19-agent-kernel-debugging-retrospective.md`. It is required reading because it documents the exact failure chain that caused repeated template output: old workflow leakage, fake Agent naming without real control, Markdown routed through JSON parsing, fallback artifacts hiding failure, frontend graph drift, and fake-test overconfidence.
- Version isolation governance is now `docs/20-version-isolation-and-cutover-rules.md`. It is required reading before changing Agent entrypoints, product-mode routing, workflow definitions, or anything that could make archived workflow code reachable again. New architecture work must isolate or delete old executable paths first; runtime guards are smoke alarms only.
- Living knowledge-base roadmap is now `docs/21-living-knowledge-base-roadmap.md`. It captures the product distinction from one-shot Deep Search reports: structured retention, evidence continuity, Obsidian links, and human-in-the-loop vault growth. The first real growth loop is implemented: follow-up RAG answers are persisted as `followups/*.md` artifacts and exported with `.sectorbreaker/` state. Full visual reopen/resume remains future work.
- The frontend now exposes a mode selector and multi-provider search settings (Tavily recommended, Serper/Brave/Exa visible). It also carries explicit guardrails: do not scrape login-gated job boards by default; use uploads and configured search providers first.
- Backend: FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger + explainable agent selection traces.
- Frontend: Vite + React + TypeScript explainable research workbench with real workflow graph, vertical layout, and active-node centering.
- Local debugging note: the default Vite proxy targets `http://127.0.0.1:8030`. If the landing page reports LLM/search as unconfigured, check for stale `uvicorn` processes on other ports and restart Vite after changing backend ports. Prefer `scripts/start_clean_dev.ps1`, which clears backend/frontend port listeners before starting the dev stack.
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

Latest V1.5 focused verification:

```bash
python -m pytest tests/unit/test_v1_pipeline.py -q
python -m pytest tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_opens_export_folder_inside_export_root tests/api/test_app.py::test_api_rejects_opening_folder_outside_export_root tests/api/test_app.py::test_api_uploads_text_document_file tests/api/test_app.py::test_api_rejects_unsupported_document_file_type tests/api/test_app.py::test_api_uploads_docx_document_file -q
cd frontend && npm test -- --run App.test.tsx
cd frontend && npm run build
```

Expected result: 15 V1 pipeline tests pass, 6 focused API tests pass with the
known TestClient warning, 17 frontend App tests pass, and frontend build passes
with only the existing Vite chunk-size warning.

Latest V1.6 focused verification:

```bash
python -m pytest tests/unit/test_v1_pipeline.py -q
python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q
cd frontend && npm test -- --run App.test.tsx
```

Expected result: 16 V1 pipeline tests pass, workflow-definition API test passes
with the known TestClient warning, 17 frontend App tests pass, and frontend
build passes with the existing Vite chunk-size warning.

Latest V2 legacy verification:

```bash
python -m pytest tests/unit/test_agent_state_models.py tests/unit/test_context_pack_builder.py tests/unit/test_report_internalizer.py tests/unit/test_react_loop.py tests/unit/test_specialists_and_iceberg_agent.py tests/graph/test_v2_react_graph.py tests/unit/test_v2_pipeline.py -q
python -m pytest tests/unit/test_v1_pipeline.py tests/api/test_app.py::test_api_v1_run_creates_knowledge_system_artifacts -q
cd frontend && npm test -- --run App.test.tsx
```

Expected result: 15 legacy V2 tests pass, 17 V1.6/API regression tests pass with the
known TestClient warning, and 17 frontend App tests pass.

Latest V2 Agent Kernel verification:

```bash
python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts tests/api/test_app.py::test_api_agent_kernel_uploaded_report_reaches_writer_context -q
cd frontend && npm test -- --run App.test.tsx
```

Expected result: 7 Agent Kernel/API tests pass with the known TestClient warning, and 17 frontend App tests pass. A minimal real LLM probe also passed against local runtime config for structured JSON and plain-text calls using `mimo-v2.5-pro`.

Latest export/failure regression verification:

```bash
python -m pytest tests/api/test_app.py::test_api_agent_kernel_failed_run_does_not_persist_partial_artifacts tests/unit/test_markdown_exporter.py::test_markdown_exporter_copies_default_obsidian_config -q
```

Expected result: 2 tests pass with the known TestClient warning.

Latest real Agent Kernel acceptance:

```text
Project: api中转站-v2-agent-kernel验收5
Export: E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2-agent-kernel验收5
```

Expected result: five exported V2 Markdown documents, each with
`schema_version: "v2-agent-kernel"`, `EV-KERNEL-*` evidence ids, and no legacy
V1/fallback event markers.

Latest cutover closeout verification:

```bash
python -m py_compile backend/app/providers/openai_compatible.py backend/app/agent_kernel/tools/artifacts.py backend/app/api/app.py backend/app/exporters/markdown.py backend/app/graph/planner.py
python -m pytest tests/unit/test_agent_kernel_tools.py tests/unit/test_openai_provider.py tests/unit/test_markdown_exporter.py::test_markdown_exporter_copies_default_obsidian_config -q
cd frontend && npm test -- --run App.test.tsx
```

Expected result: compile passes, focused Python suite reports 4 passed, frontend
App suite reports 18 passed, production legacy import scan returns no matches,
and the accepted export contains V2 schema markers only.

Latest V2 running-page UX verification:

```bash
cd frontend && npm test -- --run App.test.tsx
cd frontend && npm run build
```

Expected result: App suite reports 20 passed, and frontend build passes with
only the existing Vite chunk-size warning.

Latest version-isolation verification:

```bash
python tools/check_version_isolation.py
```

Expected result: production paths do not reference legacy workflow modules or
forbidden runtime markers outside the explicit fail-closed smoke alarm.

Latest Agent Kernel governance verification:

```bash
python -m py_compile backend/app/agent_state/models.py backend/app/agent_state/context_pack.py backend/app/agent_kernel/models.py backend/app/agent_kernel/reducer.py backend/app/agent_kernel/context.py backend/app/agent_kernel/tools/state.py backend/app/agent_kernel/runtime.py backend/app/agent_kernel/policy.py backend/app/agent_kernel/pipeline.py backend/app/agent_kernel/schema_planner.py
python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_state_models.py tests/unit/test_agent_kernel_runtime.py tests/unit/test_agent_kernel_tools.py tests/unit/test_context_pack_builder.py tests/unit/test_agent_kernel_schema_planner.py -q
python tools/check_version_isolation.py
python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q
```

Expected result: compile passes, Agent Kernel/State suite reports 15 passed,
version isolation passes, and the workflow-definition API test passes with the
known TestClient warning. A slower API trio was interrupted after hanging
locally; do not treat it as passed.

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
- Master Agent Research Core follow-up from `docs/16-master-agent-research-core.md` and `docs/17-agent-state-memory-architecture.md`: personal auto-runs now use V2 state/memory + layered specialist search while preserving the V1 writer. Remaining high-risk work is richer LLM/tool policies inside specialist loops, persistence/migration for V2 state, full `ask_user` interruption, stronger source verification, and vector/hybrid RAG inside the Master Agent context.

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
