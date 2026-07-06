# V2 Agent Kernel Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake fixed V2 workflow with a real ReAct Agent Kernel where LLM reads State, chooses Tools, observes results, updates memory, and decides whether to continue, search, write, ask the user, block, or finish.

**Architecture:** LangGraph may be used as the loop/checkpoint/human-in-loop shell, but the brain is the LLM policy. L1-L5 becomes a cognitive schema inside State, not a hard-coded execution chain. The production personal `domain_knowledge` path must call the Agent Kernel, not the current fixed `v2_pipeline.py` traversal.

**Tech Stack:** Python, FastAPI, Pydantic, LangGraph, SQLite repository, existing provider interfaces, Tavily `SearchProvider`, OpenAI-compatible `LLMProvider`, React/Vite SSE frontend, Obsidian Markdown exporter.

---

## Scope

This is a V2 architecture rebuild. Do not optimize frontend visuals in this plan unless required to show the new Agent loop events. Do not add new external vendors. Do not scrape login-gated platforms. Do not keep patching the current workflow as if it were the final Agent.

The first working version must support:

- personal `domain_knowledge` mode;
- uploaded external AI reports and user materials as first-class inputs;
- Tavily search through the existing `SearchProvider`;
- project retrieval over existing evidence/documents/artifacts where available;
- LLM tool-decision loop;
- structured state updates;
- L1-L5 knowledge schema as guidance;
- Obsidian Markdown writing as an Agent tool;
- human-in-loop action shape, with API/UI pause if feasible in this pass;
- visible `Thought Summary / Action / Observation / State Update / Decision` events.

## Critical Existing Problem To Avoid

The current V2 path has implementation artifacts that look like Agent architecture but still behave like a workflow:

- `backend/app/v2_pipeline.py` traverses layers in code.
- Search queries are partly hard-coded or fallback-generated.
- Sufficiency can still be reduced to code heuristics.
- V2 state exists, but the production path does not let LLM control the loop.
- V1 writer is reused or conceptually preserved in too many places.
- LLM failures fall back to templates, creating false success.

Implementation must replace this behavior, not decorate it.

## File Structure

Create:

- `backend/app/agent_kernel/__init__.py`: public exports for the Agent Kernel.
- `backend/app/agent_kernel/models.py`: action, tool, observation, state-delta, loop-result, budget, and event models.
- `backend/app/agent_kernel/tool_registry.py`: typed registry and dispatcher for approved tools.
- `backend/app/agent_kernel/context.py`: context-pack builder for Agent decisions.
- `backend/app/agent_kernel/policy.py`: LLM decision policy that returns structured `AgentDecision`.
- `backend/app/agent_kernel/reducer.py`: validates and applies `StateDelta` to `SectorBreakerState`.
- `backend/app/agent_kernel/runtime.py`: bounded ReAct loop.
- `backend/app/agent_kernel/tools/search.py`: `search_web` tool.
- `backend/app/agent_kernel/tools/documents.py`: `read_uploaded_report`, `retrieve_project_memory`, `inspect_evidence`.
- `backend/app/agent_kernel/tools/state.py`: `internalize_observation`, `update_task_state`.
- `backend/app/agent_kernel/tools/artifacts.py`: `write_layer_document`, `review_artifact`, `finish_run`.
- `backend/app/agent_kernel/tools/human.py`: `ask_user` action payload and pause result.
- `backend/app/agents/prompts/master_agent_system.md`: Master Agent system prompt.
- `backend/app/agents/prompts/state_reader.md`: State reading rules.
- `backend/app/agents/prompts/tool_decision.md`: action selection rules.
- `backend/app/agents/prompts/search_strategy.md`: search strategy rules.
- `backend/app/agents/prompts/state_internalizer.md`: observation-to-state rules.
- `backend/app/agents/prompts/coverage_judge.md`: sufficiency judgment rules.
- `backend/app/agents/prompts/artifact_writer.md`: Obsidian writing rules.
- `backend/app/agents/prompts/artifact_reviewer.md`: artifact review rules.
- `backend/app/agents/prompts/human_feedback_router.md`: feedback routing rules.
- `backend/app/graph/v2_agent_kernel_graph.py`: optional thin LangGraph shell around the runtime loop.
- `tests/unit/test_agent_kernel_models.py`: model validation.
- `tests/unit/test_agent_kernel_runtime.py`: scripted fake LLM loop.
- `tests/unit/test_agent_kernel_tools.py`: fake repository/search/LLM tools.
- `tests/api/test_v2_agent_kernel_api.py`: minimal personal mode API routing test.

