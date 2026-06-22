"""Tavily search provider."""

import httpx

from backend.app.providers.interfaces import SearchQuery, SearchResult


class TavilySearchProvider:
    def __init__(self, api_key: str, endpoint: str = "https://api.tavily.com/search") -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        payload = {
            "query": query.query,
            "max_results": query.max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        if query.allowed_domains:
            payload["include_domains"] = query.allowed_domains
        if query.blocked_domains:
            payload["exclude_domains"] = query.blocked_domains
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content") or item.get("snippet") or "",
                published_date=item.get("published_date"),
                provider_metadata={"provider": "tavily", "market_scope": query.market_scope},
            )
            for item in data.get("results", [])
        ]
