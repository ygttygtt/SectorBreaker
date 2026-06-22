"""Provider interfaces and implementations."""

from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    CounterevidenceProvider,
    DocumentSegment,
    ExtractedPage,
    LLMProvider,
    ReportIngestionProvider,
    RetrievalProvider,
    RetrievalResult,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SourceAssessment,
    SourceVerificationProvider,
    UploadedDocument,
    VerificationTask,
    CitationTarget,
)
from backend.app.providers.content_extraction import HttpContentExtractionProvider
from backend.app.providers.content_extraction import (
    FirecrawlContentExtractionProvider,
    JinaReaderContentExtractionProvider,
)
from backend.app.providers.brave import BraveSearchProvider
from backend.app.providers.exa import ExaSearchProvider
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_llm_provider,
    build_search_provider,
    build_source_registry,
    build_source_verification_provider,
)
from backend.app.providers.counterevidence import HeuristicCounterevidenceProvider
from backend.app.providers.multi_search import MultiSearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.serper import SerperSearchProvider
from backend.app.providers.source_packs import (
    SourceConnector,
    SourceConnectorType,
    SourcePack,
    SourceRegistry,
    build_default_source_registry,
)
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.providers.tavily import TavilySearchProvider

__all__ = [
    "CitationTarget",
    "BraveSearchProvider",
    "ChatMessage",
    "ContentExtractionProvider",
    "CounterevidenceProvider",
    "ExaSearchProvider",
    "FirecrawlContentExtractionProvider",
    "HeuristicCounterevidenceProvider",
    "DocumentSegment",
    "ExtractedPage",
    "HttpContentExtractionProvider",
    "JinaReaderContentExtractionProvider",
    "build_content_extraction_provider",
    "build_default_source_registry",
    "build_llm_provider",
    "build_search_provider",
    "build_source_registry",
    "build_source_verification_provider",
    "LLMProvider",
    "MultiSearchProvider",
    "OpenAICompatibleLLMProvider",
    "ReportIngestionProvider",
    "RetrievalProvider",
    "RetrievalResult",
    "SearchProvider",
    "SearchQuery",
    "SearchResult",
    "SerperSearchProvider",
    "SourceConnector",
    "SourceConnectorType",
    "SourcePack",
    "SourceRegistry",
    "HeuristicSourceVerificationProvider",
    "SourceAssessment",
    "SourceVerificationProvider",
    "TavilySearchProvider",
    "UploadedDocument",
    "VerificationTask",
]
