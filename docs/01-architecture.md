# Architecture

## Architectural Style

SectorBreaker uses an adaptive research workflow: fixed quality gates on the outside, dynamic Supervisor task assignment inside each gate.

The goal is not to simulate a free-form Agent meeting. The goal is stable research output with enough flexibility to handle different industries, market scopes, and source availability.

## Fixed Gates

1. Scope Gate: normalize domain, market scope, research depth, source policy, and user constraints.
2. Supervisor Plan Gate: generate an explainable research plan, selected/skipped agents, verification plan, assumptions, and success criteria.
3. Human Confirm Plan: pause for user confirmation. The user may add direction, materials, or an external AI brief; the system still owns research and verification.
4. Source Strategy Gate: apply `open_web`, `reliable_first`, `reliable_only`, or `user_materials_only`.
5. Source Intake Gate: collect search results, user materials, reliable-source candidates, and optional assistant briefs.
6. Evidence Ledger Gate: normalize evidence, extract claims, grade source quality, and mark counterevidence needs.
7. Business Analysis Fan-out: run market, player, transaction, opportunity, and optional content/policy agents based on the plan.
8. QA Critic Gate: block unsupported claims, weak-source misuse, missing coverage, and unverified critical claims.
9. Export/RAG Gate: export Markdown/Obsidian artifacts and index approved evidence for local retrieval.

## Supervisor Boundary

The Supervisor may:

- inspect current state and coverage gaps;
- assign tasks to specialist agents;
- request retry or extra evidence;
- decide that a gate is ready for human review.
- generate an explainable `SupervisorPlan` using the rule matrix plus LLM explanation.

The Supervisor may not:

- bypass a fixed gate;
- export claims without evidence metadata;
- call external APIs directly;
- mutate storage outside repository/service interfaces;
- change public schemas without documentation and tests.
- treat assistant briefs, marketing articles, or community posts as verified facts.

## Agent Pool

- Research Planner: creates research frame and learning path.
- Supervisor Agent: creates the plan and explains selected/skipped agents.
- Source Strategy Agent: applies source policy and source scope.
- Search Scout: queries external search providers.
- Assistant Brief Agent: turns pasted external AI reports into low-trust claims and leads.
- User Materials Agent: normalizes user-provided notes and documents.
- Evidence Curator: normalizes sources and confidence metadata.
- Counterevidence Agent: marks and challenges weak critical claims.
- Market Mapper: summarizes market size, growth drivers, and constraints.
- Player Analyst: maps roles, players, bargaining power, and business models.
- Transaction Analyst: identifies transaction units, pricing, frequency, risk, and margin logic.
- Content Channel Analyst: studies content ecosystem, channels, keywords, and conversion paths.
- Knowledge Mapper: turns findings into cards and maps.
- Opportunity Analyst: creates opportunity hypotheses and validation paths.
- QA Critic: blocks unsupported claims and detects missing coverage.
- Export Writer: writes Markdown/Obsidian artifacts.
- RAG Indexer: indexes approved evidence and artifacts through the retrieval interface.

## Data Flow

User input enters the API as structured project configuration. The workflow stores normalized state in SQLite and graph checkpoints. Agents read state, produce structured outputs, attach evidence references, and write artifacts through services. The frontend observes node-level events and asks the user to confirm the Supervisor plan before the graph continues.

External AI reports are optional. When provided, they are stored as `assistant_brief` evidence, split into claims, downgraded by default, and used only as leads until verified by allowed sources.

## Upgrade Points

- Search providers can be swapped without changing graph nodes.
- Retrieval can move from SQLite FTS to hybrid vector retrieval.
- Export format is versioned for future Obsidian and web publishing targets.
- Team collaboration can be added around project ownership and run permissions without changing Agent contracts.

## Master Agent Principle

The next architecture direction is documented in
`docs/16-master-agent-research-core.md`. SectorBreaker must evolve from a fixed
pipeline with LLM-assisted writing into a Master-Agent-controlled research loop.
The Master Agent is responsible for understanding the task, inspecting uploaded
materials and evidence, calling approved tools through provider interfaces,
maintaining run-local working memory, judging coverage, and deciding whether to
continue, search again, ask the user, degrade, or block.

Hard-coded evidence counts may remain only as guardrails. They must not replace
the Master Agent's coverage judgment.

## V1.3 Talent Demand Branch

`ResearchProject.project_mode` now selects the product-facing auto-run branch:

- `domain_knowledge` remains the default V1.2 learning-oriented knowledge-base path.
- `talent_demand` runs the V1.3 Talent Demand Intelligence path.

The talent-demand branch is intentionally additive. It reuses provider
interfaces, SQLite repository persistence, Evidence Ledger, run events, and the
Markdown exporter instead of replacing the older workflow.

Talent-demand auto-run stages:

1. `talent_source_intake`: read uploaded JD/user materials and assistant briefs;
   use search-provider evidence only as supplement when materials are thin.
