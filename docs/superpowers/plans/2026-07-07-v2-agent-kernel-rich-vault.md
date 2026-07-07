# V2 Agent Kernel Rich Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V2 Agent Kernel exports look and behave like a living Obsidian knowledge base, not only five main reports.

**Architecture:** Keep the production owner as `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`. Add Agent-selectable artifact tools for explainer cards and a vault index, then teach the Master Agent policy to use them when State reveals concept gaps or navigation needs. Export remains evidence-linked and fail-closed: no fake fallback artifacts.

**Tech Stack:** FastAPI backend, Pydantic Agent Kernel models, provider-backed LLM text completion, Markdown/Obsidian exporter, React runtime UI.

---

### Task 1: Add Agent-Selectable Rich Vault Artifact Tools

**Files:**
- Modify: `backend/app/agent_kernel/tools/artifacts.py`
- Modify: `backend/app/agent_kernel/runtime.py`
- Test: `tests/unit/test_agent_kernel_tools.py`

- [x] Register `write_explainer_card` so the LLM can create concept/tool/player/risk/process/question cards from discovered blind spots.
- [x] Register `write_vault_index` so the LLM can create a navigation page that links main documents, cards, evidence, and open questions.
- [x] Route both tools through `artifact_writing` events and fail closed on writing failure.
- [x] Add tests proving explainer cards use plain text LLM writing, persist as `v2-agent-kernel-card`, and update State through `artifact_ids`.
- [x] Add tests proving the vault index links main docs and cards.

### Task 2: Teach The Master Agent To Prefer Knowledge-Base Growth

**Files:**
- Modify: `backend/app/agent_kernel/policy.py`
- Modify: `backend/app/agents/prompts/tool_decision.md`

- [x] Remove the early-stop pressure that treated three artifacts as enough.
- [x] Add explicit guidance that main documents are not the whole vault.
- [x] Instruct the Agent to create explainer cards when a term, process, tool, risk, or drill-down question would block a beginner.
- [x] Instruct the Agent to create a vault index before finishing when there are multiple artifacts.

### Task 3: Make V2 Exports Visibly Rich In Obsidian

**Files:**
- Modify: `backend/app/exporters/markdown.py`
- Test: `tests/unit/test_markdown_exporter.py`

- [x] Detect V2 Agent Kernel vaults by `schema_version.startswith("v2-agent-kernel")`.
- [x] Generate a V2-specific `README.md` that separates main docs, explainer cards, evidence/state files, and continuation guidance.
- [x] Add a regression test proving `README.md` links V2 main docs, cards, and the generated index.

### Task 4: Sync Contracts, Memory, And Acceptance

**Files:**
- Modify: `docs/02-agent-contracts.md`
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`

- [x] Document `write_explainer_card` and `write_vault_index` as V2 Agent Kernel tools.
- [x] Record that rich-vault acceptance requires more than five main documents when the Agent discovers useful concept gaps.
- [x] Keep the real acceptance rule: use Mimo or the configured fast provider for validation runs and inspect exported Markdown.

### Task 5: Verify

**Files:**
- No new files expected.

- [x] Run focused Agent Kernel and exporter tests.
- [x] Run `python tools/check_version_isolation.py`.
- [x] Run frontend tests/build only if UI files changed.
- [ ] Run one real fast-provider acceptance project and inspect the export for V2 schema, `EV-KERNEL-*`, main documents, explainer cards, and absence of legacy markers.
