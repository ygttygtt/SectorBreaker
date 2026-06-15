from backend.app.providers.factory import build_llm_provider, build_search_provider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.tavily import TavilySearchProvider


def test_provider_factory_returns_none_without_required_environment(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

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
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    provider = build_search_provider()

    assert isinstance(provider, TavilySearchProvider)
