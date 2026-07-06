# Agent Kernel Version Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the personal `domain_knowledge` product path over to a clean Agent Kernel version so old V1/V2 workflow code cannot affect new runs.

**Architecture:** Production personal runs must use `backend/app/agent_kernel/` only. Old V1/V2 workflow files are moved under an explicit legacy namespace, and API/export code must not import them for personal auto-run. Validation is by one real Mimo + Tavily end-to-end run and inspection of exported Markdown, not by broad fake unit-test loops.

**Tech Stack:** FastAPI, SQLite repository, OpenAI-compatible Mimo LLM, Tavily SearchProvider, React/Vite frontend, Obsidian Markdown export.

---

## File Structure

- Modify: `backend/app/api/app.py`
  - Ensure `auto_run=true` + `project_mode=domain_knowledge` imports and calls only `run_v2_agent_kernel_pipeline`.
  - Ensure export can use current-run artifacts rather than stale project-wide V1 artifacts.
- Modify: `backend/app/agent_kernel/tools/artifacts.py`
  - Write Markdown through plain text LLM completion, not structured JSON parsing.
- Modify: `backend/app/providers/interfaces.py`
  - Add plain text `complete(messages) -> str` to `LLMProvider`.
- Modify: `backend/app/providers/openai_compatible.py`
  - Implement `complete()` for Markdown/plain text output.
- Modify: `backend/app/providers/fakes.py`
  - Keep fake provider compatible for any remaining lightweight checks.
- Move: `backend/app/v1_pipeline.py` -> `backend/app/legacy/legacy_v1_pipeline.py`
- Move: `backend/app/v2_pipeline.py` -> `backend/app/legacy/legacy_fixed_v2_pipeline.py`
- Create: `backend/app/legacy/__init__.py`
  - Mark legacy files as archived and not production imports.
- Modify: legacy tests only if import paths break.
- Modify: `frontend/src/App.tsx`
  - Running personal graph maps only to Agent Kernel nodes.
- Modify: `docs/05-api-contract.md`
  - State personal auto-run is Agent Kernel, not V1/V1.6.
- Modify: `docs/10-current-status-and-handoff.md`, `docs/11-tooling-handoff.md`, `.claude/memory/current-progress-and-handoff.md`, `.claude/memory/tooling-handoff.md`
  - Record version cutover and real-run acceptance rule.

---

### Task 1: Cut Legacy Code Out Of The Production Namespace

**Files:**
- Create: `backend/app/legacy/__init__.py`
- Move: `backend/app/v1_pipeline.py` -> `backend/app/legacy/legacy_v1_pipeline.py`
- Move: `backend/app/v2_pipeline.py` -> `backend/app/legacy/legacy_fixed_v2_pipeline.py`
- Modify: `tests/unit/test_v1_pipeline.py`
- Modify: `tests/unit/test_v2_pipeline.py`

- [x] **Step 1: Create the legacy package**

Use `apply_patch` to add:

```python
"""Archived workflow implementations.

These modules are kept only for historical comparison and legacy tests.
Production personal domain-knowledge runs must use backend.app.agent_kernel.
"""
```

- [x] **Step 2: Move old pipeline files with git**

Run:

```powershell
New-Item -ItemType Directory -Force backend/app/legacy
git mv backend/app/v1_pipeline.py backend/app/legacy/legacy_v1_pipeline.py
git mv backend/app/v2_pipeline.py backend/app/legacy/legacy_fixed_v2_pipeline.py
```

- [x] **Step 3: Fix legacy self-import**

In `backend/app/legacy/legacy_fixed_v2_pipeline.py`, change:

```python
from backend.app.v1_pipeline import (
```

to:

```python
from backend.app.legacy.legacy_v1_pipeline import (
```

- [x] **Step 4: Fix legacy unit-test imports only**

In `tests/unit/test_v1_pipeline.py`, change:

```python
from backend.app.v1_pipeline import (
```

to:

```python
from backend.app.legacy.legacy_v1_pipeline import (
```

In `tests/unit/test_v2_pipeline.py`, change:

```python
from backend.app.v2_pipeline import run_v2_react_knowledge_pipeline
```

to:

```python
from backend.app.legacy.legacy_fixed_v2_pipeline import run_v2_react_knowledge_pipeline
```

- [x] **Step 5: Verify production code no longer imports legacy**

Run:

```powershell
rg -n "backend\.app\.(v1_pipeline|v2_pipeline)|from backend\.app\.legacy|import backend\.app\.legacy" backend/app -g "!backend/app/legacy/**"
```

Expected: no output.

---

### Task 2: Fix Real LLM Markdown Writing

**Files:**
- Modify: `backend/app/providers/interfaces.py`
- Modify: `backend/app/providers/openai_compatible.py`
- Modify: `backend/app/providers/fakes.py`
- Modify: `backend/app/agent_kernel/tools/artifacts.py`
- Modify: `tests/api/test_app.py`
- Modify: `tests/unit/test_agent_kernel_tools.py`

