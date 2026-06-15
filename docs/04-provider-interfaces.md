# Provider Interfaces

## Principle

External services must be replaceable. Graph nodes and API handlers should depend on interfaces, not vendor SDKs.

## LLMProvider

V1 default: OpenAI-compatible chat completion endpoint, created by
`backend.app.providers.factory.build_llm_provider()` when all required
environment variables exist.

Configuration:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

Required behavior:

- structured output support;
- no API keys in logs.

Upgrade target:

- retry with bounded attempts;
- clear provider error mapping;
- schema-specific validation models instead of raw `dict`.

## SearchProvider

V1 default: Tavily, created by `build_search_provider()` when `TAVILY_API_KEY`
exists.

Required methods:

- `search(SearchQuery) -> list[SearchResult]`

Search results must include:

- title;
- url;
- snippet;
- published date when available;
- provider metadata.

## RetrievalProvider

V1 default: SQLite FTS.

Required methods:

- `search_project(project_id, query, limit)`

V2 upgrade target: embeddings plus vector retrieval through the same interface.

## Exporter

Required methods:

- `export_project(project, artifacts, evidence)`

Exporters must write a manifest containing export version, artifact list, source evidence list, and generated timestamp.
