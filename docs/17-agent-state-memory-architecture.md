# Agent State, Memory, And Knowledge Architecture

## Why This Document Exists

V1.6 introduced a bounded Master Agent loop, but it is not enough for the final
SectorBreaker architecture. The core product is not search. The core product is
a domain-cognition system that can internalize information, maintain task state,
decide what is missing, call tools, update memory, and generate an expandable
Obsidian knowledge base.

This document records the next architecture direction: SectorBreaker must evolve
from "workflow plus LLM writing" into a stateful, memory-backed, ReAct-capable
research Agent.

## Product Principle

SectorBreaker should behave like a focused domain-research version of Codex or
Claude Code:

- it receives a target domain and optional external research reports;
- it understands the goal: build a structured, expandable knowledge base;
- it decides what information is needed;
- it calls approved tools to collect information;
- it observes results and updates structured state;
- it judges whether each knowledge area is sufficient;
- it routes back to search, asks the user, degrades, or proceeds;
- it writes Obsidian-ready files from curated state, not raw search dumps.

The system should not rely on static counters such as "8 sources means enough".
Counts are guardrails only. Sufficiency is a judgment over goals, state, evidence
quality, coverage, and missing questions.

## Knowledge Architecture: Dynamic Practical Cognition Schema

The knowledge base must follow human learning, not a fixed academic outline.
The Master Agent should generate a domain-specific `KnowledgeSchema` at run
start. A strong default is the five-layer practical cognition model:

1. **L1 What & Why:** What is this thing? Why does the need exist? What problem
   does it solve?
2. **L2 Who:** Who uses it? Who provides it? Who are the major players, user
   groups, communities, institutions, or resource holders?
3. **L3 How:** How does it work? What tools, processes, frameworks, resources,
   prerequisites, and implementation paths are involved?
4. **L4 Money / Incentives:** How does value flow? Who pays whom? What are the
   costs, margins, supply chains, outsourcing links, or monetization patterns?
5. **L5 Risks / Boundaries:** What policies, platform rules, technical limits,
   ethical risks, fragility points, and failure modes exist?

The schema must be dynamic:

- if the user is a beginner, the Master Agent may add `L0 Prerequisite Basics`;
- if a domain is technical, L3 may split into architecture, tools, protocols,
  deployment, data, and evaluation;
- if a domain is market-oriented, L2/L4 may expand into players, channels,
  transactions, demand, and supply-chain nodes;
- if user feedback reveals a missing foundation, the graph can add a new layer
  or sub-vault without destroying the existing knowledge base.

## State Architecture

State is not a dumping ground. It is the structured memory that lets the Agent
work coherently across steps.

### 1. Meta Context

Read-mostly context that every node can access:

- project id, domain, market scope, source policy, product mode;
- user goal and constraints;
- generated `KnowledgeSchema`;
- current phase and active task;
- success criteria and blocking rules;
- source and safety policies.

### 2. Shared Knowledge State

The curated material that will become the knowledge base:

- entities: concepts, players, tools, processes, resources, policies, risks;
- claims: structured factual statements with evidence ids and confidence;
- relationships: upstream/downstream, prerequisite, implements, competes with,
  causes, mitigates, depends on;
- layer outputs: L1-L5 section drafts and card candidates;
- open questions: missing facts, weak claims, unknown terms, user confusion;
- coverage reports by layer and by task;
- accepted source summaries and source-quality labels.

Only normalized and useful information should enter this area.

### 3. Evidence Store

Evidence should be persisted outside prompt context and referenced by ids:

- raw uploaded documents;
- document segments;
- extracted citations;
- search results;
- extracted page text when available;
- source quality and verification metadata;
- rejected/filtered source diagnostics.

The prompt should receive a curated `ContextPack`, not the entire evidence
store.

### 4. Working Memory

Short-lived local memory for the active Master Agent or specialist Agent:

- current checklist;
- tool calls attempted;
- observations;
- failed queries and why they failed;
- local reflections;
- next candidate actions;
- loop count and stop reason.

Working memory should be summarized before crossing node boundaries. Raw failed
attempts, duplicate snippets, page noise, and intermediate logs should not pollute
the shared knowledge state.

