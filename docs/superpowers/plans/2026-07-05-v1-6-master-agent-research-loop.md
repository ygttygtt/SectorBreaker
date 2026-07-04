# V1.6 Master Agent Research Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Turn the V1 personal domain-knowledge path from a fixed search-then-write pipeline into a bounded Master-Agent-controlled research loop.

**Architecture:** V1.6 keeps the existing runnable spine and provider interfaces, but moves source planning and sufficiency judgment into structured Master Agent models. Uploaded external reports become first-class evidence before search planning, search runs by research intent, and a `CoverageReport` decides continue/search again/degrade/block.

**Tech Stack:** FastAPI backend, Python/Pydantic, existing `SearchProvider` and `LLMProvider` interfaces, React/Vite workflow visualization, pytest/Vitest focused checks.

---

### Task 1: Backend Master Agent Loop

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [x] Implement `_build_master_search_plan` to produce multi-intent search plans from the user goal, uploaded materials, evidence, previous coverage gaps, and previous attempts. Use LLM structured output when available; fall back to deterministic domain-aware dimensions.
- [x] Implement `_execute_search_intents` so every intent calls `SearchProvider.search(SearchQuery)`, records raw/accepted/rejected counts, persists accepted evidence, and emits readable per-intent events.
- [x] Implement `_evaluate_coverage_with_master_agent` so coverage is judged by dimensions and evidence quality, not a fixed count. Use LLM structured output when available; fall back to deterministic coverage scoring.
- [x] Implement `_decision_from_coverage` and `_emit_zero_or_low_evidence_block` so zero evidence and blocked coverage stop before writing, while thin-but-usable coverage degrades explicitly.
- [x] Preserve existing reliable-first fallback behavior and the user-materials-only path.

### Task 2: External Report Evidence

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [x] Ensure `assistant_brief`, user uploads, document segments, and extracted citations become V1 evidence before search planning.
- [x] Ensure document summaries and evidence IDs are stored in `RunWorkingMemory.document_sources`.
- [x] Add tests proving uploaded external reports and their citations are persisted and visible through run events.

### Task 3: Frontend Workflow Alignment

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/WorkflowEditor.tsx`
- Test: `frontend/src/App.test.tsx`

- [x] Map V1 run gates to actual V1 graph node IDs: `master_agent`, `external_report_intake`, `source_collection`, `coverage_evaluation`, `knowledge_structuring`, `document_writing`, `artifact_review`, and `export`.
- [x] Update the personal-mode preview graph to show Master Agent fan-out/fan-in and a visible coverage loop instead of a single decorative line.
- [x] Keep talent-demand mappings compatible with existing enterprise flow.

### Task 4: Documentation And Memory

**Files:**
- Modify: `docs/01-architecture.md`
- Modify: `docs/02-agent-contracts.md`
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

- [x] Record that V1.6 implements the first bounded Master Agent research loop.
- [x] Record remaining limitations: search provider quality still depends on configured provider; external reports are first-class low-trust inputs, not automatically verified facts; coverage judgment is bounded to V1 dimensions.
- [x] Update verification baseline with focused commands.

### Task 5: Focused Verification And Commit

**Commands:**
- `python -m pytest tests/unit/test_v1_pipeline.py -q`
- `cd frontend && npm test -- --run App.test.tsx`
- `cd frontend && npm run build`
- `git diff --check`

- [x] Run focused backend tests and fix regressions.
- [x] Run focused frontend tests/build and fix regressions.
- [x] Review `git diff --stat` and exclude generated/local files.
- [ ] Commit with a Chinese message.
- [ ] Push current branch to both `origin` and `gitee` when credentials/network allow.

Verification completed during implementation:

- `python -m pytest tests/unit/test_v1_pipeline.py -q` => 16 passed.
- `python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q` => 1 passed, 1 known TestClient warning.
- `cd frontend && npm test -- --run App.test.tsx` => 17 passed.
- `cd frontend && npm run build` => passed with the existing Vite chunk-size warning.
