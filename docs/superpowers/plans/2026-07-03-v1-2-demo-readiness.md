# V1.2 Demo Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring SectorBreaker V1.2 to a stable, demonstrable state before the 2026-07-04 afternoon recording: real API flow remains runnable, progress is visible, exports look like an Obsidian knowledge base, and failures do not destroy the demo.

**Architecture:** Preserve the current runnable V1 spine: Tavily search -> structured `DomainKnowledgeBase` -> LLM-written main documents -> bounded artifact review -> Obsidian export. Add only low-risk presentation and resilience layers around this spine: workflow state mapping, result quality summary, export README upgrade, and demo-safe fallback. Do not reintroduce the old broad multi-agent business-analysis path as the main CTA.

**Tech Stack:** Python/FastAPI backend, existing provider interfaces, SQLite repository, React/Vite frontend, Obsidian-compatible Markdown export, focused pytest and frontend component tests.

---

**Execution Status:** Implemented in the V1.2 demo-readiness closeout. Final recording validation is intentionally left for the user to run locally with real Tavily/Mimo credentials.

## Scope Guardrails

- Do not add multi-search-provider UI. V1.2 still exposes Tavily as the primary search provider.
- Do not implement full vector RAG, monitoring jobs, content-ecosystem scraping, or competitor/revenue analysis.
- Do not run long real-provider acceptance loops as the default verification step. The user will do final manual recording validation.
- Do not commit API keys, local exports, caches, or generated runtime data.
- Keep the main auto-run path working after every task.

## Current Baseline To Preserve

- Current local working tree already contains V1.2 rich Obsidian output changes.
- `backend/app/v1_pipeline.py` now includes `ArtifactExpansionReview`, artifact review/expansion events, and deterministic Obsidian card generation.
- `backend/app/exporters/markdown.py` now emits more Obsidian-friendly front matter.
- `tests/unit/test_v1_pipeline.py` has focused checks for main artifacts, card artifacts, wikilinks, and artifact review events.
- Focused verification already used for this baseline: `python -m pytest tests/unit/test_v1_pipeline.py -q`.

### Task 0: Commit Current V1.2 Rich Obsidian Baseline

**Files:**
- Existing changes: `backend/app/v1_pipeline.py`
- Existing changes: `backend/app/exporters/markdown.py`
- Existing changes: `tests/unit/test_v1_pipeline.py`
- Existing changes: `docs/06-export-spec.md`
- Existing changes: `docs/10-current-status-and-handoff.md`
- Existing changes: `docs/11-tooling-handoff.md`
- Existing changes: `.claude/memory/current-progress-and-handoff.md`
- Existing changes: `.claude/memory/tooling-handoff.md`
- Existing new plan: `docs/superpowers/plans/2026-06-29-v1-rich-obsidian-output.md`

- [ ] Run `python -m pytest tests/unit/test_v1_pipeline.py -q`.
- [ ] Run `git diff --check`.
- [ ] Scan staged diff for accidental Tavily or OpenAI-compatible API secrets. Avoid committing real values that start with Tavily dev-key or long `sk-` style prefixes.
- [ ] Commit with Chinese message: `增强V1.2富Obsidian知识库输出`.
- [ ] Push `main` to both remotes with `git push origin main && git push gitee main`.

### Task 1: Make V1.2 Progress Visible In The UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/WorkflowEditor.tsx` if node labels/details need a clearer display.
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] Extend frontend event mapping so these backend gates are visible and human-readable: `source_collection`, `knowledge_structuring`, `document_writing`, `artifact_review`, `obsidian_export`.
- [ ] Show the latest event message near the workflow/status area, especially during long LLM calls.
- [ ] Ensure `artifact_review` maps to a visible node or detail state instead of disappearing into generic logs.
- [ ] Add or update a focused frontend test that feeds a `RunEvent` with `gate: "artifact_review"` and asserts the user can see review progress.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.

### Task 2: Add Result Quality Summary Panel

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] Derive display metrics from existing loaded data, without adding new backend schema: evidence count, main document count, knowledge card count, review event count, unresolved question/card count, export manifest path count.
- [ ] Render a compact quality panel on the result screen with labels such as `证据`, `主文档`, `知识卡片`, `审查补写`, `待验证问题`, `导出文件`.
- [ ] Treat `schema_version === "v1-card"` as knowledge cards and `schema_version === "v1"` as main documents.
- [ ] If no export manifest exists yet, show a clear next action: `点击导出生成 Obsidian Vault`.
- [ ] Add a focused frontend test with mixed artifacts and evidence to assert the quality panel renders correct counts.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.

### Task 3: Upgrade Export README As Obsidian Vault Home

**Files:**
- Modify: `backend/app/exporters/markdown.py`
- Test: `tests/unit/test_v1_pipeline.py` or a new focused exporter unit test if nearby exporter tests already exist.

- [ ] Update `_generate_readme` to create a stronger Vault home page for V1.2 exports.
- [ ] Include reading order: `00-领域总览.md`, `01-入门路线.md`, `02-核心概念.md`, `03-玩家与工具地图.md`, `04-趋势与证据.md`, `05-问题与机会.md`, `99-待验证问题.md`.
- [ ] Include Obsidian entry sections for `[[核心概念]]`, concept cards under `concepts/`, architecture cards under `architectures/`, tool cards under `tools/`, and open-question cards under `questions/`.
- [ ] Include a short `如何继续补库` section that tells users to add new sources to `_sources/evidence-ledger.md` and create/update linked cards.
- [ ] Keep existing `manifest.json` and artifact path behavior compatible.
- [ ] Run `python -m pytest tests/unit/test_v1_pipeline.py -q`.

### Task 4: Add Demo-Safe Failure And Restore Messaging

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] If a run fails after partial progress, keep the current run trace and show a recovery block instead of leaving the user with an empty result.
- [ ] In the recovery block, show these options when data exists: `查看已生成内容`, `重新运行`, `导出已有结果`.
- [ ] If the app restores a latest completed run after refresh, make that state obvious with a small banner such as `已恢复最近一次完成结果`.
- [ ] Add a focused frontend test for failed run UI that asserts the run trace remains visible.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.

### Task 5: Final Lightweight Verification For Demo Build

**Files:**
- No new implementation files unless a prior task requires a fix.

- [ ] Run `python -m pytest tests/unit/test_v1_pipeline.py -q`.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `git diff --check`.
- [ ] Do not run full real Tavily/Mimo acceptance by default; the user will run the final recording scenario manually.
- [ ] Update `docs/10-current-status-and-handoff.md`, `docs/11-tooling-handoff.md`, `.claude/memory/current-progress-and-handoff.md`, and `.claude/memory/tooling-handoff.md` with the final V1.2 demo-readiness result.
- [ ] Commit with Chinese message.
- [ ] Push `main` to both remotes with `git push origin main && git push gitee main`.
