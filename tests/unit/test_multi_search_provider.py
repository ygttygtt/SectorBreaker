import asyncio

import pytest

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


def test_multi_search_provider_queries_in_parallel_and_fairly() -> None:
    class SlowProvider(FakeSearchProvider):
        async def search(self, query):
            await asyncio.sleep(0.01)
            return await super().search(query)

    provider = MultiSearchProvider(
        [
            SlowProvider(results=[{"title": "A1", "url": "https://a.example/1", "snippet": "a"}, {"title": "A2", "url": "https://a.example/2", "snippet": "a"}]),
            SlowProvider(results=[{"title": "B1", "url": "https://b.example/1", "snippet": "b"}, {"title": "B2", "url": "https://b.example/2", "snippet": "b"}]),
        ]
    )

    results = asyncio.run(provider.search(SearchQuery(query="test", market_scope="mixed", max_results=3)))

    assert [item.title for item in results] == ["A1", "B1", "A2"]


def test_multi_search_provider_keeps_partial_success_and_fails_when_all_fail() -> None:
    class BrokenProvider:
        async def search(self, query):
            raise RuntimeError("upstream down")

    partial = MultiSearchProvider(
        [
            BrokenProvider(),
            FakeSearchProvider(results=[{"title": "usable", "url": "https://example.com/usable", "snippet": "ok"}]),
        ]
    )
    results = asyncio.run(partial.search(SearchQuery(query="test", market_scope="mixed", max_results=3)))
    assert [item.title for item in results] == ["usable"]

    with pytest.raises(RuntimeError, match="all search providers failed"):
        asyncio.run(MultiSearchProvider([BrokenProvider()]).search(
            SearchQuery(query="test", market_scope="mixed", max_results=3)
        ))


def test_multi_search_provider_reports_partial_failure_and_budget_skip() -> None:
    class BrokenProvider:
        async def search(self, query):
            raise TimeoutError("upstream timeout")

    provider = MultiSearchProvider([
        FakeSearchProvider(results=[{"title": "A", "url": "https://a.example/1", "snippet": "a"}]),
        BrokenProvider(),
        FakeSearchProvider(results=[{"title": "C", "url": "https://c.example/1", "snippet": "c"}]),
    ])

    response = asyncio.run(provider.search_with_diagnostics(
        SearchQuery(query="test", market_scope="mixed", max_results=5),
        request_budget=2,
    ))

    assert response.request_count == 2
    assert [item.title for item in response.results] == ["A"]
    assert [item.status for item in response.provider_outcomes] == ["ok", "timeout", "skipped_budget"]


def test_multi_search_provider_sums_actual_nested_request_count() -> None:
    class DiagnosticProvider:
        max_requests_per_search = 1

        async def search(self, query):
            raise AssertionError("legacy search should not be called")

        async def search_with_diagnostics(self, query, *, request_budget=None):
            from backend.app.providers.interfaces import ProviderOutcome, SearchResponse

            return SearchResponse(
                results=[],
                provider_outcomes=[ProviderOutcome(provider_id="nested", status="skipped_budget")],
                request_count=0,
            )

    response = asyncio.run(MultiSearchProvider([DiagnosticProvider()]).search_with_diagnostics(
        SearchQuery(query="test", market_scope="mixed", max_results=5),
        request_budget=1,
    ))

    assert response.request_count == 0


def test_multi_search_provider_skips_malformed_urls_without_losing_accounting() -> None:
    class CountingProvider:
        def __init__(self, url):
            self.url = url
            self.calls = 0

        async def search(self, query):
            from backend.app.providers.interfaces import SearchResult

            self.calls += 1
            return [SearchResult(title="result", url=self.url, snippet="snippet")]

    malformed = CountingProvider("https://[invalid")
    valid = CountingProvider("https://example.com/valid")
    response = asyncio.run(MultiSearchProvider([malformed, valid]).search_with_diagnostics(
        SearchQuery(query="test", market_scope="mixed", max_results=5),
        request_budget=2,
    ))

    assert malformed.calls == 1
    assert valid.calls == 1
    assert response.request_count == 2
    assert [item.url for item in response.results] == ["https://example.com/valid"]
