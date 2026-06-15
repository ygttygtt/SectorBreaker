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