### 5. Decision And Audit Log

Append-only trace for observability and debugging:

- thoughts / brief reasoning summaries;
- tool call requests and results;
- coverage judgments;
- decisions: continue, search again, ask user, degrade, block;
- user feedback and follow-up tasks.

This log is for UI trace and audit. It is not automatically included in every
LLM prompt.

## Context Selection Rules

Every LLM call should receive a purpose-built `ContextPack`.

Always include:

- user goal and active task;
- relevant schema layer and completion criteria;
- current coverage gaps;
- top relevant evidence snippets with ids;
- important accepted entities/claims/relationships;
- unresolved questions related to the current task.

Usually exclude:

- raw HTML;
- full uploaded reports unless the task is document analysis;
- duplicate search snippets;
- failed search logs except as a compressed reflection;
- unrelated layer outputs;
- low-relevance sources and noisy navigation text.

Keep as references, not prompt text:

- full document files;
- full evidence ledgers;
- long source pages;
- old event logs;
- rejected result lists.

The system should store long material, summarize and index it, then retrieve
only relevant fragments when a node needs them.

## External AI Report Ingestion

External DeepSearch reports from Gemini, Kimi, Qwen, DeepSeek, or similar tools
are first-class inputs. They are not automatically verified facts, but they are
valuable research assets.

Processing pipeline:

1. Store the raw report as a document.
2. Segment the report.
3. Extract citations, URLs, named entities, claims, and open questions.
4. Create low-trust evidence records for report claims.
5. Create citation evidence for linked sources.
6. Ask the Master Agent which report claims should be trusted, verified, used as
   search leads, or marked as uncertain.
7. Use search as supplement and verification, not as a blind restart.
8. Integrate accepted information into `Shared Knowledge State` with source ids.

The report should influence:

- the initial `KnowledgeSchema`;
- search planning;
- coverage evaluation;
- final writing;
- later Q&A and RAG retrieval.

## ReAct Architecture

ReAct must exist at two levels.

### Global Master Agent ReAct

The Master Agent controls the whole run:

1. **Understand:** parse goal, user level, constraints, uploaded materials.
2. **Plan:** create schema, tasks, coverage goals, and tool strategy.
3. **Act:** call tools or dispatch specialist Agents.
4. **Observe:** read tool outputs, evidence deltas, and specialist summaries.
5. **Update State:** integrate accepted knowledge, rejected noise, and open
   questions.
6. **Reflect:** judge whether information is sufficient.
7. **Route:** continue, search again, dispatch another task, ask user, degrade,
   or block.

### Specialist Agent ReAct

Each layer or task can have a smaller ReAct loop:

- L1 Concept Agent: explains What/Why and identifies missing primitives.
- L2 Player Agent: finds users, providers, institutions, communities, and
  important people/resources.
- L3 How Agent: recursively investigates tools, implementation, prerequisites,
  hidden terms, and operational chains.
- L4 Incentive Agent: maps value flow, business model, costs, supply chain, and
  outsourcing links.
- L5 Risk Agent: maps policy, compliance, platform stability, fragility, and
  abuse/fraud risks.

Specialists write structured outputs to shared state. They should not pass
free-form prose as the main handoff.

## Iceberg / Shadow Investigation

Some domains have hidden jargon, grey-market incentives, scams, or informal
chains that ordinary overview searches miss. SectorBreaker can support an
optional "iceberg investigation" mode, but it must be framed as risk and market
understanding, not as operational guidance for wrongdoing.

This node should be SOP-guided ReAct, not a hard-coded workflow:

- it may start with seed searches such as domain plus "风险", "骗局", "灰产",
  "内幕", "产业链", or safer equivalents;
- it extracts jargon and suspicious service names;
- it asks whether these terms are relevant to L4 incentives or L5 risks;
- it may run deeper searches on high-value terms;
- it summarizes demand, actors, incentives, warning signs, and risk boundaries;
- it must avoid producing step-by-step instructions that enable fraud, evasion,
  account abuse, or illegal operations.

Completion should be judged by whether the system has enough to explain the risk
surface and incentives, not by whether it can teach the user how to execute the
grey activity.

