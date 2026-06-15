# Provider Interfaces

## Principle

External services must be replaceable. Graph nodes and API handlers should depend on interfaces, not vendor SDKs.

## LLMProvider

Default: OpenAI-compatible chat completion endpoint.

Configuration:

- `base_url`
- `api_key`
- `model`
- `temperature`
- `timeout_seconds`

Required behavior:

- structured output support;
- retry with bounded attempts;
- clear error mapping;
- no API keys in logs.

## SearchProvider

Default: Tavily.

Required methods:

- `search(query, market_scope, max_results)`
- `get_provider_name()`

Search results must include:

- title;
- url;
- snippet;
- published date when available;
- provider metadata.

## RetrievalProvider

V1 default: SQLite FTS.

Required methods:

- `index_project_artifact(project_id, artifact)`
- `search_project(project_id, query, limit)`

V2 upgrade target: embeddings plus vector retrieval through the same interface.

## Exporter

Required methods:

- `export_obsidian(project_id, artifacts, evidence)`
- `export_markdown(project_id, artifacts, evidence)`

Exporters must write a manifest containing export version, artifact list, source evidence list, and generated timestamp.

