# Current Status And Handoff

## Purpose

This document tells future agents and teammates where the project stands, what to do next, what can be delegated safely, and which parts need architecture-level review.

Read this after `AGENTS.md`, `CLAUDE.md`, `docs/00-project-brief.md`, `docs/01-architecture.md`, and `docs/02-agent-contracts.md`.

## Current Implemented State

### Collaboration Foundation

- Root `AGENTS.md` exists.
- `CLAUDE.md` is adapted for Claude Code.
- `.claude/memory/` contains project memories.
- Architecture, Agent contracts, state/storage, provider interfaces, API contract, export spec, testing strategy, workflow, and roadmap docs exist.

### Backend Foundation

- Pydantic schemas exist for projects, evidence, artifacts, and research state.
- Provider interfaces exist for LLM, search, retrieval, and fake test providers.
- Tavily provider exists and is tested with fake HTTP.
- SQLite migrations exist for projects, evidence, FTS, and artifacts.
- Repository supports project creation, evidence storage, artifact storage, FTS search.

### Workflow And Export

- LangGraph is installed and used in a minimal deterministic workflow.
- Workflow produces evidence-linked research frame, industry map, and opportunity map.
- Markdown exporter writes an Obsidian-friendly package and `manifest.json`.

### API And Frontend

- FastAPI app factory exists with project, run, evidence, artifact, export, and chat endpoints.
- React/Vite workbench exists with the current name "破壁工作台".
- Frontend is still mostly static and not yet wired to the backend API.

## Verification Commands

Run these before claiming progress:

```bash
python -m pytest -q
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm audit --audit-level=high
```

Current known baseline:

- Python tests: 14 passing, 1 Starlette deprecation warning from FastAPI TestClient.
- Frontend tests: 1 passing.
- Frontend build: passing.
- npm audit high severity: 0 vulnerabilities.

## What Is Easy

These are suitable for regular teammates or lower-capability coding agents if they read the relevant docs first:

- Add React project creation form.
- Add typed API client for frontend.
- Render evidence and artifact lists from API responses.
- Improve Markdown export formatting.
- Add more fixture examples.
- Add small API endpoints that match `docs/05-api-contract.md`.
- Add frontend component tests.

## What Needs Strong Architecture Review

Do not hand these off without a clear task contract and review:

- Real `LLMProvider` implementation and structured output parsing.
- Research Planner prompts and output schemas.
- Tavily Search Scout query planning.
- Evidence Curator confidence and verification rules.
- QA Critic gate-blocking logic.
- LangGraph interrupt/resume/checkpoint design.
- Any change to `ResearchState`, Agent output schemas, export schema, or provider interfaces.

Why: these parts control hallucination risk, evidence integrity, workflow stability, and future upgrade safety.

## Recommended Next Steps

### Step 1: Real LLM Provider

Implement OpenAI-compatible `LLMProvider` using `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Keep tests deterministic with fake HTTP or fake provider fixtures.

### Step 2: Research Planner Agent

Replace the deterministic research-frame node with an LLM-backed planner that returns structured output. The output must include research sections, key questions, and coverage checklist items.

### Step 3: Search Scout And Evidence Curator

Wire Tavily into the graph through `SearchProvider`. Convert search results into `EvidenceItem` objects with confidence and verification status.

### Step 4: QA Critic Gate

Add a QA node that blocks export when important artifacts lack evidence references or contain unsupported claims.

### Step 5: Human Review

Add real LangGraph interrupt/resume behavior for gate review. The API should expose `waiting_for_human` state and a resume endpoint.

### Step 6: Frontend API Integration

Wire the workbench to backend endpoints: create project, start run, view artifacts, export, and chat.

### Step 7: Acceptance Examples

Run two end-to-end examples:

- China/local-market industry.
- Global or mixed-scope AI trend industry.

Use outputs to tighten prompts, evidence rules, and export structure.

## How To Read Project Progress

1. Check latest commits:

   ```bash
   git log --oneline -8
   ```

2. Check current working state:

   ```bash
   git status --short --branch
   ```

3. Read this file for current status.
4. Read docs for the subsystem you will touch.
5. Run the verification commands before and after changes.

## How To Sync Project Memory

When meaningful progress happens, update memory in the same commit:

1. Update this file with completed work and next steps.
2. Update `.claude/memory/current-progress-and-handoff.md` with the concise memory version.
3. Update `.claude/memory/MEMORY.md` if a new memory file is added.
4. Update `CLAUDE.md` if Claude Code onboarding changes.
5. Update `AGENTS.md` if cross-agent rules change.
6. Commit and push both remotes:

   ```bash
   git push origin main && git push gitee main
   ```

If one remote fails, report the exact failure and leave the commit local or pushed to the successful remote.
