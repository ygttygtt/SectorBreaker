import asyncio

from backend.app.providers.brave import BraveSearchProvider
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

    async def get(self, url: str, params: dict, headers: dict) -> FakeResponse:
        self.requests.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(
            {
                "web": {
                    "results": [
                        {
                            "title": "AI agent market map",
                            "url": "https://example.com/ai-agent-market",
                            "description": "Official overview of the market.",
                            "page_age": "2026-06-01",
                            "family_friendly": True,
                            "language": "en",
                        }
                    ]
                }
            }
        )


def test_brave_search_provider_maps_results(monkeypatch) -> None:
    import backend.app.providers.brave as brave_module

    monkeypatch.setattr(brave_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = BraveSearchProvider(api_key="test-key")

    results = asyncio.run(
        provider.search(SearchQuery(query="ai agent market", market_scope="mixed", max_results=3))
    )

    assert results[0].title == "AI agent market map"
    assert results[0].url == "https://example.com/ai-agent-market"
    assert results[0].snippet == "Official overview of the market."
    assert results[0].provider_metadata["provider"] == "brave"


def test_brave_search_provider_appends_domain_filters(monkeypatch) -> None:
    import backend.app.providers.brave as brave_module

    captured: dict = {}

    class CaptureAsyncClient(FakeAsyncClient):
        async def get(self, url: str, params: dict, headers: dict) -> FakeResponse:
            captured["params"] = params
            return await super().get(url, params, headers)

    monkeypatch.setattr(brave_module.httpx, "AsyncClient", CaptureAsyncClient)
    provider = BraveSearchProvider(api_key="test-key")

    asyncio.run(
        provider.search(
            SearchQuery(
                query="ai agent market",
                market_scope="mixed",
                max_results=3,
                allowed_domains=["sec.gov", "investor.gov"],
                blocked_domains=["medium.com"],
            )
        )
    )

    assert "(site:sec.gov OR site:investor.gov)" in captured["params"]["q"]
    assert "-site:medium.com" in captured["params"]["q"]
