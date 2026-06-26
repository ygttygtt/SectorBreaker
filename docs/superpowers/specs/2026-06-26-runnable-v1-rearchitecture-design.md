# Runnable V1 Rearchitecture Design

## Purpose

SectorBreaker V1 must become a product that can reliably run from a topic to an Obsidian-ready knowledge system. The current codebase contains useful parts, but the product path is too broad: workflow orchestration, multi-agent selection, search provider configuration, UI review states, exports, evidence verification, and chat all exist before the core loop is dependable.

This redesign keeps the useful wheels, but changes the center of gravity. V1 is not a report generator and not a complex agent workbench. V1 is a local-first domain knowledge system builder.

## Product Promise

Given a topic such as "Agent development", SectorBreaker creates a reusable Obsidian knowledge base that helps the user enter the domain faster:

- defines the domain boundary;
- gathers and records source material;
- extracts evidence, concepts, players, trends, problems, and opportunities;
- generates structured Markdown notes;
- preserves source links and unresolved questions for later updating.

The first successful version must complete this loop without manual recovery:

```text
Create project
-> collect sources
-> build evidence ledger
-> build knowledge system
-> export Obsidian vault
-> show readable results
```

## Non-Goals For This Rebuild Phase

- No complex agent auto-selection UI.
- No mandatory human confirmation gate.
- No run state stored only in frontend memory.
- No multi-provider setup surface beyond one primary search provider for the happy path.
- No claim that every market fact is fully verified.
- No workbench-style advanced editing before the basic run is stable.

These features can return later, but only after the V1 loop is dependable.

## Architecture Direction

The system should be organized around durable project state rather than transient workflow screens.

### Core Domain Objects

`Project`

The long-lived container for a domain knowledge system. A project can have many runs and many source documents.

`Run`

A single execution attempt. The frontend renders from backend run state, not from local phase guesses.

`RunSnapshot`

The API object that drives the UI:

```json
{
  "run_id": "string",
  "project_id": "string",
  "status": "idle|collecting|structuring|exporting|completed|failed",
  "current_stage": "string",
  "progress": {
    "current": 0,
    "total": 0
  },
  "events": [],
  "errors": [],
  "artifact_summary": [],
  "updated_at": "iso datetime"
}
```

`SourceDocument`

Raw source material from search, user upload, pasted notes, or assistant reports. This is the source inbox.

`EvidenceItem`

A structured claim or useful excerpt linked back to a source document. Evidence must include source metadata and verification status.

`KnowledgeNode`

A reusable piece of the knowledge system: concept, player, trend, problem, opportunity, question, or map relationship.

`KnowledgeSystem`

The structured output assembled from evidence and knowledge nodes.

`ObsidianExport`

The generated Markdown package and manifest.

### V1 Pipeline

V1 should use a simple explicit pipeline. It can reuse LangGraph internally if helpful, but the product contract should not expose a complex agent graph as the primary user experience.

```text
Stage 1: Project Intake
Normalize the topic, scope, depth, and source policy.

Stage 2: Source Collection
Use Tavily when configured, plus user-provided materials. Store every source as SourceDocument.

Stage 3: Evidence Building
Extract claims, definitions, entities, trends, and useful excerpts into EvidenceItem records.

Stage 4: Knowledge Structuring
Build the domain overview, learning path, concept map, player map, trend map, problem map, opportunities, and unresolved questions.

Stage 5: Obsidian Export
Write a stable Markdown vault layout and manifest.

Stage 6: Result Review
Show generated notes, source ledger, unresolved questions, and export path.
```

## Reuse Existing Wheels

### Keep And Reuse

- FastAPI app factory and route structure.
- SQLite repository and migrations where compatible.
- Existing Pydantic schemas for projects, evidence, artifacts, and documents.
- Tavily provider and provider factory.
- OpenAI-compatible LLM provider.
- Markdown exporter foundation.
- Current document upload foundation.
- Current evidence metadata fields.
- Existing frontend API client as a starting point.
- Existing frontend config panel only after it is simplified.

### Keep But Move Behind Simpler Contracts

- LangGraph workflow can remain as implementation detail, but the UI should consume `RunSnapshot`.
- Agent names can remain in logs, but they should not define the product state model.
- QA critic can become a final validation step that marks warnings and blockers in a stable result model.
- Search provider registry can stay in code, but V1 UI should emphasize the active provider rather than exposing every possible provider equally.

