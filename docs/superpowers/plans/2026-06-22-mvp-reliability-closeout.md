# MVP Reliability Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the MVP research run while strengthening reliable-source enforcement enough for `open_web`, `reliable_first`, and `reliable_only` acceptance.

**Architecture:** Keep the existing LangGraph workflow and provider boundaries. Fix schema normalization so LLM/provider outputs survive gate-to-gate validation, then make reliable-source constraints and verification evidence traceable through existing `EvidenceItem` fields.

**Tech Stack:** Python, FastAPI, LangGraph, Pydantic, SQLite, pytest, Vite/React.

---

## Scope Boundaries

Allowed files:
- `backend/app/schemas/agent_outputs.py`
- `backend/app/schemas/evidence.py`
- `backend/app/graph/workflow.py`
- `backend/app/storage/sqlite.py` only if persistence fields are needed
- focused tests under `tests/unit/` and `tests/graph/`
- handoff docs under `docs/10-current-status-and-handoff.md` and `docs/11-tooling-handoff.md`

Out of scope:
- new search providers
- frontend redesign
- public API route changes unless required by existing schema behavior
- broad prompt rewrites
- vector retrieval or production deployment work

## Task 1: Preserve LLM Provider Research Frame Output

**Files:**
- Modify: `backend/app/schemas/agent_outputs.py`
- Test: `tests/unit/test_schemas.py`
- Existing regression: `tests/graph/test_research_workflow.py::test_research_workflow_uses_search_and_llm_providers`

- [ ] Add a failing unit test proving `ResearchFrameOutput` preserves `sections` and extracts string questions from dict-shaped `key_questions`.
- [ ] Run the unit test and confirm it fails before implementation.
- [ ] Update only the schema normalization logic to accept dict entries with `question`, `title`, `text`, `importance`, or `source` without dropping the whole frame.
- [ ] Run the unit test and graph regression.

## Task 2: Reliable Source Traceability And QA Guardrail

**Files:**
- Modify: `backend/app/graph/workflow.py`
- Modify: `backend/app/schemas/evidence.py` only if existing fields cannot express the relationship
- Modify: `backend/app/storage/sqlite.py` only if schema fields change
- Test: `tests/unit/test_workflow_counterevidence.py`
- Test: `tests/graph/test_research_workflow.py`

- [ ] Add a failing test proving verification evidence links back to the original weak evidence through `corroborating_evidence_ids` or `conflicting_evidence_ids`.
- [ ] Add a failing test proving `reliable_only` blocks weak fact-support evidence but does not reject conflicting counterevidence solely because it came from broad-web challenge search.
- [ ] Implement the smallest workflow change that attaches verification evidence IDs back to the original evidence item and keeps QA focused on fact-support evidence.
- [ ] Run the reliable-source tests.

## Task 3: Verification And Handoff

**Files:**
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`

- [ ] Run `python -m pytest tests/unit/test_schemas.py tests/graph/test_research_workflow.py tests/unit/test_workflow_counterevidence.py -q`.
- [ ] Run `npm run build` in `frontend/`.
- [ ] Start backend and frontend if verification passes.
- [ ] Update handoff docs with the new baseline and remaining MVP risks.
