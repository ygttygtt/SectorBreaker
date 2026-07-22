# Agent Contracts

## Contract Rules

Every Agent and tool boundary must document its typed input, typed output,
allowed tools, disallowed behavior, budget, and failure mode. Internal modules
must not use free-form prose as the only handoff when a Pydantic model exists.

Any output containing factual claims supports:

- claim id;
- evidence ids;
- confidence;
- verification status;
- notes and conflict/supersession metadata.

## Master Knowledge Manager

Project source preferences are trusted control-plane input. They are included
in MetaContext and cannot be widened by an LLM tool call. `require` is enforced
both before provider dispatch and after URL return; `prefer` records any
fallback to the broader project source policy in the typed observation and
Evidence collection metadata.

- Input: `SectorBreakerState`, active artifacts, latest health snapshot,
  maintenance backlog, autonomy policy, provider/tool registry, recent trace,
  and optional user objective.
- Output: typed `AgentDecision`, tool calls or specialist tasks, user-facing
  summary, plan, progress check, and stop reason.
- Owns: task selection, specialist delegation, research/verification routing,
  ChangeSet acceptance, budget use, and finish/block/ask-user judgment.
- May not: bypass autonomy policy, directly call vendors, treat a fixed Agent
  sequence as autonomy, export unsupported facts, or silently overwrite an
  active note.
- Failure mode: wait for user when authority is missing; block when evidence or
  a safe write path is unavailable; preserve partial diagnostics without
  presenting fake success.
- Completion gate: historical active artifacts do not count as work completed
  in the current run. `finish`/`finish_run` requires a new artifact in this
  execution or an artifact durably attributed to the same resumed run id.
- Budget durability gate: consumed search-tool, Provider, extraction, and
  writer counts are typed State. Same-run human resume restores those counts;
  only a new run receives a fresh allowance.
- Durability gate: artifact and final State checkpoint failures propagate to
  the API run boundary; they must not be swallowed while marking a run
  completed.
- Execution lease gate: a run worker must own an unexpired lease before it can
  append runtime events or finalize status. A crashed `running` run becomes
  `interrupted` only when a durable checkpoint exists; otherwise it fails as
  `orphaned_no_checkpoint`.
- Recovery gate: human feedback resumes the same waiting run through an atomic
  claim. Crash recovery creates one child run with `resumed_from_run_id` and
  keeps the parent's audit history immutable.

## Vault Auditor Specialist

- Input: deterministic health findings, scoped note metadata, relevant content
  excerpts, and task budget.
- Output: typed semantic findings, maintenance task proposals, and optional
  verification questions.
- Allowed tools: project retrieval and evidence inspection.
- May not: invent broken links or other structural findings already owned by
  the deterministic scanner; directly edit or apply changes.
- Failure mode: return insufficient-context status and requested note/evidence
  ids.

## Researcher Specialist

- Input: maintenance objective, current State gaps, source policy, relevant
  project memory, bounded local retrieval citations, and a search budget.
- Output: structured source memories, evidence ids, claims, unresolved
  questions, and a stop reason.
- Allowed tools: unified project retrieval, uploaded-material reading, approved
  SearchProvider, and content extraction through provider interfaces. In the
  current implementation local retrieval is executed while building the
  Specialist context; external tool recommendations are returned to the Master
  dispatcher and do not bypass its budgets.
- May not: use restricted providers, upgrade weak sources to verified, or write
  files.
- Failure mode: report exhausted queries and missing evidence instead of
  fabricating an answer.

## Verifier Specialist

- Input: target claims, supporting evidence, counterevidence, source quality,
  bounded local retrieval, and verification criteria.
- Output: verification decisions, conflicts, supersession candidates, evidence
  gaps, and confidence adjustments.
- Allowed tools: project retrieval, evidence inspection, approved verification
  searches.
- May not: erase conflicting history or mark a claim verified without evidence.
- Failure mode: retain `unverified`/`conflicting` state and request more
  evidence or human judgment.

## Knowledge Editor Specialist

- Input: target active artifact revisions, verified State, maintenance task,
  writing goal, and path/write policy.
- Output: typed `ChangeSetProposal` with complete after-content, evidence ids,
  base hashes, and unified diffs.
- Allowed tools: scoped retrieval and drafting only.
- May not: call external vendors directly, edit files, apply a ChangeSet,
  delete/move notes, or introduce unsupported facts.
