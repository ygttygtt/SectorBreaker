# V1 Domain Knowledge Base Design

## Goal

SectorBreaker V1.1 focuses on one useful product promise: turn a陌生领域 topic into a maintainable Obsidian knowledge base. It intentionally excludes competitor revenue analysis and content ecosystem scraping from the main path.

## Scope

The first useful loop contains:

- Search and evidence collection.
- Structured domain database construction.
- Knowledge map generation from that database.
- Obsidian export with rich, evidence-linked Markdown.

Out of scope for this version:

- Competitor business model and revenue structure.
- Video/social content ecosystem crawling.
- Full multi-agent orchestration through the old LangGraph business workflow.

## Backend Shape

The V1 pipeline should no longer treat Markdown as the primary intermediate output. It should build a structured `DomainKnowledgeBase` first, with these sections:

- `overview`: field boundary, current maturity, and how to read the knowledge base.
- `concepts`: terms, definitions, why they matter, related concepts, evidence IDs.
- `architectures`: mainstream patterns, use cases, strengths, limitations, evidence IDs.
- `tools`: frameworks/platforms/libraries, category, use case, tradeoffs, evidence IDs.
- `trends`: current shifts and evidence-backed signals.
- `learning_path`: ordered learning steps with expected outcome.
- `open_questions`: questions that need more evidence.

Markdown artifacts are views over this database:

- `00-领域总览.md`
- `01-入门路线.md`
- `02-核心概念.md`
- `03-主流架构.md`
- `04-工具与框架.md`
- `05-趋势与问题.md`
- `99-待验证问题.md`

Each artifact should contain enough standalone content to be useful in Obsidian and should include evidence references where claims depend on sources.

## Quality Bar

A generated knowledge base is acceptable only if:

- At least three concept cards exist.
- At least two architecture cards exist.
- At least two tool/framework entries exist.
- The learning path has at least four steps.
- Exported Markdown has explanatory sections, not only one-line placeholders.
- Missing evidence is explicit and marked as待验证 instead of silently hallucinated.

## Incremental Strategy

Keep the existing runnable V1 path and improve the generation layer behind it. If the LLM returns incomplete structured output, merge it with evidence-derived fallback data so the run still completes with usable content.
