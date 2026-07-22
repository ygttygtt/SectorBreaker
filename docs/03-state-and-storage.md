# State And Storage

## Principles

SQLite stores structured control-plane state and metadata. Markdown stores the
human-readable knowledge base. Runtime data, imported mirrors, indexes, and
exports are not committed.

The first V3 release treats imported source vaults as read-only inputs and
manages revisions in project storage/export. Direct synchronization is later
work.

## Core Entities

### ResearchProject

- id, title, domain, market scope, depth, source policy, status;
- typed source preferences: selected source-pack ids, custom allow/block
  domains, and `prefer` or `require` enforcement;
- one surviving knowledge-management product path;
- creation/update timestamps.

The historical `project_mode` database column may remain for migration
compatibility, but the public V3 contract has no enterprise mode selector.

### ResearchRun

- id, project id, status, current gate/step;
- checkpoint and completion metadata;
- run events and user inputs.

### EvidenceItem / EvidenceClaim

Evidence retains source channel, source quality, verification status, claim
strength, bias/conflict metadata, and artifact usage. Verified claims require
acceptable evidence.

Search Evidence also retains collection metadata: selected project source
packs, enforcement mode, effective allow/block domains, query, provider
request count, and whether a preferred-source fallback occurred.

### ProjectDocument / DocumentSegment

Uploaded reports and imported vault notes are stored as documents and segments
for retrieval. Imported vault documents preserve their relative Markdown path
in `file_name` and use channel `vault_note`.

### Artifact Revision

- id, project id, type, title, relative content path, content;
- evidence ids and schema version;
- revision number and content hash;
- active status;
- supersedes / superseded_by ids;
- originating run and ChangeSet ids;
- creation timestamp.

Artifact revisions are immutable. Retrieval and export use active revisions by
default.

### VaultImport

- id, project id, source path;
- note count and snapshot hash;
- created timestamp.

### KnowledgeHealthReport

- id, project/import ids and snapshot hash;
- metrics and typed findings JSON;
- generated timestamp.

### MaintenanceTask

- id, project id, finding ids, type, objective, target paths;
- priority, status, specialist, approval requirement;
- evidence requirements and ChangeSet reference;
- timestamps.

### ChangeSet

- id, project/task ids, status, summary, evidence ids;
- operations JSON including path, base hash, before/after content, and diff;
- approval/apply/rollback timestamps and actor.

## SectorBreakerState V3

V3 extends the current structured State with:

- meta context and adaptive knowledge schema;
- shared entities, claims, relationships, source memories, and open questions;
- working memory and decision log;
- ArtifactMemory for active and historical note revisions;
- current vault import and health snapshot refs;
- maintenance task refs and active objective;
- delegation log;
- AutonomyPolicy.

LLM calls receive a curated ContextPack, never the entire database, raw vault,
or event history.

## Checkpoint Rules

Resumable checkpoint types:

- `artifact_write`: durable artifact revision and matching State are available;
- `run_end_completed`: run completed with durable active artifacts.

Diagnostic/partial types:

- `run_end_partial`: useful work exists but completion was not reached;
- `run_end`: failed/blocked diagnostics only.

Default continuation loads only explicitly resumable checkpoints. It also loads
active project artifacts into runtime context before any revise operation.

Artifact persistence and the checkpoint that references it must share a safe
transaction boundary or be ordered artifact-first.

## Retrieval Indexing

The current evidence-only FTS and Python scans are replaced by one lexical
retrieval service covering:

- evidence;
- documents and segments;
- active artifacts / imported vault notes.

Index rows retain source type, parent id, relative path, content hash, and
active status. Superseded revisions are excluded or removed from the active
index.

The local vector index is derived data and records project/source/chunk ids,
model/version, dimension, vector bytes, content hash, active source metadata,
and indexed timestamp. Project synchronization removes stale/superseded chunks
and only re-embeds content whose hash or model identity changed.

## Migration Rules

- Existing enterprise talent projects are archived and normalized so removing
  the enum does not break row deserialization.
- Enterprise-only artifacts and Boss evidence are removed from active storage or
  exported by a one-time migration before cleanup.
- Historical migration files remain immutable.
- Breaking State/artifact changes require migration tests and version notes.

See `docs/23-autonomous-knowledge-management-v3.md` for full V3 contracts.
