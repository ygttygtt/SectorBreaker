# Current Status And Handoff

## Purpose

This document tells future agents and teammates where the project stands, what to do next, what can be delegated safely, and which parts need architecture-level review.

Read this after `AGENTS.md`, `CLAUDE.md`, `docs/00-project-brief.md`, `docs/01-architecture.md`, and `docs/02-agent-contracts.md`.
For Cursor, Windsurf, Gemini, Codex, Claude Code, or other tools, also read `docs/11-tooling-handoff.md`.

## Current Implemented State

### Collaboration Foundation

- Root `AGENTS.md` exists.
- `CLAUDE.md` is adapted for Claude Code.
- `.claude/memory/` contains project memories.
- Architecture, Agent contracts, state/storage, provider interfaces, API contract, export spec, testing strategy, workflow, and roadmap docs exist.
- 交接与记忆文件已同步到当前的多 Agent 协作状态。

### Backend Foundation

- Pydantic schemas exist for projects, evidence, artifacts, and research state.
- Project creation now includes `source_policy`.
- Supervisor planning schemas exist: `SupervisorPlan`, `AgentTask`, `VerificationPlan`, `QAReport`, and workflow definition nodes/edges.
- Provider interfaces exist for LLM, search, retrieval, and fake test providers.
- OpenAI-compatible LLM provider exists and is created from environment variables when configured.
- Provider factory returns `None` by default when no real credentials are configured, so tests and local demos stay deterministic.
- Tavily provider exists and is tested with fake HTTP.
- SQLite migrations exist for projects, evidence, FTS, and artifacts.
- Evidence Ledger fields now store source channel, source policy, claims, source quality, claim strength, bias risk, counterevidence flags, and artifact usage.
- Repository supports project creation, evidence storage, artifact storage, FTS search.
- Repository supports project listing and detail lookup.

### Workflow And Export

- LangGraph workflow now includes Scope, Supervisor Plan, Source Strategy, Source Intake, Claim Extractor, Counterevidence, Evidence Ledger, Business Analysis fan-out, QA Critic, Export, and RAG Indexer gates.
- Runs pause at `supervisor_plan` for user confirmation unless `auto_run=true`.
- Assistant briefs are optional manual Markdown/text inputs and are treated as low-trust lead material.
- Workflow can use injected search and LLM providers.
- Workflow produces evidence-linked research frame, industry map, market overview, player map, content/channel map, and opportunity map.
- QA Critic emits structured `QAReport` and blocks missing coverage, missing evidence references, weak-source misuse, and unverified counterevidence needs.
- Markdown exporter writes an Obsidian-friendly package and `manifest.json`.

### API And Frontend

- FastAPI app factory exists with project create/list/detail, run, evidence, artifact, export, and chat endpoints.
- API exposes `/api/projects/{project_id}/workflow-definition` and `/api/runs/{run_id}/workflow-definition`.
- SSE emits node-level progress, degraded, blocked, completed, evidence, and claim events.
- Module-level ASGI app exists at `backend.app.api.app:app`.
- React/Vite workbench has been rebuilt around a real workflow graph, source policy selection, optional assistant brief input, Supervisor Plan review, live node status, event stream, elapsed time, QA blocking view, evidence/artifact rendering, chat, export, and vertical graph centering.
- Vite proxies `/api` to `http://127.0.0.1:8000`.

## Verification Commands

Run these before claiming progress:

```bash
python -m pytest -q
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm audit --audit-level=high
```

Current known baseline:

- Python tests: 23 passing, 1 Starlette deprecation warning from FastAPI TestClient.
- Frontend tests: 3 passing.
- Frontend build: passing.
- npm audit high severity: 0 vulnerabilities.

## What Is Easy

These are suitable for regular teammates or lower-capability coding agents if they read the relevant docs first:

- Add editable React project creation form.
- Extract typed API client from `frontend/src/App.tsx`.
- Add artifact detail viewer and richer evidence filters.
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

### Step 1: Planner And Agent Output Hardening

Replace remaining raw `dict` LLM outputs in business agents with dedicated Pydantic output schemas.

### Step 2: Search Scout And Evidence Curator

Enhance Tavily query planning, reliable-source packs, source-quality rules, and real counterevidence search.

### Step 3: QA Critic Gate

Current QA blocks structural and weak-source issues. Next, add unsupported-claim detection inside generated artifact prose and automatic retry suggestions.

### Step 4: Human Review

Human review exists for Supervisor Plan confirmation. Next, add richer decisions such as "degrade and continue" for unresolved low-trust claims.

### Step 5: Frontend Productization

Add artifact detail viewer, evidence filters, source policy editing before run, and workflow node detail drill-down backed by real run state.

### Step 6: Acceptance Examples

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
2. Update `docs/11-tooling-handoff.md` when cross-tool onboarding or baseline changes.
3. Update `.claude/memory/current-progress-and-handoff.md` with the concise memory version.
4. Update `.claude/memory/tooling-handoff.md` when cross-tool onboarding or baseline changes.
5. Update `.claude/memory/MEMORY.md` if a new memory file is added.
6. Update `CLAUDE.md` if Claude Code onboarding changes.
7. Update `AGENTS.md` if cross-agent rules change.
8. Commit and push both remotes:

   ```bash
   git push origin main && git push gitee main
   ```

If one remote fails, report the exact failure and leave the commit local or pushed to the successful remote.
