# Agent Contracts

## Contract Rules

Every Agent must have a documented input model, output model, allowed tools, disallowed behavior, and failure mode. Agents must return structured data, not prose-only payloads.

## Shared Output Metadata

All Agent outputs that include factual claims must support:

- `claim_id`
- `evidence_ids`
- `confidence`
- `verification_status`
- `notes`

`verification_status` values:

- `verified`: supported by at least one acceptable source.
- `partially_verified`: supported but source quality or scope is limited.
- `unverified`: useful hypothesis, not safe as a fact.
- `conflicting`: sources disagree and need user review.

## Agent Contracts

### Research Planner

- Input: project configuration, user notes, market scope, depth.
- Output: research frame, key questions, learning path, coverage checklist.
- Must not: invent market facts.
- Failure mode: ask for missing scope only when project config cannot be normalized.

### Supervisor Agent

- Input: project config, source policy, user guidance, optional assistant brief/user material flags.
- Output: `SupervisorPlan` with intent summary, selected/skipped agents, verification plan, human review points, assumptions, risks, and success criteria.
- Must not: invent new agent IDs outside the registry or bypass QA.
- Failure mode: pause for intent clarification when the user goal is too ambiguous.

### Master Agent

- Input: `ResearchContext` containing project config, user intent, uploaded
  reports/materials, evidence ledger summary, rejected/filtered search results,
  run-local memory, and product mode.
- Output: `MasterAgentDecision`, `CoverageReport`, and bounded
  `ToolCallRequest` records. Decisions include `continue`, `search_again`,
  `ask_user`, `degrade`, and `block`.
- Allowed tools: provider/service interfaces only, including search, document
  ingestion/citation extraction, project retrieval/RAG, source verification,
  content extraction, and enterprise job-source provider when explicitly enabled
  in `talent_demand`.
- Must have state: it must know what has already been searched, which evidence
  was accepted or rejected, which uploaded reports exist, what new information
  was added, and which coverage gaps remain.
- Must not: use hard-coded evidence count as the primary sufficiency rule, call
  vendors directly, bypass source policy, hide zero-evidence states, or write
  final claims without evidence metadata.
- Failure mode: emit a readable decision and stop or ask for user input when the
  workflow lacks enough material to generate a credible knowledge base.
- V1.6 implementation note: the personal `domain_knowledge` path now implements
  the first bounded version with `RunWorkingMemory`, `SearchPlan`,
  `SearchIntent`, `ToolCallResult`, `CoverageReport`, and
  `MasterAgentDecision`. It can call the configured `SearchProvider`, ingest
  uploaded reports/documents/citations as evidence, loop through up to three
  source rounds, degrade visibly when thin evidence remains, and block on zero
  evidence. `ask_user` remains a documented decision target for a later
  human-in-the-loop upgrade.
- V2 state/memory note: the next implementation uses `SectorBreakerState`,
  `KnowledgeSchema`, `TaskMemory`, `ContextPack`, and `AgentDecision` from
  `backend/app/agent_state/`. The Master Agent should not pass the whole state
  to the LLM; it should request a task-specific `ContextPack`.

### Context Pack Builder

- Input: `SectorBreakerState`, active layer/task, optional `TaskMemory`.
- Output: `ContextPack` containing goal, active layer, coverage gaps, selected
  entity/claim summaries, selected evidence/source snippets, open questions,
  compressed working-memory reflection, included source ids, excluded source
  ids, and filter notes.
- Must not: include raw HTML, duplicate snippets, unrelated layers, noisy logs,
  long reports, or rejected sources by default.
- Failure mode: trim lower-priority evidence/claims to fit the configured
  context budget and record filter notes.

### External Report Internalizer

- Input: uploaded external AI report or user document.
- Output: low/medium-trust `SourceMemory`, `KnowledgeClaim`, `EntityRecord`,
  `OpenQuestion`, citation URLs, and state deltas.
- Must not: treat external AI report claims as verified facts.
- Failure mode: keep the raw report as source memory and mark extracted claims
  as unverified search leads.

### Specialist ReAct Agents

- Input: `ContextPack`, layer-specific mission, allowed tools, completion
  criteria, and local `TaskMemory`.
- Output: structured `StateDelta` with entity ids, claim ids, source memory ids,
  open question ids, notes, and stop reason.
- Must not: hand off only free-form prose, ignore discovered unknown terms, or
  judge completion by source count alone.
- Failure mode: stop by `max_steps`, summarize failed attempts, and ask the
  Master Agent to retry, degrade, or ask the user.

### Iceberg Risk Agent

- Input: domain, risk-surface text/search observations, source policy.
- Output: risk terms, warning signals, safe related queries, and L5 risk
  findings.
- Must not: output operational wrongdoing instructions, evasion steps, fraud
  playbooks, or abuse tutorials.
- Failure mode: redact operational details and keep only high-level risk,
  incentive, warning, and boundary information.

### Source Strategy Agent

- Input: `SupervisorPlan`, project source policy.
- Output: source scope for each agent and source-use explanation.
- Must not: upgrade weak sources into reliable sources.
- Failure mode: degrade to allowed user/system materials and record source gaps.

### Search Scout

- Input: search tasks, market scope, language preference, source constraints.
- Output: source candidates with title, url, snippet, provider metadata.
- Must not: scrape restricted sources or summarize as final evidence.
- Failure mode: return empty result with query diagnostics. In the V1
  domain-knowledge path, topic filtering must not require an exact Chinese full
  phrase match; generic Chinese topics should use domain-neutral relevance
  markers and emit a degraded event when evidence remains thin. After all
  allowed collection attempts, zero usable evidence is blocking: emit
  `node_blocked` and stop before downstream knowledge generation.

