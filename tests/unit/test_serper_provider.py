import asyncio

from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.serper import SerperSearchProvider


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
                "organic": [
                    {
                        "title": "Pet services market",
                        "link": "https://example.com/pet-services-market",
                        "snippet": "Demand is growing in pet care.",
                        "date": "2026-03-01",
                        "position": 1,
                    }
                ]
            }
        )


def test_serper_search_provider_maps_results(monkeypatch) -> None:
    import backend.app.providers.serper as serper_module

    monkeypatch.setattr(serper_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = SerperSearchProvider(api_key="test-key")

    results = asyncio.run(
        provider.search(SearchQuery(query="pet services market", market_scope="china", max_results=3))
    )

    assert results[0].title == "Pet services market"
    assert results[0].url == "https://example.com/pet-services-market"
    assert results[0].snippet == "Demand is growing in pet care."
    assert results[0].provider_metadata["provider"] == "serper"


def test_serper_search_provider_appends_domain_filters(monkeypatch) -> None:
    import backend.app.providers.serper as serper_module

    captured: dict = {}

    class CaptureAsyncClient(FakeAsyncClient):
        async def post(self, url: str, json: dict, headers: dict) -> FakeResponse:
            captured["json"] = json
            return await super().post(url, json, headers)

    monkeypatch.setattr(serper_module.httpx, "AsyncClient", CaptureAsyncClient)
    provider = SerperSearchProvider(api_key="test-key")

    asyncio.run(
        provider.search(
            SearchQuery(
                query="pet services market",
                market_scope="china",
                max_results=3,
                allowed_domains=["gov.cn"],
                blocked_domains=["example.com"],
            )
        )
    )

    assert "site:gov.cn" in captured["json"]["q"]
    assert "-site:example.com" in captured["json"]["q"]
