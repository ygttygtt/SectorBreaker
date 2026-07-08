# Export Specification

## Goals

Exports must be useful without the app. A user should be able to open the generated folder in Obsidian or any Markdown editor and understand the research result.

## Export Formats

- Obsidian knowledge base folder.
- Plain Markdown folder with the same content and fewer Obsidian-specific links.

## Frontmatter

Each Markdown file should include:

```yaml
---
project: "<project title>"
artifact_type: "<type>"
schema_version: "1"
evidence_ids: []
tags: []
generated_at: "<ISO timestamp>"
---
```

## Required Sections

- `00-研究框架`
- `01-行业地图`
- `02-市场现状`
- `03-玩家与交易单位`
- `04-内容与渠道`
- `05-机会地图`
- `99-待验证问题`

## Evidence Links

Important claims should include evidence references using stable IDs. Obsidian exports may include backlinks such as `[[证据库#EV-001]]`.

## Manifest

Every export must include `manifest.json` with:

- export version;
- project id;
- generated timestamp;
- artifact paths;
- evidence ids;
- absolute `export_dir` for the local workbench open-folder action;
- app version when available.

## Default Obsidian Vault Configuration

The repository-root `.obsidian/` directory is the default Obsidian vault
configuration template. Each generated knowledge-base export must copy this
folder into the project export directory so the user's preferred Obsidian
plugins, core settings, and workspace defaults are available immediately after
opening the vault.

The `.obsidian/` template is export packaging metadata, not research evidence or
an Agent artifact. It should not be added to `artifact_paths`, evidence ledgers,
or generated claim metadata.

## V1 Rich Obsidian Knowledge Export

The runnable V1 path exports seven primary learning-oriented Markdown documents and a bounded set of Obsidian knowledge cards.

- Concept cards live under `concepts/`.
- Architecture cards live under `architectures/`.
- Tool cards live under `tools/`.
- Open-question cards live under `questions/`.
- Primary documents should use Obsidian wikilinks such as `[[RAG]]` when the structured knowledge base has a corresponding card.
- Card front matter uses `type: "knowledge_card"` while primary documents use `type: "main_artifact"`.
- Generated artifacts include `aliases`, `status`, `artifact_type`, `schema_version`, `evidence_ids`, and `tags` fields to support Obsidian Properties, graph exploration, and future retrieval.

V1 document generation includes a bounded review pass. The reviewer should not compress documents merely because wording is verbose; it should identify missing explanation, examples, evidence links, learning steps, Obsidian links, and unresolved questions. At most one expansion pass is allowed per primary document so the workflow remains predictable.

## V1.3 Talent Demand Obsidian Export

Talent-demand mode exports a dedicated vault layout without changing the V1.2
domain-knowledge layout.

```text
README.md
00-岗位需求总览.md
01-岗位画像与分层.md
02-技能需求矩阵.md
03-公司与行业分布.md
04-薪资与经验要求.md
05-学习路径与能力模型.md
06-作品集与项目要求.md
99-待验证问题.md
skills/
roles/
companies/
_sources/evidence-ledger.md
manifest.json
```

Talent-demand front matter includes `project_mode: "talent_demand"` in addition
to the shared export fields. Primary artifacts use schema version `talent-v1`.
Cards use schema version `talent-v1-card`.

The generated `README.md` is a talent-demand vault home page. It links to the
main documents, skill cards, role-level cards, company cards, evidence ledger,
and explains how to interpret sample limitations.

`00-岗位需求总览.md` includes a human-readable Source Coverage Matrix and a
machine-readable fenced JSON block:

````markdown
```json source_coverage
{
  "total_evidence": 0,
  "uploaded_jd_count": 0,
  "uploaded_report_count": 0,
  "boss_job_count": 0,
  "search_result_count": 0,
  "skill_signal_count": 0,
  "gaps": []
}
```
````

The UI may parse this block or use `source_coverage` run events to render the
coverage panel.

## V2 Agent Kernel Obsidian Export

The personal V2 Agent Kernel writes artifacts only after the LLM policy chooses
`write_layer_document` and the writing tool produces usable Markdown. Failed or
thin writing is not exported as a template.

V2 writing is section-based: the artifact writer asks the LLM to produce each
major section as plain Markdown through `LLMProvider.complete()`. It must not
ask the Markdown writer for JSON, and it must not parse Markdown through the
structured-output path. Long section calls should emit `artifact_writing`
heartbeat events so the UI can show that writing is still active.

Minimum V2 artifact shape:

```yaml
---
schema_version: "v2-agent-kernel"
artifact_type: "<artifact type>"
evidence_ids: []
status: "draft"
---
```

Recommended V2 vault layout:

```text
README.md
docs/
  01-本源与边界.md
  02-参与者生态.md
  03-运行机制.md
  ...
cards/
  concept-*.md
  tool-*.md
  player-*.md
  risk-*.md
  question-*.md
sources/
  evidence-ledger.md
.obsidian/
.sectorbreaker/
  project.json
  agent_state.json
  evidence_ledger.json
  trace_summary.json
  artifact_manifest.json
  open_questions.json
manifest.json
```

The Agent may create fewer or more files depending on State, but any completed
run must contain non-template Markdown, evidence metadata, and enough trace
events for the user to understand why each artifact was written.

V2.0 uses a two-tier document structure:

- main layer documents written by `write_layer_document` are exported under
  `docs/`;
- auxiliary explainers written by `write_explainer_card` are exported under
  `cards/`;
- `write_vault_index` may create a navigation artifact that links the main
  documents, cards, evidence ledger, and open questions.

Exporter behavior for V2 artifacts:

- generated artifacts may contain their own internal YAML front matter while
  they are in repository storage;
- exported Markdown must contain one clean outer YAML block generated by the
  exporter;
- therefore the exporter strips a leading inner front matter block before
  writing the artifact body to disk;
- exported V2 files must keep `schema_version: "v2-agent-kernel"` in the outer
  block and must not contain `EV-V1-*` / `ART-V1-*` identifiers.
