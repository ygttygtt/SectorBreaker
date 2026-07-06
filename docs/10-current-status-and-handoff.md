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
- V1.1 Chinese topic search relevance now handles compound topics such as `大模型开发就业` without requiring exact full-phrase matches. Large-model career topics also have a topic-specific fallback database covering application development, RAG, Agent work, model API integration, Python/backend skills, and portfolio/job-readiness questions.
- V1.1 output generation now uses the LLM for every exported Markdown artifact. After the structured `DomainKnowledgeBase` is built, `Document Writer` emits `document_writing` progress events and asks the LLM to write each Obsidian document as full Markdown. Short or under-structured generations fall back to the deterministic renderer, but normal output is no longer intended to be search-result passthrough.
- V1.1 source collection now checks evidence sufficiency before building the knowledge system. If fewer than 8 usable evidence items are available, the V1 path runs one supplemental open-web query, deduplicates URLs, and emits a warning when the run still has thin source coverage. Long LLM calls for knowledge structuring and artifact writing now emit heartbeat progress events instead of leaving the UI silent.
- V1.2 rich Obsidian output now adds a bounded `Artifact Reviewer` pass after each primary V1 document. The reviewer is tuned to expand thin output rather than compress it: it checks detail, examples, evidence linkage, learning usefulness, and Obsidian readiness, then allows at most one expansion call.
- V1.2 also generates real Obsidian knowledge cards from the structured `DomainKnowledgeBase`: `concepts/`, `architectures/`, `tools/`, and `questions/`. Main fallback Markdown now uses `[[wikilinks]]` that point to generated card titles, and exported front matter includes Obsidian-friendly `aliases`, `type`, `status`, `evidence_ids`, and `tags`.
- V1.2 demo-readiness execution plan now lives at `docs/superpowers/plans/2026-07-03-v1-2-demo-readiness.md`. It is the guiding plan for the 2026-07-04 recording push: preserve the runnable V1 spine, improve visible progress, add a result quality panel, upgrade the Obsidian README home page, and add demo-safe failure/restore messaging.
- V1.2 demo-readiness UI/export closeout is implemented: `artifact_review` now maps to the visible QA node, the result page shows quality metrics for evidence/main docs/cards/review events/open questions/export files, failed runs keep a recovery block with partial-result access, and V1 exports write a stronger Obsidian Vault README home page.
- V1.3 now adds a runnable `Talent Demand Intelligence Agent` branch while preserving the existing V1.2 domain-knowledge flow. `ResearchProject.project_mode` defaults to `domain_knowledge`; `talent_demand` routes auto-run projects into the new talent pipeline.
- V1.3 talent-demand backend now has real non-shell modules for `TalentDemandKnowledgeBase`, conservative JD/report signal extraction, skill alias normalization, Source Coverage Matrix, talent-specific artifact rendering, and Obsidian export layout. It uses uploaded JD/user materials and external AI reports first, then configured search providers as supplement when materials are thin.
- V1.3 talent-demand frontend now has a mode selector, JD text/file upload path, external report upload path, talent-specific run labels, multi-provider search settings visibility (Tavily/Serper/Brave/Exa), Source Coverage result panel, and a refreshed workbench visual direction. The old `领域建库` mode remains the default landing path.
- V1.4 now adds an enterprise-only Boss/job-source extension without changing the default personal `domain_knowledge` path. `JobSourceProvider` and `BossAgentCliProvider` can ingest structured local Boss-compatible CLI JSON/JSONL job postings into `boss_job` channel evidence. Missing CLI/login/tool failures emit degraded diagnostics and do not block uploaded JD, external report, or search fallback flows.
- V1.4 talent-demand Source Coverage now counts `boss_job_count`, exports that count in the talent vault JSON coverage block, and shows it in the frontend result panel.
- V1.4 upgrades project Q&A into lightweight project RAG. `/api/projects/{project_id}/chat` retrieves from evidence, uploaded documents, document segments, and generated artifacts, then uses the configured LLM for citation-grounded answers; without LLM it returns a deterministic citation summary. The API keeps `citations` and adds `citation_details`.
- V1.4 frontend adds a talent-mode-only Boss collection panel. Boss collection is off by default, saved through `/api/config/job-source`, and never appears as a requirement for personal domain-knowledge runs.
- V1.5 fixes the `高考教育线上培训` feedback failure class in the personal `domain_knowledge` path. Generic Chinese topics now use Chinese research-oriented search terms, Chinese compound-topic filtering no longer requires exact full-phrase matches, and non-Agent fallback output is domain-neutral `待补证草稿` instead of Agent-framework content. Agent and large-model career topics keep their dedicated fallbacks.
- V1.5 makes LLM fallback visible: structured knowledge generation and per-document writing emit degraded run events when the LLM fails or returns unusably short content, so template fallback is no longer silent.
- V1.5 now treats zero usable evidence as a blocking human-in-the-loop gate. After initial and supplemental collection, a V1 run with 0 evidence emits `node_blocked` at `source_collection`, fails the run, and does not create artifacts.
- V1.5 document upload now accepts `.docx` and `.pdf` in addition to Markdown/TXT. DOCX text is extracted through WordprocessingML; PDF uses `pypdf` when available and otherwise returns a clear parse error if text cannot be extracted.
- V1.5 export manifests include an absolute `export_dir`, and the API exposes a guarded local `POST /api/exports/open-folder` endpoint for opening folders inside the configured export root.
- V1.5 frontend separates the two product modes more clearly: personal `SectorBreaker 领域建库` and enterprise `TalentScope 人才需求情报台` now use different copy, themes, input guidance, Word/PDF upload affordances, and branched workflow preview graphs. Runtime pages remain driven by backend workflow definitions and run events.
- Architecture requirement captured: `docs/16-master-agent-research-core.md` now records the required Master Agent direction. The Master Agent must be intelligent, tool-capable, stateful during a run, memory-backed by structured context, and able to decide continue/search-again/ask-user/degrade/block. Uploaded external AI reports must be first-class external sources in its context. Hard-coded evidence counts must not be the primary sufficiency rule.
- V1.6 now implements the first bounded Master Agent research loop for the personal `domain_knowledge` path. The V1 run creates `RunWorkingMemory`, ingests uploaded external reports/user materials/citations before search planning, generates multi-intent `SearchPlan` records, calls the configured `SearchProvider` through structured `SearchIntent`s, records `ToolCallResult` diagnostics, evaluates coverage with `CoverageReport`, and maps the result to `continue` / `search_again` / `degrade` / `block`. Zero evidence blocks before writing; thin evidence is visible as degraded rather than mislabeled sufficient.
- V1.6 workflow visualization is aligned with actual run gates. Personal project/run workflow definitions now expose `master_agent`, `external_report_intake`, `source_collection`, `evidence_ledger`, `coverage_evaluation`, `knowledge_structuring`, `document_writing`, `artifact_review`, and `export`; frontend event mapping points to these real node IDs.
- Next architecture requirement captured: `docs/17-agent-state-memory-architecture.md` defines the state/memory/knowledge direction. The next rebuild must introduce explicit `SectorBreakerState`, dynamic practical cognition schema, curated `ContextPack` selection, external report internalization, specialist ReAct loops, optional safe iceberg/risk investigation, and human-feedback reopening. The implementation plan is `docs/superpowers/plans/2026-07-06-agent-state-memory-react-rebuild.md`.
- Legacy V1/V2 workflow code has been physically removed from executable Python modules. `backend/app/legacy/`, `legacy_v1_pipeline.py`, `legacy_fixed_v2_pipeline.py`, `backend/app/graph/v2_react_graph.py`, and their legacy tests were deleted after another old-process/old-workflow leakage incident. Historical context remains only in docs and retrospectives.
- V2 Agent Kernel is now the production personal `domain_knowledge` auto-run path. `backend/app/agent_kernel/pipeline.py` initializes `SectorBreakerState`, internalizes uploaded reports/materials, lets the LLM policy choose from approved tools, applies `KernelStateDelta`, and persists artifacts only when the kernel completes. The event stream exposes Thought Summary / Action / Observation / State Update / Decision messages. `write_layer_document` retries LLM Markdown generation up to three times and writes Markdown through plain text LLM completion, not JSON structured parsing; if writing still fails or is too thin, the run fails with `artifact_writing_failed` and no fake template artifact is saved.
- Production personal auto-run now has a fail-closed legacy event guard. If any event payload contains archived fixed-workflow markers such as `specialist_react_loop`, `Knowledge Builder`, `Document Writer`, `EV-V1-*`, `ART-V1-*`, or fallback markers, the run is marked failed and the marker is not re-emitted to the user-facing stream.
- Acceptance rule for the Agent Kernel path: fake/unit tests alone are not enough. Before telling the user the version is ready, run one real Mimo + Tavily end-to-end project and inspect the exported Markdown for `schema_version: "v2-agent-kernel"`, non-template content, and absence of `EV-V1-*` / `ART-V1-*`.
- Current real Agent Kernel acceptance: project `api中转站-v2-agent-kernel验收5` completed with real Mimo + Tavily and exported to `E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2-agent-kernel验收5`. The export contains five V2 Markdown artifacts, each roughly 17KB-22KB, with `schema_version: "v2-agent-kernel"` and `EV-KERNEL-*` evidence IDs. Inspection found no `EV-V1-*`, `ART-V1-*`, `Knowledge Builder`, `Document Writer`, `specialist_react_loop`, or `已使用保底` markers in the accepted path.
- V2 Agent Kernel failure handling now has a regression guard for partial writes: if an early `write_layer_document` succeeds but a later write fails, the run is marked failed and no partial artifacts are persisted to the repository.
- V2 Agent Kernel running-page UX now treats the center column as the primary user-facing Agent narration surface. It converts existing Thought Summary / Action / Observation / State Update events into concise live brief cards, keeps the flow graph as an auxiliary monitor, and moves the full raw event stream into a collapsible right-side log with wrapping. The frontend evidence metric now counts V2 `State Update: sources+N` events, so Kernel searches no longer appear as `证据事件 0` merely because they do not emit legacy `evidence_collected` events.
- V2 Agent Kernel state-governance upgrade is implemented from `docs/22-agent-kernel-architecture-review.md`. The Kernel now supports LLM-planned adaptive `KnowledgeSchema` initialization, dynamic string layer ids, layer priority/prerequisites/coverage scores, ordered `tool_calls` execution, `evaluate_coverage`, `reflect_on_progress`, `manage_state_memory`, drill-down `OpenQuestion` tasks, hidden/deleted/superseded source/claim deltas, semantic-ish claim dedupe, context filtering for hidden/superseded memories, and richer decision fields (`current_goal`, `plan_steps`, `progress_check`). This makes the Kernel less append-only and less static L1-L5, but real end-to-end output quality still requires a fresh provider-backed acceptance run before demo claims.
- V2 Agent Kernel demo-readiness follow-up: hard search/write budget guards were removed because they risk turning the Agent back into a workflow. Runtime now emits Master-Agent decision heartbeats while waiting for LLM decisions, passes Artifact Memory into the decision context, writes each artifact with a faster one-shot Markdown call before retrying, and relaxes `open_web` coverage so enough unverified public-web leads can produce a `degraded` but writable first draft. A DeepSeek short real run showed visible heartbeats, query adjustment, `degraded ready_to_write=True`, and real L1/L2 artifact writing, but full automatic completion can still be slow because the Agent keeps researching L3 details. For recording, prefer Mimo for the operator-side acceptance run or present the live Agent process rather than waiting silently for a full deep run.
- V2 running-page UX follow-up: frontend can now restore the active/last run from URL query (`project` + `run`) or localStorage after refresh, hides the broken minimap by default, centers the active graph node more reliably, constrains the workbench/log panels to viewport-height scrolling, filters zero-value `State Update +0` cards out of the main Agent brief, converts nonzero state updates into human-readable summaries, collapses secondary details, and auto-scrolls/highlights new Agent brief cards. This fixes the observed "refresh loses page", "right log stretches page", and "State Reducer +0 looks stuck" experience class.
- Markdown/Obsidian export now copies the repository-root `.obsidian/` folder into every generated project vault. This folder is the default Obsidian configuration template for the user's preferred plugins/settings/workspace and is not treated as research evidence or an Agent artifact.
- Important local debugging note: stale `uvicorn` processes on another port can make the frontend hit old code. The default Vite proxy now targets `127.0.0.1:8030`; before UI acceptance, ensure only one intended `uvicorn backend.app.api.app:app --port 8030` process is running and restart Vite after config changes.
- Use `scripts/start_clean_dev.ps1` for local demos when possible. It clears existing listeners on the backend/frontend ports before starting the dev stack, preventing multiple stale `uvicorn` instances from serving different code on the same port.
- V2 debugging retrospective is now documented at `docs/19-agent-kernel-debugging-retrospective.md`. Future Agent Kernel work must read it before changes. It records the failure chain that caused repeated unusable outputs: old workflow leakage, L1-L5 hard-coded traversal, external reports not clearly entering State, Markdown writing through JSON parsing, fake fallback artifacts, UI graph drift, and over-reliance on fake/unit tests instead of real exported-output acceptance.
- Version isolation governance is now documented at `docs/20-version-isolation-and-cutover-rules.md` and `.claude/memory/version-isolation-governance.md`. Future architecture cutovers must delete or isolate old executable paths before claiming the new path is production. Runtime guards are smoke alarms, not the primary fix. Use `python tools/check_version_isolation.py` as the lightweight production-path scan before Agent/workflow readiness claims.
- Living knowledge-base positioning is documented at `docs/21-living-knowledge-base-roadmap.md`. The demo should position SectorBreaker as a structured, Obsidian-friendly, evidence-linked knowledge base rather than a one-shot Deep Search report. The first real growth loop is implemented: result-page follow-up questions call project RAG, persist a `followups/*.md` artifact, refresh the artifact list, and export writes `.sectorbreaker/` state files. Full visual reopen/resume remains future work.
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
- Vite now proxies `/api` to `http://127.0.0.1:8030` by default, matching the current local FastAPI command used for V1 acceptance.

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
- Current V1.1 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 10 passed. Manual search diagnostic for `大模型开发就业 岗位 技能要求 职业路径 2026` returned 8 Tavily results before filtering, confirming the earlier 0-evidence run was caused by V1 filtering, not search provider outage.
- Current V1.1 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 11 passed; `cd frontend && npm test -- --run App.test.tsx` => 16 passed.
- Current V1.2 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 12 passed. `git diff --check` passed with only expected Windows LF/CRLF warnings.
- Current V1.2 demo verification: `python -m pytest tests/unit/test_v1_pipeline.py tests/unit/test_markdown_exporter.py -q` => 14 passed; `cd frontend && npm test -- --run App.test.tsx` => 16 passed; `cd frontend && npm run build` passed with only the existing Vite chunk-size warning.
- Current V1.3 focused verification: `python -m pytest tests/unit/test_talent_demand_pipeline.py tests/unit/test_talent_demand_models.py tests/unit/test_talent_demand_extraction.py tests/unit/test_talent_demand_skills.py tests/unit/test_talent_demand_source_coverage.py tests/unit/test_talent_demand_export.py tests/api/test_app.py::test_api_talent_demand_run_uses_uploaded_jd_and_creates_talent_artifacts tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_accepts_talent_demand_project_mode -q` => 16 passed, 1 warning. `cd frontend && npm test -- --run App.test.tsx` => 17 passed. `cd frontend && npm run build` passed with the existing Vite chunk-size warning.
- Current V1.4 focused verification: `python -m pytest tests/unit/test_job_source_provider.py tests/unit/test_project_retriever.py tests/unit/test_talent_demand_pipeline.py tests/unit/test_talent_demand_source_coverage.py tests/api/test_app.py::test_api_talent_demand_run_uses_uploaded_jd_and_creates_talent_artifacts tests/api/test_app.py::test_api_chat_uses_project_retrieval tests/api/test_app.py::test_api_talent_demand_run_uses_boss_job_source_when_enabled -q` => 13 passed, 1 warning. `cd frontend && npm test -- --run App.test.tsx` => 17 passed. `cd frontend && npm run build` passed with the existing Vite chunk-size warning.
- Current V1.5 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 15 passed; upload/export API subset => 6 passed, 1 warning; `cd frontend && npm test -- --run App.test.tsx` => 17 passed; `cd frontend && npm run build` passed with the existing Vite chunk-size warning.
- Current V1.6 focused verification: `python -m pytest tests/unit/test_v1_pipeline.py -q` => 16 passed; `python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q` => 1 passed, 1 warning; `cd frontend && npm test -- --run App.test.tsx` => 17 passed; `cd frontend && npm run build` passed with the existing Vite chunk-size warning.
- Current V2 Agent Kernel verification: `python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts tests/api/test_app.py::test_api_agent_kernel_uploaded_report_reaches_writer_context -q` => 7 passed, 1 warning; `cd frontend && npm test -- --run App.test.tsx` => 17 passed. Real LLM smoke probe against local runtime config also passed for both structured JSON and plain-text calls with `mimo-v2.5-pro`.
- Current export/failure regression verification: `python -m pytest tests/api/test_app.py::test_api_agent_kernel_failed_run_does_not_persist_partial_artifacts tests/unit/test_markdown_exporter.py::test_markdown_exporter_copies_default_obsidian_config -q` => 2 passed, 1 warning.
- Current real V2 Agent Kernel acceptance: `api中转站-v2-agent-kernel验收5` produced 5 exported documents (`01-API中转站：本源与需求.md` through `05-API中转站：风险与边界.md`) sized about 17KB-22KB, with V2 schema/evidence and without legacy V1/fallback markers.
- Current cutover closeout verification: Python compile for provider/kernel/API/export/planner files passed; `python -m pytest tests/unit/test_agent_kernel_tools.py tests/unit/test_openai_provider.py tests/unit/test_markdown_exporter.py::test_markdown_exporter_copies_default_obsidian_config -q` => 4 passed; `cd frontend && npm test -- --run App.test.tsx` => 18 passed; production legacy import scan returned no matches; exported acceptance Markdown has five `schema_version: "v2-agent-kernel"` files and no legacy/fallback marker hits.
- Current V2 running-page UX verification: `cd frontend && npm test -- --run App.test.tsx` => 20 passed; `cd frontend && npm run build` passed with only the existing Vite chunk-size warning.
- Current hard legacy-kill verification: `python -m pytest tests/api/test_app.py::test_api_rejects_legacy_events_in_personal_auto_run tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q` => 2 passed, 1 warning; `python -m py_compile backend/app/api/app.py backend/app/agent_kernel/pipeline.py backend/app/agent_kernel/runtime.py backend/app/graph/planner.py` passed; `python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py -q` => 4 passed; `cd frontend && npm test -- --run App.test.tsx` => 19 passed; `cd frontend && npm run build` passed with only the existing Vite chunk-size warning; production legacy import scan returned no matches.
- Current Agent Kernel governance verification: Python compile passed for Agent State/Kernel governance files; `python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_state_models.py tests/unit/test_agent_kernel_runtime.py tests/unit/test_agent_kernel_tools.py tests/unit/test_context_pack_builder.py tests/unit/test_agent_kernel_schema_planner.py -q` => 15 passed; `python tools/check_version_isolation.py` passed; `python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q` => 1 passed, 1 warning. A slower API trio was stopped after hanging locally; do not count it as passed.
- Current version-isolation rule: before future Agent/workflow readiness claims, run `python tools/check_version_isolation.py` and inspect the real export for V2 schema/evidence markers. If the scan fails, do not patch around it; remove the production reference or move history into docs-only archive.
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

