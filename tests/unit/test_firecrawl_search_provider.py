import asyncio

from backend.app.providers.firecrawl_search import FirecrawlSearchProvider
from backend.app.providers.interfaces import SearchQuery


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Firecrawl repository",
                        "url": "https://github.com/firecrawl/firecrawl",
                        "description": "Search and scrape the web for agents.",
                    }
                ]
            },
        }


class _Client:
    payload: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict, headers: dict):
        self.payload = json
        return _Response()


def test_firecrawl_search_provider_maps_results_and_filters(monkeypatch) -> None:
    import backend.app.providers.firecrawl_search as module

    client = _Client()
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *args, **kwargs: client)
    provider = FirecrawlSearchProvider(api_key="fc-test")

    results = asyncio.run(
        provider.search(
            SearchQuery(
                query="agent research",
                market_scope="mixed",
                max_results=3,
                allowed_domains=["github.com"],
                blocked_domains=["medium.com"],
            )
        )
    )

    assert results[0].provider_metadata["provider"] == "firecrawl"
    assert results[0].url.endswith("firecrawl")
    assert client.payload["includeDomains"] == ["github.com"]
    assert client.payload["excludeDomains"] == ["medium.com"]
