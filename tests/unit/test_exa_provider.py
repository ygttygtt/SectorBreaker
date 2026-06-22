import asyncio

from backend.app.providers.exa import ExaSearchProvider
from backend.app.providers.interfaces import SearchQuery


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

    async def post(self, url: str, json: dict, headers: dict) -> FakeResponse:
        self.requests.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "AI agent market map",
                        "url": "https://example.com/ai-agent-market",
                        "text": "Official overview of the AI agent market and the main categories.",
                        "publishedDate": "2026-06-01T00:00:00.000Z",
                        "author": "Example Research",
                        "score": 0.92,
                    }
                ]
            }
        )


def test_exa_search_provider_maps_results(monkeypatch) -> None:
    import backend.app.providers.exa as exa_module

    monkeypatch.setattr(exa_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = ExaSearchProvider(api_key="test-key")

    results = asyncio.run(
        provider.search(SearchQuery(query="ai agent market", market_scope="mixed", max_results=3))
    )

    assert results[0].title == "AI agent market map"
    assert results[0].url == "https://example.com/ai-agent-market"
    assert "Official overview" in results[0].snippet
    assert results[0].provider_metadata["provider"] == "exa"


def test_exa_search_provider_uses_domain_filters(monkeypatch) -> None:
    import backend.app.providers.exa as exa_module

    captured: dict = {}

    class CaptureAsyncClient(FakeAsyncClient):
        async def post(self, url: str, json: dict, headers: dict) -> FakeResponse:
            captured["json"] = json
            return await super().post(url, json, headers)

    monkeypatch.setattr(exa_module.httpx, "AsyncClient", CaptureAsyncClient)
    provider = ExaSearchProvider(api_key="test-key")

    asyncio.run(
        provider.search(
            SearchQuery(
                query="ai agent market",
                market_scope="mixed",
                max_results=3,
                allowed_domains=["sec.gov"],
                blocked_domains=["medium.com"],
            )
        )
    )

    assert captured["json"]["includeDomains"] == ["sec.gov"]
    assert captured["json"]["excludeDomains"] == ["medium.com"]
