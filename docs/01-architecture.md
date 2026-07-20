# Architecture

## Architectural Style

SectorBreaker V3 is an Agent Kernel with a knowledge-management control plane.
The production owner is one LLM-controlled loop operating over structured State
and approved Tools. LangGraph/FastAPI may host persistence, routing, events, and
human review, but fixed product workflows must not replace Agent judgment.

```text
build_context_pack(state, active_task, active_artifacts)
  -> master_agent_decide(context, tools, autonomy_policy)
  -> execute_tool_or_delegate_specialists
  -> observe
  -> validate_state_delta_or_change_set
  -> persist state + artifact versions + audit trail
  -> decide again / wait for approval / finish
```

## Product Layers

1. **Knowledge Surface**: Markdown/Obsidian vault and active artifact revisions.
2. **Retrieval Layer**: local content-hash incremental embeddings plus unified
   lexical/vector hybrid retrieval.
3. **Knowledge Control Plane**: health snapshots, maintenance backlog,
   ArtifactMemory, ChangeSets, diffs, approvals, and rollback.
4. **Agent Kernel**: Master Agent decisions, specialist delegation, evidence
   verification, state updates, and stopping judgment.
5. **Provider Boundaries**: replaceable LLM, search, extraction, retrieval, and
   future embedding providers.

## Production Entry Points

There is one production product mode and one executable owner:

```text
backend.app.agent_kernel.run_v2_agent_kernel_pipeline
```

The function name remains for compatibility during the V3 migration, but its
state and artifact schema advance to V3 knowledge management. The retired
enterprise talent-demand pipeline and job-source providers must not exist in
production imports.

## Bootstrap And Maintenance Are Agent Goals, Not Product Modes

The same Agent Kernel supports two goals:

- `bootstrap`: create a first knowledge system for an empty project;
- `maintain`: inspect an existing managed vault, execute backlog tasks, and
  revise active knowledge.

This distinction belongs in State and request context. It must not recreate
separate executable product pipelines.

## Knowledge Workspace

An imported vault is adopted into a safe managed mirror:

- relative Markdown paths are preserved;
- imported notes become retrievable documents and versioned `vault_note`
  artifacts;
- the user's source directory is not mutated by the first V3 release;
- active revisions are exported as the managed Obsidian vault;
- content hashes detect conflicts and support rollback.

## Deterministic Health Gate

Structural facts must not depend on an LLM. A deterministic scanner owns:

- broken wikilinks;
- orphan notes;
- duplicate titles;
- missing front matter;
- missing evidence metadata;
- unresolved TODO/question markers;
- path and content-hash inventory.

Semantic findings such as stale, unsupported, or conflicting factual claims
are delegated to evidence-aware Agents and must record the detector and source
ids.

## Multi-Agent Boundary

The Master Agent may dynamically call registered specialist roles. Specialists:

- receive a scoped ContextPack and task contract;
- have a role-specific tool allowlist and budget;
- return typed findings, StateDelta, or ChangeSet proposals;
- cannot directly apply a ChangeSet or mutate the vault;
- are not executed as a fixed role sequence.

Initial specialist roles are vault auditor, researcher, verifier, and knowledge
editor.

## Autonomy And Permissions

Autonomy is governed by runtime policy, not by prompt wording.

- read, retrieve, and deterministic audit may run automatically;
- network search follows source policy and hard budgets;
- new note creation may be auto-applied only in allowed paths;
- existing note updates require a valid ChangeSet and base hash;
- delete/move operations are denied in the first V3 release;
- factual updates require evidence ids;
- file-count, changed-byte, search-call, and writer-call limits are enforced by
  runtime code.

## Artifact Versioning

Artifacts are immutable revisions. An update creates a new artifact with:

- revision number;
- content hash;
- `supersedes` / `superseded_by` relation;
- active status;
- originating run and ChangeSet.

Retrieval, export, RAG, indexes, and README generation use active revisions by
default. Continuation restores active artifacts into runtime context before the
Agent can revise them.

Checkpoint and artifact persistence must not advertise a resumable completed
state unless referenced artifacts are durable. Partial states use an explicit
partial checkpoint type.

## Retrieval Architecture

Project chat and Agent tools share one retrieval service. It synchronizes a
rebuildable local vector index and retrieves over:

- evidence;
- uploaded/imported documents and segments;
- active artifacts and imported vault notes.

Lexical and vector ranks are fused with reciprocal-rank fusion. Results return
hit-local snippets, parent metadata, source type, fused score, retrieval mode,
model identity, and citation ids. Hidden or superseded memories are excluded.

`EmbeddingProvider` is replaceable; the first adapter is local FastEmbed using
a Chinese-capable model. Vector indexes are content-hash incremental, derived,
and rebuildable; SQLite and Markdown remain sources of truth. Model failure
must expose `lexical_degraded`, never a false hybrid status.

Detailed contracts and acceptance gates live in `docs/24-local-hybrid-rag.md`.

## Evidence Boundary

No final factual change may be marked verified without linked evidence.
Uploaded external AI reports remain low/partial-trust sources. Generated
artifacts are secondary knowledge and should resolve back to their original
evidence where possible.

## Export And Recovery

The exported vault includes active notes plus:

```text
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

The full Agent State checkpoint remains in SQLite for exact resume. The exported
bundle contains enough version and control-plane metadata for inspection and a
future re-import flow.

## Version Isolation

Architecture cutovers follow `docs/20-version-isolation-and-cutover-rules.md`.
V3 adds enterprise retirement markers to the isolation scan. Runtime guards are
smoke alarms; deleted or unreachable production paths are the actual fix.

The detailed V3 contracts and acceptance gates live in
`docs/23-autonomous-knowledge-management-v3.md`.
