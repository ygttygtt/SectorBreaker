"""Content-hash incremental local vector index for project knowledge."""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from backend.app.providers.interfaces import EmbeddingProvider, VectorIndexEntry
from backend.app.storage.sqlite import SQLiteRepository


@dataclass(frozen=True)
class VectorSyncResult:
    project_id: str
    source_chunks: int
    embedded_chunks: int
    unchanged_chunks: int
    deleted_chunks: int
    index_count: int
    embedding_provider: str
    embedding_model: str
    dimension: int | None


@dataclass(frozen=True)
class VectorCandidate:
    source_id: str
    chunk_id: str
    parent_id: str | None
    source_type: str
    title: str
    text: str
    similarity: float
    relative_path: str | None
    url: str | None
    verification_status: str | None
    content_hash: str
    embedding_model: str


class ProjectVectorIndex:
    def __init__(self, repository: SQLiteRepository, embedding_provider: EmbeddingProvider) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.last_error: str | None = None
        self.last_sync: VectorSyncResult | None = None
        self._locks_guard = threading.Lock()
        self._sync_locks: dict[tuple[str, str, str], threading.RLock] = {}

    def sync_project(self, project_id: str, *, force: bool = False) -> VectorSyncResult:
        provider_name = self.embedding_provider.provider_name
        model_name = self.embedding_provider.model_name
        lock = self._sync_lock(project_id, provider_name, model_name)
        with lock:
            chunks = _project_chunks(self.repository, project_id)
            existing = {
                item.chunk_id: item
                for item in self.repository.list_vector_entries(
                    project_id,
                    embedding_provider=provider_name,
                    embedding_model=model_name,
                )
            }
            pending = [
                item for item in chunks
                if force
                or item.chunk_id not in existing
                or existing[item.chunk_id].content_hash != item.content_hash
            ]
            metadata_updates = [
                _entry_from_existing(project_id, item, existing[item.chunk_id])
                for item in chunks
                if not force
                and item.chunk_id in existing
                and existing[item.chunk_id].content_hash == item.content_hash
                and not _metadata_matches(item, existing[item.chunk_id])
            ]
            try:
                vectors = self.embedding_provider.embed_documents([item.text for item in pending]) if pending else []
                if len(vectors) != len(pending):
                    raise ValueError("embedding provider returned an unexpected vector count")
                entries = [
                    _entry_from_vector(project_id, chunk, vector, provider_name, model_name)
                    for chunk, vector in zip(pending, vectors, strict=True)
                ]
                keep_ids = {item.chunk_id for item in chunks}
                deleted = self.repository.sync_vector_snapshot(
                    project_id,
                    embedding_provider=provider_name,
                    embedding_model=model_name,
                    entries=[*entries, *metadata_updates],
                    keep_chunk_ids=keep_ids,
                    force=force,
                )
                info = self.embedding_provider.info()
                result = VectorSyncResult(
                    project_id=project_id,
                    source_chunks=len(chunks),
                    embedded_chunks=len(entries),
                    unchanged_chunks=len(chunks) - len(entries),
                    deleted_chunks=deleted,
                    index_count=self.repository.count_vector_entries(
                        project_id,
                        embedding_provider=provider_name,
                        embedding_model=model_name,
                    ),
                    embedding_provider=provider_name,
                    embedding_model=model_name,
                    dimension=info.dimension or (len(vectors[0]) if vectors else None),
                )
                self.last_error = None
                self.last_sync = result
                return result
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise

    def _sync_lock(self, project_id: str, provider_name: str, model_name: str) -> threading.RLock:
        key = (project_id, provider_name, model_name)
        with self._locks_guard:
            return self._sync_locks.setdefault(key, threading.RLock())

    def rebuild_project(self, project_id: str) -> VectorSyncResult:
        return self.sync_project(project_id, force=True)

    def search(self, project_id: str, query: str, *, limit: int = 12) -> list[VectorCandidate]:
        candidates, _ = self.search_with_sync(project_id, query, limit=limit)
        return candidates

    def search_with_sync(
        self,
        project_id: str,
        query: str,
        *,
        limit: int = 12,
    ) -> tuple[list[VectorCandidate], VectorSyncResult]:
        """Return candidates with the exact sync result used by this search."""
        sync = self.sync_project(project_id)
        try:
            query_vector = self.embedding_provider.embed_query(query)
            entries = self.repository.list_vector_entries(
                project_id,
                embedding_provider=self.embedding_provider.provider_name,
                embedding_model=self.embedding_provider.model_name,
            )
            dimensions = {entry.dimension for entry in entries}
            if dimensions and dimensions != {len(query_vector)}:
                raise RuntimeError(
                    "vector index dimension mismatch; rebuild the project semantic index"
                )
            if any(len(entry.vector) != entry.dimension for entry in entries):
                raise RuntimeError(
                    "vector index payload is corrupt; rebuild the project semantic index"
                )
            scored: list[tuple[float, VectorIndexEntry]] = []
            for entry in entries:
                if len(entry.vector) != len(query_vector):
                    continue
                similarity = sum(left * right for left, right in zip(query_vector, entry.vector, strict=True))
                if not math.isfinite(similarity):
                    continue
                scored.append((float(similarity), entry))
            best_by_source: dict[str, tuple[float, VectorIndexEntry]] = {}
            for similarity, entry in sorted(scored, key=lambda item: item[0], reverse=True):
                source_family = entry.parent_id or entry.source_id
                best_by_source.setdefault(source_family, (similarity, entry))
            self.last_error = None
            candidates = [
                VectorCandidate(
                    source_id=entry.source_id,
                    chunk_id=entry.chunk_id,
                    parent_id=entry.parent_id,
                    source_type=entry.source_type,
                    title=entry.title,
                    text=entry.text,
                    similarity=similarity,
                    relative_path=entry.relative_path,
                    url=entry.url,
                    verification_status=entry.verification_status,
                    content_hash=entry.content_hash,
                    embedding_model=entry.embedding_model,
                )
                for similarity, entry in list(best_by_source.values())[: max(1, limit)]
            ]
            return candidates, sync
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise


