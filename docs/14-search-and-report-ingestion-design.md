# Search And Report Ingestion Design

## Purpose

This document defines the next-step architecture for web search, external AI
report ingestion, source verification, and counterevidence collection.

The goal is to let implementation start immediately without re-deciding
provider boundaries, API contracts, or evidence-handling rules during coding.

## Product Position

Search is not an optional convenience feature in SectorBreaker. It is a core
research dependency.

Therefore:

- the product must explicitly show when search is unavailable;
- search providers must be replaceable;
- provider output must not be treated as final evidence without local evidence
  normalization and policy checks;
- external AI reports are useful leverage, but they must enter the same
  evidence-verification pipeline as open-web search results.

## Non-Goals

This phase does not require:

- a full custom crawler before basic multi-provider search works;
- login-gated or platform-restricted scraping;
- converting every uploaded file type on day one;
- a new graph architecture.

## Core Principle

Do not rebuild the provider's ranking or search engine.

Do build the project's own evidence-governance layer.

Provider responsibilities:

- query the web;
- return candidate pages or extracted page content;
- optionally return provider-side summaries or metadata.

Local system responsibilities:

- normalize provider output into shared models;
- enforce `source_policy`;
- classify source quality and marketing risk;
- extract claims and citations;
- run corroboration / counterevidence checks;
- decide what can enter the evidence ledger as fact support.

## Capability Layers

### Layer 1: Search Provider

Purpose:

- `query -> candidate results`

Typical providers:

- Tavily
- Brave Search API
- Serper
- Bing Web Search
- Exa

Rules:

- Search results are leads, not verified evidence.
- Search providers may be combined by a router or multi-search adapter.

### Layer 2: Content Extraction Provider

Purpose:

- `url -> cleaned text + metadata`

Typical providers:

- Firecrawl
- Jina Reader-style extraction
- provider-native raw content extraction
- local readability-style extraction as fallback

Rules:

- Extraction is separate from search.
- A page can be discovered by one provider and extracted by another.

### Layer 3: Report Ingestion Provider

Purpose:

- `uploaded text/file -> normalized report document + segments + cited sources`

Supported first-phase inputs:

- pasted Markdown
- pasted plain text
- `.md`
- `.txt`

Second-phase inputs:

- `.pdf`
- `.docx`

Rules:

- an uploaded external AI report is not a verified source;
- cited URLs inside the report can become verification targets.

### Layer 4: Source Verification Provider

Purpose:

- `source url/title/domain -> source classification + quality + marketing risk`

This is not a vendor search provider. It is local project logic, optionally
assisted by LLM and heuristics.

Output decisions include:

- official vs media vs community vs assistant_brief vs user_material
- high / medium / low source quality
- likely marketing / likely neutral / unclear
- original source vs secondary aggregation

### Layer 5: Counterevidence Provider

Purpose:

- `claim -> corroboration search tasks + conflict search tasks`

This layer can reuse search providers but has a different job:

- verify a claim;
- find second-source support;
- find contradictory or weaker formulations.

## Recommended Execution Flow

### Open-Web Search Flow

1. Search Scout receives search tasks.
2. `SearchProvider` returns candidate results.
3. candidates are deduplicated and normalized.
4. `ContentExtractionProvider` extracts article text for selected candidates.
5. `SourceVerifier` scores quality, source type, and marketing risk.
6. `Evidence Curator` creates `EvidenceItem` records.
7. `Counterevidence Agent` verifies weak or critical claims.

### External AI Report Flow

1. user uploads a file or pastes report text.
2. `ReportIngestionProvider` stores raw content and segments the report.
3. the report is recorded as `assistant_brief` evidence with low default trust.
4. cited sources in the report are extracted into verification targets.
5. each citation is searched / fetched / extracted if needed.
6. `SourceVerifier` evaluates whether the citation is official, media, marketing,
   aggregator, or unclear.
7. report claims can be upgraded only when cited sources pass policy checks.

## Why Not Feed The Full Report Everywhere

A 5,000-word report fits easily in modern long-context models, so one-pass
analysis is acceptable.

But implementation should not keep sending the full report to every agent.

Recommended pattern:

1. store the original report;
2. split into segments;
3. extract claims and citations once;
4. keep segment IDs and source references;
5. pass only relevant claims/segments to later agents.

Benefits:

- lower token cost;
- better traceability;
- easier citation audit;
- easier counterevidence routing;
- less prompt drift across agents.

## Proposed New Models

These models should be added before implementation. Names may be adjusted, but
the structure should remain equivalent.

### SearchTask

```python
class SearchTask(BaseModel):
    task_id: str
    query: str
    intent: str  # discovery | verification | counterevidence | citation_lookup
    market_scope: str
    language: str | None = None
    max_results: int = 5
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    source_policy: SourcePolicy
    related_claim_id: str | None = None
```

### SearchCandidate

```python
class SearchCandidate(BaseModel):
    candidate_id: str
    title: str
    url: str
    snippet: str
    provider: str
    published_date: str | None = None
    provider_rank: int | None = None
    provider_score: float | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
```

