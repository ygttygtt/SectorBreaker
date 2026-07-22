"""Firecrawl web-search provider.

Firecrawl's search endpoint can optionally return scraped markdown.  SectorBreaker
keeps that concern separate: search returns discovery metadata and the configured
content-extraction provider owns the full-page read, preserving source evidence
and cost controls at the existing boundary.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.app.providers.interfaces import SearchQuery, SearchResult


class FirecrawlSearchProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.firecrawl.dev/v2/search",
        timeout: float = 45.0,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        payload: dict[str, Any] = {
            "query": query.query,
            "limit": query.max_results,
            "sources": ["web"],
        }
        if query.allowed_domains:
            payload["includeDomains"] = query.allowed_domains
        if query.blocked_domains:
            payload["excludeDomains"] = query.blocked_domains
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            body = response.json()

        data = body.get("data") if isinstance(body, dict) else {}
        if isinstance(data, dict):
            items = data.get("web") or data.get("results") or []
        else:
            items = data if isinstance(data, list) else []
        results: list[SearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=url,
                    snippet=str(item.get("description") or item.get("snippet") or ""),
                    published_date=item.get("date") or item.get("publishedDate"),
                    provider_metadata={
                        "provider": "firecrawl",
                        "source": item.get("source") or "web",
                        "metadata": item.get("metadata") or {},
                    },
                )
            )
        return results
