from pathlib import Path

import pytest

from backend.app.providers.embeddings import (
    DEFAULT_LOCAL_EMBEDDING_CACHE,
    FastEmbedEmbeddingProvider,
)


class _ArrayLike:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return self.values


class _AsymmetricModel:
    def __init__(self) -> None:
        self.passages: list[str] = []
        self.queries: list[str] = []

    def passage_embed(self, texts: list[str]):
        self.passages.extend(texts)
        return iter([_ArrayLike([3.0, 4.0]) for _ in texts])

    def query_embed(self, text: str):
        self.queries.append(text)
        return iter([_ArrayLike([0.0, 5.0])])

    def embed(self, texts: list[str]):  # pragma: no cover - regression alarm
        raise AssertionError("document embedding must use passage_embed")


def test_fastembed_adapter_uses_asymmetric_encoders_and_normalizes_vectors() -> None:
    provider = FastEmbedEmbeddingProvider()
    model = _AsymmetricModel()
    provider._model = model

    documents = provider.embed_documents(["document one", "document two"])
    query = provider.embed_query("query text")

    assert model.passages == ["document one", "document two"]
    assert model.queries == ["query text"]
    assert documents == [[0.6, 0.8], [0.6, 0.8]]
    assert query == [0.0, 1.0]
    assert provider.info().dimension == 2
    assert provider.info().loaded is True


def test_fastembed_adapter_uses_persistent_default_cache() -> None:
    provider = FastEmbedEmbeddingProvider()

    assert Path(provider.cache_dir) == DEFAULT_LOCAL_EMBEDDING_CACHE
    assert "sectorbreaker" in provider.cache_dir


def test_fastembed_adapter_rejects_blank_query() -> None:
    provider = FastEmbedEmbeddingProvider()

    with pytest.raises(ValueError, match="must not be blank"):
        provider.embed_query("   ")
