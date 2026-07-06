# Agent Kernel Debugging Retrospective

## Purpose

This document records the long V2 Agent Kernel debugging failure chain that led
to the current cutover. It exists as a working norm for future agents and
developers: do not repeat the same failure pattern, do not hide weak output
behind fake tests, and do not call a fixed workflow an Agent.

The important lesson is not only "one bug was fixed." The deeper lesson is that
SectorBreaker repeatedly produced poor results because architecture, verification
and acceptance drifted away from the product goal.

The follow-up governance rule lives in
`docs/20-version-isolation-and-cutover-rules.md`. Future cutovers must read that
document and treat version isolation as an architecture requirement, not a test
cleanup task.

## What The User Observed

During repeated local runs, especially with topics such as `API中转站`,
`高考教育线上培训`, `大模型开发就业`, and `信息搜集 Agent`, the user observed:

- Search collected too few sources and often looked like mechanical keyword
  splitting rather than Agent-driven research planning.
- Evidence sufficiency was judged by fixed counts or shallow heuristics instead
  of a stateful LLM coverage decision.
- Uploaded external AI reports did not clearly enter the later writing context.
- The visible workflow graph did not match the actual backend execution path.
- The event stream showed node names such as `Knowledge Builder`,
  `Document Writer`, and `specialist_react_loop`, even after the product goal
  had moved to an Agent Kernel.
- Some runs quickly traversed L1-L5 like a fixed chain, with one or two search
  results per layer, then jumped to writing.
- Writing consumed most of the runtime, then failed with `JSONDecodeError`.
- Failed writing was replaced by fallback/template Markdown, creating files that
  looked structurally valid but had almost no real LLM-written content.
- Exported Markdown sometimes carried old `EV-V1-*` / `ART-V1-*` identifiers or
  V1-style structure, proving that old paths were still influencing output.

These observations were valid. They indicated architectural drift, not just a
small presentation bug.

## Root Cause Chain

### 1. Agent language was added before Agent control was real

Earlier iterations introduced words such as Master Agent, ReAct, State,
Coverage, L1-L5 and Specialist Agents, but part of the production behavior was
still shaped like a fixed workflow:

```text
run L1
run L2
run L3
run L4
run L5
write fixed documents
```

That made the system appear agentic while still behaving like a scripted
pipeline. L1-L5 should be a cognitive schema inside State, not a hard-coded
execution chain.

### 2. Old workflow code stayed in the production namespace

The repository kept old `backend/app/v1_pipeline.py` and
`backend/app/v2_pipeline.py` beside the new Agent Kernel code. Even when the
intention was to run V2 Agent Kernel, the old files remained easy to import,
test, and accidentally reason around.

This caused two recurring problems:

- Developers could patch symptoms in old code while believing the new path was
  being fixed.
- The frontend and tests could still contain old node names or assumptions,
  making it hard to tell which path was actually running.

The correct fix was not adding more defensive checks around old paths. The fix
was version isolation: move old workflow files under `backend/app/legacy/` and
make production code outside that package unable to import them.

### 3. Markdown writing was routed through structured JSON parsing

The writer prompt asked for JSON-like structure, while the actual desired output
was long Obsidian Markdown. The provider path used structured output parsing for
content that was not naturally JSON.

With Mimo/OpenAI-compatible responses, this created a fragile failure mode:

- the LLM produced Markdown or partially wrapped text;
- the structured parser expected JSON;
- parsing failed with `JSONDecodeError`;
- the pipeline treated writing as failed.

The correct fix was to add a plain text `LLMProvider.complete()` path for
Markdown writing and reserve `complete_structured()` for Agent decisions,
schemas, and tool planning.

### 4. Fallback templates hid real failure

Earlier versions sometimes converted LLM failure or thin output into fallback
Markdown. This made the run look successful from the API or test perspective,
but the exported content was not useful. The user then opened the export and saw
template-like text.

This is especially dangerous in an Agent product because it breaks the most
important feedback loop: "Did the LLM actually do the research and writing?"

The current rule is strict:

- retry writing visibly;
- emit progress while waiting;
- if still unusable, fail or block the run;
- do not persist fake artifacts;
- do not export fallback Markdown as if it were an Agent result.

### 5. Tests over-validated internal mechanics and under-validated user output

Too much time was spent running isolated or fake-provider tests that could pass
while the user-facing artifact was still empty or wrong. This created a false
sense of completion.

For this project, fake tests are useful only as regression guards. They cannot
prove that the product is usable.

The minimum acceptance for the personal Agent Kernel path is now:

1. Run one real end-to-end project with the configured Mimo-compatible LLM and
   Tavily.
2. Inspect the event stream for:
   - `Thought Summary:`
   - `Action:`
   - `Observation:`
   - `State Update:`
3. Inspect exported Markdown manually or with a focused scan.
4. Confirm files contain `schema_version: "v2-agent-kernel"` and `EV-KERNEL-*`.
5. Confirm files do not contain old/fallback markers:
   - `EV-V1-`
   - `ART-V1-`
   - `Knowledge Builder`
   - `Document Writer`
   - `specialist_react_loop`
   - `已使用保底`
6. Confirm the content is substantial enough to read, not merely valid YAML plus
   generic scaffolding.

### 6. UI graph and backend execution drifted apart

