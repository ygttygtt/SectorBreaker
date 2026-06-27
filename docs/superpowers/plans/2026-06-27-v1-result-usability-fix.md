# V1 Result Usability Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the runnable V1 path produce readable evidence/results and keep the completed run trace visible for user verification.

**Architecture:** Clean noisy search snippets at the V1 evidence boundary before persistence, then make the result page resilient to long evidence text and show the completed run timeline. This keeps workflow decisions in the backend while making the frontend a faithful observer of backend events.

**Tech Stack:** FastAPI backend, Python/Pydantic schemas, Vite + React + TypeScript frontend, Vitest, pytest.

---

### Task 1: Clean V1 Search Evidence

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] **Step 1: Write failing tests**

Add tests that call the V1 evidence conversion helper with GitHub navigation-like snippets and assert the stored snippet is readable, capped, and does not keep `[Skip to content]` / login navigation noise.

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest tests/unit/test_v1_pipeline.py -q`
Expected: fails before implementation because snippets are currently stored raw.

- [ ] **Step 3: Implement minimal cleaning**

Add a small pure helper in `backend/app/v1_pipeline.py` that removes Markdown links/images, GitHub navigation boilerplate, excessive whitespace, and caps text length. Use it for `raw_excerpt`, `snippet`, `summary`, `claim.text`, LLM evidence brief, and fallback evidence lines.

- [ ] **Step 4: Verify focused test**

Run: `python -m pytest tests/unit/test_v1_pipeline.py -q`
Expected: passes.

### Task 2: Make Result Page Show Run Trace And Prevent Layout Breakage

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add tests that render a completed result with a long Markdown/link-heavy evidence snippet and completed run events. Assert the result page shows a run trace section and the evidence snippet is shortened in the DOM.

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && npm test -- --run`
Expected: fails before implementation because result view does not receive events and renders raw snippets.

- [ ] **Step 3: Implement result trace and snippet display guard**

Pass `effectiveEvents` into `ResultView`, render a compact completed-run timeline, add a snippet formatter that strips markdown noise for display and truncates long text, and add CSS `min-width: 0`, `overflow-wrap: anywhere`, and `overflow-x: hidden` guards for result cards/evidence content.

- [ ] **Step 4: Verify frontend tests and build**

Run: `cd frontend && npm test -- --run`
Expected: 15+ tests pass.

Run: `cd frontend && npm run build`
Expected: build succeeds.

### Task 3: Backend Smoke Audit

**Files:**
- Read: `backend/app/api/app.py`
- Read: `backend/app/graph/workflow.py`
- Read: `backend/app/v1_pipeline.py`

- [ ] **Step 1: Inspect backend flow boundaries**

Check that API handlers call provider interfaces, events persist through repository, and V1 auto-run uses the simplified path without hidden resume calls.

- [ ] **Step 2: Run real acceptance**

Run: `python run_real_search_acceptance.py`
Expected: LLM config, Tavily search, project run, evidence writeback, V1 artifacts, and Obsidian export all succeed.

- [ ] **Step 3: Start local services for user acceptance**

Start backend on `127.0.0.1:8000` and frontend on `127.0.0.1:5173 --strictPort`, then verify `/api/config/search` through the frontend proxy.
