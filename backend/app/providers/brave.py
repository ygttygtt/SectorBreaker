"""Brave Search API provider."""

import httpx

from backend.app.providers.interfaces import SearchQuery, SearchResult


class BraveSearchProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        params = {
            "q": query.query,
            "count": query.max_results,
        }
        allowed_domains = query.allowed_domains or []
        blocked_domains = query.blocked_domains or []
        if allowed_domains:
            allowed_clause = " OR ".join(f"site:{domain}" for domain in allowed_domains)
            params["q"] = f"{params['q']} ({allowed_clause})"
        if blocked_domains:
            params["q"] = f"{params['q']} {' '.join(f'-site:{domain}' for domain in blocked_domains)}"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        web_payload = data.get("web", {})
        results = web_payload.get("results", [])
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                published_date=item.get("page_age"),
                provider_metadata={
                    "provider": "brave",
                    "market_scope": query.market_scope,
                    "family_friendly": item.get("family_friendly"),
                    "language": item.get("language"),
                },
            )
            for item in results
        ]