The frontend graph sometimes displayed a richer structure than the backend
actually executed, or kept old node mappings after backend changes. This caused
the graph to look like decoration rather than an execution monitor.

The rule is now:

- workflow definition comes from backend truth;
- frontend may map aliases, but must not invent production flow;
- if a node never receives events, do not present it as active production logic;
- running personal mode should display Agent Kernel nodes:
  `initialize_state`, `external_materials`, `agent_decide`,
  `tool_execution`, `state_update`, `artifact_writing`, `artifact_review`,
  `human_feedback`, `export`.

### 7. External materials were not treated as first-class State

The user repeatedly emphasized that uploaded DeepSearch reports and external AI
research are valuable sources. Earlier flows did not always make it obvious that
these reports entered State, search planning, and writer context.

The required behavior is:

- ingest uploaded reports before planning further search;
- extract citations, claims, entities and open questions;
- mark them as low/partial-trust source memories rather than verified facts;
- use them as leads and context for writing;
- let search supplement or verify them;
- make their presence visible in events and writer context.

If uploaded reports do not affect final artifacts, the feature should be treated
as broken.

## What Was Changed To Stabilize The Current Version

The current cutover made these concrete changes:

- Old V1/V2 workflow files were moved to `backend/app/legacy/`.
- Production personal `domain_knowledge` auto-run now calls
  `run_v2_agent_kernel_pipeline`.
- Workflow definitions for personal runs now expose Agent Kernel nodes instead
  of V1.6 Master-Agent or old specialist-loop nodes.
- `LLMProvider.complete()` was added for plain text Markdown generation.
- OpenAI-compatible provider now sends `stream: false`, supports
  `max_tokens`, and tolerates keepalive/SSE-wrapped response bodies.
- `write_layer_document` now writes section by section through plain text LLM
  completion and emits heartbeat events during long writing.
- Writer failure no longer saves fake/template artifacts.
- Failed partial-write runs do not persist earlier successful partial artifacts.
- Export strips inner artifact YAML so exported Markdown has one clean front
  matter block.
- Frontend event mapping was aligned with Agent Kernel nodes.
- Project handoff docs and memory now record that real Mimo + Tavily acceptance
  is mandatory before claiming readiness.

## Current Acceptance Evidence

The accepted cutover run was:

```text
Project: api中转站-v2-agent-kernel验收5
Export: E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2-agent-kernel验收5
```

Exported files:

```text
01-API中转站：本源与需求.md      17447 bytes
02-API中转站：角色与玩家.md      18804 bytes
03-API中转站：原理与实操.md      22488 bytes
04-API中转站：商业与激励.md      22161 bytes
05-API中转站：风险与边界.md      21249 bytes
```

Inspection result:

- all five main files have `schema_version: "v2-agent-kernel"`;
- evidence IDs are `EV-KERNEL-*`;
- no accepted export hit `EV-V1-*`, `ART-V1-*`, `Knowledge Builder`,
  `Document Writer`, `specialist_react_loop`, or `已使用保底`;
- content is substantial enough to be read as a real first-pass knowledge base,
  though deeper source verification, better search planning, RAG and user
  feedback reopening remain future work.

## Development Rules From This Incident

### Rule 1: Do not patch around the wrong architecture

If a path is obsolete, isolate it or remove it. Do not add runtime checks whose
only purpose is to fail when the code accidentally reaches old behavior.

### Rule 2: Do not call a workflow an Agent

An Agent must have State, Tools, observations, state deltas and LLM decisions.
If code is just traversing a predefined list of stages, call it a workflow and
do not present it as ReAct.

### Rule 3: Do not use fake artifacts as success

Fallback Markdown can be useful only if explicitly labeled as blocked or
partial and never persisted as a successful Agent artifact. If the product goal
is useful output, empty templates are failure.

### Rule 4: Do not validate output only through unit tests

Unit tests catch regressions. They do not prove research quality. For output
features, run one real end-to-end case and inspect the exported files.

### Rule 5: Do not let frontend graphs drift from backend execution

The graph is a user-facing explanation of what the Agent is doing. If it does
not reflect actual execution, it is worse than no graph.

### Rule 6: Do not mix versions in the same production path

Versioned experiments must live under clear namespaces. Legacy tests may import
legacy modules, but production code must not.

### Rule 6A: Cut over by isolation, not by guard-only patches

Runtime guards may remain as smoke alarms, but they are never the primary fix.
If old workflow code can still be imported by production code, the cutover is
not complete.

### Rule 7: Record failures as product knowledge

When a long debugging loop happens, update:

- this retrospective when the failure pattern is architectural;
- `docs/10-current-status-and-handoff.md`;
- `docs/11-tooling-handoff.md`;
- `.claude/memory/current-progress-and-handoff.md`;
- `.claude/memory/tooling-handoff.md`;
- relevant architecture or contract docs.

The purpose is to make the next agent less likely to repeat the same mistake.

## Future Watchpoints

Even after the cutover, these remain high-risk:

- Agent decisions may still be too shallow if prompts or context packs are weak.
- Search quality may still be insufficient without deeper multi-query planning.
- External reports must be visibly internalized and cited in artifacts.
- Human feedback reopening is not fully mature yet.
- Source verification and RAG need to be deepened.
- Artifact review should eventually inspect claim quality, not only length and
  structure.

Do not treat the current V2 as finished. Treat it as the first version that is
finally on the right architecture path.
