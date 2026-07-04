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

### Source Strategy Agent

- Input: `SupervisorPlan`, project source policy.
- Output: source scope for each agent and source-use explanation.
- Must not: upgrade weak sources into reliable sources.
- Failure mode: degrade to allowed user/system materials and record source gaps.

### Search Scout

- Input: search tasks, market scope, language preference, source constraints.
- Output: source candidates with title, url, snippet, provider metadata.
- Must not: scrape restricted sources or summarize as final evidence.
- Failure mode: return empty result with query diagnostics.

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
- Failure mode: return missing coverage list.

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

### Talent Source Scout

- Input: project config, uploaded project documents, existing evidence, optional search provider.
- Output: evidence items from uploaded JD/user materials, external assistant briefs, and supplemental search results.
- Must not: scrape login-gated job boards or bypass anti-bot controls.
- Failure mode: continue with uploaded/local evidence and mark source coverage gaps.

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
