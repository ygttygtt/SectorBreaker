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
)
from backend.app.providers.counterevidence import HeuristicCounterevidenceProvider
from backend.app.providers.multi_search import MultiSearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.serper import SerperSearchProvider
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
    "build_llm_provider",
    "build_search_provider",
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
    "HeuristicSourceVerificationProvider",
    "SourceAssessment",
    "SourceVerificationProvider",
    "TavilySearchProvider",
    "UploadedDocument",
    "VerificationTask",
]
