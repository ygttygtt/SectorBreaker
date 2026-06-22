"""Exa search provider."""

import httpx

from backend.app.providers.interfaces import SearchQuery, SearchResult


class ExaSearchProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.exa.ai/search",
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        payload: dict[str, object] = {
            "query": query.query,
            "numResults": query.max_results,
            "type": "keyword",
        }
        if query.allowed_domains:
            payload["includeDomains"] = query.allowed_domains
        if query.blocked_domains:
            payload["excludeDomains"] = query.blocked_domains

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("text", "")[:400],
                published_date=item.get("publishedDate"),
                provider_metadata={
                    "provider": "exa",
                    "market_scope": query.market_scope,
                    "author": item.get("author"),
                    "score": item.get("score"),
                },
            )
            for item in results
        ]
