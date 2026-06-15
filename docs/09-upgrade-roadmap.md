# Upgrade Roadmap

## V1 Foundation

- Adaptive research workflow.
- Evidence-linked outputs.
- Obsidian and Markdown export.
- SQLite metadata and FTS project Q&A.
- Tavily default search provider.
- OpenAI-compatible LLM provider.

## V2 Retrieval And RAG

- Embedding provider interface.
- Vector store provider.
- Hybrid FTS + vector retrieval.
- Citation-aware answer generation.
- Source re-ranking and deduplication.

## V3 Monitoring And Reports

- Scheduled source checks.
- Weekly industry reports.
- Competitor and content monitoring.
- Change detection.
- Opportunity watchlist.

## V4 Collaboration

- Users and roles.
- Project sharing.
- Review comments.
- Team workspaces.
- Deployment and backup strategy.

## Upgrade Rules

New capabilities should attach through versioned interfaces and migrations. Do not rewrite the core graph to add a provider, exporter, or retrieval backend.