Modify:

- `backend/app/api/app.py`: route personal `domain_knowledge` auto-run to Agent Kernel.
- `backend/app/v2_pipeline.py`: either shrink into a compatibility wrapper that calls Agent Kernel or mark as deprecated and stop using it.
- `backend/app/agent_state/models.py`: extend only if needed for missing state fields; do not duplicate state models.
- `backend/app/agent_state/context_pack.py`: reuse or wrap for kernel decisions.
- `backend/app/providers/openai_compatible.py`: keep robust non-JSON HTTP-body diagnostics and fenced-JSON parsing.
- `backend/app/graph/planner.py`: expose Agent Kernel loop nodes instead of fake long L1-L5 chain for active runs.
- `frontend/src/App.tsx`: map new event gates to graph nodes and render Agent trace events.
- `frontend/src/components/WorkflowEditor.tsx`: update personal-mode graph preview to Agent-loop shape.
- `docs/01-architecture.md`: point V2 direction to Agent Kernel.
- `docs/02-agent-contracts.md`: add Agent Kernel action/tool contract.
- `docs/03-state-and-storage.md`: document run-local state and state snapshots.
- `docs/05-api-contract.md`: document human-in-loop and event stream changes if API shape changes.
- `docs/06-export-spec.md`: document V2 L1-L5 artifact structure.
- `docs/10-current-status-and-handoff.md`: current status and warnings.
- `.claude/memory/current-progress-and-handoff.md`: concise memory sync.

## Task 0: Freeze The New Architecture Direction

**Files:**

- Already created: `docs/18-agent-kernel-design-philosophy.md`
- Modify: `docs/01-architecture.md`
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`

- [ ] **Step 1: Add architecture reference**

In `docs/01-architecture.md`, add a short section near the Master Agent principle:

```markdown
## V2 Agent Kernel Principle

The authoritative V2 direction is `docs/18-agent-kernel-design-philosophy.md`.
SectorBreaker must not implement V2 as a fixed L1-L5 workflow. LangGraph may
host state, loop routing, checkpointing, and human-in-the-loop, but LLM policy
must decide the next action from State and Tools. L1-L5 is the cognitive schema
inside State, not a hard-coded execution chain.
```

- [ ] **Step 2: Add status warning**

In `docs/10-current-status-and-handoff.md`, add:

```markdown
- V2 architecture correction: user feedback on the `API中转站` run showed the
  current V2 path is still too workflow-like. It searches too little, writes via
  fallback templates when long LLM calls fail, and uses L1-L5 mainly as a
  traversal scaffold instead of an Agent-controlled cognition schema. The next
  implementation must follow `docs/18-agent-kernel-design-philosophy.md` and
  `docs/superpowers/plans/2026-07-06-v2-agent-kernel-rebuild.md`.
```

- [ ] **Step 3: Do not commit previous fake-workflow patches as final V2**

Current uncommitted files from the interrupted attempt may include:

```text
backend/app/v2_pipeline.py
backend/app/agents/v2_master_agent.py
backend/app/v2_writer.py
backend/app/providers/openai_compatible.py
```

Keep only provider diagnostics if useful. Do not keep `v2_master_agent.py` or `v2_writer.py` as the final architecture unless they are refactored into tools/policy modules under `backend/app/agent_kernel/`.

## Task 1: Define Agent Kernel Models

**Files:**

- Create: `backend/app/agent_kernel/__init__.py`
- Create: `backend/app/agent_kernel/models.py`
- Test: `tests/unit/test_agent_kernel_models.py`

- [ ] **Step 1: Write focused model tests**

Create tests that enforce the action grammar:

```python
from backend.app.agent_kernel.models import AgentActionType, AgentDecision, ToolCall