- [x] **Step 1: Add plain text completion interface**

`LLMProvider` must include:

```python
async def complete(self, messages: list[ChatMessage]) -> str:
    """Return plain text without forcing a structured JSON response."""
```

- [x] **Step 2: Implement OpenAI-compatible plain text completion**

`OpenAICompatibleLLMProvider.complete()` must call `/chat/completions` without `response_format`.

- [x] **Step 3: Keep structured completion for Agent decisions**

`OpenAICompatibleLLMProvider.complete_structured()` must still request:

```python
payload["response_format"] = {"type": "json_object"}
```

for Pydantic/dict outputs.

- [x] **Step 4: Use plain completion for Markdown writing**

In `write_layer_document()`, replace structured `str` generation with:

```python
markdown = await context.llm_provider.complete([ChatMessage(role="user", content=attempt_prompt)])
```

- [x] **Step 5: Update fake writer tests**

Any fake LLM intended to simulate writer failure must fail in `complete()`, not `complete_structured(..., str)`.

---

### Task 3: Stop Exporting Stale Project Artifacts

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/storage/sqlite.py` if there is no current-run artifact lookup.

- [x] **Step 1: Inspect export endpoint**

Find:

```powershell
rg -n "exports|list_artifacts|export_project" backend/app/api/app.py backend/app/storage
```

- [x] **Step 2: Ensure completed personal run artifacts are distinguishable**

If current artifacts do not record `run_id`, do not add a large migration in this task. Instead, after starting a new project run from the UI, create a new project id and ensure export for that new project contains only Agent Kernel artifacts.

- [x] **Step 3: Remove stale export folder before real acceptance**

Before the final real run, delete only the target acceptance export folder:

```powershell
Remove-Item -LiteralPath "E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2验收" -Recurse -Force -ErrorAction SilentlyContinue
```

Do not delete broad `exports/`.

---

### Task 4: Frontend Runtime Graph Uses Agent Kernel Nodes

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/WorkflowEditor.tsx` only if visual defaults are still wrong.

- [x] **Step 1: Map legacy event names away from visible production nodes**

Keep only Agent Kernel visible nodes for personal running graph:

```typescript
initialize_state
external_materials
agent_decide
tool_execution
state_update
artifact_writing
artifact_review
human_feedback
export
```

- [x] **Step 2: Set personal initial active node**

For `project.project_mode === "domain_knowledge"`, initial active node should be `initialize_state`, not `scope`.

- [x] **Step 3: Keep talent mode separate**

Do not change `talent_demand` routing or Boss/job-source UI in this cutover.

---

### Task 5: Documentation And Memory Sync

**Files:**
- Modify: `docs/05-api-contract.md`
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

- [x] **Step 1: Update API contract**

Replace personal path wording from V1/V1.6 to V2 Agent Kernel.

- [x] **Step 2: Document legacy isolation**

Record:

```text
backend/app/legacy/ contains archived V1 and fixed V2 workflow code. Production personal auto-run must not import it.
```

- [x] **Step 3: Document acceptance rule**

Record:

```text
Acceptance is one real Mimo + Tavily run and exported Markdown inspection. Passing fake tests alone is not enough.
```

---

### Task 6: Real Acceptance Run

**Files:**
- No code files unless the real run exposes a direct failure.

- [x] **Step 1: Restart backend and frontend**

Use the user’s actual commands:

```powershell
python -m uvicorn backend.app.api.app:app --port 8030 --reload
cd frontend
npm run dev
```

- [x] **Step 2: Use runtime config**

LLM:

```text
base_url = https://fufu.iqach.top/v1
model = mimo-v2.5-pro
```

Tavily remains unchanged in local runtime config.

- [x] **Step 3: Run a new project with a unique title**

Use:

```text
api中转站-v2验收
```

- [x] **Step 4: Inspect events**

Required visible markers:

```text
Agent Kernel 已启动
Thought Summary:
Action:
Observation:
State Update:
```

Forbidden markers:

```text
Knowledge Builder
Document Writer
specialist_react_loop
已使用保底
```

- [x] **Step 5: Inspect exported Markdown**

Open:

```text
E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2验收
```

Required:

```text
schema_version: "v2-agent-kernel"
ART-KERNEL
non-template Markdown with actual paragraphs
```

Forbidden:

```text
schema_version: "v1"
EV-V1-
ART-V1-
```

- [x] **Step 6: Report honestly**

If exported content is thin, say it is thin and continue fixing the Agent prompt/tool loop. Do not report success just because the run completed.

---

## Self-Review

- Spec coverage: version isolation, real LLM writing, current run acceptance, frontend graph, docs/memory are covered.
- Placeholder scan: no TBD/TODO placeholders are present.
- Type consistency: `LLMProvider.complete()` is used only for plain text; `complete_structured()` remains for Agent decisions.
