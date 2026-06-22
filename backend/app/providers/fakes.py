"""Deterministic fake providers for tests and local fixtures."""

from typing import Any

from pydantic import BaseModel

from backend.app.providers.interfaces import ChatMessage, ExtractedPage, RetrievalResult, SearchQuery, SearchResult


class FakeLLMProvider:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.messages: list[list[ChatMessage]] = []

    async def complete_structured(
        self,
        messages: list[ChatMessage],
        response_schema: type[Any],
    ) -> Any:
        self.messages.append(messages)
        if response_schema is str:
            return self.response if isinstance(self.response, str) else str(self.response)
        if response_schema is dict:
            if isinstance(self.response, BaseModel):
                return self.response.model_dump(mode="json")
            return self.response
        if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
            if isinstance(self.response, response_schema):
                return self.response
            if isinstance(self.response, BaseModel):
                return response_schema.model_validate(self.response.model_dump(mode="json"))
            return response_schema.model_validate(self.response)
        return self.response


class FakeSearchProvider:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = [SearchResult(**item) for item in results]
        self.queries: list[str] = []
        self.search_requests: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.queries.append(query.query)
        self.search_requests.append(query)
        return self.results[: query.max_results]


class FakeContentExtractionProvider:
    def __init__(self, pages: dict[str, dict[str, str]]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    async def extract_url(self, url: str) -> ExtractedPage:
        self.urls.append(url)
        payload = self.pages[url]
        return ExtractedPage(
            url=url,
            canonical_url=payload.get("canonical_url", url),
            title=payload.get("title"),
            raw_text=payload.get("raw_text", ""),
            markdown=payload.get("markdown"),
            domain=payload.get("domain"),
            extraction_provider=payload.get("extraction_provider", "fake_content"),
            extraction_metadata={"provider": "fake_content"},
        )


class FakeRetrievalProvider:
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, str]] = {}

    def index_text(self, project_id: str, document_id: str, text: str) -> None:
        self._documents.setdefault(project_id, {})[document_id] = text

    def search_project(self, project_id: str, query: str, limit: int) -> list[RetrievalResult]:
        query_lower = query.lower()
        matches: list[RetrievalResult] = []
        for document_id, text in self._documents.get(project_id, {}).items():
            if query_lower in text.lower():
                matches.append(RetrievalResult(document_id=document_id, snippet=text, score=1.0))
        return matches[:limit]
