"""Deterministic fake providers for tests and local fixtures."""

from typing import Any

from backend.app.providers.interfaces import ChatMessage, RetrievalResult, SearchQuery, SearchResult


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
        return self.response


class FakeSearchProvider:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = [SearchResult(**item) for item in results]
        self.queries: list[str] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.queries.append(query.query)
        return self.results[: query.max_results]


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