## Human Feedback Loop

The knowledge base should not be one-shot.

After export, the graph should be able to enter a `wait_for_human_feedback`
state. User feedback becomes a new input:

- "I still do not understand X";
- "Add beginner prerequisite knowledge";
- "Go deeper into this player/tool/process";
- "Verify this claim";
- "Build a new sub-vault for a prerequisite field."

The Master Agent should classify the feedback:

- add to existing card;
- create new card;
- create new schema layer such as `L0 Prerequisite Basics`;
- dispatch a specialist Agent;
- ask a clarification question;
- reject unsafe or unsupported requests.

## LangGraph Direction

The next implementation should move the personal V1 path from a large async
pipeline into an explicit LangGraph state graph:

```text
initialize_context
  -> ingest_external_reports
  -> master_plan
  -> dispatch_task
  -> specialist_react_loop
  -> integrate_state
  -> coverage_judge
  -> route_continue_or_retry
  -> write_knowledge_base
  -> artifact_review
  -> export_obsidian
  -> wait_for_human_feedback
```

Conditional edges should be responsible for:

- retrying search;
- dispatching new tasks;
- asking the user;
- degrading;
- blocking;
- exporting;
- reopening the graph after user feedback.

## Implementation Priorities

1. Define durable Pydantic state models: `SectorBreakerState`,
   `KnowledgeSchema`, `KnowledgeLayer`, `KnowledgeClaim`, `EntityRecord`,
   `RelationshipRecord`, `ContextPack`, `TaskMemory`, and `AgentDecision`.
2. Build the `ContextPackBuilder` that decides what enters each LLM call.
3. Upgrade external report ingestion from evidence-only to claim/entity/citation
   extraction and state integration.
4. Convert the V1 personal path into a LangGraph state graph with conditional
   routing.
5. Add specialist ReAct loops for L1-L5 layers.
6. Add human feedback reopening and schema expansion.
7. Strengthen RAG retrieval over evidence, documents, cards, and decisions.

## Current Implementation Status

The first V2 foundation slice is implemented side-by-side with V1.6:

- `backend/app/agent_state/models.py`: durable state and memory models,
  including `SectorBreakerState`, dynamic L0-L5 `KnowledgeSchema`,
  `TaskMemory`, `ContextPack`, source memories, claims, entities, relationships,
  open questions, and decisions.
- `backend/app/agent_state/context_pack.py`: deterministic `ContextPackBuilder`
  that keeps relevant goals, layer criteria, claims, evidence snippets, open
  questions, and compressed working memory while filtering noise, duplicates,
  unrelated layers, and rejected sources.
- `backend/app/agent_state/report_internalizer.py`: first-pass DeepSearch report
  internalizer that extracts low-trust claims, entities, open questions, citation
  URLs, and source memory.
- `backend/app/agents/react_loop.py`: generic bounded ReAct runner with
  `ThoughtSummary`, `ToolCallRequest`, `Observation`, `StateDelta`, and max-step
  stop reasons.
- `backend/app/agents/specialists.py`: L1-L5 specialist contracts and recursive
  follow-up task discovery for important unknown terms.
- `backend/app/agents/iceberg_agent.py`: safe iceberg/risk signal extraction,
  operational-detail redaction, and conversion into L4/L5 low-trust state
  objects.
- `backend/app/graph/v2_react_graph.py`: side-by-side LangGraph skeleton with
  initialization, report ingestion placeholder, master planning, specialist
  loop placeholder, integration, coverage judgment, conditional routing,
  export, and human feedback wait node.

This is not yet the production run path. The next step is wiring these modules
into the API run flow, persisting V2 state, executing specialist ReAct loops
with real LLM/tool policies, and adding human-feedback reopening.

## Non-Negotiable Rules

- Do not pass raw web dumps between nodes.
- Do not treat uploaded AI reports as verified facts by default.
- Do not call external vendors outside provider interfaces.
- Do not let failed searches or noisy snippets pollute shared state.
- Do not export unsupported factual claims without evidence ids.
- Do not reduce the system to fixed if-else workflows where Agent judgment is
  required.
- Do not make the iceberg investigation produce actionable wrongdoing
  instructions.
