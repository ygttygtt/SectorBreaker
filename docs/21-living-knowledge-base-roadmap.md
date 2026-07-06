# Living Knowledge Base Roadmap

## Positioning

SectorBreaker should not be positioned as "another Deep Search report writer".
Its strongest product direction is a living knowledge-base workbench:

- it researches a domain;
- structures the information into Obsidian-friendly documents;
- keeps evidence and Agent state;
- lets the user return later, ask follow-up questions, and grow the vault.

The first run is the "Breaker" phase. The longer-term product is closer to a
second-brain knowledge flow: the more the user asks, verifies, and expands, the
more valuable the saved domain vault becomes.

## Competitive Difference From One-Shot Deep Search

One-shot research tools usually produce a report. The report may be useful, but
it is often a finished text artifact.

SectorBreaker should emphasize a different outcome:

1. **Structured retention**: output is split into linked Markdown pages, cards,
   sources, open questions, and topic layers.
2. **Evidence continuity**: claims should remain connected to evidence ids,
   uploaded reports, search results, and verification status.
3. **Human-in-the-loop growth**: user questions after export should become new
   tasks that can add cards, update existing documents, or create missing
   concept explainers.
4. **Knowledge graph feel**: Obsidian backlinks, indexes, concepts, and related
   pages should make the vault browsable by humans and retrievable by Agents.

## Demo-Version Promise

For the current staged demo, do not overclaim unfinished persistence features.
The demo can honestly say:

- the current run uses an Agent Kernel path with State, Tools, Decisions,
  Observations, and State Updates;
- the frontend shows the Agent's short user-facing summaries while it works;
- exported Markdown is structured for Obsidian instead of being one flat report;
- `.obsidian/` workspace configuration is copied into the generated vault;
- the roadmap is to reopen the saved vault for follow-up questions and growth.

## Required Future Capability: Living Vault State

The next major product capability should save a replayable project state bundle
beside the Obsidian vault:

```text
vault/
  README.md
  01-*.md
  concepts/
  sources/
  questions/
  .obsidian/
  .sectorbreaker/
    project.json
    agent_state.json
    evidence_ledger.json
    trace_summary.json
    artifact_manifest.json
    open_questions.json
```

This bundle lets the workbench reopen a previous knowledge base and restore:

- project mode and source policy;
- current knowledge schema;
- evidence ids and source memory;
- generated artifacts and their relationships;
- open questions and missing concept gaps;
- Agent trace summaries useful for follow-up planning.

## Required Future Capability: Follow-Up Growth Loop

When a user asks a question inside an existing vault, the Agent should:

1. retrieve relevant existing artifacts, evidence, and open questions;
2. decide whether the answer is already covered;
3. if not covered, create a follow-up task;
4. search or inspect uploaded material as needed;
5. update existing pages or create new explainer cards;
6. link new pages back to the main documents;
7. record what changed in the saved state bundle.

Examples:

- "API 中转站里反向代理到底是什么？" should create or update an explainer
  card such as `concepts/反向代理.md` and link it from the main API gateway
  documents.
- "量化交易为什么能成功？" may add concept cards for `量化`,
  `回测`, `因子`, `交易信号`, and connect them to the original domain map.

## Design Constraint

Do not fake this capability in the current demo. If the saved-state reopen loop
is not implemented yet, present it as roadmap and make the current UI/exports
prepare the user to understand why the feature matters.

The implementation must be state-first:

```text
load saved state
  -> build context pack
  -> LLM decides answer/search/update/create_card/ask_user
  -> execute tools
  -> apply state delta
  -> write or update Obsidian files
  -> save new state bundle
```

This is the same Agent philosophy as the V2 Kernel: State + Tools + Decision +
Observation + StateDelta, not a fixed follow-up workflow.