### ExtractedPage

```python
class ExtractedPage(BaseModel):
    url: str
    canonical_url: str | None = None
    title: str | None = None
    raw_text: str
    markdown: str | None = None
    published_date: str | None = None
    author: str | None = None
    domain: str | None = None
    extraction_provider: str
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)
```

### UploadedDocument

```python
class UploadedDocument(BaseModel):
    document_id: str
    project_id: str
    file_name: str | None = None
    mime_type: str | None = None
    channel: str  # assistant_brief | user_upload
    original_text: str
    normalized_markdown: str | None = None
    word_count: int
    char_count: int
```

### DocumentSegment

```python
class DocumentSegment(BaseModel):
    segment_id: str
    document_id: str
    order_index: int
    heading: str | None = None
    text: str
    char_count: int
    citation_refs: list[str] = Field(default_factory=list)
```

### CitationTarget

```python
class CitationTarget(BaseModel):
    citation_id: str
    document_id: str
    source_title: str | None = None
    source_url: str | None = None
    raw_reference: str
    referenced_segments: list[str] = Field(default_factory=list)
```

### SourceAssessment

```python
class SourceAssessment(BaseModel):
    url: str | None = None
    domain: str | None = None
    source_type: SourceType
    source_quality: SourceQuality
    is_original_source: bool
    is_marketing_like: bool
    marketing_signals: list[str] = Field(default_factory=list)
    reliability_notes: str | None = None
    recommended_verification_status: VerificationStatus
```

### VerificationTask

```python
class VerificationTask(BaseModel):
    task_id: str
    claim_id: str
    verification_goal: str  # corroborate | challenge | resolve_source_quality
    query_variants: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    blocking: bool = False
```

## Proposed Provider Contracts

These are the next-step provider interfaces. They extend the current search-only
interface without breaking the graph boundary rule.

### SearchProvider

Keep the existing interface for backward compatibility, but implementation
should move toward task-oriented search:

```python
class SearchProvider(Protocol):
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        ...
```

Preferred future shape:

```python
class SearchProvider(Protocol):
    async def search_candidates(self, task: SearchTask) -> list[SearchCandidate]:
        ...
```

### ContentExtractionProvider

```python
class ContentExtractionProvider(Protocol):
    async def extract_url(self, url: str) -> ExtractedPage:
        ...
```

### ReportIngestionProvider

```python
class ReportIngestionProvider(Protocol):
    async def ingest_text(
        self,
        project_id: str,
        content: str,
        channel: str,
        file_name: str | None = None,
    ) -> tuple[UploadedDocument, list[DocumentSegment], list[CitationTarget]]:
        ...
```

### SourceVerificationProvider

```python
class SourceVerificationProvider(Protocol):
    async def assess_source(
        self,
        *,
        url: str | None,
        title: str | None,
        snippet: str | None,
        extracted_text: str | None,
        source_policy: SourcePolicy,
    ) -> SourceAssessment:
        ...
```

### CounterevidenceProvider

```python
class CounterevidenceProvider(Protocol):
    async def build_verification_tasks(
        self,
        claim: EvidenceClaim,
        project: ResearchProject,
    ) -> list[VerificationTask]:
        ...
```

## Source Policy Rules

### `open_web`

- allow broad discovery;
- weak sources may enter as downgraded evidence;
- critical claims still require verification.

### `reliable_first`

- try official, public-database, government, company-disclosure domains first;
- fall back to broader web only when reliable coverage is insufficient;
- media/web sources may support leads or partial claims.

Current implementation note:

- workflow search now injects preferred reliable-domain constraints into the
  provider query path, so this policy already affects real search calls instead
  of staying as a display-only rule.

### `reliable_only`

- assistant briefs, community posts, generic marketing pages, and weak media
  summaries cannot support facts;
- they may still create follow-up verification tasks.

Current implementation note:

- workflow search now converts this policy into a stricter allowed-domain set
  plus common noisy-domain exclusions before calling the configured search
  provider.

### `user_materials_only`

- no open-web search;
- user-uploaded files and manually supplied links are allowed;
- external AI reports still remain low-trust until their cited sources are
  verified from allowed materials or manually supplied links.

## Marketing-Risk Heuristics

This is one of the most important local layers.

Signals that a citation may be marketing-heavy:

- domain is a company blog or campaign landing page;
- article has strong CTA or lead-capture language;
- pricing, ranking, or “best tools” page without primary sourcing;
- repeated brand mentions with little underlying data;
- source is a syndication or SEO aggregator;
- cited statistics point to another article, not an original report.

Actions:

- downgrade source quality;
- mark `claim_strength=marketing` when appropriate;
- set `needs_counterevidence=True`;
- require corroboration before `verified`.

## File Upload Design

### User Experience

The frontend should support both:

- paste external AI report text;
- upload files.

First implementation:

- `.md`
- `.txt`

Second implementation:

