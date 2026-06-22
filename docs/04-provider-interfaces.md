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

When no search provider is configured, the product must show an explicit
unconfigured warning to the user. Silent fallback is not acceptable because
real-world web evidence is a core system dependency.

Required methods:

- `search(SearchQuery) -> list[SearchResult]`

Search results must include:

- title;
- url;
- snippet;
- published date when available;
- provider metadata.

Current real providers:

- Tavily
- Serper
- Brave Search API
- Exa

Upgrade direction:

- support multiple interchangeable providers behind the same boundary;
- allow provider routing or fallback without changing graph nodes;
- keep search discovery separate from page extraction and source verification.

Recommended follow-up interfaces are documented in
`docs/14-search-and-report-ingestion-design.md`:

- `ContentExtractionProvider`
- `ReportIngestionProvider`
- `SourceVerificationProvider`
- `CounterevidenceProvider`

These should be added as separate interfaces rather than overloading
`SearchProvider` with unrelated responsibilities.

## ContentExtractionProvider

Current baseline:

- `backend.app.providers.factory.build_content_extraction_provider()`
- default local fallback: `HttpContentExtractionProvider`
- optional configured providers:
  - `FirecrawlContentExtractionProvider`
  - `JinaReaderContentExtractionProvider`

Configuration:

- `CONTENT_EXTRACTION_PROVIDER` with values `http`, `firecrawl`, or `jina`
- `FIRECRAWL_API_KEY`
- `FIRECRAWL_ENDPOINT`
- `JINA_READER_ENDPOINT_PREFIX`

Required methods:

- `extract_url(url) -> ExtractedPage`

Current workflow usage:

- verification search results can be extracted into page text before source
  reassessment and evidence writeback;
- the extractor remains replaceable, so stronger page-processing providers can be
  swapped in without changing graph nodes.

## RetrievalProvider

V1 default: SQLite FTS.

Required methods:

- `search_project(project_id, query, limit)`

V2 upgrade target: embeddings plus vector retrieval through the same interface.

## Exporter

Required methods:

- `export_project(project, artifacts, evidence)`

Exporters must write a manifest containing export version, artifact list, source evidence list, and generated timestamp.
