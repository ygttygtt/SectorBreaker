# Export Specification

## Goal

An export is a usable Obsidian/Markdown knowledge base, not a report package.
It contains only active knowledge revisions plus enough evidence and control
metadata to understand how the vault evolved.

## V3 Layout

```text
README.md
docs/
cards/
followups/
sources/
  evidence-ledger.md
.obsidian/
.sectorbreaker/
  project.json
  agent_state.json
  evidence_ledger.json
  artifact_manifest.json
  health_snapshot.json
  maintenance_backlog.json
  change_sets.json
  open_questions.json
  trace_summary.json
manifest.json
```

Imported vault relative paths are preserved where safe. Generated main notes and
cards use the established `docs/` and `cards/` structure unless a ChangeSet
targets an imported note path.

## Front Matter

Active V3 notes include one clean outer front matter block:

```yaml
---
project: "<title>"
artifact_id: "ART-..."
artifact_type: "<type>"
schema_version: "v3-knowledge-ops"
revision: 2
content_hash: "sha256:..."
status: "active"
evidence_ids: []
tags: []
generated_at: "<ISO timestamp>"
---
```

The exporter strips any nested leading front matter from stored generated
content. Imported user content keeps its meaningful properties without
duplicating the outer version metadata.

## Active Revision Rule

- Normal export writes only active artifacts.
- Superseded revisions remain in SQLite and ChangeSet history.
- README, manifest, retrieval, indexes, and evidence usage must reference the
  active revision.
- No two active artifacts may write the same relative path.

## Evidence Links

Important factual changes retain stable evidence ids. Artifact-to-artifact
citations should resolve back to original evidence where possible. Unsupported,
conflicting, and unresolved material is labeled rather than silently promoted.

## Manifest

`manifest.json` includes:

- export/schema version;
- project id and generated timestamp;
- absolute export directory;
- active artifact paths and ids;
- active content hashes/revisions;
- evidence ids;
- latest health snapshot id;
- maintenance task and ChangeSet summary;
- app version when available.

## Default Obsidian Configuration

The repository-root `.obsidian/` folder remains the default vault configuration
template and is copied into exports. It is packaging metadata, not research
evidence or an Agent artifact.

## Recovery Metadata

`agent_state.json` must contain the full serializable State needed for V3
inspection/re-import, subject to secret exclusion. It may not be only a count
summary. ChangeSets record before/after hashes and diffs; rollback history must
be visible in `.sectorbreaker/change_sets.json`.

## Retired Export

Talent-demand layouts, `talent-v1` schemas, skill/company/role matrices, and
Source Coverage blocks are removed from the active exporter.
