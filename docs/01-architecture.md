# Architecture

## Architectural Style

SectorBreaker uses an adaptive research workflow: fixed quality gates on the outside, dynamic Supervisor task assignment inside each gate.

The goal is not to simulate a free-form Agent meeting. The goal is stable research output with enough flexibility to handle different industries, market scopes, and source availability.

## Fixed Gates

1. Scope Gate: normalize domain, market scope, research depth, and user constraints.
2. Research Frame Gate: produce directory structure, key questions, and learning path.
3. Evidence Gate: collect and normalize sources, detect missing evidence, tag confidence.
4. Knowledge Map Gate: build industry map, player map, transaction units, risk boundaries, and content/channel patterns.
5. Opportunity Gate: produce opportunity hypotheses with evidence, assumptions, risks, and first validation actions.
6. Export Gate: write Markdown/Obsidian artifacts and index them for project Q&A.

## Supervisor Boundary

The Supervisor may:

- inspect current state and coverage gaps;
- assign tasks to specialist agents;
- request retry or extra evidence;
- decide that a gate is ready for human review.

The Supervisor may not:

- bypass a fixed gate;
- export claims without evidence metadata;
- call external APIs directly;
- mutate storage outside repository/service interfaces;
- change public schemas without documentation and tests.

## Agent Pool

- Research Planner: creates research frame and learning path.
- Search Scout: queries external search providers.
- Evidence Curator: normalizes sources and confidence metadata.
- Market Mapper: summarizes market size, growth drivers, and constraints.
- Player Analyst: maps roles, players, bargaining power, and business models.
- Transaction Analyst: identifies transaction units, pricing, frequency, risk, and margin logic.
- Content Channel Analyst: studies content ecosystem, channels, keywords, and conversion paths.
- Knowledge Mapper: turns findings into cards and maps.
- Opportunity Analyst: creates opportunity hypotheses and validation paths.
- QA Critic: blocks unsupported claims and detects missing coverage.
- Export Writer: writes Markdown/Obsidian artifacts.

## Data Flow

User input enters the API as structured project configuration. The workflow stores normalized state in SQLite and graph checkpoints. Agents read state, produce structured outputs, attach evidence references, and write artifacts through services. The frontend observes stage status and asks the user to confirm interrupts before the graph continues.

## Upgrade Points

- Search providers can be swapped without changing graph nodes.
- Retrieval can move from SQLite FTS to hybrid vector retrieval.
- Export format is versioned for future Obsidian and web publishing targets.
- Team collaboration can be added around project ownership and run permissions without changing Agent contracts.
