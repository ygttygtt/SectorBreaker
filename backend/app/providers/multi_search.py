"""Multi-provider search aggregation."""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from backend.app.providers.interfaces import ProviderOutcome, SearchProvider, SearchQuery, SearchResponse, SearchResult
from backend.app.providers.search_execution import execute_search, search_provider_id


def _canonicalize_url(url: str) -> str | None:
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        normalized_path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", ""))
    except ValueError:
        return None


class MultiSearchProvider:
    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    @property
    def max_requests_per_search(self) -> int:
        return max(1, len(self.providers))

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        response = await self.search_with_diagnostics(query)
        failures = [item for item in response.provider_outcomes if item.status in {"error", "timeout"}]
        if not response.results and failures:
            detail = "; ".join(f"{item.provider_id}:{item.error_code}" for item in failures[:3])
            raise RuntimeError(f"all search providers failed: {detail}")
        return response.results

    async def search_with_diagnostics(
        self,
        query: SearchQuery,
        *,
        request_budget: int | None = None,
    ) -> SearchResponse:
        allowed_count = len(self.providers) if request_budget is None else max(0, min(len(self.providers), request_budget))
        active_providers = self.providers[:allowed_count]
        responses = await asyncio.gather(*(
            execute_search(provider, query, request_budget=1)
            for provider in active_providers
        ))
        provider_results = [response.results for response in responses]
        request_count = sum(response.request_count for response in responses)
        outcomes = [outcome for response in responses for outcome in response.provider_outcomes]
        outcomes.extend(
            ProviderOutcome(provider_id=search_provider_id(provider), status="skipped_budget")
            for provider in self.providers[allowed_count:]
        )
        queues = [
            (provider_index, result)
            for provider_index, result in enumerate(provider_results)
            if result
        ]
        canonical_owner: dict[str, int] = {}
        for provider_index, results in queues:
            for result in results:
                if result.url:
                    canonical = _canonicalize_url(result.url)
                    if canonical:
                        canonical_owner.setdefault(canonical, provider_index)
        merged: list[SearchResult] = []
        seen_urls: set[str] = set()
        # Round-robin keeps one high-volume provider from starving the others.
        while queues and len(merged) < query.max_results:
            next_queues: list[tuple[int, list[SearchResult]]] = []
            for provider_index, results in queues:
                if not results:
                    continue
                result = results.pop(0)
                if not result.url:
                    if results:
                        next_queues.append((provider_index, results))
                    continue
                canonical = _canonicalize_url(result.url)
                if canonical is None:
                    if results:
                        next_queues.append((provider_index, results))
                    continue
                if canonical in seen_urls or canonical_owner.get(canonical) != provider_index:
                    next_queues.append((provider_index, results))
                    continue
                seen_urls.add(canonical)
                merged.append(result)
                if len(merged) >= query.max_results:
                    return SearchResponse(results=merged, provider_outcomes=outcomes, request_count=request_count)
                if results:
                    next_queues.append((provider_index, results))
            queues = next_queues

        return SearchResponse(results=merged, provider_outcomes=outcomes, request_count=request_count)
