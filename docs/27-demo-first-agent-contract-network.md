# Demo-First Agent Contract Network

## Product Promise

The live challenge path accepts an unprepared domain and, within a bounded
deadline, uses real configured providers to propose one evidence-linked Starter
Note. It is a demo-oriented goal inside the existing V3 Agent Kernel, not a
second product mode or a replacement for long-running knowledge maintenance.

The production entrypoint remains
`backend.app.agent_kernel.run_v2_agent_kernel_pipeline`. A challenge request is
typed State input to that owner.

## Live Challenge Contract

`LiveChallengeRequest` carries the domain, optional question, a 180-600 second
deadline, `starter_note` output, adaptive multi-Agent orchestration, source
policy, and propose-before-publish policy. When the question is omitted the
goal is to explain the domain boundary, core concepts, participants, mechanism,
one controversy or uncertainty, and useful follow-up questions.

The first deliverable is one 1,500-2,500 Chinese-character Markdown note with
at least two project-owned Evidence ids and source URLs. It is persisted as a
proposed ChangeSet. It is never silently applied.

## Agent Network Contracts

- `AgentManifest` is the stable identity/capability contract. It declares role,
  skills, tool allowlist, transport, concurrency, output schemas, and observed
  performance. A prompt cannot widen it.
- `AgentMission` is a durable, acyclic WorkOrder graph with at most six nodes.
- `WorkOrder` declares dependencies, required capabilities, scoped input,
  budget, deadline, acceptance criteria, assignment trace, and status.
- `AgentDeliverable` contains typed findings, claim checks, project Evidence
  ids, tool observations, actual budget, latency, and an output hash.
- `TaskSettlement` records acceptance, evidence gain, duplicate-work ratio,
  rework, budget efficiency, and capability-scoped reliability changes. It is
  local audit data, not money or a token.

Only accepted deliverables may be promoted into Master State or a ChangeSet.
Specialists never apply a ChangeSet or write the Vault.

## Planning And Scheduling

The Master creates a typed DAG from the live goal and available Agent
manifests. Code validates the graph; it does not hard-code a role parade.
Independent ready nodes may run concurrently. Dependent nodes wait for accepted
upstream deliverables.

Eligibility is fail-closed for capabilities, tools, source policy, transport,
concurrency, and remaining deadline/budget. Eligible candidates are ranked by:

```text
40% capability match
25% capability-specific historical acceptance
15% useful evidence gain
10% budget fit
10% latency fit
```

The complete eligibility and score trace is durable and user-visible.

## Specialist Runtime

Each Specialist receives an immutable scoped ContextPack and may execute at
most three decide/act/observe steps with its role tool allowlist and task
budget. It returns a typed deliverable; it does not share mutable Master State.
The runtime may retry a rejected deliverable once, then reassign or block.

The live demo registry contains foundation research, ecosystem research,
counterevidence verification, and knowledge editing capabilities. One research
manifest may use an A2A transport; unavailable remote work is visibly
reassigned to an eligible local manifest.

## A2A Boundary

The first adapter targets A2A 1.x Agent Card discovery and JSON-RPC task
delivery through the official Python SDK. Agent Card skills map to internal
capabilities; a WorkOrder is sent as structured task input; a returned Artifact
is parsed as an AgentDeliverable and revalidated locally. Push notifications,
all transports, remote write authority, and a general marketplace are out of
scope.

## Deadline And Failure Rules

- Default live deadline: 300 seconds.
- Below 90 seconds remaining, no optional WorkOrders may start.
- Provider timeouts, malformed structured output, and A2A errors become typed
  events. A configured backup may be tried once.
- The runtime may reduce scope to already accepted evidence, but must say what
  remains unresolved.
- If fewer than two readable, project-owned sources remain, the run blocks. It
  must not write template or unsupported Markdown.

## Public API

```text
GET  /api/demo/readiness
POST /api/projects/{project_id}/challenge-runs
GET  /api/runs/{run_id}/agent-mission
GET  /api/projects/{project_id}/agent-registry
```

Mission events use typed payloads for planning, offering, assignment,
Specialist action, delivery, acceptance/rework/reassignment, settlement, and
deadline adjustment. Existing run snapshot/SSE compatibility is retained.

## Acceptance

Unit and API tests use deterministic providers for regression only. Demo
readiness additionally requires real configured providers, a real A2A worker
when that transport is advertised, and ten diverse live challenges producing
valid proposed Starter Notes within 300 seconds. Existing V3 Vault lifecycle,
evidence ownership, version isolation, export, and rollback gates remain
mandatory.

## Operator Runbook

1. Configure independent `LLM_*` and `LLM_BACKUP_*` channels, at least two
   search keys with `SEARCH_PROVIDER_MODE=multi`, distinct primary/backup
   extraction providers, and the normal SQLite/export paths.
2. Start the remote worker with `python tools/demo_a2a_researcher.py`, then set
   `SECTORBREAKER_A2A_RESEARCHER_URL` to its base URL (normally
   `http://127.0.0.1:8011`).
3. Start the main API and run `python tools/demo_preflight.py`. The preflight
   performs real calls, including a real A2A Task/Artifact; it prints no keys.
4. Run `python tools/run_demo_release_gate.py --api-base-url http://127.0.0.1:8000`
   to execute and record the mandatory ten-domain live gate.
5. Only after both checks report `DEMO READY`, use the landing-page 5-minute challenge action.
6. At review, inspect one ClaimCheck and the source ledger, then click Approve
   and Apply. Export/rollback continue through the existing V3 control plane.

The focused deterministic regression suite validates contracts and fault paths
but is not release evidence. Demo Ready requires the separate ten-domain live
provider run; results must record domain, elapsed time, sources, failovers,
ChangeSet/apply/export/rollback, and failure category.
