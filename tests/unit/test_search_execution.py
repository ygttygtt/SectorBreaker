import asyncio

from backend.app.providers.interfaces import SearchQuery
from backend.app.providers.search_execution import execute_search


def test_single_provider_execution_redacts_secrets_from_diagnostics() -> None:
    class BrokenSearchProvider:
        async def search(self, query):
            raise RuntimeError("request failed for sk-secretsecretsecretsecret and fc-1234567890abcdef")

    response = asyncio.run(execute_search(
        BrokenSearchProvider(),
        SearchQuery(query="test", market_scope="mixed", max_results=3),
        request_budget=1,
    ))

    assert response.request_count == 1
    assert response.provider_outcomes[0].status == "error"
    assert "sk-secret" not in (response.provider_outcomes[0].error_message or "")
    assert "fc-123" not in (response.provider_outcomes[0].error_message or "")


def test_single_provider_execution_skips_without_spending_budget() -> None:
    class NeverCalledSearchProvider:
        async def search(self, query):
            raise AssertionError("must not dispatch")

    response = asyncio.run(execute_search(
        NeverCalledSearchProvider(),
        SearchQuery(query="test", market_scope="mixed", max_results=3),
        request_budget=0,
    ))

    assert response.request_count == 0
    assert response.provider_outcomes[0].status == "skipped_budget"


def test_diagnostic_provider_failure_is_isolated() -> None:
    class BrokenDiagnosticProvider:
        max_requests_per_search = 3

        async def search(self, query):
            raise AssertionError("legacy search should not be called")

        async def search_with_diagnostics(self, query, *, request_budget=None):
            raise TimeoutError("diagnostic upstream timeout")

    response = asyncio.run(execute_search(
        BrokenDiagnosticProvider(),
        SearchQuery(query="test", market_scope="mixed", max_results=3),
        request_budget=3,
    ))

    assert response.request_count == 3
    assert response.results == []
    assert response.provider_outcomes[0].status == "timeout"


def test_diagnostic_provider_is_not_called_with_zero_budget() -> None:
    class NeverCalledDiagnosticProvider:
        max_requests_per_search = 3

        async def search(self, query):
            raise AssertionError("legacy search must not dispatch")

        async def search_with_diagnostics(self, query, *, request_budget=None):
            raise AssertionError("diagnostic search must not dispatch")

    response = asyncio.run(execute_search(
        NeverCalledDiagnosticProvider(),
        SearchQuery(query="test", market_scope="mixed", max_results=3),
        request_budget=0,
    ))

    assert response.request_count == 0
    assert response.provider_outcomes[0].status == "skipped_budget"


def test_invalid_diagnostic_accounting_fails_closed_and_charges_reserved_budget() -> None:
    from backend.app.providers.interfaces import SearchResponse

    class InvalidDiagnosticProvider:
        max_requests_per_search = 3

        async def search(self, query):
            raise AssertionError("legacy search should not be called")

        async def search_with_diagnostics(self, query, *, request_budget=None):
            return SearchResponse(results=[], provider_outcomes=[], request_count=-1)

    response = asyncio.run(execute_search(
        InvalidDiagnosticProvider(),
        SearchQuery(query="test", market_scope="mixed", max_results=3),
        request_budget=2,
    ))

    assert response.request_count == 2
    assert response.provider_outcomes[0].error_code == "InvalidSearchDiagnostics"
