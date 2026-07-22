# Provider Interfaces

## Principle

External and replaceable capabilities live behind interfaces. API handlers,
Agent policies, specialists, and graph nodes do not call vendor SDKs directly.

## LLMProvider

Required behavior:

- plain-text completion for Markdown drafting;
- structured completion for Agent decisions, specialist results, and State
  deltas;
- bounded retries and clear error mapping;
- no secrets in logs or trace;
- OpenAI-compatible local or remote endpoints.

## SearchProvider

Required method:

```text
search(SearchQuery) -> list[SearchResult]
```

Current adapters include Tavily, Serper, Brave, Exa, Firecrawl, or a configured
aggregate. Aggregation runs providers concurrently, isolates individual
provider failures, deduplicates canonical URLs, and round-robins results so the
first provider cannot consume the full result budget. `SearchQuery` carries
allowed/blocked domains; Agent calls may add `preferred_domains` from a trusted
source pack. Search discovery remains separate from content extraction and
source verification.

## ContentExtractionProvider

Extracts readable content from already-discovered public URLs. Current adapters
may use local HTTP extraction, Firecrawl, or Jina Reader. It must return source
metadata and explicit failures.

See `docs/25-web-source-expansion-and-multi-agent-gap.md` for crawler selection,
source-pack execution states, and the boundary for future map/crawl support.

## RetrievalProvider

V3 has one project retrieval boundary used by both chat and Agent tools.

Required input:

- project id and query;
- source type/path filters;
- active maintenance task/role context;
- limit and diversity options.

Required output:

- source and parent ids;
- source type, title, and relative path;
- hit-local snippet;
- lexical/vector/fused score metadata;
- evidence quality and verification status;
- optional URL and content hash.

The V3 implementation is local hybrid retrieval. It indexes evidence, document
segments, and active artifacts; runs lexical and vector retrieval; fuses ranks
with RRF; and reports honest retrieval provenance.

## EmbeddingProvider

The local-first provider supports:

- batch embedding;
- model name/version and vector dimension;
- offline local models from a local cache after first acquisition;
- content-hash based incremental indexing;
- explicit unavailable status.

The first adapter uses FastEmbed with `BAAI/bge-small-zh-v1.5`; no Agent or API
contract depends directly on that library.

## VectorStoreProvider

Vector storage is a rebuildable derived index. SQLite and Markdown remain the
source of truth. Hybrid retrieval uses rank fusion rather than comparing raw
lexical and vector scores directly.

See `docs/24-local-hybrid-rag.md` for synchronization and degraded-mode rules.

## SourceVerificationProvider

Evaluates source quality, verification status, corroboration, conflict, and
counterevidence needs. It must not silently upgrade generated or marketing
content into verified fact support.

## Exporter

Exports active artifact revisions, evidence, health/backlog/ChangeSet metadata,
trace summary, and the default `.obsidian/` configuration. Superseded revisions
remain in storage/history but are excluded from the normal vault view.

## Removed Provider Boundary

`JobSourceProvider`, Boss CLI adapters, and recruitment-specific provider
configuration are retired and must not remain in production imports or API
routes.
