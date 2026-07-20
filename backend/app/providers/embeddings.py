"""Local semantic embedding provider adapters."""

from __future__ import annotations

import math
import threading
from pathlib import Path

from backend.app.providers.interfaces import EmbeddingProviderInfo


DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_LOCAL_EMBEDDING_CACHE = Path.home() / ".cache" / "sectorbreaker" / "fastembed"


class FastEmbedEmbeddingProvider:
    """Lazy local FastEmbed adapter with normalized document/query vectors."""

    provider_name = "fastembed"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL,
        cache_dir: str | Path | None = None,
        threads: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = str(
            Path(cache_dir).expanduser()
            if cache_dir
            else DEFAULT_LOCAL_EMBEDDING_CACHE
        )
        self.threads = threads
        self._model = None
        self._load_lock = threading.Lock()
        self._dimension: int | None = None
        self._last_error: str | None = None

    def info(self) -> EmbeddingProviderInfo:
        try:
            import fastembed  # noqa: F401
            available = True
        except Exception as exc:
            available = False
            if self._last_error is None:
                self._last_error = f"{type(exc).__name__}: {exc}"
        return EmbeddingProviderInfo(
            provider=self.provider_name,
            model=self.model_name,
            dimension=self._dimension,
            loaded=self._model is not None,
            available=available,
            last_error=self._last_error,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        try:
            # FastEmbed applies model-specific document prefixes in passage_embed.
            # Using the generic embed method would make asymmetric retrieval models
            # compare query and document vectors with the wrong encoding contract.
            vectors = [_normalize_vector(item.tolist()) for item in model.passage_embed(texts)]
            self._capture_dimension(vectors)
            self._last_error = None
            return vectors
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"local document embedding failed: {self._last_error}") from exc

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("embedding query must not be blank")
        model = self._load_model()
        try:
            vector = next(iter(model.query_embed(text)))
            normalized = _normalize_vector(vector.tolist())
            self._capture_dimension([normalized])
            self._last_error = None
            return normalized
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"local query embedding failed: {self._last_error}") from exc

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=self.cache_dir,
                    threads=self.threads,
                    lazy_load=False,
                )
                return self._model
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                raise RuntimeError(f"local embedding model unavailable: {self._last_error}") from exc

    def _capture_dimension(self, vectors: list[list[float]]) -> None:
        if not vectors:
            return
        dimension = len(vectors[0])
        if dimension <= 0 or any(len(item) != dimension for item in vectors):
            raise ValueError("embedding provider returned inconsistent vector dimensions")
        self._dimension = dimension


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if norm <= 0:
        raise ValueError("embedding provider returned a zero vector")
    return [float(value) / norm for value in vector]