### Assistant Brief Agent

- Input: user-pasted Markdown/text from Gemini, Kimi, Qwen, DeepSeek, or similar external research tools.
- Output: low-trust `EvidenceItem` records with extracted claims and leads.
- Must not: treat an assistant brief as a verified factual source.
- Failure mode: store the raw brief as unverified user-provided lead material.

### Evidence Curator

- Input: source candidates and extracted snippets.
- Output: normalized evidence items, evidence claims, source quality, claim strength, bias risk, verification status, and counterevidence flags.
- Must not: upgrade low-quality snippets into verified claims.
- Failure mode: mark source as unusable with reason.

### Counterevidence Agent

- Input: critical claims from weak, conflicting, or assistant-brief sources.
- Output: counterevidence tasks, conflicting evidence links, and verification downgrade notes.
- Must not: erase claims; it marks status and required checks.
- Failure mode: mark unresolved claims as `unverified`.

### Knowledge Mapper

- Input: verified and partial evidence, research frame.
- Output: industry map, knowledge cards, node relationships, unresolved questions.
- Must not: hide unknowns.
- Failure mode: return missing coverage list. If LLM generation fails or source
  coverage is zero, return a clearly labeled `待补证草稿` scaffold for the
  requested topic and emit a degraded event rather than reusing an unrelated
  domain template.

### Opportunity Analyst

- Input: knowledge map, pain points, market/player/content evidence.
- Output: opportunity hypotheses, target users, logic, entry barriers, risks, first validation actions.
- Must not: present hypotheses as guaranteed opportunities.
- Failure mode: mark insufficient evidence and request more sources.

### QA Critic

- Input: any gate output.
- Output: `QAReport` with pass/fail, blocking issues, retry tasks, user action needed, and whether warning-only continuation is possible.
- Must not: rewrite final artifacts directly.
- Failure mode: fail closed when evidence references are missing.

### Export Writer

- Input: approved artifacts and export spec version.
- Output: Markdown files, Obsidian links, export manifest.
- Must not: generate new facts during export.
- Failure mode: stop export and report invalid artifact schema.

### V2 Agent Kernel

- Input: `SectorBreakerState`, available `ToolSpec` registry, recent
  `KernelTraceEvent` tail, run budgets, uploaded report/material state, and
  provider-backed search/LLM/repository services.
- Output: `AgentDecision`, `KernelObservation`, `KernelStateDelta`,
  `KernelTraceEvent`, and completed `Artifact` records with
  `schema_version="v2-agent-kernel"`.
- Allowed actions: `call_tool`, `write_artifact`, `review_artifact`,
  `ask_user`, `finish`, and `block`.
- Must not: traverse L1-L5 as a hard-coded production workflow, silently
  substitute fallback Markdown, persist partial artifacts after a failed run, or
  finish when no artifact exists.
- Failure mode: if `write_layer_document` fails or returns thin output, retry
  the LLM writing call up to three times. If still unusable, emit visible
  `artifact_writing` error events, return `artifact_writing_failed`, mark the
  run failed, and wait for user/config/material correction instead of exporting
  a fake template.

### Talent Source Scout

- Input: project config, uploaded project documents, existing evidence, optional search provider.
- Output: evidence items from uploaded JD/user materials, external assistant briefs, and supplemental search results.
- Must not: scrape login-gated job boards or bypass anti-bot controls.
- Failure mode: continue with uploaded/local evidence and mark source coverage gaps.

### Boss Job Source Scout

- Input: `JobSourceQuery`, configured `JobSourceProvider`, talent-demand project config.
- Output: `boss_job` channel evidence items derived from structured job postings.
- Must not: require Boss collection for the personal `domain_knowledge` path, bypass login/anti-bot mechanisms, or fabricate samples when the local provider is unavailable.
- Failure mode: emit a degraded run event with provider diagnostics and continue through uploaded materials / external reports / generic search.

### JD Extractor

- Input: evidence text and evidence ids.
- Output: `JobPostingSignal` records containing title, company, location, salary text, experience text, education text, responsibilities, skills, tools, seniority, evidence ids, and confidence.
- Must not: infer salary, seniority, company, or experience when the evidence does not contain a signal.
- Failure mode: emit conservative partial signals with missing fields left empty.

### Skill Normalizer

- Input: `JobPostingSignal` records.
- Output: `SkillDemandItem` matrix with canonical names, aliases, categories, frequency, seniority distribution, and representative evidence ids.
- Must not: call external taxonomies unless an adapter is explicitly configured.
- Failure mode: use local alias rules and mark future taxonomy enrichment as unavailable.

### Source Coverage Agent

- Input: evidence items and extracted job-posting signals.
- Output: `SourceCoverageMatrix` with source-channel counts, salary/experience/skill signal counts, weak-source counts, and gap ids.
- Must not: treat gaps as fatal unless the product path explicitly requires blocking.
- Failure mode: emit warning-level gaps such as `low_sample`, `no_salary_signal`, `no_experience_signal`, or `search_only_evidence`.

### Talent Analyst

- Input: postings, skill matrix, source coverage, evidence summary, and project purpose.
- Output: `TalentDemandKnowledgeBase` including overview, role levels, company/industry patterns, salary/experience notes, learning path, portfolio requirements, unresolved questions, and source coverage.
- Must not: turn unsupported salary/market claims into facts.
- Failure mode: deterministic fallback builds a usable but clearly limited knowledge base.

### Project RAG Answerer

- Input: project question and retrieved evidence/document/artifact snippets.
- Output: answer text plus citation ids and citation details.
- Must not: answer beyond retrieved project context without saying the project lacks evidence.
- Failure mode: when LLM is unavailable or fails, return a deterministic evidence summary with citations.