2. `jd_signal_extraction`: conservatively extract role, company, location,
   salary, experience, education, responsibilities, skills, tools, seniority,
   and evidence ids.
3. `skill_normalization`: merge common aliases such as LLM/大模型, RAG, Agent,
   LangChain, LangGraph, Python, FastAPI, and 向量数据库.
4. `source_coverage`: compute sample/source coverage and gap warnings.
5. `talent_synthesis`: build a structured `TalentDemandKnowledgeBase`; LLM is
   used when configured, deterministic fallback keeps the run demo-safe.
6. `artifact_review`: expand missing learning/portfolio/gap sections without
   shrinking content.
7. `obsidian_export`: persist talent-demand main documents and cards for export.

Legal and operational guardrails:

- Do not scrape login-gated job boards by default.
- Do not bypass anti-bot protections.
- Prefer uploaded JD/report text, public search-provider results, company career
  pages discovered through search, and documented APIs.
- Search snippets are treated as partial evidence unless stronger extraction and
  source assessment succeeds.

## V1.4 Enterprise Job Sources And Project RAG

V1.4 adds an enterprise-only job-source extension for `talent_demand`. The
default `domain_knowledge` path does not depend on Boss, recruitment crawlers,
or job-source configuration.

Talent-demand source intake now has an optional `boss_job_intake` step between
uploaded materials and generic search. It depends on `JobSourceProvider`, not on
direct crawler calls inside API handlers or graph nodes. The first adapter is a
local Boss-compatible CLI adapter (`boss_agent_cli`) that expects JSON output
from a user-installed tool. When the command is missing or fails, the run emits
a degraded event and continues with uploaded JD, external reports, and search
supplements.

Project Q&A now uses a lightweight project RAG retriever. It searches evidence,
uploaded documents, document segments, and generated artifacts, then asks the
configured LLM to answer with citations. If no LLM is configured, it returns a
deterministic citation summary rather than a fixed template.

## V1.5 Real Output And Mode UX Closeout

V1.5 tightens the runnable V1 spine after the `高考教育线上培训` 0-evidence
feedback run:

- The domain-knowledge search query builder no longer injects AI/software-only
  English terms into generic Chinese topics. It uses Chinese research terms such
  as industry trend, market size, regulation, players, user demand, reports, and
  cases unless the topic is explicitly AI/Agent/LLM.
- Chinese compound-topic filtering now extracts meaningful markers and n-grams,
  so results mentioning `高考`, `在线教育`, or `培训` are not discarded merely
  because they do not contain the exact full phrase.
- Fallback knowledge databases are topic-routed. Agent topics keep the Agent
  fallback; large-model career topics keep their dedicated fallback; all other
  topics use a domain-neutral `待补证草稿` scaffold instead of Agent-specific
  concepts.
- LLM failures or too-short document writing now emit degraded run events rather
  than silently substituting fallback Markdown.
- After primary and supplemental source collection, zero usable evidence is now
  a hard gate: the V1 run emits `node_blocked` at `source_collection` and stops
  before knowledge structuring. A knowledge base must not be generated from no
  source material.
- The landing workbench now presents `SectorBreaker 领域建库` and `TalentScope
  人才需求情报台` as distinct personal/enterprise modes with different copy,
  theme, inputs, and branched workflow preview graphs. Running pages still use
  backend run events and workflow definitions as the source of truth.

## V1.6 Master Agent Research Loop

V1.6 implements the first bounded Master-Agent-controlled loop for the personal
`domain_knowledge` path. It preserves the runnable V1 export spine, but moves
search planning and source sufficiency judgment out of fixed count heuristics:

1. `master_agent` builds a run-local `RunWorkingMemory` from project config,
   uploaded documents, evidence, search attempts, tool results, coverage reports,
   and decisions.
2. `external_report_intake` runs before search planning. Uploaded external AI
   reports, user materials, and extracted citations are converted into V1
   evidence with low/partial trust metadata and enter the Master Agent context.
3. `source_collection` executes Master-generated `SearchIntent` records through
   the configured `SearchProvider`. Each tool call records raw results, accepted
   evidence, rejected counts, rejection reasons, query text, and evidence ids.
4. `coverage_evaluation` produces a structured `CoverageReport` across concept
   boundary, current state, trends/reports, policy/risk, cases/players, user
   demand, and source quality.
5. `MasterAgentDecision` maps coverage to `continue`, `search_again`,
   `degrade`, or `block`. Zero evidence remains a hard block. Thin evidence can
   continue only as a visible degraded run after bounded search attempts or when
   uploaded materials provide usable context.
6. `/workflow-definition` for personal projects now returns a V1.6 graph with
   `master_agent`, `external_report_intake`, `source_collection`,
   `coverage_evaluation`, `knowledge_structuring`, `document_writing`,
   `artifact_review`, and `export`, so the UI highlights actual gates.

Limits: V1.6 is bounded to three source rounds and still depends on configured
search-provider quality. Uploaded external AI reports are first-class research
inputs, not automatically verified facts. Full vector retrieval and stronger
source verification remain later upgrades.
