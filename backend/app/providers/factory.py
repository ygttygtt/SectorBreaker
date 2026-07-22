"""Environment-backed provider construction."""

import os

from backend.app.providers.brave import BraveSearchProvider
from backend.app.providers.content_extraction import (
    FirecrawlContentExtractionProvider,
    HttpContentExtractionProvider,
    JinaReaderContentExtractionProvider,
)
from backend.app.providers.exa import ExaSearchProvider
from backend.app.providers.firecrawl_search import FirecrawlSearchProvider
from backend.app.providers.embeddings import DEFAULT_LOCAL_EMBEDDING_MODEL, FastEmbedEmbeddingProvider
from backend.app.providers.interfaces import ContentExtractionProvider, EmbeddingProvider, LLMProvider, SearchProvider
from backend.app.providers.multi_search import MultiSearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.serper import SerperSearchProvider
from backend.app.providers.source_packs import SourceRegistry, build_default_source_registry
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.providers.tavily import TavilySearchProvider


def build_llm_provider_from_config(
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int = 4096,
) -> LLMProvider:
    return OpenAICompatibleLLMProvider(base_url=base_url, api_key=api_key, model=model, max_tokens=max_tokens)


def build_llm_provider() -> LLMProvider | None:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not base_url or not api_key or not model:
        return None
    max_tokens_value = os.getenv("LLM_MAX_TOKENS", "4096")
    try:
        max_tokens = int(max_tokens_value)
    except ValueError:
        max_tokens = 4096
    return build_llm_provider_from_config(base_url=base_url, api_key=api_key, model=model, max_tokens=max_tokens)


def build_search_provider_from_config(
    *,
    provider_mode: str = "auto",
    tavily_api_key: str | None = None,
    tavily_endpoint: str = "https://api.tavily.com/search",
    serper_api_key: str | None = None,
    serper_endpoint: str = "https://google.serper.dev/search",
    brave_api_key: str | None = None,
    brave_endpoint: str = "https://api.search.brave.com/res/v1/web/search",
    exa_api_key: str | None = None,
    exa_endpoint: str = "https://api.exa.ai/search",
    firecrawl_api_key: str | None = None,
    firecrawl_search_endpoint: str = "https://api.firecrawl.dev/v2/search",
) -> SearchProvider | None:
    normalized_mode = (provider_mode or "auto").strip().lower()
    provider_builders: dict[str, SearchProvider | None] = {
        "tavily": TavilySearchProvider(api_key=tavily_api_key, endpoint=tavily_endpoint) if tavily_api_key else None,
        "serper": SerperSearchProvider(api_key=serper_api_key, endpoint=serper_endpoint) if serper_api_key else None,
        "brave": BraveSearchProvider(api_key=brave_api_key, endpoint=brave_endpoint) if brave_api_key else None,
        "exa": ExaSearchProvider(api_key=exa_api_key, endpoint=exa_endpoint) if exa_api_key else None,
        "firecrawl": FirecrawlSearchProvider(api_key=firecrawl_api_key, endpoint=firecrawl_search_endpoint)
        if firecrawl_api_key else None,
    }
    providers: list[SearchProvider] = [provider for provider in provider_builders.values() if provider is not None]

    if normalized_mode in provider_builders:
        return provider_builders[normalized_mode]

    if normalized_mode == "multi":
        return MultiSearchProvider(providers) if providers else None

    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]
    return MultiSearchProvider(providers)


def build_search_provider() -> SearchProvider | None:
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")
    brave_api_key = os.getenv("BRAVE_API_KEY")
    exa_api_key = os.getenv("EXA_API_KEY")
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    return build_search_provider_from_config(
        provider_mode=os.getenv("SEARCH_PROVIDER_MODE", "auto"),
        tavily_api_key=tavily_api_key,
        tavily_endpoint=os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search"),
        serper_api_key=serper_api_key,
        serper_endpoint=os.getenv("SERPER_ENDPOINT", "https://google.serper.dev/search"),
        brave_api_key=brave_api_key,
        brave_endpoint=os.getenv("BRAVE_ENDPOINT", "https://api.search.brave.com/res/v1/web/search"),
        exa_api_key=exa_api_key,
        exa_endpoint=os.getenv("EXA_ENDPOINT", "https://api.exa.ai/search"),
        firecrawl_api_key=firecrawl_api_key,
        firecrawl_search_endpoint=os.getenv("FIRECRAWL_SEARCH_ENDPOINT", "https://api.firecrawl.dev/v2/search"),
    )


def build_content_extraction_provider_from_config(
    *,
    provider_name: str = "http",
    firecrawl_api_key: str | None = None,
    firecrawl_endpoint: str = "https://api.firecrawl.dev/v1/scrape",
    jina_reader_endpoint_prefix: str = "https://r.jina.ai/http://",
) -> ContentExtractionProvider:
    normalized_provider_name = provider_name.strip().lower()

    if normalized_provider_name == "firecrawl" and firecrawl_api_key:
        return FirecrawlContentExtractionProvider(api_key=firecrawl_api_key, endpoint=firecrawl_endpoint)

    if normalized_provider_name in {"jina", "jina_reader"}:
        return JinaReaderContentExtractionProvider(endpoint_prefix=jina_reader_endpoint_prefix)

    return HttpContentExtractionProvider()


def build_content_extraction_provider() -> ContentExtractionProvider:
    return build_content_extraction_provider_from_config(
        provider_name=(os.getenv("CONTENT_EXTRACTION_PROVIDER") or "http"),
        firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY"),
        firecrawl_endpoint=os.getenv("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev/v1/scrape"),
        jina_reader_endpoint_prefix=os.getenv("JINA_READER_ENDPOINT_PREFIX", "https://r.jina.ai/http://"),
    )


def build_embedding_provider_from_config(
    *,
    provider_name: str = "auto",
    model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL,
    cache_dir: str | None = None,
    threads: int | None = None,
) -> EmbeddingProvider | None:
    normalized = (provider_name or "auto").strip().lower()
    if normalized in {"disabled", "none", "off"}:
        return None
    if normalized not in {"auto", "fastembed"}:
        raise ValueError(f"unsupported embedding provider: {provider_name}")
    try:
        import fastembed  # noqa: F401
    except Exception:
        if normalized == "fastembed":
            raise RuntimeError("fastembed is configured but not installed")
        return None
    return FastEmbedEmbeddingProvider(
        model_name=model_name,
        cache_dir=cache_dir,
        threads=threads,
    )


def build_embedding_provider() -> EmbeddingProvider | None:
    raw_threads = os.getenv("SECTORBREAKER_EMBEDDING_THREADS")
    try:
        threads = int(raw_threads) if raw_threads else None
    except ValueError:
        threads = None
    if threads is not None and threads <= 0:
        threads = None
    return build_embedding_provider_from_config(
        provider_name=os.getenv("SECTORBREAKER_EMBEDDING_PROVIDER", "auto"),
        model_name=os.getenv("SECTORBREAKER_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL),
        cache_dir=os.getenv("SECTORBREAKER_EMBEDDING_CACHE_DIR"),
        threads=threads,
    )


def build_source_registry() -> SourceRegistry:
    return build_default_source_registry()


def build_source_verification_provider(
    source_registry: SourceRegistry | None = None,
) -> HeuristicSourceVerificationProvider:
    return HeuristicSourceVerificationProvider(source_registry=source_registry or build_source_registry())