- Any Agent Kernel change that could reintroduce fixed-workflow behavior. Read
  `docs/19-agent-kernel-debugging-retrospective.md` first and verify against its
  failure checklist.
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

Before broader architecture work, complete the V1.2 demo-readiness plan at `docs/superpowers/plans/2026-07-03-v1-2-demo-readiness.md`. The plan intentionally avoids multi-search UI, full RAG, content scraping, and competitor/revenue analysis until the demo loop is stable.

Replace remaining raw `dict` LLM outputs in business agents with dedicated Pydantic output schemas.

### Step 1A: Master Agent Research Core

The next major iteration should follow `docs/16-master-agent-research-core.md`.
V1.6 has implemented the first bounded version: structured run memory,
external-report intake into V1 context, Master-Agent-generated tool/search
plans, coverage judgment, bounded search/evaluation loops, and graph/UI
alignment around the actual executing nodes. Next upgrades should add full
`ask_user` human interruption, stronger source verification, and RAG/vector
retrieval inside the Master Agent context.

### Step 1B: State, Memory, And Knowledge Architecture

Follow `docs/17-agent-state-memory-architecture.md` and
`docs/superpowers/plans/2026-07-06-agent-state-memory-react-rebuild.md`.
The next implementation should define durable state models, context-pack
selection, external-report internalization, dynamic L0-L5 knowledge schema,
specialist ReAct loops, safe iceberg/risk investigation, and human-feedback
reopen flow. This is now the main architecture path; avoid adding more isolated
heuristics that do not write into structured state.

V2 status: state/memory models, ContextPackBuilder, report internalizer,
generic bounded ReAct runner, L1-L5 specialist contracts, recursive follow-up
task discovery, safe iceberg/risk extraction, a side-by-side V2 LangGraph
skeleton, and a real V2 personal auto-run pipeline are implemented and tested.
Next work is to persist V2 state, execute specialist loops with richer
LLM/tool policies, deepen source verification/RAG, and add human-feedback
reopening.

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
8. Update `docs/20-version-isolation-and-cutover-rules.md` and `.claude/memory/version-isolation-governance.md` if the version-isolation rule changes.
9. Commit and push both remotes:

   ```bash
   git push origin main && git push gitee main
   ```

If one remote fails, report the exact failure and leave the commit local or pushed to the successful remote.
