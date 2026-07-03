# V1 Rich Obsidian Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V1 exports richer and more Obsidian-native while preserving the currently runnable end-to-end flow.

**Architecture:** Keep the existing V1 pipeline as the stable spine. Add a bounded Artifact Reviewer pass after each main Markdown artifact, then generate linked Obsidian knowledge cards from the structured `DomainKnowledgeBase`. Do not introduce multi-provider search or long real-provider acceptance tests in this iteration.

**Tech Stack:** Python, FastAPI backend models, existing provider interfaces, Pydantic schemas, Markdown/Obsidian export writer, focused pytest checks.

---

### Task 1: Add Bounded Artifact Expansion Review

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Add an `ArtifactExpansionReview` Pydantic model with fields for `needs_expansion`, `detail_score`, `missing_angles`, `expansion_brief`, and `quality_notes`.
- [ ] After each generated main artifact, run one review pass that rewards detail, examples, learning usefulness, evidence linkage, and Obsidian readiness.
- [ ] If the review or local heuristic says the document is thin, run one expansion call only.
- [ ] Emit progress events before review and before expansion.
- [ ] Keep fallback behavior: if review or expansion fails, preserve the previously generated document.

### Task 2: Generate Real Obsidian Knowledge Cards

**Files:**
- Modify: `backend/app/v1_pipeline.py`
- Modify: `backend/app/exporters/markdown.py`
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Generate concept cards under `concepts/`.
- [ ] Generate architecture cards under `architectures/`.
- [ ] Generate tool cards under `tools/`.
- [ ] Generate open-question cards under `questions/`.
- [ ] Ensure main fallback Markdown uses `[[...]]` links that correspond to generated card titles.
- [ ] Keep card count bounded by structured database size and avoid over-fragmenting.

### Task 3: Make Export Metadata More Obsidian-Friendly

**Files:**
- Modify: `backend/app/exporters/markdown.py`

- [ ] Render YAML front matter with quoted evidence IDs and tag values.
- [ ] Add `aliases`, `type`, and `status` style fields where possible without changing public API schemas.
- [ ] Keep existing paths and manifest behavior compatible.

### Task 4: Focused Verification Only

**Files:**
- Test: `tests/unit/test_v1_pipeline.py`

- [ ] Run `python -m pytest tests/unit/test_v1_pipeline.py -q`.
- [ ] Run `git diff --check`.
- [ ] Do not run real Tavily/Mimo full acceptance in this pass; the user will perform final manual workflow validation.

