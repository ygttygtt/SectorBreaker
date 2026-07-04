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
- app version when available.
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
  "search_result_count": 0,
  "skill_signal_count": 0,
  "gaps": []
}
```
````

The UI may parse this block or use `source_coverage` run events to render the
coverage panel.