@dataclass(frozen=True)
class _SourceChunk:
    chunk_id: str
    source_id: str
    parent_id: str | None
    source_type: str
    title: str
    text: str
    content_hash: str
    relative_path: str | None = None
    url: str | None = None
    verification_status: str | None = None


def _entry_from_vector(
    project_id: str,
    chunk: _SourceChunk,
    vector: list[float],
    provider_name: str,
    model_name: str,
) -> VectorIndexEntry:
    return VectorIndexEntry(
        chunk_id=chunk.chunk_id,
        project_id=project_id,
        source_id=chunk.source_id,
        parent_id=chunk.parent_id,
        source_type=chunk.source_type,
        title=chunk.title,
        text=chunk.text,
        content_hash=chunk.content_hash,
        embedding_provider=provider_name,
        embedding_model=model_name,
        dimension=len(vector),
        vector=tuple(vector),
        relative_path=chunk.relative_path,
        url=chunk.url,
        verification_status=chunk.verification_status,
        indexed_at=datetime.now(UTC).isoformat(),
    )


def _entry_from_existing(
    project_id: str,
    chunk: _SourceChunk,
    existing: VectorIndexEntry,
) -> VectorIndexEntry:
    return VectorIndexEntry(
        chunk_id=chunk.chunk_id,
        project_id=project_id,
        source_id=chunk.source_id,
        parent_id=chunk.parent_id,
        source_type=chunk.source_type,
        title=chunk.title,
        text=chunk.text,
        content_hash=chunk.content_hash,
        embedding_provider=existing.embedding_provider,
        embedding_model=existing.embedding_model,
        dimension=existing.dimension,
        vector=existing.vector,
        relative_path=chunk.relative_path,
        url=chunk.url,
        verification_status=chunk.verification_status,
        indexed_at=datetime.now(UTC).isoformat(),
    )


def _metadata_matches(chunk: _SourceChunk, existing: VectorIndexEntry) -> bool:
    return (
        chunk.source_id == existing.source_id
        and chunk.parent_id == existing.parent_id
        and chunk.source_type == existing.source_type
        and chunk.title == existing.title
        and chunk.relative_path == existing.relative_path
        and chunk.url == existing.url
        and chunk.verification_status == existing.verification_status
    )


def _project_chunks(repository: SQLiteRepository, project_id: str) -> list[_SourceChunk]:
    chunks: list[_SourceChunk] = []
    for evidence in repository.list_evidence(project_id):
        text = "\n".join(filter(None, [
            evidence.source_title,
            evidence.summary,
            evidence.snippet,
            evidence.raw_excerpt,
        ])).strip()
        if text:
            chunks.append(_chunk(
                chunk_id=f"evidence:{evidence.id}",
                source_id=evidence.id,
                parent_id=None,
                source_type="evidence",
                title=evidence.source_title,
                text=text,
                url=evidence.source_url,
                verification_status=evidence.verification_status.value,
            ))

    for document in repository.list_documents(project_id):
        segments = repository.list_document_segments(document.id)
        if segments:
            for segment in segments:
                if not segment.text.strip():
                    continue
                chunks.append(_chunk(
                    chunk_id=f"segment:{segment.id}",
                    source_id=segment.id,
                    parent_id=document.id,
                    source_type=f"document_segment:{document.channel}",
                    title=segment.heading or document.file_name or document.id,
                    text=segment.text,
                    relative_path=document.file_name,
                ))
        elif document.content.strip():
            chunks.append(_chunk(
                chunk_id=f"document:{document.id}",
                source_id=document.id,
                parent_id=None,
                source_type=f"document:{document.channel}",
                title=document.file_name or document.id,
                text=document.content,
                relative_path=document.file_name,
            ))

    for artifact in repository.list_artifacts(project_id):
        for index, text in enumerate(_split_markdown(artifact.content)):
            chunks.append(_chunk(
                chunk_id=f"artifact:{artifact.id}:{index:04d}",
                source_id=artifact.id,
                parent_id=artifact.id,
                source_type="artifact",
                title=artifact.title,
                text=text,
                relative_path=artifact.content_path,
            ))
    return chunks


def _chunk(
    *,
    chunk_id: str,
    source_id: str,
    parent_id: str | None,
    source_type: str,
    title: str,
    text: str,
    relative_path: str | None = None,
    url: str | None = None,
    verification_status: str | None = None,
    content_hash: str | None = None,
) -> _SourceChunk:
    normalized = " ".join(text.split())
    return _SourceChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        parent_id=parent_id,
        source_type=source_type,
        title=title,
        text=normalized,
        content_hash=content_hash or "sha256:" + sha256(normalized.encode("utf-8")).hexdigest(),
        relative_path=relative_path,
        url=url,
        verification_status=verification_status,
    )


def _split_markdown(content: str, *, max_chars: int = 1400, overlap_chars: int = 180) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []
    sections = re.split(r"(?m)(?=^#{1,4}\s+)", normalized)
    chunks: list[str] = []
    buffer = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(buffer) + len(section) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{section}".strip()
            continue
        if buffer:
            chunks.append(buffer)
        while len(section) > max_chars:
            chunks.append(section[:max_chars])
            section = section[max_chars - overlap_chars:]
        buffer = section
    if buffer:
        chunks.append(buffer)
    return chunks
