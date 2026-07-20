# Local Hybrid RAG

## Decision

SectorBreaker V3 retrieval is a real local hybrid RAG system. Lexical search is
retained, but it is no longer the only retrieval signal.

The production retrieval path is:

```text
active project sources
  -> content-hash incremental local embedding index
  -> lexical candidates + vector candidates
  -> reciprocal-rank fusion
  -> typed citations with retrieval provenance
  -> LLM answer / Agent ContextPack
```

If the configured local embedding runtime or model is unavailable, retrieval
must report `lexical_degraded`; it must not label keyword-only results as
hybrid or semantic.

## Provider Contract

`EmbeddingProvider` exposes provider/model identity, vector dimension,
synchronous local batch embedding, normalized float vectors, and explicit
availability/load errors.

The first production adapter uses FastEmbed with the Chinese-capable local
model `BAAI/bge-small-zh-v1.5`. Model files live in the configured local cache
and are never committed. Tests may use a deterministic fake provider to verify
indexing and fusion, but fake embeddings are not product acceptance.

## Vector Index

SQLite stores a rebuildable derived index with:

- project id;
- stable source/chunk id and parent id;
- source type, title, relative path, URL, and verification status;
- source content hash;
- embedding provider/model/dimension;
- vector bytes and indexed timestamp.

Indexable sources are evidence excerpts/summaries, uploaded/imported document
segments, and chunks from active artifacts/Vault notes. Superseded artifacts
and deleted sources are removed during synchronization. Changed content is
re-embedded only when its content hash or model identity changes. Metadata-only
changes refresh citation fields without re-embedding. Force rebuilds publish in
one SQLite transaction, so a failed model load never destroys the prior index.

## Retrieval And Fusion

The shared `ProjectRetriever` performs lexical retrieval, vector retrieval,
reciprocal-rank fusion (RRF), source-id deduplication, and result diversity.
Every citation reports retrieval mode, lexical/vector ranks, fused score,
embedding model, path/hash/verification metadata, and a hit-local snippet.
Document segments retain their parent id and only the best segment per parent
occupies the vector candidate list.

Both project chat and Agent retrieval tools use this same service and index.

## Configuration And API

```text
SECTORBREAKER_EMBEDDING_PROVIDER=auto|fastembed|disabled
SECTORBREAKER_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
SECTORBREAKER_EMBEDDING_CACHE_DIR=<local path>
SECTORBREAKER_EMBEDDING_THREADS=<positive integer>
```

When no cache path is supplied, the model is persisted under
`~/.cache/sectorbreaker/fastembed`; it is not downloaded into the project or
committed to source control.

```text
GET  /api/config/retrieval
POST /api/projects/{project_id}/retrieval/reindex
```

Status returns configured/available state, model, dimension, index counts,
last error, and the honest effective mode.

## Acceptance Gates

- a semantic query with no shared keyword retrieves the intended chunk through
  vector search;
- lexical-only and vector-only candidates both participate in fused results;
- citations expose real retrieval provenance and model identity;
- unchanged content is not re-embedded on repeated retrieval;
- changed content is re-indexed and stale chunks are deleted;
- superseded artifacts never appear in vector or lexical results;
- deleting and rebuilding the vector index preserves retrievable source ids;
- failed force rebuild preserves the prior vector snapshot;
- metadata-only evidence changes refresh citation provenance without embedding;
- configured-model failure yields explicit `lexical_degraded` status;
- one real local FastEmbed smoke test proves non-keyword semantic recall.
