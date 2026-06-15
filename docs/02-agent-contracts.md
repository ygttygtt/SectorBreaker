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

### Search Scout

- Input: search tasks, market scope, language preference, source constraints.
- Output: source candidates with title, url, snippet, provider metadata.
- Must not: scrape restricted sources or summarize as final evidence.
- Failure mode: return empty result with query diagnostics.

### Evidence Curator

- Input: source candidates and extracted snippets.
- Output: normalized evidence items, confidence, source type, scope notes.
- Must not: upgrade low-quality snippets into verified claims.
- Failure mode: mark source as unusable with reason.

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
- Output: pass/fail, blocking issues, suggested retries.
- Must not: rewrite final artifacts directly.
- Failure mode: fail closed when evidence references are missing.

### Export Writer

- Input: approved artifacts and export spec version.
- Output: Markdown files, Obsidian links, export manifest.
- Must not: generate new facts during export.
- Failure mode: stop export and report invalid artifact schema.
