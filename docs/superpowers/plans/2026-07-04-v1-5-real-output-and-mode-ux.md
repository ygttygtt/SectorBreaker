# V1.5 Real Output And Mode UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 V1 领域建库的 0 证据与模板污染问题，并把个人版/企业版工作台、流程图、外部报告上传和导出体验推进到可展示状态。

**Architecture:** 后端先保证真实输入链路：Tavily 搜索结果不能被中文复合主题误杀，证据不足时不得混入错误领域模板，LLM 失败必须可见降级。前端再做模式感知体验：`domain_knowledge` 与 `talent_demand` 使用不同视觉语义、输入模块和流程图定义，但运行态仍以后端 run events / workflow definition 为准。

**Tech Stack:** FastAPI, SQLite repository, provider interfaces, V1 pipeline, React + TypeScript, React Flow, Markdown/Obsidian exporter, stdlib DOCX/PDF text extraction fallback.

---

### Task 1: V1 Search And Fallback Correctness

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`
- Docs: `docs/01-architecture.md`, `docs/02-agent-contracts.md`

- [ ] Add Chinese compound-topic token extraction that keeps meaningful 2-6 character tokens and known domain markers such as `高考`, `教育`, `培训`, `在线教育`, `线上培训`, `就业`, `岗位`.
- [ ] Make generic V1 search queries Chinese-domain friendly: include `行业趋势`, `市场规模`, `政策监管`, `主要玩家`, `用户需求`, `研究报告`, `案例`, `2026`; keep AI-specific query only for AI topics.
- [ ] Replace non-AI fallback database with domain-neutral scaffolding derived from the requested topic and evidence titles, not Agent-specific concepts/tools.
- [ ] Add tests proving `高考教育线上培训` accepts snippets mentioning `高考`, `在线教育`, `培训`, and fallback output does not contain Agent-specific default terms.

### Task 2: LLM Output Visibility And Safe Degrade

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Emit degraded events when structured knowledge generation or document writing falls back because the LLM failed or returned unusable short output.
- [ ] Keep deterministic fallback usable but label zero-evidence output as `待补证草稿`.
- [ ] Ensure document-writing prompts still ask for detailed Markdown and evidence ids, while avoiding silent template substitution.

### Task 3: External Report Upload Supports DOCX/PDF

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/documents.py`
- Modify: `docs/05-api-contract.md`
- Test: `tests/api/test_app.py`

- [ ] Extend upload validation to `.docx`, `.pdf`, Word/PDF MIME types.
- [ ] Implement `.docx` text extraction through `zipfile` + WordprocessingML XML.
- [ ] Implement best-effort `.pdf` text extraction with optional `pypdf` when installed and a clear parse error when text cannot be extracted.
- [ ] Update frontend accepted file types for JD/material uploads and external AI report uploads.

### Task 4: Export Folder UX

**Files:**
- Modify: `backend/app/exporters/markdown.py`
- Modify: `backend/app/api/app.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Test: `tests/api/test_app.py`

- [ ] Add `export_dir` to export manifest with the absolute project export folder.
- [ ] Add local-only `POST /api/exports/open-folder` that validates the target is inside the configured export root and opens it through the OS.
- [ ] Show the exported path in the result page and add an `打开文件夹` button.

### Task 5: Personal/Enterprise Mode UX And Workflow Graph

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/WorkflowEditor.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] Rename/position modes as personal `SectorBreaker 领域建库` and enterprise extension `TalentScope 人才需求情报台`.
- [ ] Apply mode-specific theme class and copy: personal emphasizes external AI reports/Obsidian knowledge base; enterprise emphasizes JD/Boss/job evidence/skill matrix.
- [ ] Replace the landing default graph with mode-specific branched definitions:
  - Personal: scope + external report + Tavily search fan-in to evidence ledger, then knowledge builder, reviewer, Obsidian export/RAG.
  - Enterprise: JD upload + Boss/job samples + search supplement fan-in to source coverage, skill matrix, talent synthesis, export/RAG.
- [ ] Keep run page graph driven by real workflow definition and node event statuses.

### Task 6: Focused Verification And Handoff

**Files:**
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

- [ ] Run `python -m pytest tests/unit/test_v1_pipeline.py -q`.
- [ ] Run focused API upload/export tests.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.
- [ ] Run `cd frontend && npm run build` if time permits after UI changes.
- [ ] Check `git diff --stat`, `git diff --check`, and avoid committing runtime secrets/data.
- [ ] Commit with a Chinese message and push both `origin` and `gitee`.
