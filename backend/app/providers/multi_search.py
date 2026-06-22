"""Multi-provider search aggregation."""

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
        merged: list[SearchResult] = []
        seen_urls: set[str] = set()

        for provider in self.providers:
            results = await provider.search(query)
            for result in results:
                if not result.url:
                    continue
                canonical = _canonicalize_url(result.url)
                if canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                merged.append(result)
                if len(merged) >= query.max_results:
                    return merged

        return merged
