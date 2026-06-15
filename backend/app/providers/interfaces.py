"""Replaceable provider contracts."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class SearchQuery:
    query: str
    market_scope: str
    max_results: int


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str | None = None
    provider_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RetrievalResult:
    document_id: str
    snippet: str
    score: float


class LLMProvider(Protocol):
    async def complete_structured(
        self,
        messages: list[ChatMessage],
        response_schema: type[Any],
    ) -> Any:
        """Return a structured response matching the requested schema."""


class SearchProvider(Protocol):
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search external sources."""


class RetrievalProvider(Protocol):
    def index_text(self, project_id: str, document_id: str, text: str) -> None:
        """Index project-local text."""

    def search_project(self, project_id: str, query: str, limit: int) -> list[RetrievalResult]:
        """Search project-local indexed text."""
