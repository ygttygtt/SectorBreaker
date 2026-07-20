"""Shared deterministic test doubles."""

from collections.abc import Callable
from math import sqrt

import pytest

from backend.app.providers.interfaces import EmbeddingProviderInfo


class DeterministicEmbeddingProvider:
    """Small semantic embedding double with observable incremental behavior.

    Tests provide substring-to-vector rules rather than deriving vectors from
    shared keywords. This lets a query and a document with no lexical overlap
    deliberately occupy the same semantic direction.
    """

    provider_name = "deterministic-local"
    model_name = "test-semantic-v1"

    def __init__(
        self,
        *,
        document_vectors: dict[str, tuple[float, ...]],
        query_vectors: dict[str, tuple[float, ...]],
        fail_documents: bool = False,
        fail_query: bool = False,
    ) -> None:
        dimensions = {
            len(vector)
            for vector in [*document_vectors.values(), *query_vectors.values()]
        }
        if len(dimensions) != 1:
            raise ValueError("all deterministic vectors must have the same dimension")
        self.document_vectors = document_vectors
        self.query_vectors = query_vectors
        self.dimension = dimensions.pop()
        self.fail_documents = fail_documents
        self.fail_query = fail_query
        self.loaded = False
        self.document_batches: list[list[str]] = []
        self.query_calls: list[str] = []

    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.provider_name,
            model=self.model_name,
            dimension=self.dimension if self.loaded else None,
            loaded=self.loaded,
            available=True,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.loaded = True
        self.document_batches.append(list(texts))
        if self.fail_documents:
            raise RuntimeError("deterministic document embedding failure")
        return [self._vector_for(text, self.document_vectors) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.loaded = True
        self.query_calls.append(text)
        if self.fail_query:
            raise RuntimeError("deterministic query embedding failure")
        return self._vector_for(text, self.query_vectors)

    def _vector_for(
        self,
        text: str,
        rules: dict[str, tuple[float, ...]],
    ) -> list[float]:
        for marker, vector in rules.items():
            if marker in text:
                norm = sqrt(sum(value * value for value in vector))
                if norm == 0:
                    raise ValueError("deterministic test vectors must be non-zero")
                return [value / norm for value in vector]
        fallback = [0.0] * self.dimension
        fallback[-1] = 1.0
        return fallback


@pytest.fixture
def embedding_provider_factory() -> Callable[..., DeterministicEmbeddingProvider]:
    return DeterministicEmbeddingProvider
