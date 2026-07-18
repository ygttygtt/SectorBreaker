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

Current adapters may include Tavily, Serper, Brave, Exa, or a configured
aggregate. Search discovery remains separate from content extraction and source
verification.

## ContentExtractionProvider

Extracts readable content from already-discovered public URLs. Current adapters
may use local HTTP extraction, Firecrawl, or Jina Reader. It must return source
metadata and explicit failures.

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

The first V3 implementation is local lexical retrieval. It must index evidence,
document segments, and active artifacts. It replaces the separate chat-side and
Kernel-side keyword implementations.

## EmbeddingProvider (Later)

The optional local-first upgrade supports:

- batch embedding;
- model name/version and vector dimension;
- offline local models where configured;
- content-hash based incremental indexing;
- explicit unavailable status.

No Agent or API contract may depend directly on a specific embedding library.

## VectorStoreProvider (Later)

Vector storage is a rebuildable derived index. SQLite and Markdown remain the
source of truth. Hybrid retrieval uses rank fusion rather than comparing raw
lexical and vector scores directly.

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
