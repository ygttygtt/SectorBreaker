import asyncio

from backend.app.providers.fakes import FakeSearchProvider
from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.multi_search import MultiSearchProvider


def test_multi_search_provider_merges_and_deduplicates_results() -> None:
    provider = MultiSearchProvider(
        [
            FakeSearchProvider(
                results=[
                    {
                        "title": "Result A",
                        "url": "https://example.com/a",
                        "snippet": "A snippet",
                    },
                    {
                        "title": "Result B",
                        "url": "https://example.com/shared",
                        "snippet": "Shared snippet from provider 1",
                    },
                ]
            ),
            FakeSearchProvider(
                results=[
                    {
                        "title": "Result B duplicate",
                        "url": "https://example.com/shared/",
                        "snippet": "Shared snippet from provider 2",
                    },
                    {
                        "title": "Result C",
                        "url": "https://example.com/c",
                        "snippet": "C snippet",
                    },
                ]
            ),
        ]
    )

    results = asyncio.run(
        provider.search(SearchQuery(query="test", market_scope="mixed", max_results=5))
    )

    assert [item.title for item in results] == ["Result A", "Result B", "Result C"]
