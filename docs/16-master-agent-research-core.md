# Master Agent Research Core

## Why This Exists

SectorBreaker must not remain a fixed workflow that merely calls an LLM to write
documents after search. The product goal is an Agentic research system: the
system should understand the user's research goal, decide what information is
missing, call tools to fill gaps, and stop when it cannot build a trustworthy
knowledge base.

The `Master Agent` is the core node that owns this judgment.

## Non-Negotiable Requirements

The Master Agent must be:

- **Intelligent:** It must reason over the user's task, uploaded materials,
  current evidence, generated artifacts, and missing coverage. Hard-coded counts
  such as "8 evidence items means sufficient" are not acceptable as the primary
  decision rule.
- **Tool-capable:** It must be able to call approved provider tools through
  interfaces, including search, uploaded-report ingestion, document retrieval,
  evidence inspection, and later RAG/vector retrieval. Graph nodes and API
  handlers still must not call vendors directly.
- **Flow-controlling:** It can decide whether the workflow should continue,
  collect another round of sources, ask for user input, degrade with explicit
  warnings, or stop.
- **Stateful during a run:** It must know what has already been searched, which
  sources were accepted or rejected, what new information was added, which gaps
  remain, and why a decision was made.
- **Memory-backed within task context:** At minimum, each run needs a structured
  working memory containing the research goal, source inventory, coverage state,
  attempted queries, rejected results, external reports, and decision history.

## Master Agent Inputs

The Master Agent should receive a structured `ResearchContext`:

- project config: domain, market scope, depth, source policy, project mode;
- user intent: original user prompt, extra guidance, constraints;
- uploaded materials: JD files, user notes, external AI reports, citations;
- evidence ledger summary: accepted evidence, low-trust evidence, rejected or
  filtered results, source channels, verification state;
- run memory: previous search plans, queries attempted, coverage reports,
  tool-call outcomes, warnings, and blocked reasons;
- product mode: personal domain knowledge vs enterprise talent demand.

## Tool Boundaries

The Master Agent may request tool calls through provider/service boundaries:

- `SearchProvider.search(SearchQuery)` for broad web search;
- document ingestion and citation extraction for uploaded external reports;
- project retriever / RAG search over existing project documents, evidence, and
  artifacts;
- source verification and content extraction providers when configured;
- job-source provider only in `talent_demand` mode and only when explicitly
  enabled.

The Master Agent must not:

- call external vendor APIs directly;
- bypass source policy;
- treat assistant reports as verified facts without evidence status;
- hide zero-evidence or low-coverage conditions;
- generate final research claims without linked evidence metadata.

## Decision Loop

The target loop is:

1. **Understand:** Parse the task and produce a research objective, success
   criteria, and required coverage dimensions.
2. **Inspect:** Review uploaded reports, user materials, current evidence,
   accepted/rejected search results, and previous attempts.
3. **Plan:** Generate multi-intent search and ingestion tasks. Search should be
   driven by research needs, not by mechanical token splitting.
4. **Act:** Call approved tools. Store raw result counts, filtered counts,
   accepted evidence, rejected evidence, and diagnostics.
5. **Evaluate:** Produce a `CoverageReport` that judges sufficiency by dimension:
   concept coverage, current state, trend evidence, reliable sources, examples,
   risks/conflicts, and user-specific goal coverage.
6. **Decide:** Continue, search again, ask user for materials, degrade with
   explicit limitations, or block.
7. **Record:** Persist the decision and reason as run memory and run events so
   the UI can show what happened.

## Coverage Judgment

Evidence sufficiency must be a structured judgment, not a raw count.

Recommended output:

```json
{
  "status": "sufficient | needs_more_sources | blocked | degraded",
  "coverage_score": 0.0,
  "covered_dimensions": ["concepts", "current_state"],
  "missing_dimensions": ["policy", "case_studies"],
  "recommended_tool_calls": [
    {
      "tool": "search",
      "intent": "find recent policy and regulation sources",
      "query": "高考 教育 线上培训 政策 监管 2026",
      "reason": "current evidence lacks policy constraints"
    }
  ],
  "can_continue": false,
  "block_reason": "zero usable evidence after two search rounds"
}
```

Hard thresholds may remain as guardrails, for example "zero usable evidence must
block" or "maximum search rounds is 3", but they must not replace the Master
Agent's coverage judgment.

## External AI Reports

Uploaded reports from Kimi, Gemini, Qwen, DeepSeek, or similar tools are first-
class external sources. They should be ingested before search planning:

- store the raw report as project document material;
- split it into segments;
- extract citations and source URLs;
- create low-trust `assistant_brief` evidence for report claims;
- include the report summary and citations in the Master Agent's context;
- let search act as supplement or verification, not as the only source.

These reports are not automatically verified facts, but they are real research
inputs and must influence planning, coverage judgment, and final writing.

## Workflow Visualization Requirement

The UI graph must reflect actual execution state:

- preview graphs may differ by product mode, but running graphs must be backed
  by the active workflow definition and run events;
- nodes that never execute should not appear as active pipeline steps;
- every displayed execution node should be able to receive started, progress,
  completed, degraded, blocked, or failed status;
- repeated search/evaluation loops should be visible as either loop counters or
  event history tied to the Master Agent / Source Collection nodes.

## Implementation Plan

### Phase 1: Context And Memory

- Add a `ResearchContext` / `RunWorkingMemory` schema.
- Populate it from project config, uploaded documents, evidence ledger, previous
  search attempts, and run events.
- Ensure V1 auto-run reads uploaded external reports and user materials, not only
  pre-existing evidence rows.

### Phase 2: Master Agent Contract

- Add `MasterAgentDecision`, `CoverageReport`, `ToolCallRequest`, and
  `ToolCallResult` schemas.
- Document allowed decisions: `continue`, `search_again`, `ask_user`, `degrade`,
  `block`.
- Require every decision to include a reason and state snapshot.

### Phase 3: Tool-Calling Search Loop

- Replace static query-only V1 source collection with Master Agent generated
  search intents.
- Record raw result counts, filtered counts, accepted evidence, rejected reasons,
  and query diagnostics.
- Allow bounded loops, for example max 2-3 tool rounds, with explicit blocked
  output when coverage remains insufficient.

### Phase 4: LLM Coverage Judgment

- Replace the current primary "8 evidence item" sufficiency rule with
  `CoverageReport`.
- Keep zero evidence as a hard block.
- Use coverage dimensions and missing angles to decide whether writing can start.

### Phase 5: Graph And UI Alignment

- Update backend workflow definition to expose the Master Agent, source loop,
  coverage evaluation, external report intake, and block/degrade decisions.
- Update frontend graph mapping so running nodes match actual event gates.
- Display Master Agent decisions as readable cards, not raw JSON.

### Phase 6: Acceptance Tests

Minimum acceptance examples:

- A run with an uploaded external AI report shows report intake and uses report
  citations/evidence in the final knowledge base.
- A run with 0 usable evidence blocks before writing artifacts.
- A run with 3 evidence items may continue only if the Master Agent says the
  required coverage is sufficient and explains why.
- A run with missing policy/case/source dimensions triggers another search round
  with new intent-driven queries.
- The running graph highlights the same nodes that emit run events.

