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
