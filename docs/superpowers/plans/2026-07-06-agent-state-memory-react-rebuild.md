# Agent State, Memory, And ReAct Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade SectorBreaker from a bounded Master Agent source loop into a stateful, memory-backed, LangGraph-native ReAct research system.

**Architecture:** Introduce durable state and memory models first, then add context-pack selection, external-report internalization, specialist ReAct loops, and human-feedback reopening. The implementation must preserve the currently runnable V1.6 export path while gradually moving decision logic into explicit LangGraph state and conditional routing.

**Tech Stack:** Python, Pydantic, LangGraph, FastAPI, SQLite repository, existing provider interfaces, React/Vite workflow UI, Obsidian Markdown export.

---

### Task 1: Define State And Memory Contracts

**Files:**
- Create: `backend/app/agent_state/models.py`
- Modify: `docs/03-state-and-storage.md`
- Modify: `docs/02-agent-contracts.md`
- Test: `tests/unit/test_agent_state_models.py`

- [ ] Add `KnowledgeSchema` with dynamic layers (`L0` optional, `L1` What/Why, `L2` Who, `L3` How, `L4` Money/Incentives, `L5` Risks/Boundaries).
- [ ] Add `KnowledgeLayer` with goal, questions, completion criteria, required evidence types, generated cards, open questions, and coverage status.
- [ ] Add `EntityRecord`, `KnowledgeClaim`, `RelationshipRecord`, `OpenQuestion`, `SourceMemory`, `TaskMemory`, `ContextPack`, and `AgentDecision`.
- [ ] Add `SectorBreakerState` with `meta_context`, `knowledge_schema`, `shared_knowledge`, `evidence_refs`, `working_memory`, `decision_log`, and `human_feedback`.
- [ ] Unit-test serialization, enum values, evidence-id requirements, and safe defaults.

### Task 2: Build ContextPackBuilder

**Files:**
- Create: `backend/app/agent_state/context_pack.py`
- Test: `tests/unit/test_context_pack_builder.py`

- [ ] Implement context selection rules: always include goal, active layer/task, coverage gaps, relevant accepted entities/claims, and top evidence snippets.
- [ ] Exclude raw HTML, duplicate snippets, unrelated layers, noisy logs, and long reports unless explicitly requested.
- [ ] Compress failed tool attempts into short reflections.
- [ ] Enforce token/character budgets and deterministic ordering.
- [ ] Test that important claims are retained while rejected/noisy material is filtered.

### Task 3: Upgrade External Report Internalization

**Files:**
- Modify: `backend/app/documents.py`
- Create: `backend/app/agent_state/report_internalizer.py`
- Modify: `backend/app/v1_pipeline.py` or new V1.7 graph entrypoint
- Test: `tests/unit/test_report_internalizer.py`

- [ ] Convert uploaded DeepSearch reports into segments, citations, claims, entities, open questions, and source leads.
- [ ] Store raw report separately from curated memory.
- [ ] Mark assistant-report claims as low trust until verified.
- [ ] Feed extracted report memory into Master planning and coverage judgment.
- [ ] Test that report claims affect search planning and final context without being treated as verified facts.

### Task 4: Convert Personal V1 Into LangGraph StateGraph

**Files:**
- Create: `backend/app/graph/v1_react_graph.py`
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/graph/planner.py`
- Test: `tests/graph/test_v1_react_graph.py`

- [ ] Define nodes: `initialize_context`, `ingest_external_reports`, `master_plan`, `dispatch_task`, `specialist_react_loop`, `integrate_state`, `coverage_judge`, `write_knowledge_base`, `artifact_review`, `export_obsidian`, `wait_for_human_feedback`.
- [ ] Add conditional edges for search again, dispatch next task, ask user, degrade, block, write, export, and reopen after feedback.
- [ ] Keep existing V1.6 path behind a fallback flag until the graph path is stable.
- [ ] Test 0 evidence block, thin evidence degrade, external report first run, and missing layer retry.

### Task 5: Add Specialist ReAct Loops

**Files:**
- Create: `backend/app/agents/specialists.py`
- Create: `backend/app/agents/react_loop.py`
- Test: `tests/unit/test_specialist_react_loop.py`

- [ ] Implement a generic bounded ReAct runner with `ThoughtSummary`, `ToolCallRequest`, `Observation`, `StateDelta`, and `StopReason`.
- [ ] Add L1 Concept Agent, L2 Player Agent, L3 How Agent, L4 Incentive Agent, and L5 Risk Agent contracts.
- [ ] Each specialist must read a `ContextPack`, call tools through provider interfaces, write only structured `StateDelta`, and summarize local working memory.
- [ ] Completion must be judged by layer criteria, not source count.
- [ ] Test recursive term discovery: when L3 finds an unknown important term, it creates a follow-up task instead of ignoring it.

### Task 6: Add Iceberg / Shadow Investigation With Safety Guardrails

**Files:**
- Create: `backend/app/agents/iceberg_agent.py`
- Modify: `docs/02-agent-contracts.md`
- Test: `tests/unit/test_iceberg_agent.py`

- [ ] Implement optional risk-surface discovery as SOP-guided ReAct, not fixed queries.
- [ ] Let the Agent choose safer seed terms such as risk, scam, grey market, hidden chain, fraud warning, and industry pitfalls.
- [ ] Extract jargon and suspicious service names as risk intelligence.
- [ ] Route accepted findings into L4 incentives and L5 risks.
- [ ] Block or redact operational wrongdoing instructions while preserving high-level risk understanding.

### Task 7: Add Human Feedback Reopen Flow

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/graph/v1_react_graph.py`
- Modify: `frontend/src/App.tsx`
- Test: `tests/api/test_human_feedback_reopen.py`

- [ ] Add a run state for `wait_for_human_feedback`.
- [ ] Add API endpoint to submit feedback against an exported knowledge base.
- [ ] Let Master Agent classify feedback into add card, expand card, create `L0`, dispatch specialist, ask clarification, or reject unsafe request.
- [ ] Update Obsidian export without destroying previous files.
- [ ] Test the "量化投资小白需要股票/经济学前置知识" scenario.

### Task 8: Verification And Migration

**Files:**
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

- [ ] Run focused state/model tests.
- [ ] Run V1.6 regression tests to ensure old runnable path still works.
- [ ] Run graph tests for V1.7 ReAct routing.
- [ ] Run frontend workflow tests after UI changes.
- [ ] Update memory and handoff docs with the new stable baseline.

## Acceptance Criteria

- A run can explain what it kept in context, what it filtered, and why.
- Uploaded DeepSearch reports affect schema, search planning, coverage, and final writing.
- Master Agent and specialists can create follow-up tasks from observations.
- Coverage is judged by layer goals and missing questions, not raw evidence count.
- Long raw sources are stored and retrieved as relevant snippets, not blindly pasted into prompts.
- Human feedback can add prerequisite knowledge or expand a missing area after export.
- The UI exposes readable Thought/Action/Observation summaries without leaking raw noisy logs.
