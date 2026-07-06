# V2 Agent Kernel Architecture Review

## Purpose

This document provides a structured architectural review of the current V2
Agent Kernel implementation. It covers state management, agent scheduling,
knowledge schema, and state update mechanisms. The goal is to help future
agents and teammates understand what is mature, what is fragile, and where
the next improvements should go.

Read this after `docs/17-agent-state-memory-architecture.md` and
`docs/18-agent-kernel-design-philosophy.md`.

## Current Architecture Summary

The V2 Agent Kernel follows a classic ReAct pattern:

```text
initialize SectorBreakerState
  -> internalize uploaded documents (ReportInternalizer)
  -> for iteration in 1..max_iterations:
       LLMAgentPolicy.decide(state, tools, trace_tail)
         -> ToolRegistry.dispatch(tool_call)
           -> apply_state_delta(observation)
             -> continue / finish / block
```

Production entry point: `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`

---

## 1. State Management

### 1.1 What Works Well

**Layered memory structure**

```text
SectorBreakerState
├── meta_context          # read-only project metadata
├── knowledge_schema      # L0-L5 cognitive map
├── shared_knowledge      # long-term: entities, claims, relationships, questions, sources
├── working_memory        # short-term: current task attempts and reflections
├── decision_log          # decision history
└── evidence_refs         # evidence ID references
```

This separation matches a reasonable cognitive model: long-term knowledge
(`shared_knowledge`) versus short-lived task context (`working_memory`).

**Source trust tracking**

Every `SourceMemory` carries `use` (context / evidence / search_lead / verify /
rejected) and `trust_level` (high / medium / low / unknown). The Agent can
distinguish reliable evidence from low-trust leads.

**Claim verification state**

Every `KnowledgeClaim` carries `verification_status` (unverified / verified /
partially_verified), `trust_level`, `evidence_ids`, and `needs_verification`.
This prevents the system from treating raw search snippets as confirmed facts.

### 1.2 Current Weaknesses

**No forgetting mechanism**

The reducer only appends; it never decays or removes low-relevance memories:

```python
# backend/app/agent_kernel/reducer.py
state.shared_knowledge.source_memories.extend(_dedupe_source_memories(state, delta))
state.shared_knowledge.claims.extend(_valid_new_claims(state, delta))
```

After 20 search rounds, all sources accumulate in State. The ContextPack grows
until LLM attention is diluted.

Possible fixes:

- add `relevance_score` to `SourceMemory` and decay it over time;
- let `ContextPackBuilder` select only sources related to the current `layer_id`;
- introduce memory compression: merge similar sources into a summary.

**working_memory has no lifecycle management**

`TaskMemory.attempts` and `TaskMemory.local_reflections` only grow:

```python
class TaskMemory(BaseModel):
    attempts: list[ToolAttempt]       # append-only
    local_reflections: list[str]      # append-only
```

The `compressed_reflection()` method does simple truncation at 600 chars, not
semantic compression.

Possible fixes:

- every N attempts, call LLM to generate a structured reflection and replace
  raw attempts with it;
- keep only the last K attempts plus an accumulated reflection summary.

**decision_log has no summarization**

After 24 iterations, `decision_log` has 24 entries. The context builder only
takes `trace_tail[-10:]`, but the full history is never compressed or used for
retrospective learning.

Possible fixes:

- every 10 decisions, generate a "phase reflection" and store it in
  `shared_knowledge`;
- let the Agent review "what I tried before and why it failed."

---

## 2. Agent Scheduling

### 2.1 What Works Well

**Clean ReAct loop**

```python
for iteration in range(1, max_iterations + 1):
    decision = await policy.decide(...)       # Thought
    observation = await registry.dispatch(...)  # Action
    state = apply_state_delta(state, delta)    # Observation + State Update
```

Classic Thought -> Action -> Observation -> State Update.

**Strict failure handling**

```python
if observation.tool_name == "write_layer_document" and not observation.success:
    # Writing failure terminates immediately, no fake artifacts saved
    return KernelRunStatus.FAILED

if consecutive_failed_tools >= max_consecutive_failed_tools:
    # 3 consecutive failures terminate
    return KernelRunStatus.FAILED
```

**JSON repair mechanism**

When LLM outputs invalid JSON, the policy tries a repair prompt before giving
up. This makes the loop more robust against LLM formatting errors.

### 2.2 Current Weaknesses

**No parallel tool execution**

Current dispatch is strictly serial:

```python
observation = await self.registry.dispatch(decision.tool_call, context)
```

If the Agent wants to search 3 different angles simultaneously, it must spend
3 iterations. This wastes budget.

Possible fixes:

- let `AgentDecision` support `tool_calls: list[ToolCall]`;
- use `asyncio.gather` for parallel dispatch;
- but consider State update atomicity.

**No planning layer**

The LLM decides only "what to do next," not "what goal to achieve this round":

```python
class AgentDecision(BaseModel):
    thought_summary: str      # this round's thought
    action_type: ...          # this round's action
    tool_call: ...            # this round's tool
```

