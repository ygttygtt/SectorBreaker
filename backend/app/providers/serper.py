"""Serper search provider."""

import httpx

from backend.app.providers.interfaces import SearchQuery, SearchResult


class SerperSearchProvider:
    def __init__(self, api_key: str, endpoint: str = "https://google.serper.dev/search") -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        payload = {
            "q": query.query,
            "num": query.max_results,
        }
        allowed_domains = query.allowed_domains or []
        blocked_domains = query.blocked_domains or []
        if allowed_domains:
            allowed_clause = " OR ".join(f"site:{domain}" for domain in allowed_domains)
            payload["q"] = f"{payload['q']} ({allowed_clause})"
        if blocked_domains:
            payload["q"] = f"{payload['q']} {' '.join(f'-site:{domain}' for domain in blocked_domains)}"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        organic_results = data.get("organic", [])
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                published_date=item.get("date"),
                provider_metadata={
                    "provider": "serper",
                    "market_scope": query.market_scope,
                    "position": item.get("position"),
                },
            )
            for item in organic_results
        ]
