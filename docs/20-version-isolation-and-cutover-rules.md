# Version Isolation And Cutover Rules

## Purpose

This document records the non-negotiable version-isolation rules created after
the V2 Agent Kernel cutover incident. The incident was not a normal bug. It was
an architecture-boundary failure: old fixed-workflow code remained reachable
while the product promise had already moved to a stateful ReAct Agent Kernel.

Future agents must treat this as project memory, not as optional background.

## What Went Wrong

The repeated old-link leakage happened because several risks compounded:

- new Agent code was implemented beside old workflow code instead of being cut
  over behind one clear production entrypoint;
- historical V1/V2 modules stayed in the production package namespace long
  enough to be imported, tested, patched, or accidentally reasoned around;
- frontend graph/state assumptions drifted from backend execution truth;
- isolated tests passed while the actual UI/API/export path still produced old
  events or template artifacts;
- stale local backend processes could keep serving old code even after files had
  changed.

The lesson is strict: architecture rewrites must isolate versions first. Do not
do a major Agent rewrite by gradually patching the old executable spine.

## Why This Project Hit The Failure Hard

This was not caused by a normal feature iteration. Earlier iterations mostly
expanded behavior inside the existing architecture. The V2 Agent Kernel work was
different: it changed the architectural center of gravity from a fixed workflow
to a stateful LLM-controlled Agent loop.

That kind of rewrite fails if the old architecture remains executable. AI coding
agents are especially vulnerable to this because they optimize locally around
visible imports, nearby tests, and existing file names. If old files remain in
the production namespace, an agent can accidentally improve or defend the old
path while believing it is improving the new system.

The project therefore needs an explicit cutover discipline:

- isolate or delete old executable code before expanding the new architecture;
- make the production route point to one owner;
- verify the real user path, not only unit tests;
- record the incident in project memory so future agents do not rediscover it
  through another expensive debugging loop.

## Non-Negotiable Rules

1. Production product modes must have exactly one executable owner.
   For personal `domain_knowledge` auto-run, that owner is the V2 Agent Kernel.

2. Old executable workflow code must be deleted or moved outside production
   imports before a new architecture is considered active.

3. Historical code may exist only as documentation or as an explicitly archived
   reference that production code cannot import.

4. Do not keep old workflow modules in `backend/app/` and rely on runtime
   guards to stop them. Runtime guards are smoke alarms, not architecture.

5. Frontend workflow graphs must come from backend workflow definitions. The
   frontend may render and summarize events, but it must not invent the
   production flow.

6. Unit tests are not acceptance for research-output architecture. Before
   claiming an Agent cutover is ready, run one real end-to-end project through
   the same API/UI path the user will use and inspect exported Markdown.

7. If three or more fixes fail around the same behavior, stop patching and
   question the architecture boundary. Repeated leakage means the old path is
   still structurally reachable.

8. Long-running local development must use a clean-start script or an explicit
   port/process check. "Code changed" does not prove the browser is connected to
   the changed backend process.

## Required Cutover Checklist

Before merging or reporting a new Agent architecture as ready:

- confirm the product-mode API route calls the intended new entrypoint directly;
- scan production code for imports of archived workflow modules;
- scan production events and exported artifacts for legacy markers;
- run the smallest relevant regression tests;
- run one real end-to-end project with configured providers when the change
  affects Agent behavior or output quality;
- inspect exported files for schema/version/evidence markers and real content;
- update `docs/10-current-status-and-handoff.md`,
  `docs/11-tooling-handoff.md`, and `.claude/memory/`.

## Current SectorBreaker Rule

Personal `domain_knowledge` auto-run must not execute or import legacy V1/V2
workflow paths. It should use:

```text
backend.app.agent_kernel.run_v2_agent_kernel_pipeline
```

The expected user-facing event vocabulary is:

```text
Thought Summary
Action
Observation
State Update
Decision
artifact_writing
artifact_review
```

The following markers are forbidden in current personal Agent Kernel runs and
exports:

```text
Knowledge Builder
Document Writer
specialist_react_loop
EV-V1-
ART-V1-
已使用保底
```

If these markers appear in a new personal auto-run, treat it as an architecture
regression, not a cosmetic bug.