def test_agent_decision_requires_tool_call_for_call_tool():
    decision = AgentDecision(
        thought_summary="需要先搜索 API 中转站的需求来源。",
        action_type=AgentActionType.CALL_TOOL,
        tool_call=ToolCall(
            tool_name="search_web",
            args={"query": "API中转站 是什么 需求 痛点"},
            reason="L1 缺少本源与需求信息。",
        ),
        expected_observation="获得定义、需求和使用场景线索。",
    )

    assert decision.tool_call.tool_name == "search_web"
```

- [ ] **Step 2: Implement models**

Create models with these required fields:

```python
class AgentActionType(StrEnum):
    CALL_TOOL = "call_tool"
    UPDATE_STATE = "update_state"
    WRITE_ARTIFACT = "write_artifact"
    REVIEW_ARTIFACT = "review_artifact"
    ASK_USER = "ask_user"
    FINISH = "finish"
    BLOCK = "block"


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str


class AgentDecision(BaseModel):
    thought_summary: str
    action_type: AgentActionType
    tool_call: ToolCall | None = None
    state_delta: KernelStateDelta | None = None
    expected_observation: str = ""
    stop_reason: str = ""
```

Also include:

```python
KernelObservation
KernelStateDelta
KernelLoopConfig
KernelRunResult
KernelTraceEvent
ToolSpec
```

- [ ] **Step 3: Run model tests**

Run:

```powershell
python -m pytest tests/unit/test_agent_kernel_models.py -q
```

Expected: tests pass.

## Task 2: Build The Prompt System

**Files:**

- Create: all files under `backend/app/agents/prompts/`
- Modify: `backend/app/agent_kernel/policy.py` later reads these files.
- Test: `tests/unit/test_agent_kernel_policy.py`

- [ ] **Step 1: Write `master_agent_system.md`**

It must say:

```markdown
You are SectorBreaker V2 Master Agent.

Your job is not to follow a fixed workflow. Your job is to read State, use
approved Tools, update memory, and build an Obsidian-ready domain knowledge
system.

L1-L5 is a cognitive schema, not a hard-coded route.
You must decide the next action based on current State.
```

Include hard rules:

```markdown
- Use uploaded reports before blind web search.
- Generate search queries from missing dimensions, not token splitting.
- Do not decide sufficiency by source count alone.
- If no useful evidence exists after reasonable tool attempts, ask user or block.
- Write only when State contains enough support for a useful document.
- Never hide fallback or LLM failure.
- For grey/unsafe domains, explain risk boundaries and do not provide operational wrongdoing steps.
```

- [ ] **Step 2: Write `tool_decision.md`**

It must require JSON output:

```json
{
  "thought_summary": "Brief user-visible reasoning summary.",
  "action_type": "call_tool",
  "tool_call": {
    "tool_name": "search_web",
    "args": {"query": "...", "layer_hint": "L3_how", "search_goal": "..."},
    "reason": "Why this tool is needed now."
  },
  "expected_observation": "What useful result should come back."
}
```

- [ ] **Step 3: Write `search_strategy.md`**

It must include the user-emphasized behavior:

```markdown
Do not mechanically split the user's domain phrase.
First identify the missing knowledge dimension:
- definition / what-why
- users / providers / players
- implementation / tools / hidden terms
- money / incentives / upstream-downstream
- risks / policy / stability / scams
Then generate a query that targets that missing dimension.
If the first search reveals a hidden term, decide whether to drill down.
```

- [ ] **Step 4: Write writer and reviewer prompts**

`artifact_writer.md` must require detailed output:

```markdown
The output must be a useful knowledge-base document, not a template.
Prefer concrete mechanisms, examples, relationships, evidence ids, open questions,
and Obsidian wikilinks. If evidence is weak, mark it as weak and explain what
would verify it. Do not shrink content during review.
```

`artifact_reviewer.md` must check:

```markdown
- Is it detailed?
- Does it answer the layer's guiding questions?
- Does it cite evidence ids?
- Does it contain empty boilerplate?
- Should the Agent search again before accepting this artifact?
```

- [ ] **Step 5: Add prompt loading helper**

In `backend/app/agent_kernel/policy.py`, implement:

```python
def load_prompt(name: str) -> str:
    path = Path(__file__).parents[1] / "agents" / "prompts" / name
    return path.read_text(encoding="utf-8")