- Failure mode: return a thin/unsupported draft error; do not persist fallback
  templates.

## Deterministic Vault Scanner

This is a service, not an LLM Agent.

- Input: imported managed vault notes.
- Output: `KnowledgeHealthReport` and deterministic findings.
- Detects: broken wikilinks, orphan notes, duplicate titles, missing front
  matter, missing evidence metadata, unresolved markers, paths, links, and
  hashes.
- Must be deterministic and idempotent for the same snapshot.
- May not: label a factual claim stale or false without an evidence-aware
  verifier.

## Context Pack Builder

- Input: State, active maintenance task, role, target paths, optional
  TaskMemory, and budget.
- Output: bounded `ContextPack` with goal, relevant artifacts, claims, evidence,
  findings, open questions, prior attempts, and filter notes.
- Excludes by default: hidden/rejected/superseded memories, inactive artifact
  revisions, raw HTML, unrelated notes, duplicate snippets, and noisy logs.
- Failure mode: trim lower-priority content and record exclusions.

## Unified Retrieval Service

- Input: project id, query, filters, role/task context, and limit.
- Output: ranked citation records with source id/type, parent id, title, path,
  hit-local snippet, score, verification metadata, and optional URL.
- Current V3 implementation: local lexical/vector hybrid retrieval shared by
  chat and Agent tools, using content-hash incremental embeddings and RRF.
- When embeddings fail, diagnostics must say `lexical_degraded`; lexical-only
  results must never be labeled hybrid.
- Must exclude superseded artifacts and preserve segment/span identity.

## ChangeSet Validator And Applier

- Input: ChangeSet, current active artifacts, AutonomyPolicy, and project root.
- Output: applied/conflicted/denied result plus new artifact revisions and audit
  events.
- Required checks: allowed operation/path, base hash, evidence for factual
  updates, file/byte budget, approval status, and active revision.
- Apply behavior: create immutable new revisions and persist predecessor links.
- Rollback behavior: reactivate or recreate the exact prior content and record a
  rollback event.
- May not: silently overwrite a hash conflict or execute delete/move in first
  V3.

## Artifact Writer And Reviewer

- Writers create Markdown through plain-text LLM completion, not JSON parsing.
- Review checks evidence linkage, note usefulness, link readiness, and task
  completion.
- Writer failure retries visibly and then fails; no successful fake template is
  saved.
- Active artifact revisions carry V3 schema/version metadata and content hashes.

## Human Review

The Agent must ask the user when:

- the requested change exceeds autonomy policy;
- an existing note update requires approval;
- a base-hash conflict shows the user changed the note;
- evidence conflicts require a value or interpretation judgment;
- delete/move or an external side effect is requested.

`POST /api/runs/{run_id}/resume` is the production continuation contract for a
`waiting_for_human` run. It accepts the typed `ResumeRequest`, persists supplied
inputs, restores the same run from its durable checkpoint, writes feedback into
`SectorBreakerState.human_feedback`, and exposes it in the next Master Agent
ContextPack. An assistant brief is additionally stored as a low-trust project
document and internalized; it is not promoted to verified evidence.

## Web Acquisition

- `SearchProvider` discovers candidate URLs; provider-side domain parameters
  are hints, so the Kernel applies a final canonical-host allow/block filter.
- The production `search_web` tool extracts at most three accepted pages per
  tool call through `ContentExtractionProvider`; each extraction failure is
  isolated and recorded in typed diagnostics.
- Readable extracted body and extraction provenance are persisted on Evidence
  and become available to the shared local retriever.
- `SourceVerificationProvider` assesses source class and quality only. A
  heuristic assessment may recommend at most `partially_verified`; it cannot
  mark a claim or Evidence item `verified` without corroboration.
- Search configuration updates preserve stored API keys when an omitted or
  blank secret field is submitted. Status exposes only provider names with a
  stored key, never the secret value.
- Source-pack domain entries use `available_via_domain_filter` and are not
  counted as configured connectors. Only the currently selected executable
  extraction adapter reports `ready`.

## Retired Contracts

Talent-demand, JD extraction, skill normalization, Boss job-source collection,
and enterprise Source Coverage contracts are retired. They must not remain in
production schemas, imports, API routes, tool registries, frontend modes, or
tests. Historical documentation may exist only under an explicit archive.

## Detailed Models

The canonical V3 data shapes, API routes, permissions, and acceptance gates are
defined in `docs/23-autonomous-knowledge-management-v3.md`.
