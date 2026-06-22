from backend.app.providers.content_extraction import (
    FirecrawlContentExtractionProvider,
    HttpContentExtractionProvider,
    JinaReaderContentExtractionProvider,
)
from backend.app.providers.brave import BraveSearchProvider
from backend.app.providers.exa import ExaSearchProvider
from backend.app.providers.factory import (
    build_content_extraction_provider,
    build_llm_provider,
    build_search_provider,
    build_search_provider_from_config,
)
from backend.app.providers.multi_search import MultiSearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.serper import SerperSearchProvider
from backend.app.providers.tavily import TavilySearchProvider


def test_provider_factory_returns_none_without_required_environment(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)

    assert build_llm_provider() is None
    assert build_search_provider() is None


def test_provider_factory_builds_openai_compatible_llm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    provider = build_llm_provider()

    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.base_url == "https://llm.example.com/v1"
    assert provider.model == "test-model"


def test_provider_factory_builds_tavily_search(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)

    provider = build_search_provider()

    assert isinstance(provider, TavilySearchProvider)


def test_provider_factory_builds_serper_search(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    provider = build_search_provider()

    assert isinstance(provider, SerperSearchProvider)


def test_provider_factory_builds_brave_search(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")

    provider = build_search_provider()

    assert isinstance(provider, BraveSearchProvider)


def test_provider_factory_builds_exa_search(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    provider = build_search_provider()

    assert isinstance(provider, ExaSearchProvider)


def test_provider_factory_builds_multi_search_when_multiple_keys_exist(monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    monkeypatch.delenv("EXA_API_KEY", raising=False)

    provider = build_search_provider()

    assert isinstance(provider, MultiSearchProvider)


def test_provider_factory_honors_explicit_single_provider_mode() -> None:
    provider = build_search_provider_from_config(
        provider_mode="brave",
        tavily_api_key="tavily-key",
        serper_api_key="serper-key",
        brave_api_key="brave-key",
        exa_api_key="exa-key",
    )

    assert isinstance(provider, BraveSearchProvider)


def test_provider_factory_honors_explicit_exa_provider_mode() -> None:
    provider = build_search_provider_from_config(
        provider_mode="exa",
        tavily_api_key="tavily-key",
        serper_api_key="serper-key",
        brave_api_key="brave-key",
        exa_api_key="exa-key",
    )

    assert isinstance(provider, ExaSearchProvider)


def test_provider_factory_honors_explicit_multi_mode() -> None:
    provider = build_search_provider_from_config(
        provider_mode="multi",
        tavily_api_key="tavily-key",
        serper_api_key="serper-key",
    )

    assert isinstance(provider, MultiSearchProvider)


def test_provider_factory_builds_default_http_content_extractor(monkeypatch) -> None:
    monkeypatch.delenv("CONTENT_EXTRACTION_PROVIDER", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    provider = build_content_extraction_provider()

    assert isinstance(provider, HttpContentExtractionProvider)


def test_provider_factory_builds_firecrawl_content_extractor(monkeypatch) -> None:
    monkeypatch.setenv("CONTENT_EXTRACTION_PROVIDER", "firecrawl")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-key")

    provider = build_content_extraction_provider()

    assert isinstance(provider, FirecrawlContentExtractionProvider)


def test_provider_factory_falls_back_to_http_when_firecrawl_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("CONTENT_EXTRACTION_PROVIDER", "firecrawl")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    provider = build_content_extraction_provider()

    assert isinstance(provider, HttpContentExtractionProvider)


def test_provider_factory_builds_jina_reader_content_extractor(monkeypatch) -> None:
    monkeypatch.setenv("CONTENT_EXTRACTION_PROVIDER", "jina")

    provider = build_content_extraction_provider()

    assert isinstance(provider, JinaReaderContentExtractionProvider)