```

## Task 3: Implement The LLM Decision Policy

**Files:**

- Create: `backend/app/agent_kernel/policy.py`
- Test: `tests/unit/test_agent_kernel_policy.py`

- [ ] **Step 1: Write scripted fake LLM test**

Use fake provider that returns an `AgentDecision`:

```python
class FakeLLM:
    async def complete_structured(self, messages, response_schema):
        return response_schema(
            thought_summary="上传材料不足以解释上游链路，需要搜索。",
            action_type="call_tool",
            tool_call={
                "tool_name": "search_web",
                "args": {"query": "API中转站 上游 供应链 定价", "layer_hint": "L4_money_incentives"},
                "reason": "L4 缺少商业链路和成本结构。"
            },
            expected_observation="找到定价、上游、供应链相关资料。"
        )
```

Assert the policy passes available tools and state summary into messages.

- [ ] **Step 2: Implement `LLMAgentPolicy.decide()`**

Inputs:

```python
state: SectorBreakerState
available_tools: list[ToolSpec]
trace_tail: list[KernelTraceEvent]
loop_config: KernelLoopConfig
```

Output:

```python
AgentDecision
```

The prompt must include:

- system prompt;
- state reader rules;
- tool decision rules;
- search strategy rules;
- current compact State;
- available tool specs;
- recent trace events;
- stop/budget constraints.

- [ ] **Step 3: Add validation and retry**

If the LLM returns invalid action:

```python
return AgentDecision(
    thought_summary="上轮决策格式无效，需要先修正为可执行工具调用。",
    action_type=AgentActionType.CALL_TOOL,
    tool_call=ToolCall(
        tool_name="update_task_state",
        args={"note": "LLM decision invalid; request self-correction next turn."},
        reason="保持 loop 可观察，不静默失败。",
    ),
    expected_observation="记录格式错误并进入下一轮。"
)
```

Do not silently fall back to fixed workflow.

## Task 4: Implement Tool Registry And Real Tools

**Files:**

- Create: `backend/app/agent_kernel/tool_registry.py`
- Create: `backend/app/agent_kernel/tools/search.py`
- Create: `backend/app/agent_kernel/tools/documents.py`
- Create: `backend/app/agent_kernel/tools/state.py`
- Create: `backend/app/agent_kernel/tools/artifacts.py`
- Create: `backend/app/agent_kernel/tools/human.py`
- Test: `tests/unit/test_agent_kernel_tools.py`

- [ ] **Step 1: Implement `ToolRegistry`**

Required behavior:

```python
registry.register(ToolSpec(name="search_web", description="...", args_schema={...}), handler)
observation = await registry.dispatch(tool_call, runtime_context)
```

Unknown tools return a failed `KernelObservation`; they do not crash the run.

- [ ] **Step 2: Implement `search_web`**

Use existing `SearchProvider.search(SearchQuery)`.

Tool args:

```json
{
  "query": "string",
  "layer_hint": "L1_what_why | L2_who | L3_how | L4_money_incentives | L5_risks_boundaries",
  "search_goal": "string",
  "max_results": 8
}
```

Observation must include:

- raw result count;
- accepted evidence ids;
- rejected count;
- accepted titles;
- source summaries;
- query;
- reason.

Persist accepted search results through repository/evidence service. Reuse existing persistence helpers only if they do not force V1 semantics.

- [ ] **Step 3: Implement uploaded material tools**

`read_uploaded_report`:

```json
{"document_id": "optional", "query": "optional", "max_segments": 8}
```

If no `document_id`, return relevant uploaded documents and summaries. It must surface external AI reports before blind search.

`retrieve_project_memory`:

```json
{"query": "string", "limit": 8}
```

Search evidence, document segments, and artifacts using existing repository/RAG helpers.

`inspect_evidence`:

```json
{"evidence_id": "EV-..."}
```

Return evidence title, URL, snippet, summary, source quality, verification status, claims.

- [ ] **Step 4: Implement state tools**

`internalize_observation` must produce `KernelStateDelta` with:

- source memories;
- claims;
- entities;
- relationships;
- open questions;
- task memory notes;
- rejected noise summary.

It can call LLM with `state_internalizer.md`, but the reducer must validate the result before applying it.

`update_task_state` records local task progress and reflections without polluting shared knowledge.

- [ ] **Step 5: Implement writing tools**

`write_layer_document` args:

```json
{
  "layer_id": "L3_how",
  "title": "L3 原理与实操",
  "writing_goal": "解释 API 中转站的实现机制、工具、流程和隐藏术语",
  "required_questions": ["怎么实现？", "有哪些框架？", "哪些术语需要下钻？"]
}
```

The tool calls LLM with `artifact_writer.md` and current `ContextPack`, then creates an `Artifact` with `schema_version="v2-agent-kernel"`. If LLM fails, return failed observation. Do not silently persist a fake success artifact.

`review_artifact` args:

```json
{"artifact_id": "ART-...", "review_goal": "检查是否详实、证据足、是否需要补搜。"}
```

The reviewer can return an observation recommending:

- accept;
- revise;
- search more;
- ask user.

- [ ] **Step 6: Implement human tool**

`ask_user` returns an observation with:

```json
{
  "requires_human": true,
  "question": "...",
  "reason": "...",
  "state_snapshot_id": "..."
}
```

Runtime and API can initially mark the run waiting; if full resume is too large, implement the action shape and visible event first.

## Task 5: Implement State Reducer

**Files:**

- Create: `backend/app/agent_kernel/reducer.py`
- Modify: `backend/app/agent_state/models.py` only if required.
- Test: `tests/unit/test_agent_kernel_reducer.py`

- [ ] **Step 1: Write reducer tests**

Test that:

- accepted claims enter `state.shared_knowledge.claims`;
- rejected noise does not enter shared knowledge;
- open questions are deduplicated;
- evidence ids are stored as refs;
- task memory records failed attempts separately.

- [ ] **Step 2: Implement `apply_state_delta()`**

Signature:

```python
def apply_state_delta(
    state: SectorBreakerState,
    delta: KernelStateDelta,
    *,
    decision: AgentDecision,
    observation: KernelObservation,
) -> SectorBreakerState:
```

Rules:

- Never add verified claims without evidence ids.
- Preserve low-trust external report claims but mark them as low/partial.
- Store rejected diagnostics outside shared knowledge.
- Deduplicate entities by normalized name and type.
- Deduplicate open questions by normalized text and layer.
- Append decision log with action, reason, and coverage gaps.

## Task 6: Implement The Agent Runtime Loop

**Files:**

- Create: `backend/app/agent_kernel/runtime.py`
- Test: `tests/unit/test_agent_kernel_runtime.py`

- [ ] **Step 1: Write scripted runtime test**

Fake policy sequence:

1. `search_web`
2. `internalize_observation`
3. `write_layer_document`
4. `review_artifact`
5. `finish`

Assert:

- tools were called in policy-decided order;
- no L1-L5 fixed traversal occurred;
- trace contains thought/action/observation/state update/decision;
- artifacts are created only after write action.

- [ ] **Step 2: Implement loop**

Core loop:

```python
for iteration in range(config.max_iterations):
    context = context_builder.build_for_kernel(state, trace_tail=trace[-8:])
    decision = await policy.decide(state=state, available_tools=registry.specs(), trace_tail=trace[-8:], loop_config=config)
    emit_thought_event(decision)

    if decision.action_type == AgentActionType.CALL_TOOL:
        observation = await registry.dispatch(decision.tool_call, runtime_context)
        emit_observation_event(observation)
        delta = observation.state_delta or KernelStateDelta()
        state = apply_state_delta(state, delta, decision=decision, observation=observation)
        emit_state_update_event(delta)
        continue

    if decision.action_type == AgentActionType.ASK_USER:
        persist_waiting_state()
        return KernelRunResult(status="waiting_for_human", ...)

    if decision.action_type == AgentActionType.FINISH:
        return KernelRunResult(status="completed", ...)
