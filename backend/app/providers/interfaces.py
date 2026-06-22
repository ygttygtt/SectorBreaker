"""Replaceable provider contracts."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class SearchQuery:
    query: str
    market_scope: str
    max_results: int
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str | None = None
    provider_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    raw_text: str
    canonical_url: str | None = None
    title: str | None = None
    markdown: str | None = None
    published_date: str | None = None
    author: str | None = None
    domain: str | None = None
    extraction_provider: str | None = None
    extraction_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class UploadedDocument:
    document_id: str
    project_id: str
    channel: str
    original_text: str
    file_name: str | None = None
    mime_type: str | None = None
    normalized_markdown: str | None = None
    word_count: int = 0
    char_count: int = 0


@dataclass(frozen=True)
class DocumentSegment:
    segment_id: str
    document_id: str
    order_index: int
    text: str
    heading: str | None = None
    char_count: int = 0
    citation_refs: list[str] | None = None


@dataclass(frozen=True)
class CitationTarget:
    citation_id: str
    document_id: str
    raw_reference: str
    source_title: str | None = None
    source_url: str | None = None
    referenced_segments: list[str] | None = None


@dataclass(frozen=True)
class SourceAssessment:
    source_type: str
    source_quality: str
    is_original_source: bool
    is_marketing_like: bool
    url: str | None = None
    domain: str | None = None
    marketing_signals: list[str] | None = None
    reliability_notes: str | None = None
    recommended_verification_status: str | None = None


@dataclass(frozen=True)
class VerificationTask:
    task_id: str
    claim_id: str
    verification_goal: str
    query_variants: list[str]
    preferred_domains: list[str] | None = None
    blocking: bool = False


@dataclass(frozen=True)
class RetrievalResult:
    document_id: str
    snippet: str
    score: float


class LLMProvider(Protocol):
    async def complete_structured(
        self,
        messages: list[ChatMessage],
        response_schema: type[Any],
    ) -> Any:
        """Return a structured response matching the requested schema."""


class SearchProvider(Protocol):
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search external sources."""


class ContentExtractionProvider(Protocol):
    async def extract_url(self, url: str) -> ExtractedPage:
        """Extract page content from a URL."""


class ReportIngestionProvider(Protocol):
    async def ingest_text(
        self,
        project_id: str,
        content: str,
        channel: str,
        file_name: str | None = None,
    ) -> tuple[UploadedDocument, list[DocumentSegment], list[CitationTarget]]:
        """Normalize uploaded report text into a document plus segments and citations."""


class SourceVerificationProvider(Protocol):
    async def assess_source(
        self,
        *,
        url: str | None,
        title: str | None,
        snippet: str | None,
        extracted_text: str | None,
        source_policy: str,
    ) -> SourceAssessment:
        """Assess source quality, source type, and marketing risk."""


class CounterevidenceProvider(Protocol):
    async def build_verification_tasks(
        self,
        claim_id: str,
        claim_text: str,
        market_scope: str,
    ) -> list[VerificationTask]:
        """Build search tasks for corroboration and contradiction checks."""


class RetrievalProvider(Protocol):
    def index_text(self, project_id: str, document_id: str, text: str) -> None:
        """Index project-local text."""

    def search_project(self, project_id: str, query: str, limit: int) -> list[RetrievalResult]:
        """Search project-local indexed text."""
