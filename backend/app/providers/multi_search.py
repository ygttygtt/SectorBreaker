"""Multi-provider search aggregation."""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from backend.app.providers.interfaces import SearchProvider, SearchQuery, SearchResult


def _canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), normalized_path, "", ""))


class MultiSearchProvider:
    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        provider_results = await asyncio.gather(
            *(provider.search(query) for provider in self.providers),
            return_exceptions=True,
        )
        failures = [result for result in provider_results if isinstance(result, Exception)]
        queues = [
            (provider_index, result)
            for provider_index, result in enumerate(provider_results)
            if isinstance(result, list)
        ]
        canonical_owner: dict[str, int] = {}
        for provider_index, results in queues:
            for result in results:
                if result.url:
                    canonical_owner.setdefault(_canonicalize_url(result.url), provider_index)
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
                if canonical in seen_urls or canonical_owner.get(canonical) != provider_index:
                    next_queues.append((provider_index, results))
                    continue
                seen_urls.add(canonical)
                merged.append(result)
                if len(merged) >= query.max_results:
                    return merged
                if results:
                    next_queues.append((provider_index, results))
            queues = next_queues

        if not merged and failures:
            detail = "; ".join(f"{type(error).__name__}: {error}" for error in failures[:3])
            raise RuntimeError(f"all search providers failed: {detail}")
        return merged