### Defer

- User-controlled agent selection.
- Complex human-confirm plan resume.
- Advanced workflow graph editing.
- Multi-provider aggregation as a required user-facing path.
- Full artifact drill-down editor.
- Continuous monitoring and weekly reports.

## Frontend Direction

The first screen should be the actual working tool, not a marketing landing page.

V1 UI should have three durable views:

`Project Start`

Fields:

- topic;
- optional market scope;
- source mode;
- primary search/LLM status;
- optional upload.

Primary action:

- start run.

`Run Console`

Driven entirely by backend `RunSnapshot`.

It shows:

- current stage;
- progress;
- live event log;
- source count;
- evidence count;
- warnings and errors;
- retry action when failed.

Refresh must restore this view for an active run.

`Knowledge Result`

It shows:

- generated Obsidian sections;
- source/evidence ledger;
- unresolved questions;
- export action/path;
- ability to start another run for the same project later.

## Backend Direction

The backend must own workflow truth.

Minimum required API shape:

```text
POST /api/projects
POST /api/projects/{project_id}/runs
GET  /api/projects/{project_id}/active-run
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/snapshot
GET  /api/runs/{run_id}/events
GET  /api/projects/{project_id}/knowledge-system
POST /api/projects/{project_id}/exports
```

Existing endpoints can remain, but the frontend should stop relying on local-only phase transitions.

## Error Handling

Every failure should produce a visible user result:

- LLM not configured: block before starting and explain which field is missing.
- Search not configured: allow user-materials-only mode, or block open-web mode with a clear message.
- LLM call fails: run status becomes `failed`, with stage, error message, and retry action.
- Export fails: keep generated knowledge visible and mark export as failed.
- SSE disconnects: frontend polls `RunSnapshot` and can reconnect.

White screen is never acceptable in V1.

## Obsidian Output Layout

V1 export should generate a small stable vault:

```text
00-领域总览.md
01-入门路线.md
02-核心概念.md
03-玩家与工具地图.md
04-趋势与证据.md
05-问题与机会.md
99-待验证问题.md
_sources/evidence-ledger.md
manifest.json
```

This is intentionally simple. More granular cards can be added later after the loop is reliable.

## Testing Strategy

V1 must have two acceptance paths.

The automated regression path uses fake providers so CI and local tests can run without paid keys:

```text
create project
-> run with fake LLM and fake search
-> completed status
-> evidence exists
-> knowledge system exists
-> export manifest exists
```

The product acceptance path must use real configured APIs before the rebuild is considered usable:

```text
load .env or saved runtime config
-> verify OpenAI-compatible LLM configuration
-> verify Tavily search configuration
-> create a real project with topic "Agent development"
-> run the full pipeline with real LLM calls and real Tavily search
-> complete without manual database edits or frontend refresh recovery
-> show generated knowledge sections in the UI
-> export an Obsidian vault with source links and evidence ledger
```

Fake providers prove the code path is deterministic. Real APIs prove the product works. V1 is not accepted unless both paths pass.

Additional required tests:

- frontend restores active run from backend snapshot;
- LLM failure produces failed run and visible error state;
- missing search config blocks open-web mode but allows user-materials-only mode;
- Obsidian export contains all required files.

## Migration Strategy

Do not delete existing modules first. Add the new V1 contract beside the current code, then move frontend usage to it. Once the V1 path is stable, old workflow screens and unused agent surfaces can be retired gradually.

Recommended order:

1. Add `RunSnapshot` backend contract.
2. Add a simple V1 pipeline facade around existing workflow pieces.
3. Add acceptance tests for the V1 loop.
4. Rebuild frontend around backend snapshots.
5. Simplify settings to one primary happy path.
6. Stabilize Obsidian export layout.
7. Remove or hide old workflow UI that no longer serves V1.

## Success Criteria

- A fresh user can configure Tavily and an OpenAI-compatible LLM, enter a topic, and get a completed Obsidian export.
- The final acceptance run uses real Tavily search and a real OpenAI-compatible LLM provider, not fake providers.
- Refreshing during a run does not lose the run.
- A failed run shows a recoverable error instead of a blank page.
- The result page always shows generated notes, evidence, and unresolved questions when the backend has produced them.
- The V1 loop is covered by automated fake-provider regression tests and a documented real-provider acceptance script.