- `.pdf`
- `.docx`

UI requirements:

- keep the current textarea for fast paste;
- add file upload to the same review / input flow;
- show filename, size, and parse status;
- preserve explicit reminder that uploaded external AI reports are leads, not
  direct fact support.

### API Contract

Recommended new endpoints:

- `POST /api/projects/{project_id}/documents`
- `GET /api/projects/{project_id}/documents`
- `GET /api/documents/{document_id}`

For first phase, `multipart/form-data` is recommended for file upload.

Suggested response model:

```json
{
  "document_id": "doc-123",
  "channel": "assistant_brief",
  "file_name": "kimi-report.md",
  "word_count": 5070,
  "char_count": 9596,
  "segment_count": 18,
  "citation_count": 23
}
```

Resume contract should later evolve from plain `assistant_brief: str` to either:

- `assistant_brief_text: str`
- `assistant_brief_document_ids: list[str]`

Do not remove the existing text field until the new upload path is stable.

## Recommended Graph Changes

Do not rewrite the graph.

Add capability inside existing gates.

### Source Intake Gate

Expand responsibilities:

- receive search candidates from one or more search providers;
- receive uploaded documents and assistant briefs;
- extract citations from reports;
- emit document-ingestion and citation-ingestion progress events.

### Claim Extractor Gate

Expand responsibilities:

- extract claim candidates from report segments and extracted pages;
- preserve claim-to-segment and claim-to-evidence mapping.

### Counterevidence Gate

Expand responsibilities:

- generate verification tasks for weak, marketing-like, or critical claims;
- run targeted corroboration search instead of only tagging unresolved items.

### Evidence Ledger Gate

Expand responsibilities:

- reconcile duplicate URLs and canonical URLs;
- attach source assessment results;
- attach corroborating/conflicting evidence references.

## SSE Event Extensions

Recommended new event types:

- `document_uploaded`
- `document_parsed`
- `citation_extracted`
- `source_assessed`
- `verification_task_created`
- `counterevidence_found`

These are additive and should not replace existing node events.

## Implementation Order

This order is intended to unblock immediate API integration work.

### Step 1: Contract And Docs

- document new provider interfaces;
- document upload and document endpoints;
- document new models and migration needs.

### Step 2: Minimal Multi-Provider Search

- keep Tavily working;
- add one additional provider via the same search boundary;
- add router selection in provider factory;
- expose provider configuration status in API.

### Step 3: Content Extraction Boundary

- introduce `ContentExtractionProvider`;
- support provider-native extraction or a no-op fallback;
- do not block search implementation on crawler work.

Current implementation progress:

- `ContentExtractionProvider` is now wired into the workflow through a replaceable
  provider boundary;
- the default local implementation fetches URL content over HTTP, strips HTML,
  extracts title/text, and returns `ExtractedPage`;
- counterevidence verification search now attempts `url -> extracted page ->
  source reassessment -> evidence writeback` instead of staying snippet-only.

Recommended next upgrade:

- add provider-backed extractors such as Firecrawl or Jina Reader behind the
  same interface;
- keep the current HTTP extractor as fallback when no richer extractor is
  configured;
- add per-domain timeout / failure controls before broader crawling work.

Current implementation note:

- Firecrawl and Jina Reader-style extractors are now supported at the provider
  factory layer, with local HTTP extraction kept as fallback.

### Step 4: Report Ingestion

- support text + `.md` + `.txt`;
- store uploaded document metadata;
- split into segments;
- extract citations.

### Step 5: Source Verification

- implement domain/source heuristics;
- classify official vs media vs marketing;
- mark `needs_counterevidence`.

### Step 6: Counterevidence Search

- convert unresolved claims into targeted search tasks;
- attach corroborating/conflicting evidence IDs.

Current implementation progress:

- a first-pass local `CounterevidenceProvider` can now turn weak or marketing-like
  claims into structured verification tasks;
- the workflow now executes those tasks through the configured `SearchProvider`;
- verification search results are written back into the evidence ledger as
  `counterevidence_search` evidence with `partially_verified` or `conflicting`
  status hints.

Remaining upgrade work:

- stronger claim-specific query planning;
- domain preference routing based on source policy and claim type;
- explicit link fields from original evidence -> verification task -> supporting
  / conflicting evidence IDs;
- richer page extraction for verification results before final promotion.

### Step 7: PDF/DOCX Support

- add parser-backed ingestion for richer file formats.

## Minimal API Integration Checklist

If implementation starts now, the first concrete coding milestone should be:

1. Add config keys for at least one second search provider.
2. Add `SearchRouter` in provider factory.
3. Add `search_candidates` adapter or equivalent normalization layer.
4. Keep Tavily as default fallback.
5. Add document upload endpoint for `.md` / `.txt`.
6. Store uploaded report as low-trust evidence and document rows.
7. Extract cited URLs and create verification tasks.

If these seven items are complete, SectorBreaker will have a real search
expansion path without breaking existing workflow structure.
