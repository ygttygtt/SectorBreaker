# Living Knowledge Base Roadmap

## Positioning

SectorBreaker V3 is positioned as a local-first, multi-Agent autonomous
knowledge-base management system, not "another Deep Search report writer":

- it researches a domain;
- structures the information into Obsidian-friendly documents;
- keeps evidence and Agent state;
- lets the user return later, ask follow-up questions, and grow the vault.

The first run is the `Breaker` bootstrap phase. The long-lived product is the
`Keeper` maintenance phase: import or reopen a vault, audit it, create a
maintenance backlog, verify missing knowledge, and apply reversible revisions.
The second-brain experience is the user outcome; autonomous knowledge
management is the formal product category.

The authoritative V3 implementation contract is
`docs/23-autonomous-knowledge-management-v3.md`.

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

## Implemented V3 Maintenance Loop

The first usable autonomous knowledge-management loop now works end to end:

1. import a real Markdown/Obsidian Vault into a safe managed mirror;
2. run a deterministic health audit;
3. persist and select maintenance backlog items;
4. let the Master Agent retrieve, research, verify, or delegate scoped work;
5. create a base-hash protected ChangeSet and unified diff;
6. approve and apply an immutable active revision;
7. export only active knowledge plus control-plane metadata;
8. rollback and re-export the exact previous content.

The frontend exposes Vault import, health findings, backlog selection,
maintenance runs, ChangeSet proposal/diff, approval, apply, and rollback.
Existing-note Agent revisions no longer mutate ArtifactMemory directly; they
produce a ChangeSet and wait for review.

## Living Vault State Bundle

Exports save a replayable project state bundle beside the Obsidian vault:

```text
vault/
  README.md
  docs/
  cards/
  followups/
  sources/
  .obsidian/
  .sectorbreaker/
    project.json
    agent_state.json
    evidence_ledger.json
    artifact_manifest.json
    health_snapshot.json
    maintenance_backlog.json
    change_sets.json
    open_questions.json
    trace_summary.json
```

This bundle records:

- project and source policy;
- current knowledge schema;
- evidence ids and source memory;
- active artifact revisions and relationships;
- latest knowledge-health snapshot and maintenance backlog;
- ChangeSet diffs, before/after hashes, and rollback history;
- open questions and missing concept gaps;
- Agent trace summaries useful for follow-up planning.

## Implemented Capability: First Follow-Up Growth Loop

The result page now supports a real first-step growth loop:

1. user asks a follow-up question inside the finished project;
2. backend retrieves relevant existing evidence, uploaded document segments, and
   generated artifacts;
3. the configured LLM answers when available, otherwise the deterministic RAG
   fallback answers from citations;
4. backend persists the result as a `followups/*.md` artifact;
5. frontend refreshes the artifact list;
6. export includes the new follow-up page and updated `.sectorbreaker` state.

## Implemented Reopen And Continue Foundation

When a user asks a question or starts a maintenance run, the system now:

1. retrieve relevant existing artifacts, evidence, and open questions;
2. decide whether the answer is already covered;
3. if not covered, create or select a maintenance task;
4. search or inspect uploaded material as needed;
5. propose existing-page updates through ChangeSets or create allowed new notes;
6. link new pages back to the main documents;
7. record what changed in the saved state bundle.

Examples:

- "API 中转站里反向代理到底是什么？" should create or update an explainer
  card such as `concepts/反向代理.md` and link it from the main API gateway
  documents.
- "量化交易为什么能成功？" may add concept cards for `量化`,
  `回测`, `因子`, `交易信号`, and connect them to the original domain map.

## Design Constraint

The implementation must be state-first and revision-safe:

```text
load saved state
  -> load active artifact revisions and health backlog
  -> build context pack
  -> Master Agent decides retrieve/search/delegate/propose_change/ask_user
  -> specialist returns typed result or ChangeSet proposal
  -> apply state delta
  -> validate autonomy policy and base content hash
  -> apply a new artifact revision or wait for approval
  -> save new state bundle
```

This is the same Agent philosophy as the Kernel: State + Tools + Decision +
Observation + StateDelta, not a fixed follow-up workflow. Vector RAG is an
additive retrieval improvement; it is not a substitute for versioning,
ChangeSets, permissions, and rollback.