```

- [ ] **Step 3: Add budgets**

Initial config:

```python
max_iterations = 24
max_search_calls = 10
max_writer_calls = 8
max_consecutive_failed_tools = 3
```

Budget limits are guardrails. They do not replace coverage judgment.

- [ ] **Step 4: Emit UI-grade events**

Events must use messages like:

```text
Thought Summary: 当前 L3 缺少“号池/协议转换/开源框架”的机制解释，所以先搜索实现链路。
Action: search_web("API中转站 One API New API 协议转换 原理")
Observation: 返回 8 条，采纳 5 条，新增 EV-...
State Update: 新增 3 个实体、2 条主张、1 个待验证问题。
Decision: L3 仍缺风险边界，下一轮转 L5 风险检索。
```

Do not expose hidden chain-of-thought. Use concise summaries.

## Task 7: Wire Personal Auto-Run To Agent Kernel

**Files:**

- Modify: `backend/app/api/app.py`
- Modify: `backend/app/v2_pipeline.py`
- Create or Modify: `backend/app/graph/v2_agent_kernel_graph.py`
- Test: `tests/api/test_v2_agent_kernel_api.py`

- [ ] **Step 1: Add `run_v2_agent_kernel_pipeline()`**

Create a top-level callable:

```python
async def run_v2_agent_kernel_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
```

It initializes `SectorBreakerState`, ingests uploaded docs, creates registry, runs runtime, persists artifacts, and returns artifacts.

- [ ] **Step 2: Deprecate fixed `v2_pipeline.py` behavior**

Either:

```python
from backend.app.agent_kernel.pipeline import run_v2_agent_kernel_pipeline as run_v2_react_knowledge_pipeline
```

or replace the internal body with a call to the kernel. Do not leave the old fixed L1-L5 loop reachable from API.

- [ ] **Step 3: Route API**

In personal `domain_knowledge` auto-run, call the kernel path. Talent demand mode remains unchanged.

- [ ] **Step 4: Preserve zero-evidence hard block**

Zero evidence is still a guardrail, but only after the Agent has attempted appropriate tools or chosen to ask the user. It must not write a fake knowledge base from nothing.

## Task 8: Update Workflow Graph And Frontend Event Display

**Files:**

- Modify: `backend/app/graph/planner.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/WorkflowEditor.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Replace fake long graph**