The Agent can get "lost" after a search, forgetting the original objective.

Possible fixes:

- add `current_goal: str` or `plan: list[str]` to the decision;
- every 5 iterations, have the Agent review its plan and check progress;
- or emphasize in the prompt: "your current task is..."

**No reflection node**

The loop is linear: decide -> act -> observe -> update -> decide...

If 3 consecutive searches find nothing useful, the Agent should reflect on
"Is my search strategy wrong?" instead of continuing the same approach.

Possible fixes:

- every N tool calls, insert a "reflection step";
- let LLM review recent trace and generate a reflection;
- implement a `reflect()` tool.

**Single tool call per decision**

```python
class AgentDecision(BaseModel):
    tool_call: ToolCall | None  # only one
```

Some scenarios need combined actions, like "search X, then immediately write
a document."

Possible fixes:

- support `tool_calls: list[ToolCall]`;
- or introduce `plan: list[ToolCall]` for multi-step planning.

---

## 3. Knowledge Schema (L0-L5 Cognitive Map)

### 3.1 What Works Well

**L0-L5 is a cognitive framework, not a fixed flow**

```python
class KnowledgeSchema:
    layers: list[KnowledgeLayer]  # dynamic list
```

The Agent can skip already-covered layers and focus on weak ones.

**Each layer has explicit completion criteria**

```python
class KnowledgeLayer:
    guiding_questions: list[str]
    completion_criteria: list[str]
    required_evidence_types: list[str]
    coverage_status: CoverageStatus
```

### 3.2 Current Weaknesses

**Static template, not domain-adaptive**

```python
@classmethod
def default_for_domain(cls, domain, include_prerequisite=False):
    # Hardcoded L1-L5 goals, guiding_questions, completion_criteria
```

Different domains should have different cognitive structures:

- Technical learning (Agent development): L3 How should be heavy, focusing on
  architecture, tools, processes.
- Investment learning (quantitative trading): L4 Money should be heavy,
  focusing on strategies, risk control, returns.
- Industry learning (new energy vehicles): L2 Who should be heavy, focusing
  on players, supply chain, competitive landscape.

The current L1-L5 is a generic template without domain adaptation.

Possible fixes:

- at `initialize()`, let LLM generate a customized `KnowledgeSchema` based on
  the domain;
- pre-define domain templates (technical, commercial, academic) and let the
  Agent choose;
- let the Agent dynamically adjust layer weights and guiding questions during
  runtime.

**No inter-layer dependencies**

Current L0-L5 is a flat list without expressing "L2 understanding depends on
L1."

The Agent might search L4 business models before understanding L1 basics,
producing confusing results.

Possible fixes:

- add `prerequisite_layer_ids: list[KnowledgeLayerId]` to `KnowledgeLayer`;
- before searching a layer, check the prerequisite layer's `coverage_status`;
- or emphasize in the prompt: "understand What before How."

**coverage_status judgment is vague**

```python
class CoverageStatus(StrEnum):
    NOT_STARTED = "not_started"
    NEEDS_MORE = "needs_more"
    DEGRADED = "degraded"
    SUFFICIENT = "sufficient"
    BLOCKED = "blocked"
```

When does `needs_more` become `sufficient`? Currently depends entirely on LLM
judgment without structured criteria.

Although `completion_criteria` exists, there is no quantitative evaluation.

Possible fixes:

- add `coverage_score: float` (0-1) to `KnowledgeLayer`;
- compute a base score from `evidence_count`, `claim_count`,
  `open_question_count`;
- let LLM explain in `coverage_notes` why a layer is sufficient or not;
- or introduce a `coverage_evaluator` tool for the Agent to proactively assess
  coverage.

**No drill-down mechanism**

If the Agent discovers in L3 that "Agent development" involves many
sub-concepts (RAG, vector databases, Prompt Engineering), there is no
mechanism to automatically create sub-tasks for deeper research.

Possible fixes:

- add `sub_layers: list[KnowledgeLayer]` or
  `drill_down_tasks: list[OpenQuestion]`;
- when the Agent finds complex concepts, automatically create drill-down tasks;
- or use `OpenQuestion` as the drill-down entry point, marking each as
  `resolved` when answered.

---

## 4. State Update Mechanism

### 4.1 What Works Well

**Deduplication is thorough**

```python
# By source_id
def _dedupe_source_memories(state, delta):
    seen = {item.source_id for item in state.shared_knowledge.source_memories}

# By (name, entity_type)
def _dedupe_entities(state, delta):
    seen = {(_norm(item.name), item.entity_type) for item in ...}

# By normalized text
def _valid_new_claims(state, delta):
    seen = {_norm(item.text) for item in ...}
```

**Verified claims require evidence**

```python
if claim.verification_status == "verified" and not claim.evidence_ids:
    continue  # Skip "verified" claims without evidence
```

### 4.2 Current Weaknesses

**Exact match deduplication, not semantic**

```python
def _norm(text: str) -> str:
    return _SPACE_RE.sub("", text.strip().lower())
```

