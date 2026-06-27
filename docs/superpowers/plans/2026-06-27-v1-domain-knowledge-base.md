# V1 Domain Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the thin V1 one-shot Markdown generator with a structured domain knowledge base that exports useful Obsidian files.

**Architecture:** Keep `auto_run=true` and the current V1 pipeline runnable. Add structured Pydantic models in `backend/app/v1_pipeline.py`, build a `DomainKnowledgeBase` from evidence plus LLM output, then render the seven V1 artifacts from that database. Do not re-enable competitor/revenue/content-ecosystem work in the main path.

**Tech Stack:** Python, Pydantic, FastAPI existing providers, SQLite repository, Markdown exporter, pytest.

---

### Task 1: Add Domain Knowledge Base Models

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Add failing tests for structured concepts, architectures, tools, and learning path.
- [ ] Implement small Pydantic models in `v1_pipeline.py`.
- [ ] Ensure invalid or partial LLM output merges with fallback evidence-derived content.
- [ ] Verify `python -m pytest tests/unit/test_v1_pipeline.py -q`.

### Task 2: Render Rich V1 Artifacts

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Add failing tests that exported artifacts include rich sections rather than one-line templates.
- [ ] Render `00-领域总览.md`, `01-入门路线.md`, `02-核心概念.md`, `03-主流架构.md`, `04-工具与框架.md`, `05-趋势与问题.md`, and `99-待验证问题.md` from the database.
- [ ] Keep evidence IDs attached to all artifacts.
- [ ] Verify `python -m pytest tests/unit/test_v1_pipeline.py -q`.

### Task 3: Update Status Docs

**Files:**
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

- [ ] Record that V1.1 now builds a structured domain knowledge base.
- [ ] Record that competitor/revenue/content-ecosystem are intentionally out of main-path scope.
- [ ] Verify `git diff --check`.

### Task 4: Real Acceptance

**Files:**
- No source changes expected unless verification reveals a root-cause bug.

- [ ] Run focused unit tests.
- [ ] Run one real local UI or API run for an Agent topic.
- [ ] Inspect exported Markdown for meaningful multi-section content.
- [ ] Commit with a Chinese message and push both remotes when available.