Personal running graph should show:

```text
Initialize State
External Materials
Agent Decide
Tool Execution
State Update
Artifact Writing
Artifact Review
Human Feedback
Export
```

It may show L1-L5 as coverage panels inside node details, not as a fake execution chain.

- [ ] **Step 2: Map new event gates**

Add event gate mapping:

```typescript
agent_decide -> "agent_decide"
tool_execution -> "tool_execution"
state_update -> "state_update"
artifact_writing -> "artifact_writing"
artifact_review -> "artifact_review"
human_feedback -> "human_feedback"
export -> "export"
```

- [ ] **Step 3: Render trace type labels**

Event stream should visibly distinguish:

```text
Thought Summary
Action
Observation
State Update
Decision
Warning
Blocked
```

This is part of the product. The user must be able to see what the Agent is doing.

## Task 9: V2 Artifact Structure

**Files:**

- Modify: `docs/06-export-spec.md`
- Modify: artifact writing tool.
- Test: `tests/unit/test_agent_kernel_tools.py`

- [ ] **Step 1: Define V2 output set**

Minimum exported files:

```text
00-知识库首页.md
01-L1-本源与需求.md
02-L2-角色与玩家.md
03-L3-原理与实操.md
04-L4-商业与激励.md
05-L5-风险与边界.md
90-Agent运行日志.md
99-待验证问题与补库任务.md
concepts/*.md
players/*.md
tools/*.md
risks/*.md
```

The Agent can choose to create additional cards if State indicates they are needed.

- [ ] **Step 2: Require evidence-linked writing**

Every artifact front matter:

```yaml
schema_version: v2-agent-kernel
type: layer_artifact
layer_id: L3_how
evidence_ids:
  - EV-...
status: draft | reviewed | needs_more_evidence
```

- [ ] **Step 3: Reject template-only artifacts**

If generated markdown is too short or lacks layer-specific content, the writer tool returns failed observation. Runtime should let Agent decide whether to revise, search again, or ask user.

## Task 10: External Report First-Class Path

**Files:**

- Modify: `backend/app/agent_kernel/tools/documents.py`
- Modify: `backend/app/agent_state/report_internalizer.py` if needed.
- Test: `tests/unit/test_agent_kernel_tools.py`

- [ ] **Step 1: Add test**

Given an uploaded report with claims and citations, the first Agent context must include:

- document summary;
- extracted claims;
- citation URLs;
- suggested search leads;
- low-trust source memory.

- [ ] **Step 2: Make `read_uploaded_report` available before search**

The policy prompt must explicitly say:

```markdown
If uploaded external reports exist and have not been read, prefer read_uploaded_report
before broad web search unless the user explicitly asks for fresh-only search.
```

- [ ] **Step 3: Final writing context must include report-derived state**

Artifact writer context should include accepted report claims and citation refs. If a test uploads a report and the final artifact has no trace of it, the test fails.

## Task 11: Minimal Verification, Not Full Time Sink

**Files:**

- Test files from earlier tasks.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py -q
```

Expected: pass.

- [ ] **Step 2: Run one API route test**

Run:

```powershell
python -m pytest tests/api/test_v2_agent_kernel_api.py -q
```

Expected: pass.

- [ ] **Step 3: Run one frontend test file**

Run:

```powershell
cd frontend
npm test -- --run App.test.tsx
```

Expected: pass.

- [ ] **Step 4: Do not run expensive full E2E before user test**

After focused verification, start backend/frontend and let the user manually run:

```text
API中转站
```

Acceptance should be based on visible trace and exported files, not just automated pass/fail.

## Task 12: Manual Acceptance Script For User

**Files:**

- Create: `docs/19-v2-agent-kernel-acceptance.md`

- [ ] **Step 1: Write acceptance checklist**

Checklist:

```markdown
1. Start backend on 8030 and frontend on 5173.
2. Create personal domain project: API中转站.
3. Upload one external AI report if available.
4. Run open-web mode.
5. Confirm event stream shows Thought Summary / Action / Observation / State Update / Decision.
6. Confirm search queries are varied and tied to missing dimensions.
7. Confirm uploaded report appears in state/events/output if uploaded.
8. Confirm output files are V2 L1-L5, not old V1 fixed template names.
9. Confirm no silent fallback templates.
10. Confirm Obsidian links and evidence ids appear.
```

- [ ] **Step 2: Include failure examples**

The acceptance doc must say the run fails if:

- only 3 to 6 superficial sources are collected without Agent explanation;
- LLM writing fails and fallback templates are silently exported;
- event stream only says “recorded source” without thought/action/observation;
- uploaded reports do not affect the run;
- fixed L1-L5 traversal is visible as the main logic.

## Task 13: Commit And Push

**Files:**

- All implementation, tests, docs, memory updates.

- [ ] **Step 1: Inspect diff**

Run:

```powershell
git status --short --branch
git diff --stat
git diff --check
```

- [ ] **Step 2: Stage only relevant files**

Do not stage:

```text
.obsidian/
exports/
data/*.sqlite3
runtime config with API keys
```

- [ ] **Step 3: Commit in Chinese**

Commit message:

```powershell
git commit -m "重构V2为真实Agent Kernel"
```

- [ ] **Step 4: Push both remotes**

If on `main`:

```powershell
git push origin main
git push gitee main
```

If on feature branch, push that branch and report it clearly.

## Acceptance Criteria

This version is acceptable only if:

- personal auto-run uses Agent Kernel, not fixed `v2_pipeline.py` layer traversal;
- LLM decides actions from State and Tools;
- event stream shows thought/action/observation/state update/decision;
- uploaded external reports enter State before search planning;
- search is multi-angle and gap-driven;
- coverage judgment is LLM/state-based, not source-count-based;
- writing is triggered by Agent decision and creates V2 L1-L5 artifacts;
- LLM failures are visible and do not create fake-success templates;
- old V1 output structure is not the main V2 output;
- focused tests pass and user can manually test quickly.

## Implementation Notes For Subagents

Subagents can work independently on:

- prompt files and policy tests;
- tool registry and search/document tools;
- reducer and state tests;
- runtime loop tests;
- frontend event mapping;
- docs/export spec.

The main agent must review:

- policy prompt quality;
- whether any hard-coded workflow sneaks back in;
- whether old `v2_pipeline.py` remains reachable;
- whether external report usage is real;
- whether artifacts are genuinely written by LLM/tool flow.

Do not let any task “simplify” the architecture by moving decisions back into Python if-else except for safety, validation, budget, and provider failure handling.
