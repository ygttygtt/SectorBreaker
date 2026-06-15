import asyncio

from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.tavily import TavilySearchProvider


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        self.requests.append({"url": url, "json": json})
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "AI agent market",
                        "url": "https://example.com/ai-agent-market",
                        "content": "Market overview content.",
                        "published_date": "2026-01-15",
                    }
                ]
            }
        )


def test_tavily_search_provider_maps_results(monkeypatch) -> None:
    import backend.app.providers.tavily as tavily_module

    monkeypatch.setattr(tavily_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = TavilySearchProvider(api_key="test-key")

    results = asyncio.run(
        provider.search(SearchQuery(query="AI agent market", market_scope="mixed", max_results=2))
    )

    assert results[0].title == "AI agent market"
    assert results[0].snippet == "Market overview content."
    assert results[0].provider_metadata["provider"] == "tavily"
