"""Environment-backed provider construction."""

import os

from backend.app.providers.interfaces import LLMProvider, SearchProvider
from backend.app.providers.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.providers.tavily import TavilySearchProvider


def build_llm_provider() -> LLMProvider | None:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not base_url or not api_key or not model:
        return None
    return OpenAICompatibleLLMProvider(base_url=base_url, api_key=api_key, model=model)


def build_search_provider() -> SearchProvider | None:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None
    endpoint = os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search")
    return TavilySearchProvider(api_key=api_key, endpoint=endpoint)