"Agent development requires Python" and "Python is essential for Agent
development" have different text but the same meaning. They would be stored as
two separate claims.

Possible fixes:

- use embedding similarity for deduplication (requires vector store);
- or let LLM check for semantically similar claims before generating new ones;
- or use simple keyword overlap in the reducer.

**Append-only, no update mechanism**

```python
state.shared_knowledge.claims.extend(_valid_new_claims(state, delta))
```

If the Agent first finds "Python 3.10 is the mainstream version" and later
finds "Python 3.12 has become mainstream," both claims are kept. The old one is
never updated or marked as superseded.

Possible fixes:

- add `superseded_by: str | None` to `KnowledgeClaim`;
- let the Agent mark old claims as "superseded" when discovering new
  information;
- or detect conflicting claims in the reducer and let LLM decide which to keep.

**No delete operation in state_delta**

```python
class KernelStateDelta(BaseModel):
    source_memories: list[SourceMemory]  # add only
    claims: list[KnowledgeClaim]         # add only
    entities: list[EntityRecord]         # add only
    # No deleted_source_ids / deleted_claim_ids
```

If the Agent discovers a source is garbage, it cannot remove it from State.
It can only mark it as `rejected`, but it still occupies space and context.

Possible fixes:

- add `deleted_ids: list[str]` to `KernelStateDelta`;
- let tools return "delete certain sources/claims" instructions.

---

## 5. Maturity Assessment

| Dimension | Rating | Main Gap |
|-----------|--------|----------|
| State layering | ★★★★☆ | No forgetting mechanism |
| Source trust | ★★★★☆ | Trust level is static, no dynamic adjustment |
| Claim verification | ★★★★☆ | No conflict detection or update mechanism |
| Working memory | ★★★☆☆ | No lifecycle management, unbounded growth |
| ReAct loop | ★★★★☆ | Serial execution, no parallelism |
| LLM decision | ★★★★☆ | Good JSON repair, but no planning layer |
| Failure handling | ★★★★★ | Strict, no fake artifacts |
| Knowledge schema | ★★★☆☆ | Static template, no domain adaptation |
| Coverage judgment | ★★★☆☆ | Relies on LLM subjectivity, no quantification |
| State update | ★★★★☆ | Good dedup, but append-only (no update/delete) |

---

## 6. Optimization Priority Recommendations

### P0 — Should Do Now

1. **Introduce forgetting mechanism**
   Let `ContextPackBuilder` select only relevant sources, or decay
   low-relevance memories. Without this, State grows unbounded and LLM
   attention degrades.

2. **Introduce reflection node**
   Every N tool calls, insert a reflection step. Let the Agent review recent
   trace and decide whether to adjust strategy. This prevents "search loops"
   where the Agent repeats ineffective queries.

3. **Generate domain-adaptive KnowledgeSchema**
   At `initialize()`, let LLM generate a customized schema based on the
   domain, instead of using a hardcoded L1-L5 template.

### P1 — Should Do Soon

4. **Claim conflict detection and update**
   When new information contradicts old claims, let the Agent mark old claims
   as superseded instead of keeping both.

5. **working_memory lifecycle management**
   Compress old attempts into structured reflections instead of letting them
   grow indefinitely.

6. **Support parallel tool calls**
   Let `AgentDecision` specify multiple tools to execute simultaneously,
   saving iteration budget.

### P2 — Can Do Later

7. **Drill-down mechanism**
   When the Agent discovers complex sub-concepts, automatically create
   sub-tasks for deeper research.

8. **Quantitative coverage evaluation**
   Add `coverage_score` based on evidence count, claim count, and open
   question resolution rate.

9. **state_delta delete operation**
   Let tools remove garbage sources or superseded claims from State.

---

## Appendix: Key File References

| Component | File |
|-----------|------|
| State models | `backend/app/agent_state/models.py` |
| ContextPack builder | `backend/app/agent_state/context_pack.py` |
| Report internalizer | `backend/app/agent_state/report_internalizer.py` |
| Kernel pipeline | `backend/app/agent_kernel/pipeline.py` |
| ReAct runtime | `backend/app/agent_kernel/runtime.py` |
| LLM policy | `backend/app/agent_kernel/policy.py` |
| State reducer | `backend/app/agent_kernel/reducer.py` |
| Context builder | `backend/app/agent_kernel/context.py` |
| Tool registry | `backend/app/agent_kernel/tool_registry.py` |
| Search tool | `backend/app/agent_kernel/tools/search.py` |
| Artifact tools | `backend/app/agent_kernel/tools/artifacts.py` |
| Kernel models | `backend/app/agent_kernel/models.py` |
| Design philosophy | `docs/18-agent-kernel-design-philosophy.md` |
| State/memory architecture | `docs/17-agent-state-memory-architecture.md` |
| Debugging retrospective | `docs/19-agent-kernel-debugging-retrospective.md` |
| Version isolation rules | `docs/20-version-isolation-and-cutover-rules.md` |
